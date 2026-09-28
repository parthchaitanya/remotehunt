"""Tailored resume + cover letter for a job. Facts come only from your resume; a guardrail rejects
any skill, number, title or credential that isn't there. Output is always a DRAFT awaiting your approval.
"""
from __future__ import annotations

import copy
import logging
from typing import Any

import numpy as np

from .. import llm
from ..config import load_profile
from ..models import Job, ResumeVersion
from ..pipeline.matcher import get_embedder
from ..skills import DISPLAY, expand_implied, extract_skills
from .guardrail import Allowed, build_allowed, check_many, check_text

log = logging.getLogger(__name__)

RULES = (
    "STRICT TRUTHFULNESS RULES: Use only facts present in the candidate's resume. Never add a skill, tool, "
    "technology, employer, job title, degree, certification, duration or number that is not in the resume. "
    "Do not claim years of experience. Do not claim seniority. You may rephrase, reorder and emphasise. "
    "Mention the job's required skills ONLY if they appear in the ALLOWED SKILLS list."
)


def _context_phrases(job: Job) -> list[str]:
    cand = load_profile().get("candidate", {})
    tz = cand.get("utc_offset", 5.5)
    h = int(tz)
    m = int(round((tz - h) * 60))
    return [job.title, job.company, f"UTC+{h}:{m:02d}", "IST"]


def _allowed(resume: ResumeVersion, job: Job) -> Allowed:
    return build_allowed(resume.parsed, resume.raw_text, _context_phrases(job))


def _job_skill_keys(job: Job) -> set[str]:
    return set(job.job_skills or extract_skills(f"{job.title}\n{job.description}"))


def _rank_lines(lines: list[str], job: Job, job_keys: set[str]) -> list[int]:
    """Order bullet indexes by relevance to the job (skill overlap + embedding similarity)."""
    if len(lines) <= 1:
        return list(range(len(lines)))
    emb = get_embedder()
    vecs = emb.encode([f"{job.title}. {job.description[:2000]}", *lines])
    sims = vecs[1:] @ vecs[0]
    scores = []
    for i, line in enumerate(lines):
        overlap = len(set(extract_skills(line)) & job_keys)
        scores.append(float(sims[i]) + 0.15 * overlap)
    return list(np.argsort(scores)[::-1])


def _reorder_skills(parsed: dict[str, Any], job_keys: set[str]) -> list[dict[str, Any]]:
    cats = parsed.get("skills", {}).get("categories", {})
    out = []
    for cat, items in cats.items():
        rel = [i for i in items if set(extract_skills(i)) & job_keys]
        rest = [i for i in items if i not in rel]
        out.append({"category": cat, "items": rel + rest, "relevant": len(rel)})
    out.sort(key=lambda c: -c["relevant"])
    return out


def _template_summary(parsed: dict[str, Any], job: Job, matched: list[str]) -> str:
    edu = (parsed.get("education") or [{}])[0]
    degree = edu.get("degree") or "Computer science"
    exp = (parsed.get("experience") or [{}])[0]
    parts = [f"{degree} student"]
    if matched:
        parts[0] += f" with hands-on experience in {', '.join(matched[:5])}"
    s = parts[0] + "."
    if exp.get("title"):
        org = f" at {exp['organization']}" if exp.get("organization") else ""
        s += f" Experience as {exp['title']}{org}."
    projects = [p.get("name") for p in parsed.get("projects", []) if p.get("name")]
    if projects:
        s += f" Built {projects[0]}."
    s += f" Applying for the {job.title} role at {job.company or 'your company'}."
    return s


