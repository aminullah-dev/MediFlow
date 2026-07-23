"""Domain-level exception hierarchy.

Services raise these; the UI layer catches ``MediFlowError`` subclasses and maps
them to translated, user-facing messages. Never surface raw SQLAlchemy or OS
errors to the end user.
"""
from __future__ import annotations


class MediFlowError(Exception):
    """Base class for all expected, handled application errors."""

    # A stable message key resolved through the translation layer.
    message_key: str = "error.generic"

    def __init__(self, message: str | None = None, *, message_key: str | None = None):
        super().__init__(message or self.message_key)
        if message_key:
            self.message_key = message_key


class ValidationError(MediFlowError):
    message_key = "error.validation"

    def __init__(self, message: str | None = None, *, field: str | None = None,
                 message_key: str | None = None):
        super().__init__(message, message_key=message_key)
        self.field = field


class NotFoundError(MediFlowError):
    message_key = "error.not_found"


class DuplicateError(MediFlowError):
    message_key = "error.duplicate"


class AuthenticationError(MediFlowError):
    message_key = "error.authentication"

    def __init__(self, message: str | None = None, *, message_key: str | None = None,
                 attempts_remaining: int | None = None):
        super().__init__(message, message_key=message_key)
        # How many tries are left before the account locks (None when unknown).
        self.attempts_remaining = attempts_remaining


class PermissionDeniedError(MediFlowError):
    message_key = "error.permission_denied"


class AccountLockedError(AuthenticationError):
    message_key = "error.account_locked"

    def __init__(self, message: str | None = None, *, retry_after_seconds: int | None = None):
        super().__init__(message, message_key=self.message_key)
        # Seconds until the lock lifts, so the UI can show a live countdown.
        self.retry_after_seconds = retry_after_seconds


class BusinessRuleError(MediFlowError):
    """A domain invariant was violated (e.g. selling more stock than on hand)."""

    message_key = "error.business_rule"


class BackupError(MediFlowError):
    message_key = "error.backup"
