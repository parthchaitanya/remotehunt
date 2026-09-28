from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..profiles import generator as prof

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


@router.get("")
def overview(db: Session = Depends(get_db)):
    return prof.overview(db)


@router.post("/{platform}/generate")
def generate(platform: str, db: Session = Depends(get_db)):
    try:
        prof.generate(db, platform)
    except LookupError as exc:
        raise HTTPException(400, str(exc)) from None
    return next(p for p in prof.overview(db) if p["platform"] == platform)


class CurrentBody(BaseModel):
    field: str
    text: str


@router.put("/{platform}/current")
def set_current(platform: str, body: CurrentBody, db: Session = Depends(get_db)):
    if platform not in prof.PLATFORMS:
        raise HTTPException(404, "Unknown platform")
    prof.set_current(db, platform, body.field, body.text)
    return next(p for p in prof.overview(db) if p["platform"] == platform)


class CheckBody(BaseModel):
    item: str
    done: bool


@router.post("/{platform}/checklist")
def checklist(platform: str, body: CheckBody, db: Session = Depends(get_db)):
    if platform not in prof.PLATFORMS:
        raise HTTPException(404, "Unknown platform")
    prof.toggle_item(db, platform, body.item, body.done)
    return next(p for p in prof.overview(db) if p["platform"] == platform)


@router.get("/consistency")
def consistency(db: Session = Depends(get_db)):
    return prof.consistency(db)
