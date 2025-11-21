# at the top of app/main.py
import sys
import asyncio

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())



from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.api.watch import router as watch_router
from app.api.status import router as status_router
from app.core.scheduler import start_scheduler
from app.db.models import Base
from app.db.session import engine

app = FastAPI()
app.mount('/static', StaticFiles(directory='static'), name='static')

@app.get('/')
def ui():
    return FileResponse('app/ui/index.html')

app.include_router(watch_router, prefix='/watch')
app.include_router(status_router, prefix='/status')

@app.on_event('startup')
async def startup_event():
    Base.metadata.create_all(bind=engine)  # ensures tables exist
    start_scheduler()
