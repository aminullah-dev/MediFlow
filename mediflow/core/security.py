"""Password hashing and at-rest encryption of sensitive fields.

Passwords
    Hashed with PBKDF2-HMAC-SHA256 using the standard library only. A
    per-password random salt and a high iteration count are stored inside a
    self-describing string::

        pbkdf2_sha256$<rounds>$<salt_b64>$<hash_b64>

    Avoiding ``passlib`` is deliberate: passlib imports the stdlib ``crypt``
    module, which was **removed in Python 3.13** (our target), so it cannot even
    be imported there. ``hashlib.pbkdf2_hmac`` has no such dependency and behaves
    identically on Windows, macOS, and Linux.

Field encryption
    A symmetric Fernet key is generated on first run and stored in the app data
    directory with owner-only permissions. Selected columns (e.g. national id)
    are encrypted through :class:`FieldCipher` before being written to SQLite.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import stat
from pathlib import Path

MIN_PASSWORD_LENGTH = 8

_ALGORITHM = "pbkdf2_sha256"
_DEFAULT_ROUNDS = 390_000
_SALT_BYTES = 16


def hash_password(plain: str, *, rounds: int = _DEFAULT_ROUNDS) -> str:
    if not plain or len(plain) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    salt = secrets.token_bytes(_SALT_BYTES)
    derived = _pbkdf2(plain, salt, rounds)
    return f"{_ALGORITHM}${rounds}${_b64e(salt)}${_b64e(derived)}"


def verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        algorithm, rounds_s, salt_b64, hash_b64 = hashed.split("$")
        if algorithm != _ALGORITHM:
            return False
        rounds = int(rounds_s)
        salt = _b64d(salt_b64)
        expected = _b64d(hash_b64)
    except (ValueError, TypeError):
        return False
    candidate = _pbkdf2(plain, salt, rounds)
    return hmac.compare_digest(candidate, expected)


def needs_rehash(hashed: str, *, rounds: int = _DEFAULT_ROUNDS) -> bool:
    """True when a stored hash uses weaker parameters than the current policy."""
    try:
        algorithm, rounds_s, _, _ = hashed.split("$")
    except ValueError:
        return True
    return algorithm != _ALGORITHM or int(rounds_s) < rounds


def generate_temporary_password(length: int = 16) -> str:
    """Generate a temporary credential that can be typed on ANY keyboard layout.

    Digits only, deliberately. The digit row is identical on the US (0409) and
    Persian (0429) Windows layouts, so the operator can always enter it no
    matter which one happens to be active. The previous mixed alphabet could
    not promise that: it contained ``P`` and ``U``, whose Persian shifted
    positions emit plain ASCII (``\\`` and ``,``). Those are indistinguishable
    from deliberately typed characters, so :mod:`mediflow.core.keyboard` must
    not rewrite them — which made such temporary passwords permanently
    unenterable and drove the repeated reset-and-lockout cycle.

    On strength: 16 digits is ~53 bits. Against this threat model — an offline
    single-machine deployment, the credential shown on screen, a forced change
    on first sign-in, ten attempts per five-minute lockout, and PBKDF2 at
    390k rounds — that is ample, and it buys a credential that always works.
    """
    return "".join(secrets.choice("0123456789") for _ in range(length))


def _pbkdf2(plain: str, salt: bytes, rounds: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, rounds)


def _b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


class FieldCipher:
    """Encrypt/decrypt short sensitive strings for storage in the database."""

    def __init__(self, key: bytes):
        # Imported lazily so the rest of core works without cryptography present.
        from cryptography.fernet import Fernet

        self._key = key
        self._fernet = Fernet(key)

    @classmethod
    def from_key_file(cls, key_path: Path) -> "FieldCipher":
        return cls(_load_or_create_key(key_path))

    @property
    def key(self) -> bytes:
        return self._key

    def encrypt(self, value: str | None) -> str | None:
        if value is None:
            return None
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str | None) -> str | None:
        if token is None:
            return None
        return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")

    def sign(self, data: bytes) -> str:
        """HMAC-SHA256 of ``data`` keyed by the secret key (hex) — for backups."""
        return hmac.new(self._key, data, hashlib.sha256).hexdigest()


# Marks a key file whose contents are DPAPI-protected (vs. a legacy raw key).
_DPAPI_MAGIC = b"DPAPI1\n"


def _load_or_create_key(key_path: Path) -> bytes:
    from cryptography.fernet import Fernet

    from mediflow.core import dpapi

    if key_path.exists():
        blob = key_path.read_bytes()
        if blob.startswith(_DPAPI_MAGIC):
            key = dpapi.unprotect(blob[len(_DPAPI_MAGIC):])
            if key is None:
                from mediflow.core.exceptions import MediFlowError

                raise MediFlowError(
                    "Cannot decrypt the field-encryption key — it was protected "
                    "for a different Windows user or machine. Sign in as the "
                    "Windows user who installed MediFlow, or restore the data "
                    "folder from a backup taken on this machine."
                )
            return key
        # Legacy plaintext key: upgrade to DPAPI at rest — but only rewrite the
        # file when protection actually succeeded, never truncate-rewrite the
        # same plaintext on every startup (a crash mid-write would lose the key).
        protected = dpapi.protect(blob)
        if protected:
            key_path.write_bytes(_DPAPI_MAGIC + protected)
            try:
                os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:  # pragma: no cover
                pass
        return blob

    key = Fernet.generate_key()
    _write_key(key_path, key)
    return key


def _write_key(key_path: Path, key: bytes) -> None:
    """Write the key DPAPI-protected when possible, else as a restricted plain file."""
    from mediflow.core import dpapi

    protected = dpapi.protect(key)
    if not protected and dpapi.is_available():  # same gate as the write below
        # DPAPI is present but protection failed — surface it rather than
        # silently persisting the encryption key in the clear.
        from mediflow.core.logging_config import get_logger

        get_logger("security").warning(
            "DPAPI protection failed; the field-encryption key is stored "
            "unprotected. It relies on filesystem permissions only."
        )
    key_path.write_bytes(_DPAPI_MAGIC + protected if protected else key)
    try:
        os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)  # best-effort owner-only
    except OSError:
        pass
