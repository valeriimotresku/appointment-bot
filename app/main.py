import asyncio
import sys
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# Keep Playwright compatible with local Windows development.
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Load environment variables before importing modules that read os.getenv()
# at import time.
load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.status import router as status_router
from app.api.watch import router as watch_router
from app.core.scheduler import start_scheduler, stop_scheduler
from app.core.auth import admin_auth_middleware, validate_auth_config
from app.db.models import Base
from app.db.session import engine
from app.services.browser_manager import browser_manager
from app.services.email_parser import parse_confirmation_email
from app.services.mailgun_security import (
    validate_mailgun_config,
    verify_mailgun_signature,
)
from app.services.email_waiter import deliver_code
from app.services.scraper import frontdesk_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_auth_config()
    validate_mailgun_config()
    Base.metadata.create_all(bind=engine)

    # Browser + APScheduler now live on the same asyncio event loop as FastAPI.
    # This avoids the old BackgroundScheduler -> asyncio.run() cross-loop setup.
    await browser_manager.start()
    await frontdesk_client.prepare()
    start_scheduler()

    try:
        yield
    finally:
        stop_scheduler()
        await browser_manager.stop()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.middleware("http")(admin_auth_middleware)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def ui():
    return FileResponse("app/ui/index.html")


app.include_router(watch_router, prefix="/watch")
app.include_router(status_router, prefix="/status")


@app.post("/email/incoming")
async def incoming_email(request: Request):
    # This endpoint must remain reachable without UI Basic Auth so Mailgun can
    # call it, but the request itself is authenticated with Mailgun's HMAC.
    form = await request.form()

    if not verify_mailgun_signature(
        timestamp=form.get("timestamp"),
        token=form.get("token"),
        signature=form.get("signature"),
    ):
        print("[Mailgun] Rejected webhook: invalid signature or stale timestamp")
        raise HTTPException(status_code=401, detail="Invalid Mailgun signature")

    result = parse_confirmation_email(form)

    if result is None:
        return {"status": "ignored"}

    email, code = result
    delivered = deliver_code(email, code)

    return {
        "status": "ok",
        "delivered": delivered,
    }
