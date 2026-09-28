from __future__ import annotations

import logging
import threading

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import llm
from ..db import SessionLocal, get_db
from ..models import ResumeVersion
from ..pipeline.run import rescore_all
from ..resume import service
from ..resume.parser import ResumeParseError
from ..resume.skill_gap import skill_gap
from ..resume.suggestions import generate_suggestions
from ..serializers import resume_version

router = APIRouter(prefix="/api/resume", tags=["resume"])
log = logging.getLogger(__name__)
MAX_BYTES = 5 * 1024 * 1024


def _rescore_bg() -> None:
    def work():
        try:
            with SessionLocal() as db:
                rescore_all(db)
        except Exception as exc:
            log.warning("Background rescore failed: %s", type(exc).__name__)
    threading.Thread(target=work, daemon=True).start()


@router.post("/upload")
async def upload(file: UploadFile = File(...), label: str = Form(""), note: str = Form(""),
                 db: Session = Depends(get_db)):
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File too large (max 5 MB)")
    try:
        v = service.create_version(db, data, file.filename or "resume.pdf", label, note)
    except ResumeParseError as exc:
        raise HTTPException(422, str(exc)) from None
    _rescore_bg()
    return resume_version(v, full=True)


@router.get("/active")
def active(db: Session = Depends(get_db)):
    v = service.active_version(db)
    return resume_version(v, full=True) if v else None


@router.get("/versions")
def versions(db: Session = Depends(get_db)):
    return [resume_version(v) for v in db.scalars(select(ResumeVersion).order_by(ResumeVersion.version_no.desc()))]


@router.get("/versions/{vid}")
def version(vid: int, db: Session = Depends(get_db)):
    v = db.get(ResumeVersion, vid)
    if v is None:
        raise HTTPException(404, "Version not found")
    return resume_version(v, full=True)


@router.get("/versions/{vid}/file")
def version_file(vid: int, db: Session = Depends(get_db)):
    v = db.get(ResumeVersion, vid)
    if v is None or not v.file_path:
        raise HTTPException(404, "File not found")
    return FileResponse(v.file_path, filename=v.filename)


@router.get("/diff")
def diff(a: int, b: int, db: Session = Depends(get_db)):
    va, vb = db.get(ResumeVersion, a), db.get(ResumeVersion, b)
    if va is None or vb is None:
        raise HTTPException(404, "Version not found")
    return service.diff_versions(va, vb)


@router.post("/versions/{vid}/rollback")
def rollback(vid: int, db: Session = Depends(get_db)):
    try:
        v = service.rollback(db, vid)
    except LookupError:
        raise HTTPException(404, "Version not found") from None
    _rescore_bg()
    return resume_version(v, full=True)


@router.post("/suggestions")
def suggestions(refresh: bool = False, db: Session = Depends(get_db)):
    v = service.active_version(db)
    if v is None:
        raise HTTPException(400, "Upload a resume first")
    if v.suggestions is None or refresh:
        v.suggestions = generate_suggestions(v.parsed, v.raw_text, service.target_roles())
        db.commit()
    return {"llm_available": llm.available(), "suggestions": v.suggestions}


@router.post("/ats/rescore")
def ats_rescore(db: Session = Depends(get_db)):
    v = service.active_version(db)
    if v is None:
        raise HTTPException(400, "Upload a resume first")
    service.rescore_ats(db, v)
    return v.ats


@router.get("/skill-gap")
def gap(db: Session = Depends(get_db)):
    v = service.active_version(db)
    if v is None:
        raise HTTPException(400, "Upload a resume first")
    return skill_gap(db, v.parsed, service.target_roles())