def build_resume(resume: ResumeVersion, job: Job) -> tuple[dict[str, Any], dict[str, Any], str]:
    parsed = copy.deepcopy(resume.parsed)
    job_keys = _job_skill_keys(job)
    have = expand_implied(set(parsed.get("skill_keys", [])))
    matched_keys = [k for k in job_keys if k in have]
    matched = [DISPLAY.get(k, k) for k in matched_keys]
    allowed = _allowed(resume, job)
    changes: list[str] = []

    experience = []
    for e in parsed.get("experience", []):
        order = _rank_lines(e.get("bullets", []), job, job_keys)
        bullets = [e["bullets"][i] for i in order]
        if order != list(range(len(order))):
            changes.append(f"Reordered bullets under '{e.get('title')}' by relevance")
        experience.append({**e, "bullets": bullets})
    projects = []
    for p in parsed.get("projects", []):
        order = _rank_lines(p.get("bullets", []), job, job_keys)
        projects.append({**p, "bullets": [p["bullets"][i] for i in order]})
    skills = _reorder_skills(parsed, job_keys)
    changes.append("Moved skills that the job mentions to the front of each group")

    summary = _template_summary(parsed, job, matched)
    generator = "template"
    violations_seen: list[dict[str, str]] = []

    if llm.available():
        bullet_map = {}
        for ei, e in enumerate(experience):
            for bi, b in enumerate(e["bullets"]):
                bullet_map[f"e{ei}b{bi}"] = b
        for pi, p in enumerate(projects):
            for bi, b in enumerate(p["bullets"]):
                bullet_map[f"p{pi}b{bi}"] = b
        allowed_names = sorted(DISPLAY.get(k, k) for k in allowed.skills)
        prompt = (
            f"JOB: {job.title} at {job.company}\n{job.description[:3500]}\n\n"
            f"ALLOWED SKILLS: {', '.join(allowed_names)}\n"
            f"SKILLS THE JOB WANTS THAT THE CANDIDATE HAS: {', '.join(matched) or 'none'}\n\n"
            f"CANDIDATE RESUME:\n{resume.raw_text[:6000]}\n\n"
            f"BULLETS (id: text):\n" + "\n".join(f"{k}: {v}" for k, v in bullet_map.items()) + "\n\n"
            'Return {"summary": "<2-3 sentence summary tailored to this job>", '
            '"bullets": [{"id": "<id>", "text": "<rephrased bullet emphasising relevance; keep every number exactly>"}]}'
        )
        feedback = ""
        for attempt in range(2):
            data = llm.chat_json("You tailor resumes for specific jobs. " + RULES, prompt + feedback, max_tokens=2500)
            if not isinstance(data, dict):
                break
            cand = str(data.get("summary", "")).strip()
            v = check_text(cand, allowed)
            if cand and not v:
                summary, generator = cand, "llm"
                changes.append("Rewrote summary for this job (AI, guardrail-checked)")
            else:
                violations_seen += v
            rewritten = 0
            for item in data.get("bullets") or []:
                bid, text = str(item.get("id", "")), str(item.get("text", "")).strip()
                if bid not in bullet_map or not text:
                    continue
                bv = check_text(text, allowed)
                if bv:
                    violations_seen += bv
                    continue
                kind, rest = bid[0], bid[1:]
                idx, bi = (int(x) for x in rest.split("b"))
                target = experience if kind == "e" else projects
                if idx < len(target) and bi < len(target[idx]["bullets"]):
                    target[idx]["bullets"][bi] = text
                    rewritten += 1
            if rewritten:
                changes.append(f"Rephrased {rewritten} bullet(s) to emphasise relevant work (AI, guardrail-checked)")
            if generator == "llm":
                break
            feedback = ("\n\nYour previous answer was rejected because: "
                        + "; ".join(x["message"] for x in v) + " Fix this.") if v else ""

    content = {
        "name": parsed.get("name", ""),
        "contact": parsed.get("contact", {}),
        "summary": summary,
        "skills": skills,
        "experience": experience,
        "projects": projects,
        "education": parsed.get("education", []),
        "extracurricular": parsed.get("extracurricular", []) + parsed.get("achievements", []),
        "certifications": parsed.get("certifications", []),
        "job": {"id": job.id, "title": job.title, "company": job.company},
        "keywords_matched": matched,
        "keywords_missing": [DISPLAY.get(k, k) for k in job_keys - have][:10],
        "changes": changes,
    }
    final = check_many(resume_texts(content), allowed)
    guard = {"passed": not final, "violations": final, "rejected_ai_output": _uniq(violations_seen)}
    return content, guard, generator


def resume_texts(content: dict[str, Any]) -> list[str]:
    texts = [content.get("summary", "")]
    for e in content.get("experience", []):
        texts += e.get("bullets", [])
    for p in content.get("projects", []):
        texts += p.get("bullets", [])
    return texts


def cover_texts(content: dict[str, Any]) -> list[str]:
    return [content.get("greeting", ""), *content.get("paragraphs", []), content.get("closing", "")]


def _uniq(vs: list[dict[str, str]]) -> list[dict[str, str]]:
    seen, out = set(), []
    for v in vs:
        k = (v["type"], v["value"].lower())
        if k not in seen:
            seen.add(k)
            out.append(v)
    return out


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s and not s[:2].isupper() else s


