# app/api/status.py
from fastapi import APIRouter, HTTPException
from app.db.session import SessionLocal
from app.db.models import WatchRequest

router = APIRouter()

@router.get("/")
def status():
    db = SessionLocal()
    try:
        return db.query(WatchRequest).all()
    finally:
        db.close()

@router.delete("/{request_id}")
def delete_request(request_id: int):
    db = SessionLocal()
    try:
        req = db.query(WatchRequest).get(request_id)
        if not req:
            raise HTTPException(status_code=404, detail="Request not found")
        db.delete(req)
        db.commit()
        return {"status": "deleted", "id": request_id}
    finally:
        db.close()
