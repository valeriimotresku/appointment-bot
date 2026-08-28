import asyncio
from datetime import date, datetime

from playwright.async_api import (
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from app.db.models import WatchRequest
from app.services.browser_manager import browser_manager
from app.services.date_parser import parse_german_date
from app.services.email_waiter import (
    register_code_waiter,
    wait_for_code,
)
from app.services.telegram_notifier import send_telegram_message


BASE = "https://reservation.frontdesksuite.com/kempten/abh/"

DATE_SELECTOR = (
    ".date-list .date .title "
    ".header-text:not(.not-available)"
)


class FrontDeskClient:
    """
    Reuses one Playwright page for all FrontDeskSuite checks.

    One shared Page must not be manipulated by multiple tasks
    at the same time, so availability checks and booking flows
    share the same lock.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def prepare(self) -> None:
        """
        Prepare the shared browser page once during application startup.
        """
        async with self._lock:
            page = await browser_manager.get_page()
            await self._navigate_to_date_picker(page)

    async def get_first_available_date(self) -> date:
        """
        Refresh the existing date-picker page and return
        the first available date.

        This is the cheap scheduler operation:
        one refresh regardless of the number of WatchRequests.
        """
        async with self._lock:
            page = await self._get_ready_date_picker(
                refresh=True
            )

            text_date = await self._read_first_available_date_text(
                page
            )

            parsed_date = parse_german_date(text_date)

            print(
                f"[FrontDesk] First available date: {text_date}"
            )

            return parsed_date

    async def book_available_datetime(
        self,
        request: WatchRequest,
    ) -> datetime | None:
        """
        Re-check current availability and book an appointment
        for one WatchRequest.

        Rules:
        - if no confirmed booking exists yet -> book normally
        - if a confirmed booking exists -> only book if the
          newly available DATE is strictly earlier
        - time differences on the same date are ignored for now
        - booked_datetime is returned only after a successful
          confirmation
        """

        async with self._lock:
            page = await self._get_ready_date_picker(
                refresh=True
            )

            try:
                date_el = page.locator(
                    DATE_SELECTOR
                ).first

                text_date = await date_el.inner_text()

                available_date = parse_german_date(
                    text_date
                )

                print(
                    f"[FrontDesk] Booking check: {text_date}, "
                    f"request={request.email}"
                )

                date_from = datetime.strptime(
                    request.date_from,
                    "%Y-%m-%d",
                ).date()

                date_to = datetime.strptime(
                    request.date_to,
                    "%Y-%m-%d",
                ).date()

                #
                # Check requested date range.
                #

                if not date_from <= available_date <= date_to:
                    print(
                        f"[FrontDesk] Date moved out of range for "
                        f"{request.email}: {text_date}"
                    )

                    return None

                #
                # Existing confirmed booking:
                # only book a strictly earlier DATE.
                #

                if request.booked_datetime:
                    booked_date = (
                        request.booked_datetime.date()
                    )

                    if available_date >= booked_date:
                        print(
                            "[FrontDesk] Existing booking "
                            f"{request.booked_datetime:%Y-%m-%d %H:%M} "
                            "is on an earlier or equal date than "
                            f"available date {available_date}. "
                            f"Skipping for {request.email}"
                        )

                        return None

                    print(
                        "[FrontDesk] Earlier date found: "
                        f"{available_date} instead of current "
                        f"booking {booked_date} "
                        f"for {request.email}"
                    )

                #
                # Open selected date.
                #

                parent_div = (
                    date_el
                    .locator("..")
                    .locator("..")
                    .locator("..")
                )

                await date_el.click()

                await self._wait_for_page(page)

                #
                # Keep current behaviour:
                # select the last available time on that date.
                #

                time_el = parent_div.locator(
                    ".times-list .time button"
                ).last

                time_text = await time_el.locator(
                    "span.available-time"
                ).inner_text()

                time_obj = datetime.strptime(
                    time_text,
                    "%H:%M",
                ).time()

                candidate_datetime = datetime.combine(
                    available_date,
                    time_obj,
                )

                print(
                    "[FrontDesk] Selected candidate: "
                    f"{candidate_datetime:%Y-%m-%d %H:%M}"
                )

                #
                # Open booking form.
                #

                await time_el.click()

                await page.fill(
                    "#telephone",
                    request.phone,
                )

                await page.fill(
                    "#email",
                    request.email,
                )

                await page.fill(
                    "#field11745",
                    request.full_name,
                )

                await page.fill(
                    "#field11756",
                    request.birth_date,
                )

                #
                # Register BEFORE submit.
                #
                # This prevents a race where Mailgun delivers
                # the email before the Future exists.
                #

                code_future = register_code_waiter(
                    request.email
                )

                await page.click("#submit-btn")

                timestamp = candidate_datetime.strftime(
                    "%Y-%m-%d %H:%M"
                )

                print(
                    "[FrontDesk] Form submitted: "
                    f"datetime={timestamp}, "
                    f"email={request.email}"
                )

                #
                # Wait for Mailgun webhook.
                #

                code = await wait_for_code(
                    request.email,
                    code_future,
                    timeout=60,
                )

                #
                # IMPORTANT:
                # No confirmed booking -> do NOT return the
                # candidate datetime.
                #
                # Therefore the scheduler will NOT overwrite
                # request.booked_datetime in the database.
                #

                if code is None:
                    print(
                        "[FrontDesk] Confirmation email was not "
                        f"received for {request.email}. "
                        "Booking is not considered confirmed."
                    )

                    return None

                print(
                    "[FrontDesk] Confirmation code received: "
                    f"{code}"
                )

                #
                # Fill confirmation code.
                #

                await page.fill(
                    "#code",
                    code,
                )

                #
                # Submit confirmation.
                #

                await page.locator(
                    "button.mdc-button",
                    has_text="Termin",
                ).click()

                #
                # Only after this succeeds do we consider
                # the booking confirmed.
                #

                await page.locator(
                    ".confirmed-reservation",
                    has_text="gebucht",
                ).wait_for(
                    state="visible",
                    timeout=30_000,
                )

                print(
                    "[FrontDesk] Appointment confirmed successfully: "
                    f"{timestamp}, {request.email}"
                )

                #
                # Telegram notification.
                #

                await send_telegram_message(
                    f"{timestamp} is booked for "
                    f"{request.full_name}. "
                    "Check your email!"
                )

                #
                # Scheduler can now safely persist this value
                # into request.booked_datetime.
                #

                return candidate_datetime

            finally:
                #
                # Booking flow moves the shared page away from
                # the date picker.
                #
                # Restore it for the next scheduler cycle.
                #

                await self._restore_date_picker()

    async def _get_ready_date_picker(
        self,
        refresh: bool,
    ) -> Page:
        """
        Return a usable date-picker page.

        Recovery strategy:
        1. reuse existing page
        2. reload if requested
        3. if picker disappeared, navigate again
        4. if browser/session is broken, restart Chromium
        """

        page = await browser_manager.get_page()

        try:
            if refresh:
                await page.reload(
                    wait_until="domcontentloaded",
                    timeout=30_000,
                )

            await page.locator(
                DATE_SELECTOR
            ).first.wait_for(
                state="visible",
                timeout=10_000,
            )

            return page

        except Exception as exc:
            print(
                "[FrontDesk] Date picker unavailable after "
                f"refresh; rebuilding navigation: {exc}"
            )

        #
        # Try recovering the current browser session.
        #

        try:
            await self._navigate_to_date_picker(
                page
            )

            return page

        except Exception as exc:
            print(
                "[FrontDesk] Navigation recovery failed: "
                f"{exc}"
            )

        #
        # Browser itself may be unhealthy.
        #

        page = await browser_manager.restart()

        await self._navigate_to_date_picker(
            page
        )

        return page

    async def _navigate_to_date_picker(
        self,
        page: Page,
    ) -> None:
        """
        Navigate from the FrontDeskSuite start page
        to the Wohnsitz Anmeldung date picker.
        """

        print(
            "[FrontDesk] Navigating to date picker..."
        )

        await page.goto(
            BASE,
            wait_until="domcontentloaded",
            timeout=30_000,
        )

        await page.locator(
            ".section-buttons a.button",
            has_text="Stadt Kempten (Allgäu)",
        ).click()

        #
        # TODO:
        # Extract appointment type into a strategy/configuration.
        #

        await page.locator(
            ".section-buttons a.button",
            has_text="Wohnsitz",
        ).click()

        await page.locator(
            ".section-buttons a.button",
            has_text="Wohnsitz An",
        ).click()

        await page.locator(
            ".section-buttons a.button",
            has_text=(
                "Termin in der Ausländerbehörde "
                "vereinbaren"
            ),
        ).click()

        await page.locator(
            ".section-buttons a.button",
            has_text="Einzelperson",
        ).click()

        await page.locator(
            DATE_SELECTOR
        ).first.wait_for(
            state="visible",
            timeout=15_000,
        )

        print(
            f"[FrontDesk] Date picker ready: "
            f"{page.url}"
        )

    async def _read_first_available_date_text(
        self,
        page: Page,
    ) -> str:
        """
        Read the first currently available date.
        """

        return await page.locator(
            DATE_SELECTOR
        ).first.inner_text()

    async def _wait_for_page(
        self,
        page: Page,
    ) -> None:
        """
        Wait only for DOM content.

        We intentionally avoid depending on networkidle
        because some websites keep background connections
        or requests alive.
        """

        try:
            await page.wait_for_load_state(
                "domcontentloaded",
                timeout=10_000,
            )

        except PlaywrightTimeoutError:
            pass

    async def _restore_date_picker(
        self,
    ) -> None:
        """
        Return the shared browser to the date picker
        after a booking attempt.
        """

        try:
            page = await browser_manager.get_page()

            date_picker_exists = (
                await page.locator(
                    DATE_SELECTOR
                ).first.count()
                > 0
            )

            if date_picker_exists:
                return

            print(
                "[FrontDesk] Returning to date picker..."
            )

            await self._navigate_to_date_picker(
                page
            )

        except Exception as exc:
            print(
                "[FrontDesk] Failed to restore "
                f"date picker: {exc}"
            )

            #
            # Last-resort recovery:
            # restart browser and rebuild session.
            #

            try:
                page = await browser_manager.restart()

                await self._navigate_to_date_picker(
                    page
                )

            except Exception as restart_exc:
                print(
                    "[FrontDesk] Browser recovery "
                    "failed completely: "
                    f"{restart_exc}"
                )


frontdesk_client = FrontDeskClient()


async def book_available_datetime(
    request: WatchRequest,
) -> datetime | None:
    """
    Backward-compatible wrapper for callers outside scheduler.
    """

    return await frontdesk_client.book_available_datetime(
        request
    )