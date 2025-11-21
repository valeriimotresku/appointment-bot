from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class WatchRequest(Base):
    __tablename__ = 'watch_requests'
    id = Column(Integer, primary_key=True)
    full_name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String, nullable=False, default="111111111111")
    birth_date = Column(String, nullable=False)
    date_from = Column(String, nullable=False)
    date_to = Column(String, nullable=False)
    active = Column(Boolean, default=True)
    booked_datetime = Column(DateTime, nullable=True)
