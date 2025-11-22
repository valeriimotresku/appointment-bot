#!/bin/bash
set -e

echo "Initializing database..."
python3 - <<END
from app.db.models import Base
from app.db.session import engine
Base.metadata.create_all(bind=engine)
END

echo "Ensuring Playwright Chromium is installed..."
playwright install chromium

echo "Starting FastAPI server..."
uvicorn app.main:app --host 0.0.0.0 --port $PORT
