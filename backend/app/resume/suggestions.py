"""Line-by-line resume suggestions: rule-based issues + optional Groq rewrites (guardrailed)."""
from __future__ import annotations

import logging
import re
from typing import Any

from .. import llm
from ..tailor.guardrail import build_allowed, check_text
from .ats import ACTION_VERBS, METRIC_RE, WEAK_STARTS, _first_word
from .parser import all_bullets

log = logging.getLogger(__name__)
FILLER = ("various", "several", "etc", "successfully", "effectively", "efficiently", "hard-working",
          "passionate", "team player", "go-getter", "synergy")


def rule_issues(text: str, section: str) -> list[str]:
    issues = []
    words = text.split()
    if section in ("experience", "projects"):
        if not METRIC_RE.search(text):
            issues.append("No measurable result - add a number (scale, %, time, users).")
        if text.lower().startswith(WEAK_STARTS):
            issues.append("Weak opener - start with an action verb.")
        elif _first_word(text) not in ACTION_VERBS:
            issues.append("Doesn't start with a strong past-tense action verb.")
        if len(words) > 32:
            issues.append("Too long - aim for one to two lines.")
        if len(words) < 8:
            issues.append("Too short - say what you built, how, and the outcome.")
    if re.search(r"\b(I|my|me)\b", text):
        issues.append("Avoid first-person pronouns.")
    fillers = [f for f in FILLER if re.search(rf"\b{re.escape(f)}\b", text, re.I)]
    if fillers:
        issues.append(f"Filler words: {', '.join(fillers)}.")
    if section == "summary" and len(words) > 70:
        issues.append("Summary is long - keep it to 2-3 lines targeted at your roles.")
    if section == "summary" and not re.search(r"(python|data analyst|ai|machine learning)", text, re.I):
        issues.append("Summary doesn't name your target roles.")
    return issues


SYSTEM = (
    "You are an expert technical resume editor for entry-level candidates. You rewrite individual resume "
    "lines to be concise, specific and ATS-friendly. STRICT RULES: never add a skill, tool, technology, "
    "employer, title, degree, certification or number that is not in the original line or the provided "
    "resume. If a metric would help but is unknown, insert a placeholder such as [X%] or [N users]. Keep "
    "each bullet rewrite under 30 words and start it with a strong past-tense verb. For [summary] lines, write "
    "the actual replacement summary (2-3 sentences, no first-person pronouns) that names the target roles and the "
    "candidate's strongest real skills - never describe or comment on the summary itself."
)


def generate_suggestions(parsed: dict[str, Any], raw_text: str, target_roles: list[str]) -> list[dict[str, Any]]:
    lines = all_bullets(parsed)
    out: list[dict[str, Any]] = []
    for i, item in enumerate(lines):
        out.append({"id": i, "section": item["section"], "context": item["context"], "original": item["text"],
                    "issues": rule_issues(item["text"], item["section"]), "suggestion": "", "reason": "",
                    "source": "rules", "guardrail": []})

    if llm.available() and lines:
        allowed = build_allowed(parsed, raw_text)
        numbered = "\n".join(f"{i}. [{x['section']}] {x['original']}" for i, x in enumerate(out[:30]))
        user = (f"Target roles: {', '.join(target_roles)}\n\nFull resume for context (facts you may use):\n"
                f"{raw_text[:6000]}\n\nLines to improve:\n{numbered}\n\n"
                'Return {"suggestions": [{"id": <int>, "rewrite": "<improved line>", "reason": "<why, <=20 words>"}]}. '
                "Only include lines that can genuinely be improved.")
        data = llm.chat_json(SYSTEM, user, max_tokens=2500)
        for s in (data or {}).get("suggestions", []) if isinstance(data, dict) else []:
            try:
                idx = int(s.get("id"))
            except (TypeError, ValueError):
                continue
            if not (0 <= idx < len(out)):
                continue
            rewrite = str(s.get("rewrite", "")).strip()
            if not rewrite or rewrite == out[idx]["original"]:
                continue
            violations = check_text(rewrite, allowed)
            out[idx]["guardrail"] = violations
            if violations:
                # Reject rewrites that invent facts; keep the rule-based guidance instead.
                out[idx]["reason"] = "AI rewrite rejected by guardrail: " + "; ".join(v["message"] for v in violations)
                continue
            out[idx].update(suggestion=rewrite, reason=str(s.get("reason", ""))[:200], source="llm")

    for item in out:
        if not item["suggestion"] and item["issues"]:
            item["suggestion"] = _rule_rewrite_hint(item["original"], item["issues"])
    return out


def _rule_rewrite_hint(text: str, issues: list[str]) -> str:
    """Deterministic nudge when no LLM rewrite is available."""
    hint = text.strip()
    for weak in WEAK_STARTS:
        if hint.lower().startswith(weak):
            hint = "[Action verb]" + hint[len(weak):]
            break
    if any(i.startswith("No measurable result") for i in issues):
        hint = hint.rstrip(".") + ", resulting in [metric: %, time saved, users, records]."
    return hint if hint != text.strip() else ""
