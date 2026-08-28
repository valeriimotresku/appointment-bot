from playwright.async_api import Browser, Page, Playwright, async_playwright


class BrowserManager:
    """Owns the single Playwright/Chromium instance used by the application."""

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._page: Page | None = None

    async def start(self) -> None:
        """Start Chromium once. Safe to call more than once."""
        if (
            self._browser is not None
            and self._browser.is_connected()
            and self._page is not None
            and not self._page.is_closed()
        ):
            return

        await self.stop()

        print("[Browser] Starting Chromium...")
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._page = await self._browser.new_page()
        print("[Browser] Chromium started.")

    async def stop(self) -> None:
        """Close the page/browser and stop Playwright."""
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception as exc:
                print(f"[Browser] Error while closing Chromium: {exc}")

        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception as exc:
                print(f"[Browser] Error while stopping Playwright: {exc}")

        self._page = None
        self._browser = None
        self._playwright = None

    async def restart(self) -> Page:
        print("[Browser] Restarting Chromium...")
        await self.stop()
        await self.start()
        return await self.get_page()

    async def get_page(self) -> Page:
        """Return the shared page, recreating Chromium if it died."""
        if (
            self._browser is None
            or not self._browser.is_connected()
            or self._page is None
            or self._page.is_closed()
        ):
            await self.start()

        if self._page is None:
            raise RuntimeError("Browser page could not be initialized")

        return self._page


browser_manager = BrowserManager()
