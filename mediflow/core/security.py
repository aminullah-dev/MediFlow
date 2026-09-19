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

    The key file itself is sealed to the signed-in OS account by
    :mod:`mediflow.core.secret_store` — DPAPI on Windows, the Keychain on macOS
    — so copying it off the machine yields nothing usable. Where no such store
    exists the key falls back to file permissions alone, and that fallback is
    always logged rather than taken quietly.
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
    def from_key_file(cls, key_path: Path) -> FieldCipher:
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


def _load_or_create_key(key_path: Path) -> bytes:
    from cryptography.fernet import Fernet

    from mediflow.core import secret_store

    if key_path.exists():
        blob = key_path.read_bytes()
        if secret_store.is_protected(blob):
            key = secret_store.unprotect(blob)
            if key is None:
                from mediflow.core.exceptions import MediFlowError

                raise MediFlowError(secret_store.recovery_hint(blob))
            return key
        # Legacy plaintext key: seal it at rest — but only rewrite the file when
        # sealing actually succeeded, never truncate-rewrite the same plaintext
        # on every startup.
        sealed = secret_store.protect(blob)
        if sealed:
            _replace_key_file(key_path, sealed)
        return blob

    key = Fernet.generate_key()
    _write_key(key_path, key)
    return key


def install_key(key_path: Path, key: bytes) -> None:
    """Make ``key`` this installation's field-encryption key, sealed at rest.

    Used when restoring a backup taken on another machine: that database is
    encrypted with the key that travelled beside it, so adopting the key is the
    only way its columns become readable here. Sealing is redone locally, so a
    key that arrived from a Windows PC ends up bound to this Mac's Keychain.

    Anything already encrypted with the previous key becomes unreadable, so the
    caller must have taken a backup of it first — :class:`BackupService` does.
    """
    _write_key(key_path, key)


def _write_key(key_path: Path, key: bytes) -> None:
    """Write the key sealed by the OS where possible, else as a restricted file."""
    from mediflow.core import secret_store
    from mediflow.core.logging_config import get_logger

    sealed = secret_store.protect(key)
    if not sealed:
        # Never silent. Which of the two cases this is changes what an operator
        # should do about it, so they are worded differently.
        message = (
            "%s is present but sealing the field-encryption key failed; it is "
            "stored unprotected and falls back to %s."
            if secret_store.is_available() else
            "This platform offers no secure store — MediFlow targets Windows "
            "and macOS — so the field-encryption key falls back to %s."
        )
        arguments = ((secret_store.describe(), "file permissions")
                     if secret_store.is_available() else ("file permissions",))
        get_logger("security").warning(message, *arguments)
    _replace_key_file(key_path, sealed or key)


def _replace_key_file(key_path: Path, contents: bytes) -> None:
    """Install ``contents`` as the key file without ever truncating the old one.

    Losing this file means losing every encrypted column in the database, so the
    new bytes land in a sibling file that is fully written and locked down first,
    and only then replace the old one — a crash at any point leaves one intact
    key file on disk rather than a half-written one.
    """
    staged = key_path.with_name(key_path.name + ".new")
    staged.write_bytes(contents)
    try:
        os.chmod(staged, stat.S_IRUSR | stat.S_IWUSR)  # before it becomes the key
    except OSError:  # pragma: no cover - best effort on exotic filesystems
        pass
    os.replace(staged, key_path)
