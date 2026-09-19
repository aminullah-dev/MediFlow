"""At-rest protection of MediFlow's own secrets, across both target platforms.

MediFlow ships for Windows and macOS. Each seals the field-encryption key with
a different OS facility, and the file on disk says which — so these tests cover
the dispatch and the migrations, not just a happy-path round trip:

* an unsealed legacy key file is upgraded in place, without ever losing the key;
* a key file from the *other* platform fails with a sentence an operator can act
  on, rather than a decryption error;
* a machine with no secure store still runs, but never quietly — the fallback
  is logged.

The real OS backend is exercised too, but only when
``MEDIFLOW_TEST_OS_KEYCHAIN=1`` is set (CI does, on macOS). A test run must not
write into a developer's login Keychain just because they ran ``pytest``.
"""
from __future__ import annotations

import logging
import os

import pytest
from cryptography.fernet import Fernet

from mediflow.core import dpapi, macos_keychain, secret_store
from mediflow.core.exceptions import MediFlowError
from mediflow.core.security import FieldCipher, _load_or_create_key, _write_key

WINDOWS_MAGIC = b"DPAPI1\n"
MACOS_MAGIC = b"KEYCHAIN1\n"


@pytest.fixture()
def fake_keychain(monkeypatch):
    """Drive the macOS backend's real crypto over an in-memory Keychain.

    The wrapping-key logic, the Fernet wrap and the on-disk header are all the
    production ones; only the ``SecItem*`` calls are replaced. That lets the
    macOS path be tested on every platform CI runs on.
    """
    items: dict[str, bytes] = {}

    def get_secret(account: str = macos_keychain.ACCOUNT) -> bytes | None:
        return items.get(account)

    def set_secret(raw: bytes, account: str = macos_keychain.ACCOUNT) -> bool:
        if account in items:       # matches the real "never overwrite" rule
            return False
        items[account] = raw
        return True

    monkeypatch.setattr(macos_keychain, "get_secret", get_secret)
    monkeypatch.setattr(macos_keychain, "set_secret", set_secret)
    monkeypatch.setattr(macos_keychain, "is_available", lambda: True)
    monkeypatch.setattr(dpapi, "is_available", lambda: False)
    return items


@pytest.fixture()
def no_backend(monkeypatch):
    """A machine whose secure store cannot be reached."""
    monkeypatch.setattr(dpapi, "is_available", lambda: False)
    monkeypatch.setattr(macos_keychain, "is_available", lambda: False)


def test_backend_reports_none_when_no_store_is_reachable(no_backend):
    assert secret_store.backend() == secret_store.NONE
    assert not secret_store.is_available()
    assert secret_store.protect(b"anything") is None


def test_is_protected_only_recognises_known_headers():
    assert secret_store.is_protected(WINDOWS_MAGIC + b"payload")
    assert secret_store.is_protected(MACOS_MAGIC + b"payload")
    assert not secret_store.is_protected(Fernet.generate_key())


def test_keychain_round_trip_and_header(fake_keychain):
    sealed = secret_store.protect(b"the-field-key")

    assert sealed is not None
    assert sealed.startswith(MACOS_MAGIC)
    assert b"the-field-key" not in sealed          # actually encrypted, not wrapped
    assert secret_store.unprotect(sealed) == b"the-field-key"


def test_keychain_reuses_one_wrapping_key(fake_keychain):
    secret_store.protect(b"first")
    secret_store.protect(b"second")

    assert list(fake_keychain) == [macos_keychain.ACCOUNT]


def test_unprotect_fails_rather_than_guesses_when_the_keychain_item_is_gone(
        fake_keychain):
    sealed = secret_store.protect(b"the-field-key")
    fake_keychain.clear()

    assert secret_store.unprotect(sealed) is None


def test_unprotect_ignores_a_blob_with_no_header(fake_keychain):
    assert secret_store.unprotect(b"a bare key with no header") is None


def test_key_file_is_created_sealed_and_reloads(tmp_path, fake_keychain):
    key_path = tmp_path / ".secret_key"

    key = _load_or_create_key(key_path)

    assert key_path.read_bytes().startswith(MACOS_MAGIC)
    assert _load_or_create_key(key_path) == key


def test_legacy_plaintext_key_is_sealed_in_place_without_changing_it(
        tmp_path, fake_keychain):
    key_path = tmp_path / ".secret_key"
    legacy = Fernet.generate_key()
    key_path.write_bytes(legacy)

    assert _load_or_create_key(key_path) == legacy      # data stays readable
    assert key_path.read_bytes().startswith(MACOS_MAGIC)
    assert _load_or_create_key(key_path) == legacy      # and again, once sealed


def test_legacy_plaintext_key_is_left_alone_when_nothing_can_seal_it(
        tmp_path, no_backend):
    key_path = tmp_path / ".secret_key"
    legacy = Fernet.generate_key()
    key_path.write_bytes(legacy)

    assert _load_or_create_key(key_path) == legacy
    assert key_path.read_bytes() == legacy             # not rewritten every boot


