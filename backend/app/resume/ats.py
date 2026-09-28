"""Rule-based ATS score (0-100) with a transparent per-category breakdown."""
from __future__ import annotations

import re
from typing import Any

from ..skills import DISPLAY, ROLE_SKILLS, expand_implied
from .parser import all_bullets

ACTION_VERBS = {
    "achieved", "analyzed", "analysed", "architected", "automated", "built", "championed", "collaborated",
    "conducted", "configured", "contributed", "created", "cut", "debugged", "decreased", "delivered", "deployed",
    "designed", "developed", "drove", "engineered", "enhanced", "established", "evaluated", "executed",
    "expanded", "facilitated", "generated", "grew", "identified", "implemented", "improved", "increased",
    "initiated", "integrated", "introduced", "launched", "led", "maintained", "managed", "mentored", "migrated",
    "modeled", "monitored", "optimized", "optimised", "orchestrated", "organized", "organised", "owned",
    "pioneered", "processed", "produced", "programmed", "prototyped", "published", "reduced", "refactored",
    "resolved", "scaled", "shipped", "simplified", "spearheaded", "streamlined", "strengthened", "tested",
    "trained", "transformed", "tuned", "visualized", "wrote", "coordinated", "authored", "benchmarked",
    "containerized", "curated", "extracted", "forecasted", "ingested", "predicted", "presented", "researched",
}
WEAK_STARTS = ("responsible for", "worked on", "helped", "assisted", "involved in", "participated in",
               "duties included", "tasked with", "handled")
METRIC_RE = re.compile(r"\d|%|\bpercent\b|\bx\b", re.I)


def _first_word(text: str) -> str:
    m = re.match(r"[A-Za-z]+", text.strip())
    return m.group(0).lower() if m else ""


def _cat(name: str, max_points: int, score: float, details: list[str], tips: list[str]) -> dict[str, Any]:
    return {"category": name, "score": round(max(0.0, min(score, max_points)), 1), "max": max_points,
            "details": details, "tips": tips}


