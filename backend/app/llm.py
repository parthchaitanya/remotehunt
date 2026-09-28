"""Groq LLM wrapper with a daily cap and minimum spacing between calls.

Every feature that uses the LLM has a deterministic fallback, so the app works without a key.
Contact details are stripped from anything sent to the LLM.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import timedelta

from sqlalchemy import func, select

from .config import get_settings
from .db import SessionLocal
from .models import ApiCall, utcnow

log = logging.getLogger(__name__)
_lock = threading.Lock()
_last_call = 0.0
SOURCE = "llm:groq"

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_PHONE = re.compile(r"\+?\d[\d\s().-]{8,}\d")


def scrub(text: str) -> str:
    """Remove contact details before sending text to the LLM."""
    return _PHONE.sub("[phone]", _EMAIL.sub("[email]", text or ""))


def available() -> bool:
    return bool(get_settings().groq_api_key)


def _calls_last_24h() -> int:
    with SessionLocal() as db:
        since = utcnow() - timedelta(days=1)
        return db.scalar(select(func.count()).select_from(ApiCall)
                         .where(ApiCall.source == SOURCE, ApiCall.ts >= since)) or 0


def _record(ok: bool, status: int | None = None) -> None:
    with SessionLocal() as db:
        db.add(ApiCall(source=SOURCE, ok=ok, status_code=status, purpose="llm"))
        db.commit()


def chat(system: str, user: str, *, json_mode: bool = False, max_tokens: int = 1200,
         temperature: float = 0.3) -> str | None:
    """Return the completion text, or None if the LLM is unavailable / over budget / failing."""
    settings = get_settings()
    if not settings.groq_api_key:
        return None
    global _last_call
    with _lock:
        if _calls_last_24h() >= settings.llm_daily_cap:
            log.warning("LLM daily cap reached (%s calls); using fallback", settings.llm_daily_cap)
            return None
        wait = settings.llm_min_interval_seconds - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()
        try:
            from groq import Groq

            client = Groq(api_key=settings.groq_api_key, max_retries=1, timeout=60)
            kwargs = {}
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            if "gpt-oss" in settings.groq_model:
                # Reasoning models spend output tokens on thinking; keep it short and leave room for the answer.
                kwargs["reasoning_effort"] = "low"
                max_tokens += 1500
            resp = client.chat.completions.create(
                model=settings.groq_model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": scrub(user)}],
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )
            _record(True, 200)
            return resp.choices[0].message.content or ""
        except Exception as exc:  # network, rate limit, auth...
            status = getattr(exc, "status_code", None)
            _record(False, status)
            log.warning("LLM call failed (%s: status=%s); using fallback", type(exc).__name__, status)
            return None


def chat_json(system: str, user: str, **kw) -> dict | None:
    text = chat(system + "\nRespond with a single JSON object only.", user, json_mode=True, **kw)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    log.warning("LLM returned non-JSON output; using fallback")
    return None
