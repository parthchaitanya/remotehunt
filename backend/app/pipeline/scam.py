"""Rule-based job-scam detector. Each hit adds weight; negated mentions ("we never charge a fee") don't count."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

NEGATION = re.compile(r"\b(no|never|not|don't|do not|doesn't|does not|won't|will not|without|zero|free of)\b[^.]{0,40}$",
                      re.I)

RULES: list[tuple[str, int, str, list[str]]] = [
    ("upfront_payment", 45, "Asks you to pay a fee or deposit",
     [r"\b(registration|training|joining|application|processing|security|onboarding|kit|placement)\s+"
      r"(fee|fees|charges?|deposit|amount)\b",
      r"\bpay\s+(a|an|the)?\s*(small|one[- ]time|refundable)?\s*(fee|deposit|amount)\b",
      r"\brefundable (deposit|fee|amount)\b", r"\bpurchase (a|the|your own)? ?(starter|training) kit\b"]),
    ("messaging_app_contact", 25, "Recruitment happens over Telegram/WhatsApp",
     [r"\b(telegram|whatsapp|signal|wechat|google hangouts)\b[^.\n]{0,50}\b(contact|message|text|reach|interview|"
      r"apply|dm|chat)\b",
      r"\b(contact|message|text|reach|interview|apply|dm|chat)\b[^.\n]{0,40}\b(on|via|through)\s+(telegram|whatsapp|"
      r"signal|wechat)\b",
      r"\b(t\.me|wa\.me|chat\.whatsapp\.com)/"]),
    ("personal_email_contact", 15, "Asks you to send your CV to a free email address",
     [r"[\w.+-]+@(gmail|yahoo|hotmail|outlook|aol|protonmail|rediffmail|ymail|live)\.(com|in|co\.in)"]),
    ("unrealistic_pay", 30, "Unrealistic pay promises",
     [r"\b(earn|make)\s+(up to\s+)?(\$|usd|₹|rs\.?|inr|€|£)\s?\d[\d,]*\s*(k\s*)?(per|a|/|each)\s*(day|week|hour)\b",
      r"\b(quick|easy|fast)\s+(money|cash|income)\b",
      r"\bno (experience|skills?) (needed|required)\b[^.]{0,80}\b(earn|\$|₹|income)\b",
      r"\bearn (money|income) from home\b"]),
    ("sensitive_info_request", 35, "Asks for bank/ID details up front",
     [r"\b(send|provide|share|submit|need)\b[^.\n]{0,40}\b(bank account|account number|ssn|social security|aadhaa?r|"
      r"pan card|credit card|debit card|otp|passport (copy|number))\b",
      r"\b(bank account|ssn|social security number|aadhaa?r|pan card|credit card)\s+(details|number|copy)\s+"
      r"(is|are)?\s*(required|needed|mandatory)\b"]),
    ("check_or_crypto_payment", 35, "Payment via cheques, gift cards, crypto or reshipping",
     [r"\b(cashier'?s? che(ck|que)|money order|gift cards?|reshipping|re-shipping|package forwarding|"
      r"deposit (the|a) che(ck|que)|paid in (bitcoin|crypto|usdt))\b"]),
    ("mlm_language", 25, "Multi-level-marketing / commission-only language",
     [r"\b(be your own boss|unlimited earning|financial freedom|recruit (others|friends|members)|network marketing|"
      r"commission[- ]only|passive income opportunity|mlm)\b"]),
    ("urgency_pressure", 10, "High-pressure urgency",
     [r"\b(limited (slots|seats|positions) (left|available)|act now|hurry|apply within 24 hours|"
      r"immediate joining[^.]{0,30}(fee|pay)|only today)\b"]),
    ("vague_task_job", 15, "Typical scam task job (data entry / typing / likes / reviews)",
     [r"\b(data entry|typing job|copy[- ]paste (job|work)|form filling|captcha (entry|typing)|like (and|&) "
      r"subscribe|rate products|product reviews? (task|job)|online tasks?)\b"]),
    ("shortened_links", 10, "Uses URL shorteners",
     [r"\b(bit\.ly|tinyurl\.com|goo\.gl|cutt\.ly|rb\.gy|is\.gd|shorturl\.at)/"]),
    ("guaranteed_job", 20, "Guaranteed job / placement promises",
     [r"\b(100%|guaranteed)\s+(job|placement|selection|hiring)\b", r"\bjob guarantee\b"]),
]
_COMPILED = [(code, w, msg, [re.compile(p, re.I) for p in pats]) for code, w, msg, pats in RULES]
ALERT_SOURCES = {"gmail_alerts"}


@dataclass
class ScamResult:
    score: int
    level: str
    flags: list[dict[str, Any]] = field(default_factory=list)


def _negated(text: str, start: int) -> bool:
    window = text[max(0, start - 60):start]
    return bool(NEGATION.search(window))


def detect(title: str, company: str, description: str, source: str = "", apply_url: str = "",
           salary_max: float | None = None, salary_currency: str = "") -> ScamResult:
    text = f"{title}\n{description or ''}"
    flags: list[dict[str, Any]] = []
    for code, weight, message, pats in _COMPILED:
        for pat in pats:
            hit = next((m for m in pat.finditer(text) if not _negated(text, m.start())), None)
            if hit:
                flags.append({"code": code, "weight": weight, "message": message, "evidence": hit.group(0)[:80]})
                break

    if not (company or "").strip():
        flags.append({"code": "missing_company", "weight": 15, "message": "No company name", "evidence": ""})
    if source not in ALERT_SOURCES and len((description or "").strip()) < 150:
        flags.append({"code": "thin_description", "weight": 10, "message": "Very little detail in the posting",
                      "evidence": f"{len((description or '').strip())} chars"})
    if salary_max and salary_currency.upper() == "USD" and salary_max > 400_000:
        flags.append({"code": "salary_outlier", "weight": 15, "message": "Salary far above market",
                      "evidence": f"USD {salary_max:,.0f}"})
    if re.search(r"\b(apply|contact)\b[^.\n]{0,30}\b(dm|direct message)\b", text, re.I):
        flags.append({"code": "dm_to_apply", "weight": 10, "message": "Apply via DM", "evidence": ""})

    score = min(100, sum(f["weight"] for f in flags))
    level = "high" if score >= 50 else "medium" if score >= 25 else "low"
    return ScamResult(score=score, level=level, flags=flags)
