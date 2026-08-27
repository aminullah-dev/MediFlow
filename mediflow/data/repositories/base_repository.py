"""Generic repository implementing the Repository pattern over SQLAlchemy.

Concrete repositories subclass :class:`BaseRepository`, bind a model, and add
query methods specific to that aggregate. Soft-deleted rows are excluded by
default (``include_deleted=True`` opts in) so callers cannot accidentally read
or count logically-removed data.

Repositories do **not** commit; the caller (a service, inside a unit of work)
owns the transaction boundary. This keeps multiple repository calls atomic.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mediflow.core.exceptions import NotFoundError
from mediflow.data.base import Base
from mediflow.data.mixins import SoftDeleteMixin

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    model: type[T]

    def __init__(self, session: Session):
        self.session = session

    # -- creation -----------------------------------------------------------
    def add(self, entity: T) -> T:
        self.session.add(entity)
        return entity

    def add_all(self, entities: Iterable[T]) -> None:
        self.session.add_all(list(entities))

    # -- reads --------------------------------------------------------------
    def get(self, entity_id: int, *, include_deleted: bool = False) -> T | None:
        entity = self.session.get(self.model, entity_id)
        if entity is None:
            return None
        if not include_deleted and self._is_soft_deleted(entity):
            return None
        return entity

    def get_or_raise(self, entity_id: int, *, include_deleted: bool = False) -> T:
        entity = self.get(entity_id, include_deleted=include_deleted)
        if entity is None:
            raise NotFoundError(f"{self.model.__name__} id={entity_id} not found")
        return entity

    def list(
        self,
        *,
        include_deleted: bool = False,
        limit: int | None = None,
        offset: int | None = None,
        order_by=None,
    ) -> Sequence[T]:
        stmt = self._base_select(include_deleted)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        elif hasattr(self.model, "id"):
            stmt = stmt.order_by(self.model.id.desc())
        if offset:
            stmt = stmt.offset(offset)
        if limit:
            stmt = stmt.limit(limit)
        return self.session.execute(stmt).scalars().all()

    def count(self, *, include_deleted: bool = False) -> int:
        stmt = select(func.count()).select_from(self.model)
        if not include_deleted and issubclass(self.model, SoftDeleteMixin):
            stmt = stmt.where(self.model.is_deleted.is_(False))
        return int(self.session.execute(stmt).scalar_one())

    # -- deletion -----------------------------------------------------------
    def soft_delete(self, entity: T) -> None:
        if isinstance(entity, SoftDeleteMixin):
            entity.soft_delete()
        else:
            self.session.delete(entity)

    def hard_delete(self, entity: T) -> None:
        self.session.delete(entity)

    # -- helpers ------------------------------------------------------------
    def _base_select(self, include_deleted: bool):
        stmt = select(self.model)
        if not include_deleted and issubclass(self.model, SoftDeleteMixin):
            stmt = stmt.where(self.model.is_deleted.is_(False))
        return stmt

    @staticmethod
    def _is_soft_deleted(entity: Base) -> bool:
        return isinstance(entity, SoftDeleteMixin) and entity.is_deleted
