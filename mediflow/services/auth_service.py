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

from mediflow.core.exceptions import (
    AccountLockedError,
    AuthenticationError,
    ValidationError,
)
from mediflow.data.base import utcnow
from mediflow.core.logging_config import get_logger
from mediflow.core.security import (
    MIN_PASSWORD_LENGTH,
    hash_password,
    needs_rehash,
    verify_password,
)
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
            elif not verify_password(password, user.password_hash):
                error = self._register_failure(session, user, username, now)
            else:
                user.failed_login_count = 0
                user.locked_until = None
                user.last_login_at = utcnow()
                if needs_rehash(user.password_hash):
                    user.password_hash = hash_password(password)
                snapshot = AuthenticatedUser(
                    id=user.id,
                    username=user.username,
                    full_name=user.full_name,
                    permissions=frozenset(user.all_permission_codes()),
                    must_change_password=user.must_change_password,
                )
                self._record_login(session, user.id, username, True, None)

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
            if not verify_password(current, user.password_hash):
                raise AuthenticationError("Current password is incorrect.")
            user.password_hash = hash_password(new)
            user.must_change_password = False
            user.password_changed_at = utcnow()

    def logout(self) -> None:
        current_user_id.set(None)
        current_permissions.set(frozenset())

    # -- internals ----------------------------------------------------------
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
