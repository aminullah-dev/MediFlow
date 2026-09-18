"""macOS Keychain wrapper (via ctypes — no external dependency).

Why this exists
---------------
On Windows MediFlow seals its field-encryption key with DPAPI, so the file on
disk is useless to any other account or machine. macOS offers the same
guarantee through the login Keychain, and this module reaches it the way
:mod:`mediflow.core.dpapi` reaches crypt32: ctypes against a system framework.
Nothing to build, no third-party package, and it survives PyInstaller freezing
unchanged — which matters, because the shipped app is a frozen bundle.

What actually goes into the Keychain
------------------------------------
One generic-password item (service ``MediFlow``) holding a random *wrapping
key* — never the secret itself. The secret stays in the data folder, encrypted
with that wrapping key. Two reasons: the Keychain holds a single fixed-size
item no matter how many secrets the app protects, and the on-disk shape stays
identical to the DPAPI one, so :mod:`mediflow.core.secret_store` can treat both
backends alike. The wrap itself lives there, not here.

Why Security.framework and not the ``security`` CLI
---------------------------------------------------
``security add-generic-password -w <secret>`` puts the secret in the process
argument list, where ``ps`` shows it to every other account on the machine.
A clinic Mac with a second staff login is exactly the case this protection
exists for, so the leak is not acceptable.

A note on prompts
-----------------
Keychain ACLs are bound to the calling binary. An unsigned or re-signed
MediFlow.app is a *different* binary as far as macOS is concerned, so the first
launch after an update can raise the "MediFlow wants to use your confidential
information" dialog. Choosing "Always Allow" settles it for that build; the key
is not lost, and declining only drops the app back to file-permission
protection.

Every function returns ``None``/``False`` off macOS, so tests and non-macOS
tooling keep working.
"""
from __future__ import annotations

import ctypes
import sys

SERVICE = "MediFlow"
ACCOUNT = "field-encryption-wrapping-key"

_ERR_SEC_SUCCESS = 0

_K_CF_STRING_ENCODING_UTF8 = 0x08000100

_AVAILABLE = sys.platform == "darwin"


