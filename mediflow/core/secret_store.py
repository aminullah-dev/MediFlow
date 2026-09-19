"""One at-rest protection interface over whatever the host OS provides.

MediFlow ships for Windows and macOS, and both bind a secret to the signed-in
account without any third-party dependency:

======== ================== =========================================
Platform Backend            On-disk header
======== ================== =========================================
Windows  DPAPI              ``DPAPI1\\n``
macOS    Keychain + Fernet  ``KEYCHAIN1\\n``
other    none               no header — the raw secret, owner-only
======== ================== =========================================

Blobs are self-describing on purpose. :func:`unprotect` dispatches on the
header in the file, never on the platform running it, so a data folder carried
from a clinic's Windows PC to a Mac produces :func:`recovery_hint` — a sentence
naming what the file needs — instead of a decryption error nobody can act on.

The unprotected path is a real fallback, not a fourth backend: it exists so the
app still runs on a machine whose secure store is unreachable (a locked
Keychain, a headless CI box). It is never silent — :mod:`mediflow.core.security`
logs a warning whenever a secret is written without protection.

Why a wrapping key on macOS
---------------------------
DPAPI encrypts arbitrary bytes; the Keychain stores items. To give both the
same shape, the macOS backend keeps a random wrapping key in the Keychain and
Fernet-encrypts the payload with it. The Keychain item is fixed-size and
written once; the ciphertext lives in the data folder like the DPAPI blob does.
"""
from __future__ import annotations

from mediflow.core import dpapi, macos_keychain

DPAPI = "dpapi"
KEYCHAIN = "keychain"
NONE = "none"

_WINDOWS_MAGIC = b"DPAPI1\n"
_MACOS_MAGIC = b"KEYCHAIN1\n"

_BY_MAGIC = {_WINDOWS_MAGIC: DPAPI, _MACOS_MAGIC: KEYCHAIN}

_LABELS = {
    DPAPI: "Windows DPAPI",
    KEYCHAIN: "the macOS Keychain",
    NONE: "file permissions only",
}


def backend() -> str:
    """Which protection backend this machine offers: ``dpapi``/``keychain``/``none``."""
    if dpapi.is_available():
        return DPAPI
    if macos_keychain.is_available():
        return KEYCHAIN
    return NONE


def is_available() -> bool:
    """True when the OS offers real protection (not just file permissions)."""
    return backend() != NONE


def describe() -> str:
    """Human-readable name of this machine's backend, for logs."""
    return _LABELS[backend()]


def is_protected(blob: bytes) -> bool:
    """True when ``blob`` carries one of the known protection headers."""
    return blob.startswith(tuple(_BY_MAGIC))


def protect(data: bytes) -> bytes | None:
    """Seal ``data`` to this OS account. ``None`` when no backend can do it.

    The result carries its own header, so :func:`unprotect` needs nothing else.
    """
    active = backend()
    if active == DPAPI:
        sealed = dpapi.protect(data)
        return _WINDOWS_MAGIC + sealed if sealed else None
    if active == KEYCHAIN:
        sealed = _keychain_protect(data)
        return _MACOS_MAGIC + sealed if sealed else None
    return None


def unprotect(blob: bytes) -> bytes | None:
    """Unseal a blob produced by :func:`protect`; ``None`` when it cannot be."""
    for magic, name in _BY_MAGIC.items():
        if blob.startswith(magic):
            payload = blob[len(magic):]
            if name == DPAPI:
                return dpapi.unprotect(payload)
            return _keychain_unprotect(payload)
    return None


def recovery_hint(blob: bytes) -> str:
    """Explain, in terms an operator can act on, why a blob will not open."""
    needed = next((name for magic, name in _BY_MAGIC.items()
                   if blob.startswith(magic)), NONE)
    if needed != backend():
        return (
            f"This MediFlow data folder was protected with {_LABELS[needed]}, "
            f"but this machine offers {_LABELS[backend()]}. Open it on the "
            "computer it came from and restore from a backup taken there, or "
            "start a fresh data folder on this one."
        )
    if needed == DPAPI:
        return (
            "Cannot decrypt the field-encryption key — it was protected for a "
            "different Windows user or machine. Sign in as the Windows user who "
            "installed MediFlow, or restore the data folder from a backup taken "
            "on this machine."
        )
    return (
        "Cannot decrypt the field-encryption key — the macOS Keychain item it "
        "was sealed with is missing or access was denied. Unlock the login "
        "keychain and allow MediFlow when prompted, sign in as the macOS user "
        "who installed MediFlow, or restore the data folder from a backup taken "
        "on this Mac."
    )


def _wrapping_key() -> bytes | None:
    """The Keychain-held key the macOS backend encrypts with; created on demand."""
    from cryptography.fernet import Fernet

    existing = macos_keychain.get_secret()
    if existing is not None:
        return existing
    created = Fernet.generate_key()
    if not macos_keychain.set_secret(created):
        return None
    # Read back rather than trust the write: if the item did not really land,
    # returning the key would produce a file nothing can ever decrypt.
    stored = macos_keychain.get_secret()
    return created if stored == created else None


def _keychain_protect(data: bytes) -> bytes | None:
    from cryptography.fernet import Fernet

    key = _wrapping_key()
    if key is None:
        return None
    try:
        return Fernet(key).encrypt(data)
    except (ValueError, TypeError):  # pragma: no cover - a corrupt Keychain item
        return None


def _keychain_unprotect(payload: bytes) -> bytes | None:
    from cryptography.fernet import Fernet, InvalidToken

    key = macos_keychain.get_secret()
    if key is None:
        return None
    try:
        return Fernet(key).decrypt(payload)
    except (InvalidToken, ValueError, TypeError):
        return None
