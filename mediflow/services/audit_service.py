"""Audit service: read-only access to the audit trail and login history."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from mediflow.data.database import Database
from mediflow.data.models.audit import AuditLog
from mediflow.data.models.user import LoginHistory, User


@dataclass(slots=True)
class AuditEntryDTO:
    id: int
    occurred_at: datetime
    user_name: str
    action: str
    entity_type: str
    entity_id: int | None
    summary: str | None
    has_changes: bool


@dataclass(slots=True)
class ChangeDTO:
    field: str
    old: str
    new: str


@dataclass(slots=True)
class LoginEntryDTO:
    occurred_at: datetime
    username: str
    user_name: str | None
    success: bool
    reason: str | None


class AuditService:
    def __init__(self, db: Database):
        self._db = db

    # -- audit trail --------------------------------------------------------
    def list_events(self, *, entity_type: str | None = None, action: str | None = None,
                    limit: int = 300) -> list[AuditEntryDTO]:
        with self._db.unit_of_work() as session:
            names = self._user_names(session)
            # Sign-in events have their own view; keep the change log focused on data.
            stmt = select(AuditLog).where(AuditLog.entity_type != "LoginHistory")
            if entity_type:
                stmt = stmt.where(AuditLog.entity_type == entity_type)
            if action:
                stmt = stmt.where(AuditLog.action == action)
            stmt = stmt.order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc()).limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [
                AuditEntryDTO(
                    id=r.id, occurred_at=r.occurred_at,
                    user_name=names.get(r.user_id, "—") if r.user_id else "—",
                    action=r.action, entity_type=r.entity_type, entity_id=r.entity_id,
                    summary=r.summary, has_changes=bool(r.changes and r.changes != "{}"),
                )
                for r in rows
            ]

    def get_changes(self, audit_id: int) -> list[ChangeDTO]:
        with self._db.unit_of_work() as session:
            row = session.get(AuditLog, audit_id)
            if row is None or not row.changes:
                return []
            try:
                data = json.loads(row.changes)
            except (ValueError, TypeError):
                return []
            result: list[ChangeDTO] = []
            for field, pair in data.items():
                if isinstance(pair, (list, tuple)) and len(pair) == 2:
                    result.append(ChangeDTO(field, self._fmt(pair[0]), self._fmt(pair[1])))
                else:
                    result.append(ChangeDTO(field, "", self._fmt(pair)))
            return result

    def entity_types(self) -> list[str]:
        with self._db.unit_of_work() as session:
            rows = session.execute(
                select(AuditLog.entity_type).distinct()
                .where(AuditLog.entity_type != "LoginHistory")
                .order_by(AuditLog.entity_type)
            ).scalars().all()
            return list(rows)

    def actions(self) -> list[str]:
        with self._db.unit_of_work() as session:
            rows = session.execute(
                select(AuditLog.action).distinct().order_by(AuditLog.action)
            ).scalars().all()
            return list(rows)

    # -- integrity ----------------------------------------------------------
    def verify_chain(self) -> tuple[bool, int | None, int]:
        """Recompute the audit hash chain.

        Returns ``(ok, first_broken_id, total_rows)``. ``ok`` is False if any
        row's stored hash disagrees with a fresh recomputation — i.e. a row was
        edited, inserted, or deleted after the fact.
        """
        from mediflow.data.audit import compute_row_hash

        with self._db.unit_of_work() as session:
            rows = session.execute(
                select(AuditLog).order_by(AuditLog.id)
            ).scalars().all()
            prev = ""
            for row in rows:
                expected = compute_row_hash(
                    prev, row.user_id, row.action, row.entity_type,
                    row.entity_id, row.changes, row.occurred_at,
                )
                if row.row_hash != expected:
                    return (False, row.id, len(rows))
                prev = row.row_hash or ""
            return (True, None, len(rows))

    # -- login history ------------------------------------------------------
    def list_logins(self, *, success: bool | None = None, limit: int = 200) -> list[LoginEntryDTO]:
        with self._db.unit_of_work() as session:
            names = self._user_names(session)
            stmt = select(LoginHistory)
            if success is not None:
                stmt = stmt.where(LoginHistory.success.is_(success))
            stmt = stmt.order_by(LoginHistory.occurred_at.desc()).limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [
                LoginEntryDTO(
                    occurred_at=r.occurred_at, username=r.username_attempted,
                    user_name=names.get(r.user_id) if r.user_id else None,
                    success=r.success, reason=r.reason,
                )
                for r in rows
            ]

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _user_names(session) -> dict[int, str]:
        return {u.id: u.full_name for u in session.execute(select(User)).scalars().all()}

    @staticmethod
    def _fmt(value) -> str:
        if value is None:
            return "—"
        return str(value)