def _template_cover(resume: ResumeVersion, job: Job, matched: list[str]) -> dict[str, Any]:
    p = resume.parsed
    name = p.get("name", "")
    edu = (p.get("education") or [{}])[0]
    paras = []
    intro = f"I'm writing to apply for the {job.title} role at {job.company or 'your company'}."
    if edu.get("degree"):
        intro += f" I'm pursuing a {edu['degree']}"
        intro += f" at {edu['institution']}." if edu.get("institution") else "."
    paras.append(intro)
    job_keys = _job_skill_keys(job)
    for e in (p.get("experience") or [])[:1]:
        order = _rank_lines(e.get("bullets", []), job, job_keys)
        best = [e["bullets"][i].rstrip(".") for i in order[:2]]
        if best:
            paras.append(f"As {e.get('title')} at {e.get('organization')}, I " + _lower_first(best[0])
                         + (f", and " + _lower_first(best[1]) if len(best) > 1 else "") + ".")
    for pr in (p.get("projects") or [])[:1]:
        order = _rank_lines(pr.get("bullets", []), job, job_keys)
        if order:
            paras.append(f"In my project {pr.get('name')}, I " + _lower_first(pr["bullets"][order[0]].rstrip(".")) + ".")
    if matched:
        paras.append(f"The role's focus on {', '.join(matched[:5])} matches the tools I work with day to day, and "
                     "I'm keen to keep growing them on a team like yours.")
    paras.append("I'm based in India (IST, UTC+5:30), comfortable with asynchronous remote collaboration, and "
                 "happy to overlap with your team's working hours. Thank you for considering my application.")
    return {"greeting": "Dear Hiring Team,", "paragraphs": paras, "closing": f"Sincerely,\n{name}",
            "job": {"id": job.id, "title": job.title, "company": job.company}}


def build_cover_letter(resume: ResumeVersion, job: Job) -> tuple[dict[str, Any], dict[str, Any], str]:
    allowed = _allowed(resume, job)
    job_keys = _job_skill_keys(job)
    have = expand_implied(set(resume.parsed.get("skill_keys", [])))
    matched = [DISPLAY.get(k, k) for k in job_keys if k in have]
    template = _template_cover(resume, job, matched)
    content, generator = template, "template"
    rejected: list[dict[str, str]] = []
    if llm.available():
        allowed_names = sorted(DISPLAY.get(k, k) for k in allowed.skills)
        prompt = (
            f"JOB: {job.title} at {job.company}\n{job.description[:3500]}\n\n"
            f"ALLOWED SKILLS: {', '.join(allowed_names)}\n"
            f"MATCHING SKILLS: {', '.join(matched) or 'none'}\n"
            f"CANDIDATE TIME ZONE: IST (UTC+5:30), based in India, early-career.\n\n"
            f"CANDIDATE RESUME:\n{resume.raw_text[:6000]}\n\n"
            "Write a concise cover letter (under 250 words, 3-4 paragraphs, warm and specific, no cliches). "
            'Return {"greeting": "Dear ...,", "paragraphs": ["..."], "closing": "Sincerely,\\n<name>"}'
        )
        feedback = ""
        for _ in range(2):
            data = llm.chat_json("You write honest cover letters. " + RULES, prompt + feedback, max_tokens=1200,
                                 temperature=0.5)
            if not isinstance(data, dict) or not data.get("paragraphs"):
                break
            cand = {"greeting": str(data.get("greeting", "Dear Hiring Team,")),
                    "paragraphs": [str(x) for x in data.get("paragraphs", []) if str(x).strip()],
                    "closing": str(data.get("closing", f"Sincerely,\n{resume.parsed.get('name', '')}")),
                    "job": template["job"]}
            v = check_many(cover_texts(cand), allowed)
            if not v:
                content, generator = cand, "llm"
                break
            rejected += v
            feedback = "\n\nYour previous letter was rejected because: " + "; ".join(x["message"] for x in v)
    final = check_many(cover_texts(content), allowed)
    return content, {"passed": not final, "violations": final, "rejected_ai_output": _uniq(rejected)}, generator


def recheck(kind: str, content: dict[str, Any], resume: ResumeVersion, job: Job) -> dict[str, Any]:
    allowed = _allowed(resume, job)
    texts = resume_texts(content) if kind == "resume" else cover_texts(content)
    v = check_many(texts, allowed)
    return {"passed": not v, "violations": v}


def plain_text(kind: str, c: dict[str, Any]) -> str:
    if kind == "cover_letter":
        return "\n\n".join([c.get("greeting", ""), *c.get("paragraphs", []), c.get("closing", "")])
    lines = [c.get("name", ""), "", "SUMMARY", c.get("summary", ""), "", "SKILLS"]
    lines += [f"{s['category']}: {', '.join(s['items'])}" for s in c.get("skills", [])]
    for title, key in (("EXPERIENCE", "experience"), ("PROJECTS", "projects")):
        lines += ["", title]
        for e in c.get(key, []):
            head = " – ".join(x for x in (e.get("title") or e.get("name"), e.get("organization")) if x)
            lines.append(head + (f" ({e['dates']})" if e.get("dates") else ""))
            lines += [f"• {b}" for b in e.get("bullets", [])]
    lines += ["", "EDUCATION"] + [f"{e.get('institution')} – {e.get('degree')} {e.get('dates', '')}"
                                  for e in c.get("education", [])]
    return "\n".join(lines)

