"""Resume versions: create, activate, diff, rollback."""
from __future__ import annotations

import difflib
import re
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..config import get_settings, load_profile
from ..models import ResumeVersion
from ..skills import DISPLAY
from .ats import score_resume
from .parser import parse_resume


def target_roles() -> list[str]:
    return load_profile()["candidate"].get("target_roles") or ["Python Developer", "Data Analyst", "AI Engineer"]


def active_version(db: Session) -> ResumeVersion | None:
    return db.scalar(select(ResumeVersion).where(ResumeVersion.is_active.is_(True))
                     .order_by(ResumeVersion.id.desc()))


def _next_no(db: Session) -> int:
    return (db.scalar(select(func.max(ResumeVersion.version_no))) or 0) + 1


def _activate(db: Session, v: ResumeVersion) -> None:
    db.execute(update(ResumeVersion).values(is_active=False))
    v.is_active = True


def create_version(db: Session, data: bytes, filename: str, label: str = "", note: str = "") -> ResumeVersion:
    parsed, raw = parse_resume(data, filename)
    ats = score_resume(parsed, raw, target_roles())
    no = _next_no(db)
    safe = re.sub(r"[^\w.-]+", "_", filename)[-80:]
    store = get_settings().data_dir / "resumes"
    store.mkdir(parents=True, exist_ok=True)
    path = store / f"v{no}_{safe}"
    path.write_bytes(data)
    v = ResumeVersion(version_no=no, label=label or f"v{no}", filename=filename, file_type=parsed.get("file_type", ""),
                      file_path=str(path), raw_text=raw, parsed=parsed, ats=ats, ats_score=ats["score"], note=note)
    db.add(v)
    db.flush()
    _activate(db, v)
    db.commit()
    return v


def rescore_ats(db: Session, v: ResumeVersion) -> ResumeVersion:
    v.ats = score_resume(v.parsed, v.raw_text, target_roles())
    v.ats_score = v.ats["score"]
    db.commit()
    return v


def rollback(db: Session, version_id: int) -> ResumeVersion:
    """Rollback never deletes history: it creates a new version that copies the chosen one."""
    src = db.get(ResumeVersion, version_id)
    if src is None:
        raise LookupError("version not found")
    no = _next_no(db)
    v = ResumeVersion(version_no=no, label=f"v{no} (rollback to v{src.version_no})", filename=src.filename,
                      file_type=src.file_type, file_path=src.file_path, raw_text=src.raw_text, parsed=src.parsed,
                      ats=src.ats, ats_score=src.ats_score, suggestions=src.suggestions, parent_id=src.id,
                      note=f"Rollback to v{src.version_no}")
    db.add(v)
    db.flush()
    _activate(db, v)
    db.commit()
    return v


def _section_texts(parsed: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {"Summary": [parsed.get("summary", "")] if parsed.get("summary") else []}
    out["Skills"] = [f"{k}: {', '.join(v)}" for k, v in parsed.get("skills", {}).get("categories", {}).items()]
    out["Experience"] = [line for e in parsed.get("experience", [])
                         for line in [f"{e.get('title')} – {e.get('organization')}", *e.get("bullets", [])]]
    out["Projects"] = [line for p in parsed.get("projects", []) for line in [p.get("name", ""), *p.get("bullets", [])]]
    out["Education"] = [f"{e.get('institution')} – {e.get('degree')}" for e in parsed.get("education", [])]
    out["Activities"] = parsed.get("extracurricular", []) + parsed.get("achievements", [])
    return out


def diff_versions(a: ResumeVersion, b: ResumeVersion) -> dict[str, Any]:
    sa, sb = _section_texts(a.parsed), _section_texts(b.parsed)
    sections = []
    for name in sa.keys() | sb.keys():
        la, lb = sa.get(name, []), sb.get(name, [])
        if la == lb:
            continue
        ops = []
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=la, b=lb).get_opcodes():
            if tag == "equal":
                continue
            ops.append({"op": tag, "removed": la[i1:i2], "added": lb[j1:j2]})
        sections.append({"section": name, "changes": ops})
    ka, kb = set(a.parsed.get("skill_keys", [])), set(b.parsed.get("skill_keys", []))
    unified = list(difflib.unified_diff(a.raw_text.splitlines(), b.raw_text.splitlines(),
                                        fromfile=f"v{a.version_no}", tofile=f"v{b.version_no}", lineterm="", n=1))
    return {
        "from": {"id": a.id, "version_no": a.version_no, "ats_score": a.ats_score},
        "to": {"id": b.id, "version_no": b.version_no, "ats_score": b.ats_score},
        "ats_delta": b.ats_score - a.ats_score,
        "skills_added": sorted(DISPLAY.get(k, k) for k in kb - ka),
        "skills_removed": sorted(DISPLAY.get(k, k) for k in ka - kb),
        "sections": sorted(sections, key=lambda s: s["section"]),
        "unified": unified,
    }
