"""Profile text for job platforms + completion tracker + cross-platform keyword consistency."""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import llm
from ..config import load_profile
from ..models import ProfileChecklist, ProfileText, ResumeVersion
from ..skills import DISPLAY, ROLE_SKILLS, expand_implied, extract_skills
from ..tailor.guardrail import build_allowed, check_text

# platform -> fields (name, char limit, hint) and checklist items
PLATFORMS: dict[str, dict[str, Any]] = {
    "linkedin": {
        "label": "LinkedIn",
        "fields": [("headline", 220, "Role keywords + value; shown in every search result"),
                   ("about", 2600, "First 2 lines matter most; include target roles and top skills"),
                   ("skills", 1000, "Comma-separated; pin your top 3")],
        "checklist": ["Professional photo", "Banner image", "Headline set", "About section", "NeGD internship added",
                      "Education added", "10+ skills added", "Open to Work: remote, target roles",
                      "Custom profile URL", "Featured: FFI Predictor project", "1+ recommendation"],
    },
    "github": {
        "label": "GitHub profile README",
        "fields": [("readme", 5000, "Markdown for github.com/<you>/<you>/README.md"),
                   ("bio", 160, "Profile bio")],
        "checklist": ["Profile README repo created", "Bio + location/time zone", "Pinned FFI Predictor repo",
                      "Each pinned repo has a README with demo/screenshots", "Contribution graph active"],
    },
    "wellfound": {
        "label": "Wellfound",
        "fields": [("bio", 280, "Short bio"), ("looking_for", 1000, "What you're looking for"),
                   ("achievements", 1000, "Achievements")],
        "checklist": ["Roles & remote preference set", "Salary expectations set", "Resume uploaded",
                      "Bio", "Skills", "Mark as actively looking"],
    },
    "himalayas": {
        "label": "Himalayas",
        "fields": [("headline", 120, "Headline"), ("bio", 1500, "About you")],
        "checklist": ["Time zone set to IST", "Skills added", "Experience added", "Open to remote roles toggled"],
    },
    "turing": {
        "label": "Turing",
        "fields": [("summary", 1000, "Professional summary")],
        "checklist": ["Profile created", "Resume uploaded", "Skills selected", "Vetting tests taken"],
    },
    "arc": {
        "label": "Arc.dev",
        "fields": [("headline", 100, "Headline"), ("bio", 1000, "Bio"), ("highlight", 500, "Project highlight")],
        "checklist": ["Profile created", "Resume uploaded", "Skills added", "Project highlight added"],
    },
    "naukri": {
        "label": "Naukri",
        "fields": [("resume_headline", 250, "Resume headline"), ("profile_summary", 1000, "Profile summary"),
                   ("key_skills", 500, "Key skills (comma-separated)")],
        "checklist": ["Resume uploaded", "Resume headline", "Profile summary", "Key skills", "Preferred locations "
                      "incl. remote", "Profile updated in the last 7 days"],
    },
    "instahyre": {
        "label": "Instahyre",
        "fields": [("summary", 1000, "Profile summary")],
        "checklist": ["Profile created", "Resume uploaded", "Skills added", "Job preferences set"],
    },
}


def _resume(db: Session) -> ResumeVersion | None:
    return db.scalar(select(ResumeVersion).where(ResumeVersion.is_active.is_(True)).order_by(ResumeVersion.id.desc()))


def _facts(parsed: dict[str, Any]) -> dict[str, Any]:
    roles = load_profile()["candidate"].get("target_roles", [])
    keys = parsed.get("skill_keys", [])
    have = expand_implied(set(keys))
    role_rel = [k for r in roles for k in ROLE_SKILLS.get(r, {}).get("core", []) + ROLE_SKILLS.get(r, {}).get("nice", [])]
    top = []
    for k in role_rel + list(keys):
        if k in have and k not in top and k != "communication":
            top.append(k)
    edu = (parsed.get("education") or [{}])[0]
    exp = (parsed.get("experience") or [{}])[0]
    proj = (parsed.get("projects") or [{}])[0]
    return {"roles": roles, "top_skills": [DISPLAY[k] for k in top[:12]], "degree": edu.get("degree", ""),
            "institution": edu.get("institution", ""), "exp_title": exp.get("title", ""),
            "exp_org": exp.get("organization", ""), "exp_bullets": exp.get("bullets", []),
            "project": proj.get("name", ""), "project_bullets": proj.get("bullets", []), "name": parsed.get("name", "")}


def _short_org(org: str) -> str:
    return re.sub(r"\s*\(.*?\)", "", org or "").strip()


