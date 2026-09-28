"""Small text helpers shared by sources and the pipeline."""
from __future__ import annotations

import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

_TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "refId", "trackingId",
             "trk", "gh_src", "source", "lever-source", "lever-origin", "src", "fbclid", "gclid", "mc_cid", "mc_eid"}


def html_to_text(value: str | None) -> str:
    if not value:
        return ""
    text = value
    if "&lt;" in text and "<" not in text:
        text = html.unescape(text)  # double-escaped HTML (Greenhouse content)
    if "<" in text and ">" in text:
        soup = BeautifulSoup(text, "lxml")
        for br in soup.find_all(["br"]):
            br.replace_with("\n")
        for li in soup.find_all("li"):
            li.insert_before("\n• ")
        for block in soup.find_all(["p", "div", "h1", "h2", "h3", "h4", "ul", "ol", "tr"]):
            block.insert_after("\n")
        text = soup.get_text()
    text = html.unescape(text)
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def canonical_url(url: str | None) -> str:
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False) if k not in _TRACKING]
    return urlunsplit((parts.scheme.lower() or "https", parts.netloc.lower(), parts.path.rstrip("/"),
                       urlencode(query), ""))


def truncate(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"
