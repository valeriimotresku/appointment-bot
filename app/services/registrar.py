from playwright.async_api import async_playwright
from app.services.scraper import BASE

async def register_for_slot(date: str) -> bool:
    """
    Attempts to register for the given date.
    Returns True if booking successful, False otherwise.
    """
    browser = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(BASE)

            # Navigate like in scraper
            await page.get_by_text('Ausländerbehörde').click()
            await page.get_by_text('Anliegen').click()
            await page.get_by_text('Aufenthaltstitel').click()
            await page.get_by_text('Ersterteilung Aufenthaltserlaubnis').click()
            await page.get_by_text('digitales Lichtbild').click()
            await page.get_by_role('button', name='1').click()
            await page.get_by_role('button', name='Weiter').click()
            await page.wait_for_load_state('networkidle')

            # Check if requested date is available
            d = page.locator(f"[data-date='{date}']")
            if not await d.count():
                return False

            await d.click()

            times = page.locator('.btn.btn-primary.btn-block')
            if await times.count() == 0:
                return False

            await times.first.click()
            await page.get_by_role('button', name='Buchung abschließen').click()
            return True
    except Exception as e:
        print(f"Error registering for slot {date}: {e}")
        return False
    finally:
        if browser:
            await browser.close()
