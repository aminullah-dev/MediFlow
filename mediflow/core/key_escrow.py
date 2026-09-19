"""Carry the field-encryption key with a backup, without the backup becoming it.

The problem
-----------
:mod:`mediflow.core.secret_store` seals the key to *this machine* — DPAPI on
Windows, the Keychain on macOS. That is what makes a stolen data folder
worthless, and it is also why a backup restored on a different machine cannot
read a single encrypted column: the new install generates its own key and the
old one never left the old Mac.

Why not simply put the key in the backup
----------------------------------------
Because then the backup *is* the breach. A USB stick holding the database and
the key beside it hands over every patient's Tazkira to whoever picks it up —
strictly worse than a backup nobody can restore. The protection has to survive
leaving the building, and nothing bound to a machine can do that.

So the key travels wrapped with a key derived from a passphrase the operator
types. The backup stays portable and a lost backup stays unreadable.

Format
------
A small text envelope, versioned, so a file found in three years can still say
what it is::

    MEDIFLOW-KEY-1
    kdf=pbkdf2_sha256
    rounds=<n>
    salt=<base64>
    key=<fernet token>

Deliberately not binary: an operator looking at a mystery file beside their
backup should be able to see what it belongs to. Nothing secret is readable —
the token is the only payload, and it is useless without the passphrase.

Passphrase policy
-----------------
Twelve characters minimum, longer than the eight :mod:`mediflow.core.security`
requires for a login. The difference is deliberate and not an inconsistency: a
login is guarded by a five-minute lockout after ten attempts on one machine,
while this guards a file that can be copied and attacked offline, forever, on
hardware of the attacker's choosing.
"""
from __future__ import annotations

import base64
import hashlib
import secrets

from mediflow.core.exceptions import BackupError

MIN_PASSPHRASE_LENGTH = 12

_MAGIC = "MEDIFLOW-KEY-1"
_KDF = "pbkdf2_sha256"
_ROUNDS = 390_000          # matches security.py's password hashing
_SALT_BYTES = 16


def wrap(key: bytes, passphrase: str) -> str:
    """Wrap ``key`` for transport beside a backup. Returns the file's contents."""
    _check_passphrase(passphrase)
    salt = secrets.token_bytes(_SALT_BYTES)
    token = _fernet(passphrase, salt, _ROUNDS).encrypt(key).decode("ascii")
    return (
        f"{_MAGIC}\n"
        f"kdf={_KDF}\n"
        f"rounds={_ROUNDS}\n"
        f"salt={base64.b64encode(salt).decode('ascii')}\n"
        f"key={token}\n"
    )


def unwrap(envelope: str, passphrase: str) -> bytes:
    """Recover the key from an envelope. Raises :class:`BackupError` on failure.

    Every failure says which of the two it is — a file that is not an envelope,
    or the wrong passphrase. Collapsing them into one message would leave an
    operator retyping a passphrase against a file that was never going to open.
    """
    from cryptography.fernet import InvalidToken

    fields = _parse(envelope)
    try:
        salt = base64.b64decode(fields["salt"])
        rounds = int(fields["rounds"])
        token = fields["key"].encode("ascii")
    except (KeyError, ValueError) as exc:
        raise BackupError("The key file is incomplete or damaged.") from exc
    if fields.get("kdf") != _KDF:
        raise BackupError(f"Unsupported key file (kdf={fields.get('kdf')!r}).")
    try:
        return _fernet(passphrase, salt, rounds).decrypt(token)
    except (InvalidToken, ValueError) as exc:
        raise BackupError(
            "Wrong passphrase for this backup's key file, or the file has been "
            "altered. The passphrase is the one typed when the backup was made; "
            "it is not recorded anywhere and cannot be recovered."
        ) from exc


def looks_like_envelope(text: str) -> bool:
    """True when ``text`` is one of these files, without needing a passphrase."""
    return text.lstrip().startswith(_MAGIC)


def _check_passphrase(passphrase: str) -> None:
    if not passphrase or len(passphrase) < MIN_PASSPHRASE_LENGTH:
        raise BackupError(
            f"The backup passphrase must be at least {MIN_PASSPHRASE_LENGTH} "
            "characters. It protects a file that can leave the clinic, where "
            "nothing limits how many guesses an attacker gets."
        )


def _parse(envelope: str) -> dict[str, str]:
    lines = envelope.strip().splitlines()
    if not lines or lines[0].strip() != _MAGIC:
        raise BackupError("This file is not a MediFlow backup key file.")
    fields: dict[str, str] = {}
    for line in lines[1:]:
        name, separator, value = line.partition("=")
        if separator:
            fields[name.strip()] = value.strip()
    return fields


def _fernet(passphrase: str, salt: bytes, rounds: int):
    from cryptography.fernet import Fernet

    derived = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt,
                                  rounds, dklen=32)
    return Fernet(base64.urlsafe_b64encode(derived))