def template_text(platform: str, field: str, f: dict[str, Any]) -> str:
    roles = " | ".join(f["roles"])
    skills = ", ".join(f["top_skills"][:8])
    org = _short_org(f["exp_org"])
    exp_line = f"{f['exp_title']} at {org}" if f["exp_title"] else ""
    b0 = f["exp_bullets"][0].rstrip(".") if f["exp_bullets"] else ""
    p0 = f["project_bullets"][0].rstrip(".") if f["project_bullets"] else ""
    student = f"{f['degree']} student" if f["degree"] else "Computer science student"
    about = (f"{student} at {f['institution']} focused on {roles.replace(' | ', ', ')} roles.\n\n"
             + (f"Experience: {exp_line}. {b0}.\n\n" if exp_line else "")
             + (f"Project: {f['project']}. {p0}.\n\n" if f["project"] else "")
             + f"Skills: {skills}.\n\nOpen to remote roles; based in India (IST, UTC+5:30).")
    short_bio = f"{student} | {roles} | {', '.join(f['top_skills'][:4])} | Remote, IST (UTC+5:30)"
    t = {
        ("linkedin", "headline"): f"{roles} | {', '.join(f['top_skills'][:5])}"
                                  + (f" | {f['exp_title']} @ {org}" if exp_line else ""),
        ("linkedin", "about"): about,
        ("linkedin", "skills"): ", ".join(f["top_skills"]),
        ("github", "bio"): short_bio,
        ("github", "readme"): (
            f"# Hi, I'm {f['name'].split()[0] if f['name'] else 'there'} 👋\n\n"
            f"{student} building with {', '.join(f['top_skills'][:4])}. Interested in {roles.replace(' | ', ', ')} "
            f"roles.\n\n## 🔭 What I've built\n"
            + (f"- **{f['project']}** – {p0}.\n" if f["project"] else "")
            + (f"- **{exp_line}** – {b0}.\n" if exp_line else "")
            + f"\n## 🛠️ Skills\n{' · '.join(f['top_skills'])}\n\n## 🌏 Location\nIndia · IST (UTC+5:30) · open to remote\n"),
        ("wellfound", "bio"): short_bio,
        ("wellfound", "looking_for"): (f"Remote {roles.replace(' | ', ' / ')} roles (internship or entry-level) where "
                                       f"I can apply {', '.join(f['top_skills'][:5])}. Comfortable with async work "
                                       f"and overlapping with other time zones from IST."),
        ("wellfound", "achievements"): "\n".join(f"• {b}" for b in (f["project_bullets"][:2] + f["exp_bullets"][:2])),
        ("himalayas", "headline"): f"{f['roles'][0] if f['roles'] else 'Developer'} · {', '.join(f['top_skills'][:3])}",
        ("himalayas", "bio"): about,
        ("turing", "summary"): about,
        ("arc", "headline"): f"{f['roles'][0] if f['roles'] else 'Developer'} ({', '.join(f['top_skills'][:3])})",
        ("arc", "bio"): about,
        ("arc", "highlight"): f"{f['project']}: {p0}." if f["project"] else "",
        ("naukri", "resume_headline"): (f"{student} seeking {roles.replace(' | ', ' / ')} roles | "
                                        f"{', '.join(f['top_skills'][:6])}"),
        ("naukri", "profile_summary"): about,
        ("naukri", "key_skills"): ", ".join(f["top_skills"]),
        ("instahyre", "summary"): about,
    }
    return t.get((platform, field), "")


def generate(db: Session, platform: str) -> list[ProfileText]:
    if platform not in PLATFORMS:
        raise LookupError("unknown platform")
    resume = _resume(db)
    if resume is None:
        raise LookupError("Upload a resume first")
    facts = _facts(resume.parsed)
    allowed = build_allowed(resume.parsed, resume.raw_text, ["UTC+5:30", "IST", "India"] + facts["roles"])
    spec = PLATFORMS[platform]
    out = []
    ai: dict[str, str] = {}
    if llm.available():
        fields_desc = "\n".join(f'- "{n}": max {lim} chars. {hint}' for n, lim, hint in spec["fields"])
        data = llm.chat_json(
            "You write job-platform profile text for an early-career candidate. Use ONLY facts in the resume: never "
            "add skills, tools, numbers, employers, titles or credentials. Keywords should match the target roles. "
            "Respect character limits.",
            f"Platform: {spec['label']}\nTarget roles: {', '.join(facts['roles'])}\nBased in India, IST (UTC+5:30), "
            f"open to remote.\nFields:\n{fields_desc}\n\nResume:\n{resume.raw_text[:6000]}\n\n"
            'Return {"fields": {"<field>": "<text>"}}', max_tokens=2500)
        if isinstance(data, dict) and isinstance(data.get("fields"), dict):
            ai = {k: str(v) for k, v in data["fields"].items()}
    for name, limit, _ in spec["fields"]:
        text, gen = ai.get(name, ""), "llm"
        if not text or len(text) > limit or check_text(text, allowed):
            text, gen = template_text(platform, name, facts)[:limit], "template"
        row = db.scalar(select(ProfileText).where(ProfileText.platform == platform, ProfileText.field == name))
        if row is None:
            row = ProfileText(platform=platform, field=name)
            db.add(row)
        row.generated_text, row.generator = text, gen
        out.append(row)
    db.commit()
    return out


