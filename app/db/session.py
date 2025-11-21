import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# default to local path for dev, override in Render with ENV var
DB_PATH = os.getenv("DATABASE_URL", "sqlite:///./app.db")

# pool_pre_ping ensures stale connections are handled gracefully
engine = create_engine(
    DB_PATH,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Dependency for FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