def test_unsealable_key_file_raises_an_actionable_error(tmp_path, fake_keychain):
    key_path = tmp_path / ".secret_key"
    _load_or_create_key(key_path)
    fake_keychain.clear()                              # e.g. a restored-from-backup Mac

    with pytest.raises(MediFlowError) as raised:
        _load_or_create_key(key_path)
    assert "Keychain" in str(raised.value)


def test_a_key_file_from_the_other_platform_says_so(tmp_path, fake_keychain):
    key_path = tmp_path / ".secret_key"
    key_path.write_bytes(WINDOWS_MAGIC + b"sealed-on-a-windows-pc")

    with pytest.raises(MediFlowError) as raised:
        _load_or_create_key(key_path)
    message = str(raised.value)
    assert "Windows DPAPI" in message and "macOS Keychain" in message


def test_writing_an_unsealed_key_is_never_silent(tmp_path, no_backend, caplog):
    key_path = tmp_path / ".secret_key"

    with caplog.at_level(logging.WARNING):
        _write_key(key_path, Fernet.generate_key())

    assert any("file permissions" in record.getMessage() for record in caplog.records)


def test_key_replacement_leaves_no_half_written_file(tmp_path, fake_keychain):
    key_path = tmp_path / ".secret_key"
    _load_or_create_key(key_path)

    assert [path.name for path in tmp_path.iterdir()] == [".secret_key"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes only")
def test_key_file_is_owner_only(tmp_path, fake_keychain):
    key_path = tmp_path / ".secret_key"
    _load_or_create_key(key_path)

    assert key_path.stat().st_mode & 0o777 == 0o600


def test_field_cipher_round_trips_through_the_sealed_key_file(tmp_path, fake_keychain):
    key_path = tmp_path / ".secret_key"
    token = FieldCipher.from_key_file(key_path).encrypt("1402-1234567")

    assert FieldCipher.from_key_file(key_path).decrypt(token) == "1402-1234567"


@pytest.mark.skipif(
    os.environ.get("MEDIFLOW_TEST_OS_KEYCHAIN") != "1",
    reason="opt-in: writes to the real OS secure store",
)
def test_real_os_backend_round_trips():
    """The genuine platform backend — DPAPI or the Keychain, whichever is here."""
    if not secret_store.is_available():
        pytest.skip(f"no secure store on this platform ({secret_store.describe()})")

    sealed = secret_store.protect(b"a-real-secret")

    assert sealed is not None, f"{secret_store.describe()} refused to seal"
    assert secret_store.unprotect(sealed) == b"a-real-secret"


@pytest.mark.skipif(
    os.environ.get("MEDIFLOW_TEST_OS_KEYCHAIN") != "1"
    or not macos_keychain.is_available(),
    reason="opt-in, macOS only: writes to the real login Keychain",
)
def test_real_keychain_item_lifecycle():
    """Add / read / delete against Security.framework, under a test account."""
    account = f"mediflow-test-{os.getpid()}"
    macos_keychain.delete_secret(account)              # from an interrupted run
    try:
        assert macos_keychain.get_secret(account) is None
        assert macos_keychain.set_secret(b"secret-bytes", account)
        assert macos_keychain.get_secret(account) == b"secret-bytes"
        assert not macos_keychain.set_secret(b"other", account)   # never overwrites
        assert macos_keychain.get_secret(account) == b"secret-bytes"
    finally:
        assert macos_keychain.delete_secret(account)


# ── The web session key ───────────────────────────────────────────────────────
# Same sealing, deliberately different failure policy: losing this one costs a
# round of sign-ins, so it is reissued rather than raised on.

def _session_config(tmp_path):
    from mediflow.core.config import Config

    return Config.bootstrap(tmp_path)


def test_session_key_is_sealed_and_stable_across_restarts(tmp_path, fake_keychain):
    pytest.importorskip("fastapi", reason="web extras not installed")
    from mediflow.web.server import _session_secret

    config = _session_config(tmp_path)
    key = _session_secret(config)

    assert (tmp_path / ".session_key").read_bytes().startswith(MACOS_MAGIC)
    assert _session_secret(config) == key      # a restart must not sign anyone out


def test_legacy_plaintext_session_key_is_sealed_but_keeps_its_value(
        tmp_path, fake_keychain):
    pytest.importorskip("fastapi", reason="web extras not installed")
    from mediflow.web.server import _session_secret

    config = _session_config(tmp_path)
    (tmp_path / ".session_key").write_text("an-existing-cookie-key", encoding="utf-8")

    assert _session_secret(config) == "an-existing-cookie-key"
    assert (tmp_path / ".session_key").read_bytes().startswith(MACOS_MAGIC)


def test_unsealable_session_key_is_reissued_not_fatal(tmp_path, fake_keychain, caplog):
    pytest.importorskip("fastapi", reason="web extras not installed")
    from mediflow.web.server import _session_secret

    config = _session_config(tmp_path)
    first = _session_secret(config)
    fake_keychain.clear()

    with caplog.at_level(logging.WARNING):
        second = _session_secret(config)

    assert second != first                     # the server still starts
    assert any("sign in again" in record.getMessage() for record in caplog.records)