def score_resume(parsed: dict[str, Any], raw_text: str, target_roles: list[str]) -> dict[str, Any]:
    cats: list[dict[str, Any]] = []
    contact = parsed.get("contact", {})
    links = contact.get("links", {})

    # 1. Contact (10)
    pts, det, tips = 0.0, [], []
    for key, label, p in (("email", "Email", 3), ("phone", "Phone", 3)):
        if contact.get(key):
            pts += p
            det.append(f"{label} found")
        else:
            tips.append(f"Add your {label.lower()} in the header.")
    if links.get("linkedin"):
        pts += 2
        det.append("LinkedIn link found")
    else:
        tips.append("Add a LinkedIn URL.")
    if links.get("github") or links.get("portfolio"):
        pts += 2
        det.append("GitHub/portfolio link found")
    else:
        tips.append("Add a GitHub or portfolio link - important for developer roles.")
    cats.append(_cat("Contact information", 10, pts, det, tips))

    # 2. Sections (15)
    found = set(parsed.get("sections_found", []))
    pts, det, tips = 0.0, [], []
    for sec, p, tip in (("summary", 3, "Add a 2-3 line professional summary targeted at your roles."),
                        ("education", 3, "Add an Education section."),
                        ("skills", 3, "Add a Skills section with grouped technical skills."),
                        ("projects", 2, "Add a Projects section with 2-3 relevant projects.")):
        if sec in found:
            pts += p
            det.append(f"'{sec.title()}' section present")
        else:
            tips.append(tip)
    if "experience" in found:
        pts += 4
        det.append("'Experience/Internship' section present")
    elif "projects" in found:
        pts += 2
        tips.append("Add an Experience or Internship section.")
    else:
        tips.append("Add an Experience or Internship section.")
    cats.append(_cat("Standard sections", 15, pts, det, tips))

    # 3. Skills (15): breadth (10) + role relevance (5)
    skill_keys = set(parsed.get("skill_keys", []))
    have = expand_implied(skill_keys)
    n = len(skill_keys)
    breadth = min(10.0, n / 15 * 10)
    core: set[str] = set()
    for role in target_roles:
        core |= set(ROLE_SKILLS.get(role, {}).get("core", []))
    core_hit = core & have
    relevance = 5 * (len(core_hit) / len(core)) if core else 5
    tips = []
    if n < 15:
        tips.append(f"Only {n} recognisable skills - list the tools you genuinely use (aim for 15-25).")
    missing_core = sorted(core - have, key=lambda k: DISPLAY[k])
    if missing_core:
        tips.append("Core skills for your target roles not on the resume: "
                    + ", ".join(DISPLAY[k] for k in missing_core[:8])
                    + " (add only those you actually have).")
    cats.append(_cat("Skills coverage", 15, breadth + relevance,
                     [f"{n} skills recognised", f"{len(core_hit)}/{len(core)} core target-role skills"], tips))

    # 4. Quantified impact (15)
    bullets = [b["text"] for b in all_bullets(parsed) if b["section"] in ("experience", "projects")]
    quant = [b for b in bullets if METRIC_RE.search(b)]
    ratio = len(quant) / len(bullets) if bullets else 0
    tips = []
    if ratio < 0.5:
        tips.append("Add numbers to more bullets (users, %, time saved, records processed, accuracy).")
    unquantified = [b for b in bullets if not METRIC_RE.search(b)]
    if unquantified:
        tips.append(f"{len(unquantified)} bullet(s) have no metric, e.g. \"{unquantified[0][:70]}...\"")
    cats.append(_cat("Quantified impact", 15, 15 * min(1.0, ratio / 0.6),
                     [f"{len(quant)}/{len(bullets)} bullets contain a number or metric"], tips))

    # 5. Action verbs (10)
    strong = [b for b in bullets if _first_word(b) in ACTION_VERBS]
    weak = [b for b in bullets if b.lower().startswith(WEAK_STARTS)]
    v_ratio = len(strong) / len(bullets) if bullets else 0
    tips = []
    if weak:
        tips.append(f"Replace weak openers like \"{weak[0][:30]}...\" with a strong verb (Built, Led, Reduced).")
    if v_ratio < 0.8 and bullets:
        tips.append("Start every bullet with a past-tense action verb.")
    cats.append(_cat("Action verbs", 10, 10 * min(1.0, v_ratio / 0.8) - 1.5 * len(weak),
                     [f"{len(strong)}/{len(bullets)} bullets start with a strong action verb"], tips))

    # 6. Length & density (10)
    stats = parsed.get("stats", {})
    words = stats.get("word_count", 0)
    pages = stats.get("pages", 1)
    if 350 <= words <= 800:
        lpts = 7.0
    elif 250 <= words < 350 or 800 < words <= 1000:
        lpts = 4.5
    else:
        lpts = 2.0
    avg = sum(len(b.split()) for b in bullets) / len(bullets) if bullets else 0
    bpts = 3.0 if 10 <= avg <= 30 else 1.5 if bullets else 0
    tips = []
    if words < 350:
        tips.append("Resume is short - expand project/internship bullets with outcomes.")
    if words > 800 and pages <= 1:
        tips.append("Dense single page - trim filler words.")
    if pages > 2:
        tips.append("Keep it to 1 page (student/entry level) or 2 at most.")
    if avg > 30:
        tips.append("Some bullets are long; keep each to 1-2 lines.")
    cats.append(_cat("Length & readability", 10, lpts + bpts,
                     [f"{words} words, {pages} page(s)", f"Average bullet length {avg:.0f} words"], tips))

    # 7. Parseability (10)
    pts, det, tips = 0.0, [], []
    if len(raw_text.strip()) > 400:
        pts += 4
        det.append("Text extracts cleanly")
    else:
        tips.append("Little text could be extracted - avoid image-only or scanned resumes.")
    std = len(found & {"summary", "education", "skills", "experience", "projects"})
    pts += min(3.0, std * 0.75)
    det.append(f"{std} standard headings recognised")
    non_ascii = sum(1 for ch in raw_text if ord(ch) > 127 and ch not in "•–—’“”²³é") / max(1, len(raw_text))
    if non_ascii < 0.02:
        pts += 2
    else:
        tips.append("Unusual characters/icons found - use plain text for contact details and headings.")
    if all(e.get("dates") for e in parsed.get("experience", [])) and parsed.get("experience"):
        pts += 1
    else:
        tips.append("Add dates (Month YYYY – Month YYYY) to every experience entry.")
    cats.append(_cat("ATS parseability", 10, pts, det, tips))

    # 8. Keyword alignment with target roles (15)
    role_scores = []
    for role in target_roles:
        rs = ROLE_SKILLS.get(role)
        if not rs:
            continue
        wanted = set(rs["core"]) | set(rs["nice"])
        cov = len(wanted & have) / len(wanted)
        role_scores.append((role, cov))
    best = max((c for _, c in role_scores), default=0)
    avg_cov = sum(c for _, c in role_scores) / len(role_scores) if role_scores else 0
    tips = []
    title_hits = [r for r in target_roles if r.lower() in raw_text.lower()]
    if not title_hits:
        tips.append("Mention your target role titles (e.g. in the summary) so ATS keyword searches match.")
    cats.append(_cat("Target-role keywords", 15, 15 * (0.6 * best + 0.4 * avg_cov) / 0.7 + (1 if title_hits else 0),
                     [f"{r}: {c:.0%} keyword coverage" for r, c in role_scores], tips))

    total = round(sum(c["score"] for c in cats))
    total = max(0, min(100, total))
    grade = "Excellent" if total >= 85 else "Good" if total >= 70 else "Fair" if total >= 55 else "Needs work"
    top_tips = [t for c in sorted(cats, key=lambda c: c["score"] / c["max"]) for t in c["tips"]][:6]
    return {"score": total, "grade": grade, "breakdown": cats, "top_tips": top_tips}
