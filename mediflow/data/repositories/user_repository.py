"""Repositories for users, roles, and permissions."""
from __future__ import annotations

from sqlalchemy import select

from mediflow.data.models.user import Permission, Role, User
from mediflow.data.repositories.base_repository import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def get_by_username(self, username: str, *, include_deleted: bool = False) -> User | None:
        stmt = self._base_select(include_deleted).where(User.username == username)
        return self.session.execute(stmt).scalars().first()

    def search(self, term: str, *, limit: int = 50) -> list[User]:
        like = f"%{term.strip()}%"
        stmt = (
            self._base_select(include_deleted=False)
            .where((User.username.ilike(like)) | (User.full_name.ilike(like)))
            .order_by(User.full_name)
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())


class RoleRepository(BaseRepository[Role]):
    model = Role

    def get_by_name(self, name: str) -> Role | None:
        stmt = select(Role).where(Role.name == name)
        return self.session.execute(stmt).scalars().first()


class PermissionRepository(BaseRepository[Permission]):
    model = Permission

    def get_by_code(self, code: str) -> Permission | None:
        stmt = select(Permission).where(Permission.code == code)
        return self.session.execute(stmt).scalars().first()

    def all_codes(self) -> set[str]:
        return set(self.session.execute(select(Permission.code)).scalars().all())
