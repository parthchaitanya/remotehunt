"""Logging with a redaction filter: personal data and secrets never reach log output.

Modules should already avoid logging personal data; this filter is a second line of defence.
"""
from __future__ import annotations

import logging
import re

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+"), "[email]"),
    (re.compile(r"(?<![\w/])\+?\d[\d\s().-]{8,}\d(?![\w/])"), "[phone]"),
    (re.compile(r"(?i)((?:app_key|api_key|app_id|key|token|access_token|refresh_token|client_secret|affid|code)=)[^&\s\"']+"), r"\1[redacted]"),
    (re.compile(r"(?i)(bearer\s+)[\w.-]+"), r"\1[redacted]"),
    (re.compile(r"(jooble\.org/api/)[\w-]+"), r"\1[redacted]"),
    (re.compile(r"gsk_[A-Za-z0-9]+"), "[redacted]"),
]


def redact(text: str) -> str:
    for pat, repl in _PATTERNS:
        text = pat.sub(repl, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # malformed format args - keep the raw template only
            msg = str(record.msg)
        record.msg = redact(msg)
        record.args = ()
        if record.exc_info and record.exc_info[1] is not None:
            # Render the exception now so its text is redacted too.
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        return True


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # These libraries log full request URLs (which can carry API keys) at INFO/DEBUG.
    for noisy in ("httpx", "httpcore", "googleapiclient", "google_auth_oauthlib", "urllib3",
                  "apscheduler.executors", "sentence_transformers", "pdfminer", "groq", "huggingface_hub",
                  "transformers"):
        logging.getLogger(noisy).setLevel(logging.ERROR if noisy.startswith(("huggingface", "transformers"))
                                          else logging.WARNING)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
