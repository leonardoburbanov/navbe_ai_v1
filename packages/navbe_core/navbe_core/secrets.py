"""Fernet secret key stored under the Navbe profile home.

ponytail: file-based Fernet key → OS keyring when multi-user desktop ships.
"""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path

from cryptography.fernet import Fernet

from navbe_core.config import NAVBE_HOME

_KEY_PATH = NAVBE_HOME / "secret.key"


def _load_or_create_key() -> bytes:
    """Load the Fernet key from disk, creating one if missing."""
    if _KEY_PATH.exists():
        return _KEY_PATH.read_bytes()
    key = Fernet.generate_key()
    _KEY_PATH.write_bytes(key)
    with suppress(OSError):
        _KEY_PATH.chmod(0o600)
    return key


def get_fernet() -> Fernet:
    """Return a Fernet instance for encrypting secrets at rest."""
    return Fernet(_load_or_create_key())


def encrypt(plaintext: str) -> str:
    """Encrypt a UTF-8 string; return a URL-safe token string."""
    return get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    """Decrypt a token produced by :func:`encrypt`."""
    return get_fernet().decrypt(token.encode("ascii")).decode("utf-8")


def encrypt_json(payload: dict) -> str:
    """Encrypt a JSON-serializable dict."""
    import json

    return encrypt(json.dumps(payload))


def decrypt_json(token: str) -> dict:
    """Decrypt a token produced by :func:`encrypt_json`."""
    import json

    if not token:
        return {}
    return json.loads(decrypt(token))


def secret_key_path() -> Path:
    """Return the path to the Fernet key file."""
    return _KEY_PATH
