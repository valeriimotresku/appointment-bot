import os
from datetime import date, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.models import WatchRequest
from app.db.session import SessionLocal
from app.services.scraper import frontdesk_client

CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "20"))
CHECK_JITTER_SECONDS = int(os.getenv("CHECK_JITTER_SECONDS", "3"))

_scheduler: AsyncIOScheduler | None = None


def _get_active_requests() -> list[WatchRequest]:
    db = SessionLocal()
    try:
        return (
            db.query(WatchRequest)
            .filter(WatchRequest.active.is_(True))
            .all()
        )
    finally:
        db.close()


def _request_accepts_date(request: WatchRequest, available_date: date) -> bool:
    date_from = datetime.strptime(request.date_from, "%Y-%m-%d").date()
    date_to = datetime.strptime(request.date_to, "%Y-%m-%d").date()
    return date_from <= available_date <= date_to


def _save_booked_datetime(request_id: int, booked_datetime: datetime) -> None:
    db = SessionLocal()
    try:
        request = db.get(WatchRequest, request_id)
        if request is None:
            return

        request.booked_datetime = booked_datetime
        db.commit()
    finally:
        db.close()


async def check_all_async() -> None:
    """
    Run one FrontDesk availability scrape, then evaluate all active requests.

    Only requests whose date range matches the shared result enter the more
    expensive booking flow. Before each booking, scraper.py refreshes and
    validates availability again because slots may change quickly.
    """
    requests = _get_active_requests()

    if not requests:
        print("[Scheduler] No active watch requests.")
        return

    try:
        available_date = await frontdesk_client.get_first_available_date()
    except Exception as exc:
        print(f"[Scheduler] Availability check failed: {exc}")
        return

    matching_requests = [
        request
        for request in requests
        if _request_accepts_date(request, available_date)
    ]

    print(
        f"[Scheduler] {len(requests)} active request(s), "
        f"{len(matching_requests)} match {available_date}"
    )

    for request in matching_requests:
        try:
            booked_datetime = await frontdesk_client.book_available_datetime(
                request
            )
        except Exception as exc:
            print(
                f"[Scheduler] Booking failed for {request.email}: {exc}"
            )
            continue

        if booked_datetime is not None:
            _save_booked_datetime(request.id, booked_datetime)


def start_scheduler() -> None:
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        return

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        check_all_async,
        "interval",
        seconds=CHECK_INTERVAL_SECONDS,
        jitter=CHECK_JITTER_SECONDS,
        coalesce=True,
        max_instances=1,
    )
    _scheduler.start()

    print(
        "[Scheduler] Started. "
        f"Interval={CHECK_INTERVAL_SECONDS}s, "
        f"jitter={CHECK_JITTER_SECONDS}s"
    )


def stop_scheduler() -> None:
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("[Scheduler] Stopped.")

    _scheduler = None
