"""Session flush hooks: user attribution + automatic audit-trail generation.

Two coordinated listeners (registered in :mod:`mediflow.data.database`):

``before_flush``  ->  :func:`capture_changes`
    Stamps ``created_by_id`` / ``updated_by_id`` from the current user context
    and records an audit *descriptor* for each pending object. Diffs for updates
    are computed here because attribute history is only available pre-flush.

``after_flush``   ->  :func:`emit_audit_rows`
    Materialises the descriptors into append-only :class:`AuditLog` rows. This
    runs *after* INSERTs so newly created objects already have their primary
    key; the rows are added to the session and persist on the enclosing commit.

Models opt out with ``__audit__ = False`` (used by the audit log and login
history, which are themselves the record of truth).
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from mediflow.core.constants import AuditAction
from mediflow.data.base import utcnow
from mediflow.data.mixins import SoftDeleteMixin, UserAttributionMixin
from mediflow.data.models.audit import AuditLog

_IGNORED_FIELDS = {"updated_at", "created_at", "password_hash"}
_SESSION_KEY = "_pending_audit"

# Key for the audit hash chain. Set from the install secret key at startup; a
# fixed fallback keeps headless tests deterministic without a configured cipher.
_audit_key: bytes = b"mediflow-audit-chain-default"


def set_audit_key(key: bytes) -> None:
    """Bind the audit-chain HMAC key (called once at application startup)."""
    global _audit_key
    _audit_key = key


def compute_row_hash(prev_hash: str, user_id: int | None, action: str,
                     entity_type: str, entity_id: int | None,
                     changes: str | None, occurred_at: datetime) -> str:
    """Deterministic HMAC over the previous hash plus this row's canonical fields."""
    payload = "|".join([
        prev_hash or "", str(user_id), action, entity_type, str(entity_id),
        changes or "", occurred_at.isoformat(),
    ])
    return hmac.new(_audit_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass(slots=True)
class _Descriptor:
    obj: Any
    action: AuditAction
    user_id: int | None
    changes: dict[str, list[Any]] | None


def capture_changes(session: Session, user_id: int | None) -> None:
    pending: list[_Descriptor] = session.info.setdefault(_SESSION_KEY, [])

    for obj in session.new:
        _stamp(obj, user_id, created=True)
        if _is_auditable(obj):
            pending.append(_Descriptor(obj, AuditAction.CREATE, user_id, None))

    for obj in session.dirty:
        if not session.is_modified(obj, include_collections=False):
            continue
        _stamp(obj, user_id, created=False)
        if not _is_auditable(obj):
            continue
        changes = _diff(obj)
        if not changes:
            continue
        soft_deleted = (
            isinstance(obj, SoftDeleteMixin)
            and changes.get("is_deleted", [None, None])[1] is True
        )
        action = AuditAction.DELETE if soft_deleted else AuditAction.UPDATE
        pending.append(_Descriptor(obj, action, user_id, changes))

    for obj in session.deleted:
        if _is_auditable(obj):
            pending.append(_Descriptor(obj, AuditAction.DELETE, user_id, None))


def emit_audit_rows(session: Session) -> None:
    pending: list[_Descriptor] = session.info.pop(_SESSION_KEY, [])
    if not pending:
        return
    # Read the current chain head via a Core execute (no ORM autoflush during
    # this after_flush hook). Newly added rows chain among themselves in order.
    prev = session.connection().execute(
        text("SELECT row_hash FROM audit_log ORDER BY id DESC LIMIT 1")
    ).scalar() or ""
    for d in pending:
        entity_type = type(d.obj).__name__
        entity_id = getattr(d.obj, "id", None)
        changes = json.dumps(d.changes, ensure_ascii=False) if d.changes else None
        occurred_at = utcnow()
        row_hash = compute_row_hash(prev, d.user_id, d.action.value, entity_type,
                                    entity_id, changes, occurred_at)
        session.add(
            AuditLog(
                user_id=d.user_id,
                action=d.action.value,
                entity_type=entity_type,
                entity_id=entity_id,
                changes=changes,
                occurred_at=occurred_at,
                row_hash=row_hash,
            )
        )
        prev = row_hash


def _is_auditable(obj: Any) -> bool:
    if isinstance(obj, AuditLog):
        return False
    return getattr(type(obj), "__audit__", True) is not False


def _stamp(obj: Any, user_id: int | None, *, created: bool) -> None:
    if not isinstance(obj, UserAttributionMixin):
        return
    if created and obj.created_by_id is None:
        obj.created_by_id = user_id
    obj.updated_by_id = user_id


def _diff(obj: Any) -> dict[str, list[Any]]:
    state = inspect(obj)
    changes: dict[str, list[Any]] = {}
    for attr in state.attrs:
        if attr.key in _IGNORED_FIELDS:
            continue
        history = attr.history
        if not history.has_changes():
            continue
        old = history.deleted[0] if history.deleted else None
        new = history.added[0] if history.added else None
        if old != new:
            changes[attr.key] = [_jsonable(old), _jsonable(new)]
    return changes


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