def set_current(db: Session, platform: str, field: str, text: str) -> ProfileText:
    row = db.scalar(select(ProfileText).where(ProfileText.platform == platform, ProfileText.field == field))
    if row is None:
        row = ProfileText(platform=platform, field=field)
        db.add(row)
    row.current_text = text
    db.commit()
    return row


def toggle_item(db: Session, platform: str, item_key: str, done: bool) -> None:
    row = db.scalar(select(ProfileChecklist).where(ProfileChecklist.platform == platform,
                                                   ProfileChecklist.item_key == item_key))
    if row is None:
        row = ProfileChecklist(platform=platform, item_key=item_key)
        db.add(row)
    row.done = done
    db.commit()


def overview(db: Session) -> list[dict[str, Any]]:
    texts = {(t.platform, t.field): t for t in db.scalars(select(ProfileText))}
    checks = {(c.platform, c.item_key): c.done for c in db.scalars(select(ProfileChecklist))}
    out = []
    for key, spec in PLATFORMS.items():
        fields = []
        for name, limit, hint in spec["fields"]:
            t = texts.get((key, name))
            fields.append({"field": name, "limit": limit, "hint": hint,
                           "generated": t.generated_text if t else "", "current": t.current_text if t else "",
                           "generator": t.generator if t else ""})
        items = [{"key": i, "done": checks.get((key, i), False)} for i in spec["checklist"]]
        done = sum(1 for i in items if i["done"]) + sum(1 for f in fields if f["current"])
        total = len(items) + len(fields)
        out.append({"platform": key, "label": spec["label"], "fields": fields, "checklist": items,
                    "completion": round(100 * done / total) if total else 0})
    return out


def consistency(db: Session) -> dict[str, Any]:
    resume = _resume(db)
    if resume is None:
        return {"target_keywords": [], "platforms": [], "issues": ["Upload a resume first"]}
    facts = _facts(resume.parsed)
    targets = facts["top_skills"][:10]
    target_keys = {k for t in targets for k in extract_skills(t)}
    have = expand_implied(set(resume.parsed.get("skill_keys", [])))
    rows = []
    per_platform_skills: dict[str, set[str]] = {}
    for key, spec in PLATFORMS.items():
        texts = []
        using_current = False
        for t in db.scalars(select(ProfileText).where(ProfileText.platform == key)):
            if t.current_text:
                texts.append(t.current_text)
                using_current = True
            elif t.generated_text:
                texts.append(t.generated_text)
        if not texts:
            continue
        blob = "\n".join(texts)
        found = set(extract_skills(blob))
        per_platform_skills[spec["label"]] = found
        roles_mentioned = [r for r in facts["roles"] if r.lower() in blob.lower()]
        rows.append({
            "platform": spec["label"], "source": "your current text" if using_current else "generated text",
            "keyword_coverage": round(100 * len(found & target_keys) / len(target_keys)) if target_keys else 0,
            "missing_keywords": [DISPLAY[k] for k in target_keys - found],
            "roles_mentioned": roles_mentioned,
            "unsupported_claims": [DISPLAY.get(k, k) for k in found - have],
        })
    issues = []
    if len(per_platform_skills) >= 2:
        union = set().union(*per_platform_skills.values()) & target_keys
        for label, s in per_platform_skills.items():
            gap = union - s
            if gap:
                issues.append(f"{label} is missing {', '.join(DISPLAY[k] for k in sorted(gap)[:5])} "
                              f"that other profiles mention")
    for r in rows:
        if r["unsupported_claims"]:
            issues.append(f"{r['platform']} mentions skills not on your resume: {', '.join(r['unsupported_claims'])}")
        if not r["roles_mentioned"]:
            issues.append(f"{r['platform']} doesn't name any of your target roles")
    return {"target_keywords": targets, "platforms": rows, "issues": issues}
