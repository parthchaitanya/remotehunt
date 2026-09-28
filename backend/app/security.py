"""Fernet encryption for OAuth tokens at rest."""
from __future__ import annotations

import logging
import os

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings

log = logging.getLogger(__name__)
_fernet: Fernet | None = None


def _load_key() -> bytes:
    settings = get_settings()
    if settings.fernet_key:
        return settings.fernet_key.encode()
    key_file = settings.data_dir / ".fernet_key"
    if key_file.exists():
        return key_file.read_bytes().strip()
    key = Fernet.generate_key()
    key_file.write_bytes(key)
    os.chmod(key_file, 0o600)
    log.warning("FERNET_KEY not set; generated a local key in the data directory. "
                "Set FERNET_KEY in .env to keep tokens decryptable across machines.")
    return key


def fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_key())
    return _fernet


def encrypt(text: str) -> str:
    return fernet().encrypt(text.encode()).decode()


def decrypt(token: str) -> str | None:
    if not token:
        return None
    try:
        return fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        log.error("Stored token could not be decrypted (FERNET_KEY changed?). Reconnect Gmail.")
        return None
