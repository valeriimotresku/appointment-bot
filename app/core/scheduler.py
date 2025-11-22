from apscheduler.schedulers.background import BackgroundScheduler
from app.db.session import SessionLocal
from app.db.models import WatchRequest
from app.services.scraper import book_available_datetime
from datetime import datetime
import asyncio

def check_all_sync():
    """
    Windows-safe scheduler job.
    Runs async Playwright tasks via asyncio.run().
    """
    asyncio.run(check_all_async())

async def check_all_async():
    """
    Async logic for checking appointments.
    """
    # 1. Fetch active requests in sync DB session
    db = SessionLocal()
    try:
        reqs = db.query(WatchRequest).filter(WatchRequest.active == True).all()
    finally:
        db.close()

    # 2. Process each watch request
    for r in reqs:
        try:
            dt = await book_available_datetime(r)
        except Exception as e:
            print(f"[Scheduler] Error fetching available dates: {e}")
            continue
        if dt is not None:
            # Set booking time in DB
            db = SessionLocal()
            try:
                r_db = db.query(WatchRequest).get(r.id)
                if r_db:
                    #r_db.active = False
                    r_db.booked_datetime = dt
                    db.commit()
            finally:
                db.close()

def start_scheduler():
    """
    Start the scheduler using BackgroundScheduler (Windows-safe).
    """
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_all_sync, 'interval', seconds=30, 
                      next_run_time=datetime.now(), coalesce=True, max_instances=1)
    scheduler.start()
    print("[Scheduler] Started successfully on Windows.")
