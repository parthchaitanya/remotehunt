from __future__ import annotations

import re
import threading
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import load_profile
from ..db import get_db
from ..models import Job, TailoredDoc, utcnow
from ..pipeline.run import rescore_all
from ..resume.service import active_version
from ..serializers import doc, job_detail, job_summary
from ..sources import registry
from ..tailor import export, generator

router = APIRouter(prefix="/api", tags=["jobs"])


@router.get("/jobs")
def list_jobs(q: str = "", min_score: int = 0, source: str = "", eligible: str = "any", remote: str = "",
              role: str = "", apply_method: str = "", show_hidden: bool = False, include_scams: bool = False,
              sort: str = "score", limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    stmt = select(Job)
    if not show_hidden:
        stmt = stmt.where(Job.hidden.is_(False))
    if not include_scams:
        stmt = stmt.where(Job.scam_level != "high")
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Job.title.ilike(like), Job.company.ilike(like), Job.description.ilike(like)))
    if min_score:
        stmt = stmt.where(Job.match_score >= min_score)
    if source:
        stmt = stmt.where(Job.source == source)
    if eligible == "yes":
        stmt = stmt.where(Job.eligible.is_(True))
    elif eligible == "maybe":
        stmt = stmt.where(or_(Job.eligible.is_(True), Job.eligible.is_(None)))
    elif eligible == "no":
        stmt = stmt.where(Job.eligible.is_(False))
    if remote:
        stmt = stmt.where(Job.remote_type == remote)
    if role:
        stmt = stmt.where(Job.role_family == role)
    if apply_method:
        stmt = stmt.where(Job.apply_method == apply_method)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    order = {"score": Job.match_score.desc().nulls_last(), "newest": Job.first_seen_at.desc(),
             "posted": Job.posted_at.desc().nulls_last()}.get(sort, Job.match_score.desc().nulls_last())
    rows = db.scalars(stmt.order_by(order, Job.id.desc()).limit(min(limit, 200)).offset(offset))
    return {"total": total, "items": [job_summary(j) for j in rows]}


@router.get("/jobs/filters")
def filters(db: Session = Depends(get_db)):
    return {
        "sources": sorted(s for (s,) in db.execute(select(Job.source).distinct())),
        "roles": sorted(r for (r,) in db.execute(select(Job.role_family).distinct()) if r),
        "apply_methods": sorted(a for (a,) in db.execute(select(Job.apply_method).distinct()) if a),
    }


@router.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if j is None:
        raise HTTPException(404, "Job not found")
    d = job_detail(j)
    d["documents"] = [doc(x) for x in db.scalars(select(TailoredDoc).where(TailoredDoc.job_id == job_id)
                                                  .order_by(TailoredDoc.id.desc()))]
    d["tailor_min_score"] = int(load_profile()["matching"].get("tailor_min_score", 70))
    return d


class HideBody(BaseModel):
    hidden: bool = True


