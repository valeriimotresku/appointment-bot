# Appointment Bot – ABH Kempten Auto Registration

## Run locally

```bash
pip install -r requirements.txt
python -m playwright install chromium
uvicorn app.main:app --reload
```

## Scheduler

The application keeps one Chromium instance alive and reuses the FrontDeskSuite
appointment date-picker page between checks.

The scheduler performs one availability scrape per cycle for all active
`WatchRequest`s. Only requests whose requested date range matches the current
availability enter the booking flow.

Optional `.env` settings:

```env
CHECK_INTERVAL_SECONDS=20
CHECK_JITTER_SECONDS=3
```

Keep Uvicorn on a single worker because the scheduler, in-memory email waiter,
and shared Playwright browser are process-local.
