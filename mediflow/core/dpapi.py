"""Windows DPAPI wrapper (via ctypes — no external dependency).

`CryptProtectData` / `CryptUnprotectData` encrypt data so it can only be
decrypted by the same Windows user account on the same machine. This is the
Windows backend of :mod:`mediflow.core.secret_store`; callers should go through
that module rather than importing this one directly.

Importable everywhere
---------------------
``ctypes.wintypes`` raises ``ValueError`` at *import* time off Windows, so it is
imported inside the platform guard below. That matters: MediFlow also ships for
macOS, and a module that cannot even be imported there would drag the whole
``mediflow.core`` package down with it. Every public function returns
``None``/``False`` when DPAPI is not the platform's protection backend.
"""
from __future__ import annotations

import ctypes
import os

_AVAILABLE = os.name == "nt"


if _AVAILABLE:
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))]

    try:
        _crypt32 = ctypes.windll.crypt32
        _kernel32 = ctypes.windll.kernel32
        _crypt32.CryptProtectData.restype = wintypes.BOOL
        _crypt32.CryptUnprotectData.restype = wintypes.BOOL
    except (AttributeError, OSError):  # pragma: no cover
        _AVAILABLE = False


def _run(func, data: bytes) -> bytes | None:
    buffer = ctypes.create_string_buffer(data, len(data))
    blob_in = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    blob_out = _Blob()
    ok = func(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out))
    if not ok:
        return None
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        _kernel32.LocalFree(blob_out.pbData)


def protect(data: bytes) -> bytes | None:
    """DPAPI-encrypt ``data`` for the current user; ``None`` if unavailable."""
    if not _AVAILABLE:
        return None
    try:
        return _run(_crypt32.CryptProtectData, data)
    except OSError:  # pragma: no cover
        return None


def unprotect(blob: bytes) -> bytes | None:
    """DPAPI-decrypt a blob produced by :func:`protect`; ``None`` on failure."""
    if not _AVAILABLE:
        return None
    try:
        return _run(_crypt32.CryptUnprotectData, blob)
    except OSError:  # pragma: no cover
        return None


def is_available() -> bool:
    return _AVAILABLE