@router.post("/jobs/{job_id}/hide")
def hide(job_id: int, body: HideBody, db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if j is None:
        raise HTTPException(404, "Job not found")
    j.hidden = body.hidden
    db.commit()
    return job_summary(j)


class RunBody(BaseModel):
    force: bool = False
    sources: list[str] | None = None


@router.post("/search/run")
def run_search(body: RunBody):
    """Starts a search in the background. `force` skips min-interval waits but never exceeds call budgets."""
    if registry.is_running():
        return {"started": False, "message": "A search is already running"}

    def work():
        from ..scheduler import search_cycle

        if body.sources or body.force:
            registry.run_all(force=body.force, only=body.sources)
        else:
            search_cycle()

    threading.Thread(target=work, daemon=True).start()
    return {"started": True}


@router.get("/search/status")
def search_status():
    return {"running": registry.is_running()}


@router.post("/jobs/rescore")
def rescore(db: Session = Depends(get_db)):
    return {"rescored": rescore_all(db)}


# ----------------------------------------------------------------------------- tailored documents
@router.post("/jobs/{job_id}/tailor")
def tailor(job_id: int, force: bool = False, db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if j is None:
        raise HTTPException(404, "Job not found")
    resume = active_version(db)
    if resume is None:
        raise HTTPException(400, "Upload a resume first")
    threshold = int(load_profile()["matching"].get("tailor_min_score", 70))
    if (j.match_score or 0) < threshold and not force:
        raise HTTPException(400, f"Match score {j.match_score} is below the tailoring threshold ({threshold}). "
                                 "Pass force=true to tailor anyway.")
    out = []
    for kind, fn in (("resume", generator.build_resume), ("cover_letter", generator.build_cover_letter)):
        content, guard, gen = fn(resume, j)
        d = TailoredDoc(job_id=j.id, resume_version_id=resume.id, kind=kind, content=content, guardrail=guard,
                        generator=gen, status="draft")
        db.add(d)
        out.append(d)
    db.commit()
    return [doc(d) for d in out]


@router.get("/documents")
def documents(status: str = "", db: Session = Depends(get_db)):
    stmt = select(TailoredDoc).order_by(TailoredDoc.id.desc())
    if status:
        stmt = stmt.where(TailoredDoc.status == status)
    res = []
    for d in db.scalars(stmt.limit(200)):
        item = doc(d)
        job = db.get(Job, d.job_id)
        item["job"] = {"id": job.id, "title": job.title, "company": job.company} if job else None
        res.append(item)
    return res


class DocEdit(BaseModel):
    content: dict[str, Any]


@router.put("/documents/{doc_id}")
def edit_document(doc_id: int, body: DocEdit, db: Session = Depends(get_db)):
    d = db.get(TailoredDoc, doc_id)
    if d is None:
        raise HTTPException(404, "Document not found")
    resume = active_version(db)
    job = db.get(Job, d.job_id)
    d.content = body.content
    d.guardrail = {**generator.recheck(d.kind, body.content, resume, job), "edited": True}
    d.status = "draft"  # any edit needs re-approval
    d.approved_at = None
    db.commit()
    return doc(d)


@router.post("/documents/{doc_id}/approve")
def approve(doc_id: int, db: Session = Depends(get_db)):
    d = db.get(TailoredDoc, doc_id)
    if d is None:
        raise HTTPException(404, "Document not found")
    if not (d.guardrail or {}).get("passed", False):
        raise HTTPException(400, "Guardrail violations must be fixed before approval: "
                                 + "; ".join(v["message"] for v in d.guardrail.get("violations", [])))
    d.status, d.approved_at = "approved", utcnow()
    db.commit()
    return doc(d)


@router.post("/documents/{doc_id}/reject")
def reject(doc_id: int, db: Session = Depends(get_db)):
    d = db.get(TailoredDoc, doc_id)
    if d is None:
        raise HTTPException(404, "Document not found")
    d.status = "rejected"
    db.commit()
    return doc(d)


@router.get("/documents/{doc_id}/export")
def export_doc(doc_id: int, format: str = "pdf", db: Session = Depends(get_db)):
    d = db.get(TailoredDoc, doc_id)
    if d is None:
        raise HTTPException(404, "Document not found")
    if d.status != "approved":
        raise HTTPException(403, "Approve the document before exporting it")
    job = db.get(Job, d.job_id)
    resume = active_version(db)
    sender = {"name": resume.parsed.get("name", ""), "contact": resume.parsed.get("contact", {})} if resume else {}
    if format == "pdf":
        data = export.resume_pdf(d.content) if d.kind == "resume" else export.cover_pdf(d.content, sender)
        media = "application/pdf"
    elif format == "docx":
        data = export.resume_docx(d.content) if d.kind == "resume" else export.cover_docx(d.content, sender)
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        raise HTTPException(400, "format must be pdf or docx")
    slug = re.sub(r"[^\w]+", "_", f"{job.company if job else ''}_{d.kind}").strip("_")
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{slug}.{format}"'})