if _AVAILABLE:
    try:
        _cf = ctypes.CDLL(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        _sec = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
    except OSError:  # pragma: no cover - a macOS without Security.framework
        _AVAILABLE = False


if _AVAILABLE:
    _ref = ctypes.c_void_p        # CFTypeRef
    _index = ctypes.c_long        # CFIndex
    _status = ctypes.c_int32      # OSStatus

    # Explicit signatures throughout: ctypes otherwise assumes 32-bit ints for
    # pointer-sized values, which silently truncates every CF object handle.
    _cf.CFRelease.argtypes = [_ref]
    _cf.CFRelease.restype = None
    _cf.CFStringCreateWithCString.argtypes = [_ref, ctypes.c_char_p, ctypes.c_uint32]
    _cf.CFStringCreateWithCString.restype = _ref
    _cf.CFDataCreate.argtypes = [_ref, ctypes.c_char_p, _index]
    _cf.CFDataCreate.restype = _ref
    _cf.CFDataGetBytePtr.argtypes = [_ref]
    _cf.CFDataGetBytePtr.restype = ctypes.POINTER(ctypes.c_char)
    _cf.CFDataGetLength.argtypes = [_ref]
    _cf.CFDataGetLength.restype = _index
    _cf.CFDictionaryCreateMutable.argtypes = [_ref, _index, ctypes.c_void_p,
                                              ctypes.c_void_p]
    _cf.CFDictionaryCreateMutable.restype = _ref
    _cf.CFDictionarySetValue.argtypes = [_ref, _ref, _ref]
    _cf.CFDictionarySetValue.restype = None

    _sec.SecItemAdd.argtypes = [_ref, ctypes.POINTER(_ref)]
    _sec.SecItemAdd.restype = _status
    _sec.SecItemCopyMatching.argtypes = [_ref, ctypes.POINTER(_ref)]
    _sec.SecItemCopyMatching.restype = _status
    _sec.SecItemDelete.argtypes = [_ref]
    _sec.SecItemDelete.restype = _status

    # The dictionary callback tables are exported as structs, not pointers, so
    # the address of the symbol is what CFDictionaryCreateMutable wants.
    _KEY_CALLBACKS = ctypes.byref(
        ctypes.c_void_p.in_dll(_cf, "kCFTypeDictionaryKeyCallBacks"))
    _VALUE_CALLBACKS = ctypes.byref(
        ctypes.c_void_p.in_dll(_cf, "kCFTypeDictionaryValueCallBacks"))

    def _const(library, name: str) -> ctypes.c_void_p:
        return ctypes.c_void_p.in_dll(library, name)

    _TRUE = _const(_cf, "kCFBooleanTrue")
    _CLASS = _const(_sec, "kSecClass")
    _GENERIC_PASSWORD = _const(_sec, "kSecClassGenericPassword")
    _ATTR_SERVICE = _const(_sec, "kSecAttrService")
    _ATTR_ACCOUNT = _const(_sec, "kSecAttrAccount")
    _VALUE_DATA = _const(_sec, "kSecValueData")
    _RETURN_DATA = _const(_sec, "kSecReturnData")
    _MATCH_LIMIT = _const(_sec, "kSecMatchLimit")
    _MATCH_LIMIT_ONE = _const(_sec, "kSecMatchLimitOne")


class _Pool:
    """Collects CoreFoundation objects so every branch releases them once.

    CF uses manual reference counting and these functions have several early
    returns; tracking the objects in one place is what keeps a failed Keychain
    read from leaking a handle on every attempt.
    """

    def __init__(self) -> None:
        self._refs: list[ctypes.c_void_p] = []

    def keep(self, ref):
        if ref:
            self._refs.append(ref)
        return ref

    def __enter__(self) -> _Pool:
        return self

    def __exit__(self, *_exc_info) -> bool:
        for ref in reversed(self._refs):
            _cf.CFRelease(ref)
        self._refs.clear()
        return False


def _string(pool: _Pool, text: str):
    return pool.keep(_cf.CFStringCreateWithCString(
        None, text.encode("utf-8"), _K_CF_STRING_ENCODING_UTF8))


def _item_query(pool: _Pool, account: str):
    """The service/account pair identifying MediFlow's one Keychain item."""
    query = pool.keep(_cf.CFDictionaryCreateMutable(
        None, 0, _KEY_CALLBACKS, _VALUE_CALLBACKS))
    if not query:
        return None
    _cf.CFDictionarySetValue(query, _CLASS, _GENERIC_PASSWORD)
    _cf.CFDictionarySetValue(query, _ATTR_SERVICE, _string(pool, SERVICE))
    _cf.CFDictionarySetValue(query, _ATTR_ACCOUNT, _string(pool, account))
    return query


def get_secret(account: str = ACCOUNT) -> bytes | None:
    """Read the stored wrapping key, or ``None`` if absent or unreadable."""
    if not _AVAILABLE:
        return None
    try:
        with _Pool() as pool:
            query = _item_query(pool, account)
            if not query:
                return None
            _cf.CFDictionarySetValue(query, _RETURN_DATA, _TRUE)
            _cf.CFDictionarySetValue(query, _MATCH_LIMIT, _MATCH_LIMIT_ONE)
            found = ctypes.c_void_p()
            if _sec.SecItemCopyMatching(query, ctypes.byref(found)) != _ERR_SEC_SUCCESS:
                return None
            if not found.value:
                return None
            pool.keep(found)          # SecItemCopyMatching returns it retained
            length = _cf.CFDataGetLength(found)
            pointer = _cf.CFDataGetBytePtr(found)
            if length <= 0 or not pointer:
                return None
            return ctypes.string_at(pointer, length)
    except OSError:  # pragma: no cover
        return None


def set_secret(raw: bytes, account: str = ACCOUNT) -> bool:
    """Store ``raw`` as a new Keychain item. False if one already exists.

    An existing item is never overwritten. If it cannot be read (a denied ACL
    after an app update, say), replacing it would destroy the only means of
    decrypting data already on disk — whereas leaving it alone lets the user
    grant access on the next launch and recover.
    """
    if not _AVAILABLE:
        return False
    try:
        with _Pool() as pool:
            attributes = _item_query(pool, account)
            if not attributes:
                return False
            _cf.CFDictionarySetValue(
                attributes, _VALUE_DATA,
                pool.keep(_cf.CFDataCreate(None, raw, len(raw))))
            return _sec.SecItemAdd(attributes, None) == _ERR_SEC_SUCCESS
    except OSError:  # pragma: no cover
        return False


def delete_secret(account: str = ACCOUNT) -> bool:
    """Remove the Keychain item. Used by the tests; not by the application."""
    if not _AVAILABLE:
        return False
    try:
        with _Pool() as pool:
            query = _item_query(pool, account)
            if not query:
                return False
            return _sec.SecItemDelete(query) == _ERR_SEC_SUCCESS
    except OSError:  # pragma: no cover
        return False


def is_available() -> bool:
    """True when the Keychain API can be reached on this platform."""
    return _AVAILABLE
