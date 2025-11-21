
from datetime import datetime

from app.db.models import WatchRequest
from playwright.async_api import async_playwright

from app.services.date_parser import parse_german_date
from app.services.email_parser import wait_for_confirmation_code
from app.services.telegram_notifier import send_telegram_message

BASE = 'https://reservation.frontdesksuite.com/kempten/abh/'

async def book_available_datetime(request: WatchRequest) -> datetime:
    """
    Returns a list of available dates as strings.
    Safely launches and closes browser even on exceptions.
    """
    browser = None
    try:
        async with async_playwright() as p:
            # TODO change to true for production!!!
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(BASE)
            # Navigate through the site
            await page.locator(".section-buttons a.button", has_text="Stadt Kempten (Allgäu)").click()
            await page.locator(".section-buttons a.button", has_text="Aufenthaltstitel").click()
            await page.locator(".section-buttons a.button", 
                               has_text="Ersterteilung Aufenthaltserlaubnis").click()
            await page.locator(".section-buttons a.button", 
                               has_text="Termin in der Ausländerbehörde vereinbaren").click()
            await page.locator(".section-buttons a.button", 
                               has_text="digitales Lichtbild ist").click()
            await page.locator(".section-buttons a.button", has_text="Einzelperson").click()
            await page.wait_for_load_state('networkidle')
            
            date_el = page.locator(".date-list .date .title .header-text:not(.not-available)").first
            text_date = await date_el.inner_text()
            date = parse_german_date(text_date)
            date_from = datetime.strptime(request.date_from, "%Y-%m-%d").date()
            date_to   = datetime.strptime(request.date_to, "%Y-%m-%d").date()
            if date_from <= date <= date_to:
                # formatted_date = date.strftime("%Y-%m-%d")
                # print(text_date + " is available for requested period")
                
                # send telegram notification
                # msg = text_date + " is available for the requested period for " + request.full_name
                # await send_telegram_message(msg)

                # proceed with form request
                await date_el.click()
                await page.wait_for_load_state('networkidle')
                # header-text -> date-text -> a -> div.date.one-queue
                parent_div = date_el.locator("..").locator("..").locator("..") 
                # Find the last available time in .times-list
                time_el = parent_div.locator(".times-list .time a").last

                # Find prevoiusly booked time if booking was not confirmed
                if request.booked_datetime and date == request.booked_datetime.date():
                    prev_booked_time_el = parent_div.locator(".times-list .time a", 
                            has_text=request.booked_datetime.strftime("%H:%M"))
                    count = await prev_booked_time_el.count()
                    if count > 0:
                        print("Time was not confirmed in email, book again...")
                        time_el = prev_booked_time_el
                    else:
                        return
                if request.booked_datetime and request.booked_datetime.date() < date:
                        return

                # Build the datetime
                time_text = await time_el.locator("span.available-time").inner_text()
                time_obj = datetime.strptime(time_text, "%H:%M").time()
                dt = datetime.combine(date, time_obj)

                # Click the last time element
                await time_el.click()
                
                # Fill the phone number
                await page.fill("#telephone", request.phone)

                # Fill email
                await page.fill("#email", request.email)

                # Fill full name
                await page.fill("#field11745", request.full_name)

                # Fill birth date
                await page.fill("#field11756", request.birth_date)

                # Click submit button
                await page.click("#submit-btn")

                timestamp = dt.strftime("%Y-%m-%d %H:%M")
                print(f"Form filled and submitted successfully! DateTime = {timestamp}, email = {request.email}")
                
                # # Wait for confirmation email
                # code = wait_for_confirmation_code(timeout=60)
                # # fill in code
                # await page.fill("#code", code)
                # # submit code
                # await page.locator("button.mdc-button", has_text="Termin")
                # # check if confirmed
                # await page.locator(".confirmed-reservation", has_text="gebucht")
                
                # send telegram notification
                msg = (timestamp + " is booked for " + request.full_name + 
                       ". Check your email!")
                await send_telegram_message(msg)
                return dt

            return None
    finally:
        if browser:
            await browser.close()
