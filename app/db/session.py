import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Get database URL from environment; default to local SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

# Determine connect_args for SQLite only
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# Create SQLAlchemy engine
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,  # ensures stale connections are handled gracefully
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency for FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
