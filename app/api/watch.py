from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db.models import WatchRequest
from app.db.session import get_db
from datetime import datetime

router = APIRouter()

class WatchRequestIn(BaseModel):
    full_name: str
    email: str
    phone: str | None = "111111111111"
    birth_date: str
    date_from: str
    date_to: str

@router.post('/')
def add_watch(req: WatchRequestIn, db: Session = Depends(get_db)):
    r = WatchRequest(
        full_name=req.full_name,
        email=req.email,
        phone=req.phone or "111111111111",
        birth_date=req.birth_date,
        date_from=req.date_from,
        date_to=req.date_to,
        active=True
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return {'status': 'watch_started', 'id': r.id}
