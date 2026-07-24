"""The signed-in Windows account, as a stable identity MediFlow can trust.

Why this exists
---------------
Windows has already authenticated whoever is sitting at the machine. MediFlow's
data lives in that account's ``%APPDATA%`` and its field-encryption key is
sealed with DPAPI to that same account (see :mod:`mediflow.core.dpapi`), so the
Windows login is *already* the real security boundary for this deployment.
Layering a second password on top has, in practice, only produced lockouts.

This module exposes the current account's SID so a MediFlow user row can be
bound to it and signed in without a password.

Why the SID and not the username
--------------------------------
A SID (``S-1-5-21-…-1001``) is the account's permanent identifier. It survives
a Windows password change, a reboot, renaming the user, and renaming the
machine — all of which change the *username* string. It is issued by the local
authority and cannot be chosen by another local account, so it is not spoofable
by an unprivileged process on the same machine.

Implementation note
-------------------
``ctypes`` against advapi32 only — no third-party dependency and nothing that
needs a build step, so it survives PyInstaller freezing unchanged. Every
function degrades to ``None``/``False`` off Windows so tests and any non-Windows
tooling keep working.
"""
from __future__ import annotations

import os

_IS_WINDOWS = os.name == "nt"

if _IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _TOKEN_QUERY = 0x0008
    _TOKEN_USER_CLASS = 1  # TOKEN_INFORMATION_CLASS.TokenUser

    class _SID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]

    class _TOKEN_USER(ctypes.Structure):
        _fields_ = [("User", _SID_AND_ATTRIBUTES)]

    # Explicit signatures: without these ctypes assumes 32-bit ints for the
    # pointer-sized handles, which silently truncates them on 64-bit Windows.
    _kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.LocalFree.argtypes = [wintypes.HGLOBAL]
    _kernel32.LocalFree.restype = wintypes.HGLOBAL
    _advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    _advapi32.OpenProcessToken.restype = wintypes.BOOL
    _advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD)]
    _advapi32.GetTokenInformation.restype = wintypes.BOOL
    _advapi32.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    _advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL


def current_user_sid() -> str | None:
    """Return the current Windows account's SID, or ``None`` if unavailable.

    Reads the *process* token rather than the thread token: MediFlow never
    impersonates, and the process token is the account that launched the app.
    """
    if not _IS_WINDOWS:
        return None
    token = wintypes.HANDLE()
    if not _advapi32.OpenProcessToken(
        _kernel32.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)
    ):
        return None
    try:
        size = wintypes.DWORD(0)
        # First call fails with ERROR_INSUFFICIENT_BUFFER purely to size the
        # buffer; only the second call's result is meaningful.
        _advapi32.GetTokenInformation(token, _TOKEN_USER_CLASS, None, 0,
                                      ctypes.byref(size))
        if not size.value:
            return None
        buffer = ctypes.create_string_buffer(size.value)
        if not _advapi32.GetTokenInformation(token, _TOKEN_USER_CLASS, buffer,
                                             size, ctypes.byref(size)):
            return None
        token_user = ctypes.cast(buffer, ctypes.POINTER(_TOKEN_USER)).contents
        text = wintypes.LPWSTR()
        if not _advapi32.ConvertSidToStringSidW(token_user.User.Sid,
                                                ctypes.byref(text)):
            return None
        try:
            return text.value
        finally:
            _kernel32.LocalFree(text)          # the API allocated this for us
    finally:
        _kernel32.CloseHandle(token)


def current_account_name() -> str:
    """A human label for the Windows account, for display and audit messages."""
    user = os.environ.get("USERNAME", "")
    domain = os.environ.get("USERDOMAIN", "")
    if user and domain:
        return f"{domain}\\{user}"
    return user or "unknown"


def is_available() -> bool:
    """True when a Windows identity can actually be read on this platform."""
    return _IS_WINDOWS and current_user_sid() is not None
