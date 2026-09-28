"""Truthfulness guardrail: generated text may not claim skills or experience absent from the resume.

Checks (deterministic, no LLM):
  * skills   - every taxonomy skill mentioned must be on the resume (or implied by one that is)
  * numbers  - every number/metric must appear in the resume (placeholders like [X%] are allowed)
  * tenure   - "N years of experience" claims must appear verbatim in the resume
  * titles   - seniority claims ("as a Senior ...") must be backed by the resume
  * degrees  - degree/certification claims must be backed by the resume
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..skills import DISPLAY, expand_implied, extract_skills

NUM_RE = re.compile(r"(?<![\w\[])(\d+(?:[.,]\d+)*)(\s?%|\+)?(?![\w\]])")
PLACEHOLDER_RE = re.compile(r"\[[^\]]{1,20}\]")
TENURE_RE = re.compile(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\+?\s+(?:years?|yrs?)\b"
                       r"(?:\s+of)?(?:\s+\w+){0,3}\s+(?:experience|exp)\b", re.I)
TITLE_CLAIM_RE = re.compile(r"\b(?:as|am|was|worked as|served as|serving as|currently)\s+(?:a|an|the)?\s*"
                            r"(senior|lead|principal|staff|head|manager|director|architect|team lead|chief)\b", re.I)
DEGREE_RE = re.compile(r"\b(master'?s|m\.?\s?tech|m\.?\s?sc|mba|ph\.?\s?d|doctorate|certified|certification|"
                       r"certificate)\b", re.I)


@dataclass
class Allowed:
    skills: set[str]
    numbers: set[str]
    text_lower: str
    context_phrases: list[str] = field(default_factory=list)
    context_numbers: set[str] = field(default_factory=set)


def _norm_num(n: str) -> str:
    return n.replace(",", "").rstrip("0").rstrip(".") if "." in n else n.replace(",", "")


def _numbers(text: str) -> set[str]:
    return {_norm_num(m.group(1)) for m in NUM_RE.finditer(text or "")}


def build_allowed(parsed: dict[str, Any], raw_text: str, context_phrases: list[str] | None = None) -> Allowed:
    """context_phrases: names that may be quoted verbatim without counting as claims
    (job title, company name, your time zone). Skills inside them are not treated as claims."""
    phrases = sorted({p.strip() for p in (context_phrases or []) if p and p.strip()}, key=len, reverse=True)
    skills = expand_implied(set(parsed.get("skill_keys", [])) | set(extract_skills(raw_text)))
    return Allowed(skills=skills, numbers=_numbers(raw_text), text_lower=(raw_text or "").lower(),
                   context_phrases=phrases, context_numbers=set().union(*[_numbers(p) for p in phrases]) if phrases
                   else set())


def check_text(text: str, allowed: Allowed) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    if not text:
        return violations
    clean = PLACEHOLDER_RE.sub(" ", text)
    for phrase in allowed.context_phrases:
        clean = re.sub(re.escape(phrase), " ", clean, flags=re.I)

    for key in extract_skills(clean):
        if key not in allowed.skills:
            violations.append({"type": "skill", "value": DISPLAY.get(key, key),
                               "message": f"Mentions '{DISPLAY.get(key, key)}', which is not on your resume."})

    for num in _numbers(clean):
        if num not in allowed.numbers and num not in allowed.context_numbers:
            violations.append({"type": "number", "value": num,
                               "message": f"Uses the number '{num}', which does not appear on your resume."})

    for m in TENURE_RE.finditer(clean):
        if m.group(0).lower() not in allowed.text_lower:
            violations.append({"type": "experience", "value": m.group(0),
                               "message": f"Claims '{m.group(0)}', not stated on your resume."})

    for m in TITLE_CLAIM_RE.finditer(clean):
        word = m.group(1).lower()
        if word not in allowed.text_lower:
            violations.append({"type": "title", "value": m.group(0),
                               "message": f"Claims a '{word}' role, not supported by your resume."})

    for m in DEGREE_RE.finditer(clean):
        word = m.group(1).lower()
        if word not in allowed.text_lower:
            violations.append({"type": "credential", "value": m.group(0),
                               "message": f"Mentions '{m.group(0)}', not on your resume."})

    # de-duplicate
    seen, out = set(), []
    for v in violations:
        k = (v["type"], v["value"].lower())
        if k not in seen:
            seen.add(k)
            out.append(v)
    return out


def check_many(texts: list[str], allowed: Allowed) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for t in texts:
        out.extend(check_text(t, allowed))
    seen, uniq = set(), []
    for v in out:
        k = (v["type"], v["value"].lower())
        if k not in seen:
            seen.add(k)
            uniq.append(v)
    return uniq
