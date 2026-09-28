"""Gmail API access: OAuth (gmail.modify + gmail.send), Fernet-encrypted token storage,
send-to-self only, drafts (never sent), labels.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import threading
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr
from typing import Any

from sqlalchemy.orm import Session

from ..config import get_settings, load_profile
from ..models import ApiCall, OAuthToken
from ..security import decrypt, encrypt

log = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/gmail.modify", "https://www.googleapis.com/auth/gmail.send"]
PROVIDER = "google"
_pending: dict[str, tuple[float, str | None]] = {}  # state -> (created, code_verifier)
_lock = threading.Lock()
_label_cache: dict[str, str] = {}

if get_settings().oauth_redirect_uri.startswith("http://localhost") or \
        get_settings().oauth_redirect_uri.startswith("http://127.0.0.1"):
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")  # local dev redirect only
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")


class GmailNotConnected(RuntimeError):
    pass


class SendRefused(RuntimeError):
    pass


def client_config() -> dict[str, Any] | None:
    s = get_settings()
    if s.demo_mode:
        return None  # the public demo never touches a real mailbox
    if s.google_client_secrets_file and os.path.exists(s.google_client_secrets_file):
        with open(s.google_client_secrets_file, encoding="utf-8") as fh:
            return json.load(fh)
    if s.google_client_id and s.google_client_secret:
        return {"web": {"client_id": s.google_client_id, "client_secret": s.google_client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": [s.oauth_redirect_uri]}}
    return None


def _flow(state: str | None = None):
    from google_auth_oauthlib.flow import Flow

    cfg = client_config()
    if cfg is None:
        raise GmailNotConnected("Google OAuth client is not configured (see docs/SETUP.md)")
    flow = Flow.from_client_config(cfg, scopes=SCOPES, state=state)
    flow.redirect_uri = get_settings().oauth_redirect_uri
    return flow


def start_auth() -> str:
    flow = _flow()
    state = secrets.token_urlsafe(24)
    url, _ = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true",
                                    state=state, login_hint=load_profile()["gmail"].get("address") or None)
    with _lock:
        now = time.time()
        for k in [k for k, (t, _) in _pending.items() if now - t > 900]:
            _pending.pop(k, None)
        _pending[state] = (now, getattr(flow, "code_verifier", None))
    return url


def finish_auth(db: Session, code: str, state: str) -> str:
    with _lock:
        entry = _pending.pop(state, None)
    if entry is None:
        raise GmailNotConnected("OAuth state mismatch or expired; start again")
    flow = _flow(state=state)
    if entry[1]:
        flow.code_verifier = entry[1]
    flow.fetch_token(code=code)
    creds = flow.credentials
    from googleapiclient.discovery import build

    svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
    email = svc.users().getProfile(userId="me").execute().get("emailAddress", "")
    expected = (load_profile()["gmail"].get("address") or "").lower()
    if expected and email.lower() != expected:
        raise GmailNotConnected("Signed in with a different Google account than config/profile.yaml gmail.address")
    _save(db, creds, email)
    log.info("Gmail connected")
    return email


def _save(db: Session, creds, email: str | None = None) -> None:
    row = db.get(OAuthToken, PROVIDER)
    if row is None:
        row = OAuthToken(provider=PROVIDER, encrypted_token="")
        db.add(row)
    row.encrypted_token = encrypt(creds.to_json())
    if email is not None:
        row.encrypted_email = encrypt(email)
    row.scopes = list(creds.scopes or SCOPES)
    db.commit()


def connected_email(db: Session) -> str | None:
    row = db.get(OAuthToken, PROVIDER)
    return decrypt(row.encrypted_email) if row and row.encrypted_email else None


def is_connected(db: Session) -> bool:
    row = db.get(OAuthToken, PROVIDER)
    return bool(row and decrypt(row.encrypted_token))


def get_credentials(db: Session):
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    row = db.get(OAuthToken, PROVIDER)
    raw = decrypt(row.encrypted_token) if row else None
    if not raw:
        raise GmailNotConnected("Gmail is not connected")
    creds = Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError as exc:
                raise GmailNotConnected("Gmail token expired or revoked; reconnect Gmail") from exc
            _save(db, creds)
        else:
            raise GmailNotConnected("Gmail token invalid; reconnect Gmail")
    return creds


def service(db: Session):
    from googleapiclient.discovery import build

    return build("gmail", "v1", credentials=get_credentials(db), cache_discovery=False)


def record_call(db: Session, n: int = 1, ok: bool = True) -> None:
    for _ in range(n):
        db.add(ApiCall(source="gmail", ok=ok, purpose="gmail"))
    db.commit()


def disconnect(db: Session) -> None:
    row = db.get(OAuthToken, PROVIDER)
    if row is None:
        return
    raw = decrypt(row.encrypted_token)
    if raw:
        try:
            import httpx

            tok = json.loads(raw).get("refresh_token") or json.loads(raw).get("token")
            if tok:
                httpx.post("https://oauth2.googleapis.com/revoke", params={"token": tok}, timeout=10)
        except Exception:
            log.warning("Token revoke request failed; token deleted locally anyway")
    db.delete(row)
    db.commit()
    _label_cache.clear()


# ----------------------------------------------------------------------------- sending (self only)
def send_to_self(db: Session, subject: str, html: str, text: str) -> str:
    """Send an email to the connected account itself. There is no API to send to anyone else."""
    svc = service(db)
    me = svc.users().getProfile(userId="me").execute().get("emailAddress", "")
    expected = (load_profile()["gmail"].get("address") or "").lower()
    if not me or (expected and me.lower() != expected):
        raise SendRefused("Connected account does not match the configured digest address")
    msg = MIMEMultipart("alternative")
    msg["To"] = me
    msg["From"] = me
    msg["Subject"] = subject
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    res = svc.users().messages().send(userId="me", body={"raw": raw}).execute()
    record_call(db, 2)
    return res.get("id", "")


# ----------------------------------------------------------------------------- drafts (never sent)
def create_reply_draft(db: Session, message_id: str, body_text: str) -> str:
    """Create a Gmail *draft* replying to a message. Drafts are never sent by RemoteHunt."""
    svc = service(db)
    orig = svc.users().messages().get(userId="me", id=message_id, format="metadata",
                                      metadataHeaders=["Subject", "From", "Reply-To", "Message-ID",
                                                       "References"]).execute()
    headers = {h["name"].lower(): h["value"] for h in orig.get("payload", {}).get("headers", [])}
    to_addr = parseaddr(headers.get("reply-to") or headers.get("from", ""))[1]
    subject = headers.get("subject", "")
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    msg = MIMEText(body_text, "plain", "utf-8")
    msg["To"] = to_addr
    msg["Subject"] = subject
    if headers.get("message-id"):
        msg["In-Reply-To"] = headers["message-id"]
        msg["References"] = (headers.get("references", "") + " " + headers["message-id"]).strip()
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    draft = svc.users().drafts().create(
        userId="me", body={"message": {"raw": raw, "threadId": orig.get("threadId")}}).execute()
    record_call(db, 2)
    return draft.get("id", "")


# ----------------------------------------------------------------------------- labels
def ensure_label(db: Session, svc, name: str) -> str:
    if name in _label_cache:
        return _label_cache[name]
    labels = svc.users().labels().list(userId="me").execute().get("labels", [])
    for lb in labels:
        _label_cache[lb["name"]] = lb["id"]
    if name not in _label_cache:
        created = svc.users().labels().create(
            userId="me", body={"name": name, "labelListVisibility": "labelShow",
                               "messageListVisibility": "show"}).execute()
        _label_cache[name] = created["id"]
    record_call(db)
    return _label_cache[name]


def add_labels(db: Session, svc, message_id: str, label_names: list[str]) -> None:
    ids = [ensure_label(db, svc, n) for n in label_names]
    svc.users().messages().modify(userId="me", id=message_id, body={"addLabelIds": ids}).execute()
    record_call(db)


def message_body(payload: dict[str, Any]) -> tuple[str, str]:
    """Return (html, text) bodies from a Gmail message payload."""
    html, text = "", ""
    stack = [payload]
    while stack:
        part = stack.pop()
        mime = part.get("mimeType", "")
        data = (part.get("body") or {}).get("data")
        if data:
            decoded = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
            if mime == "text/html" and not html:
                html = decoded
            elif mime == "text/plain" and not text:
                text = decoded
        stack.extend(part.get("parts") or [])
    return html, text
