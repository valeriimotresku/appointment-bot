import asyncio
from datetime import date, datetime

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from app.db.models import WatchRequest
from app.services.browser_manager import browser_manager
from app.services.date_parser import parse_german_date
from app.services.email_waiter import register_code_waiter, wait_for_code
from app.services.telegram_notifier import send_telegram_message

BASE = "https://reservation.frontdesksuite.com/kempten/abh/"

DATE_SELECTOR = (
    ".date-list .date .title .header-text:not(.not-available)"
)


class FrontDeskClient:
    """
    Reuses one browser page for all FrontDeskSuite checks.

    The lock is intentionally shared by availability checks and booking flows:
    one Playwright Page must not be clicked/reloaded concurrently by two jobs.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def prepare(self) -> None:
        """Prepare the shared page once during application startup."""
        async with self._lock:
            page = await browser_manager.get_page()
            await self._navigate_to_date_picker(page)

    async def get_first_available_date(self) -> date:
        """
        Refresh the existing date-picker page and return the first available date.

        This is the cheap operation used by the scheduler once per cycle,
        regardless of how many WatchRequests exist.
        """
        async with self._lock:
            page = await self._get_ready_date_picker(refresh=True)
            text_date = await self._read_first_available_date_text(page)
            parsed_date = parse_german_date(text_date)
            print(f"[FrontDesk] First available date: {text_date}")
            return parsed_date

    async def book_available_datetime(
        self,
        request: WatchRequest,
    ) -> datetime | None:
        """
        Re-check current availability and book an appointment for one request.

        The scheduler has already filtered requests using one shared availability
        scrape. We still refresh here because availability can change between the
        initial check and the actual booking click.
        """
        async with self._lock:
            page = await self._get_ready_date_picker(refresh=True)

            try:
                date_el = page.locator(DATE_SELECTOR).first
                text_date = await date_el.inner_text()
                available_date = parse_german_date(text_date)

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

                if not date_from <= available_date <= date_to:
                    print(
                        f"[FrontDesk] Date moved out of range for "
                        f"{request.email}: {text_date}"
                    )
                    return None

                # Keep the parent locator before moving deeper into the flow.
                parent_div = date_el.locator("..").locator("..").locator("..")

                await date_el.click()
                await self._wait_for_page(page)

                time_el = parent_div.locator(".times-list .time button").last

                # If a previous attempt reserved a time but email confirmation
                # failed, retry that exact time when it is still available.
                if (
                    request.booked_datetime
                    and available_date == request.booked_datetime.date()
                ):
                    previous_time = request.booked_datetime.strftime("%H:%M")
                    previous_time_el = parent_div.locator(
                        ".times-list .time button",
                        has_text=previous_time,
                    )

                    if await previous_time_el.count() > 0:
                        print(
                            "[FrontDesk] Previous time was not confirmed; "
                            f"retrying {previous_time} for {request.email}"
                        )
                        time_el = previous_time_el
                    else:
                        print(
                            "[FrontDesk] Previous time is no longer listed; "
                            f"assuming it is still reserved for {request.email}"
                        )
                        return None

                if (
                    request.booked_datetime
                    and request.booked_datetime.date() < available_date
                ):
                    print(
                        "[FrontDesk] An earlier date is already booked for "
                        f"{request.email}; skipping later availability"
                    )
                    return None

                time_text = await time_el.locator(
                    "span.available-time"
                ).inner_text()
                time_obj = datetime.strptime(time_text, "%H:%M").time()
                booked_datetime = datetime.combine(available_date, time_obj)

                await time_el.click()

                await page.fill("#telephone", request.phone)
                await page.fill("#email", request.email)
                await page.fill("#field11745", request.full_name)
                await page.fill("#field11756", request.birth_date)

                # Register before submit so an unusually fast email cannot race
                # ahead of waiter creation.
                code_future = register_code_waiter(request.email)
                await page.click("#submit-btn")

                timestamp = booked_datetime.strftime("%Y-%m-%d %H:%M")
                print(
                    "[FrontDesk] Form submitted: "
                    f"datetime={timestamp}, email={request.email}"
                )

                code = await wait_for_code(
                    request.email,
                    code_future,
                    timeout=60,
                )

                if code is None:
                    print(
                        "[FrontDesk] Confirmation email was not received for "
                        f"{request.email}"
                    )
                    # Preserve the previous behavior: remember the attempted
                    # datetime so the next run can retry that exact time.
                    return booked_datetime

                print(f"[FrontDesk] Confirmation code received: {code}")

                await page.fill("#code", code)
                await page.locator(
                    "button.mdc-button",
                    has_text="Termin",
                ).click()

                await page.locator(
                    ".confirmed-reservation",
                    has_text="gebucht",
                ).wait_for(state="visible", timeout=30_000)

                print(
                    "[FrontDesk] Appointment confirmed successfully: "
                    f"{timestamp}, {request.email}"
                )

                await send_telegram_message(
                    f"{timestamp} is booked for {request.full_name}. "
                    "Check your email!"
                )

                return booked_datetime

            finally:
                # A booking flow leaves the date picker. Restore it so the next
                # scheduler cycle can usually do only a reload.
                await self._restore_date_picker()

    async def _get_ready_date_picker(self, refresh: bool) -> Page:
        """Return a usable date-picker page, recovering session/browser state."""
        page = await browser_manager.get_page()

        try:
            if refresh:
                await page.reload(wait_until="domcontentloaded", timeout=30_000)

            await page.locator(DATE_SELECTOR).first.wait_for(
                state="visible",
                timeout=10_000,
            )
            return page

        except Exception as exc:
            print(
                "[FrontDesk] Date picker unavailable after refresh; "
                f"rebuilding navigation: {exc}"
            )

        # The page/session may have expired. Re-enter from the base page.
        try:
            await self._navigate_to_date_picker(page)
            return page
        except Exception as exc:
            # Chromium itself may have become unhealthy. Restart it once.
            print(f"[FrontDesk] Navigation recovery failed: {exc}")
            page = await browser_manager.restart()
            await self._navigate_to_date_picker(page)
            return page

    async def _navigate_to_date_picker(self, page: Page) -> None:
        """Navigate from BASE to the Wohnsitz Anmeldung date picker."""
        print("[FrontDesk] Navigating to date picker...")

        await page.goto(BASE, wait_until="domcontentloaded", timeout=30_000)

        await page.locator(
            ".section-buttons a.button",
            has_text="Stadt Kempten (Allgäu)",
        ).click()

        # TODO: extract appointment type into a strategy/configuration.
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
            has_text="Termin in der Ausländerbehörde vereinbaren",
        ).click()
        await page.locator(
            ".section-buttons a.button",
            has_text="Einzelperson",
        ).click()

        await page.locator(DATE_SELECTOR).first.wait_for(
            state="visible",
            timeout=15_000,
        )

        print(f"[FrontDesk] Date picker ready: {page.url}")

    async def _read_first_available_date_text(self, page: Page) -> str:
        return await page.locator(DATE_SELECTOR).first.inner_text()

    async def _wait_for_page(self, page: Page) -> None:
        """Avoid relying on networkidle for pages with background traffic."""
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=10_000)
        except PlaywrightTimeoutError:
            # The subsequent locator interactions are the real readiness check.
            pass

    async def _restore_date_picker(self) -> None:
        try:
            page = await browser_manager.get_page()
            if await page.locator(DATE_SELECTOR).first.count() > 0:
                return
            await self._navigate_to_date_picker(page)
        except Exception as exc:
            print(f"[FrontDesk] Failed to restore date picker: {exc}")
            try:
                page = await browser_manager.restart()
                await self._navigate_to_date_picker(page)
            except Exception as restart_exc:
                print(
                    "[FrontDesk] Browser recovery failed completely: "
                    f"{restart_exc}"
                )


frontdesk_client = FrontDeskClient()


async def book_available_datetime(request: WatchRequest) -> datetime | None:
    """Backward-compatible wrapper for callers outside the scheduler."""
    return await frontdesk_client.book_available_datetime(request)
