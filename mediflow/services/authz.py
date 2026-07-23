"""Service-layer authorization.

Enforces RBAC in the layer that owns the transaction, not just in the UI. The
acting user's effective permissions are published to a ContextVar on login
(:data:`mediflow.data.database.current_permissions`); these decorators check
against it and raise :class:`PermissionDeniedError` when a permission is missing.

Defense in depth: even if a UI path forgets to hide a control, or a method is
reached from a script/automation, the mutation is refused.
"""
from __future__ import annotations

from functools import wraps

from mediflow.core.exceptions import PermissionDeniedError
from mediflow.data.database import current_permissions


def require(*codes: str):
    """Require the caller to hold *all* of the given permission codes."""

    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            held = current_permissions.get()
            missing = [c for c in codes if c not in held]
            if missing:
                raise PermissionDeniedError(
                    f"You do not have permission to perform this action "
                    f"(requires {', '.join(codes)})."
                )
            return func(self, *args, **kwargs)

        return wrapper

    return decorator


def require_any(*codes: str):
    """Require the caller to hold *at least one* of the given permission codes."""

    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            held = current_permissions.get()
            if not any(c in held for c in codes):
                raise PermissionDeniedError(
                    f"You do not have permission to perform this action "
                    f"(requires one of {', '.join(codes)})."
                )
            return func(self, *args, **kwargs)

        return wrapper

    return decorator
