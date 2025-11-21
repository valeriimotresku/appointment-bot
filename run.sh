#!/bin/bash
set -e

echo "Initializing database..."
python3 - <<END
from app.db.models import Base
from app.db.session import engine
Base.metadata.create_all(bind=engine)
END

uvicorn app.main:app --host 0.0.0.0 --port $PORT
