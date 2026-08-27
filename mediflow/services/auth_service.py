"""Authentication and session security.

Enforces:
* Credential verification with constant-time hash comparison (passlib).
* Progressive account lockout after repeated failures.
* Transparent password-hash upgrades when parameters change.
* Full login-history recording (success and failure) for the audit module.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import NamedTuple

from mediflow.core.exceptions import (
    AccountLockedError,
    AuthenticationError,
    ValidationError,
)
from mediflow.core.keyboard import from_persian_layout, has_persian_layout_chars
from mediflow.core.logging_config import get_logger
from mediflow.core.security import (
    MIN_PASSWORD_LENGTH,
    hash_password,
    needs_rehash,
    verify_password,
)
from mediflow.data.base import utcnow
from mediflow.data.database import Database, current_permissions, current_user_id
from mediflow.data.models.user import LoginHistory, User
from mediflow.data.repositories.user_repository import UserRepository

log = get_logger("services.auth")

# Offline single-machine deployment: brute-force risk is low (an attacker with
# the machine has bigger levers), while a harsh lockout mostly punishes a
# legitimate operator fat-fingering a password. Keep a lock, but a forgiving one
# — and the UI now shows the remaining attempts and a live unlock countdown.
MAX_FAILED_ATTEMPTS = 10
LOCKOUT_MINUTES = 5


class _Match(NamedTuple):
    """Result of checking a submitted password against a stored hash."""

    matched: bool
    recovered: bool     # True when only the layout-corrected form matched
    effective: str = ""  # the exact string that verified — never the raw input
    #                      when recovery kicked in, so a transparent rehash can
    #                      never re-store an unenterable Persian password.


@dataclass(slots=True)
class AuthenticatedUser:
    """Lightweight, detached snapshot handed to the UI after login."""

    id: int
    username: str
    full_name: str
    permissions: frozenset[str]
    must_change_password: bool

    def can(self, permission_code: str) -> bool:
        return permission_code in self.permissions


class AuthService:
    def __init__(self, db: Database):
        self._db = db

    def authenticate(self, username: str, password: str) -> AuthenticatedUser:
        """Verify credentials.

        Bookkeeping (failure counters, lockout, login history) is committed
        inside the unit of work; the failure exception is raised *afterwards* so
        the rollback-on-error semantics of the transaction never discard the
        security state we just recorded.
        """
        username = (username or "").strip()
        error: AuthenticationError | None = None
        snapshot: AuthenticatedUser | None = None

        with self._db.unit_of_work() as session:
            repo = UserRepository(session)
            user = repo.get_by_username(username)
            if user is None and has_persian_layout_chars(username):
                # Same layout slip as the password, but on the username: "admin"
                # typed under the Persian layout arrives as "شیئهد". Retry the
                # lookup with the corrected reading and adopt it, so the login
                # history records the real account rather than the mojibake.
                corrected = from_persian_layout(username)
                if corrected != username:
                    user = repo.get_by_username(corrected)
                    if user is not None:
                        username = corrected
            now = utcnow()  # one snapshot for every time comparison below

            # A lock whose window has elapsed is cleared here, so the user gets
            # a fresh set of attempts instead of being re-locked by the very
            # next wrong password (failed_login_count was still at the max).
            if user is not None and user.locked_until and user.locked_until <= now:
                user.failed_login_count = 0
                user.locked_until = None

            if user is None:
                self._record_login(session, None, username, False, "unknown_user")
                error = AuthenticationError("Invalid username or password.")
            elif user.locked_until and user.locked_until > now:
                self._record_login(session, user.id, username, False, "locked")
                retry = int((user.locked_until - now).total_seconds())
                error = AccountLockedError(retry_after_seconds=max(retry, 0))
            elif not user.is_active:
                self._record_login(session, user.id, username, False, "inactive")
                error = AuthenticationError("Account is disabled.")
            elif not (match := self._match_password(password, user.password_hash)).matched:
                error = self._register_failure(session, user, username, now)
            else:
                user.failed_login_count = 0
                user.locked_until = None
                user.last_login_at = utcnow()
                if needs_rehash(user.password_hash):
                    # match.effective, NOT the raw input: after a layout
                    # recovery the raw input is the Persian rendering, and
                    # re-storing that would lock the account out for good.
                    user.password_hash = hash_password(match.effective)
                snapshot = AuthenticatedUser(
                    id=user.id,
                    username=user.username,
                    full_name=user.full_name,
                    permissions=frozenset(user.all_permission_codes()),
                    must_change_password=user.must_change_password,
                )
                if match.recovered:
                    log.info("Password for '%s' matched only after correcting for "
                             "the Persian keyboard layout.", username)
                self._record_login(session, user.id, username, True,
                                   "layout_recovered" if match.recovered else None)

        if error is not None:
            raise error

        assert snapshot is not None
        # Bind identity + permissions for attributed writes and authorization.
        current_user_id.set(snapshot.id)
        current_permissions.set(snapshot.permissions)
        log.info("User '%s' authenticated.", snapshot.username)
        return snapshot

    def change_password(self, user_id: int, current: str, new: str) -> None:
        if len(new) < MIN_PASSWORD_LENGTH:
            raise ValidationError(
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
                field="new_password",
            )
        with self._db.unit_of_work() as session:
            user = UserRepository(session).get_or_raise(user_id)
            if not self._match_password(current, user.password_hash).matched:
                raise AuthenticationError("Current password is incorrect.")
            user.password_hash = hash_password(new)
            user.must_change_password = False
            user.password_changed_at = utcnow()

    def load_session_user(self, user_id: int) -> AuthenticatedUser | None:
        """Rebuild the signed-in snapshot for an already-authenticated id.

        The web layer calls this on every request instead of trusting whatever
        the session cookie carries, so revoking a role or deactivating an
        account takes effect on the very next page load rather than at the
        user's next sign-in. Returns ``None`` for unknown or disabled accounts.
        """
        with self._db.unit_of_work() as session:
            user = session.get(User, user_id)
            if user is None or user.is_deleted or not user.is_active:
                return None
            return AuthenticatedUser(
                id=user.id,
                username=user.username,
                full_name=user.full_name,
                permissions=frozenset(user.all_permission_codes()),
                must_change_password=user.must_change_password,
            )

    def logout(self) -> None:
        current_user_id.set(None)
        current_permissions.set(frozenset())

    # -- internals ----------------------------------------------------------
    @staticmethod
    def _match_password(password: str, password_hash: str) -> _Match:
        """Verify ``password``, forgiving a wrong-keyboard-layout slip.

        Clinic machines carry both a US and a Persian Windows layout. With the
        Persian one active the operator types ``Amin2026`` but the masked field
        receives ``َئهد2026`` — indistinguishable, to them, from a correct
        entry. So a failed check is retried once against the layout-corrected
        reading of the very same keystrokes.

        This is not a security relaxation: the retry tests one specific
        alternate *rendering* of the keys already pressed, not an additional
        guess. ASCII-only input is never rewritten, so a correctly typed
        password takes exactly one comparison.
        """
        if verify_password(password, password_hash):
            return _Match(True, False, password)
        if has_persian_layout_chars(password):
            corrected = from_persian_layout(password)
            if corrected != password and verify_password(corrected, password_hash):
                return _Match(True, True, corrected)
        return _Match(False, False, "")

    def _register_failure(self, session, user: User, username, now) -> AuthenticationError:
        """Record a bad password and return the error the caller should raise.

        A failure that trips the threshold locks the account and yields an
        :class:`AccountLockedError` carrying the retry window; otherwise the
        generic error carries how many attempts remain, so the UI can warn the
        operator *before* the next mistake locks them out.
        """
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_FAILED_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            log.warning("Account '%s' locked after %d failures.", username,
                        user.failed_login_count)
            self._record_login(session, user.id, username, False, "locked_out")
            return AccountLockedError(retry_after_seconds=LOCKOUT_MINUTES * 60)
        self._record_login(session, user.id, username, False, "bad_password")
        remaining = MAX_FAILED_ATTEMPTS - user.failed_login_count
        return AuthenticationError(
            "Invalid username or password.", attempts_remaining=remaining
        )

    @staticmethod
    def _record_login(session, user_id, username, success, reason) -> None:
        session.add(
            LoginHistory(
                user_id=user_id,
                username_attempted=username,
                success=success,
                reason=reason,
            )
        )
