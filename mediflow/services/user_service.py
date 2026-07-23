"""User and role administration (RBAC management).

Operates on the existing users/roles/permissions tables. Creating a user or
resetting a password returns a generated temporary password *once*, which the
admin relays to the user; it is stored only as a hash.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select

from mediflow.core.exceptions import BusinessRuleError, DuplicateError, ValidationError
from mediflow.core.logging_config import get_logger
from mediflow.core.security import generate_temporary_password, hash_password
from mediflow.data.base import utcnow
from mediflow.data.database import Database, current_user_id
from mediflow.services.authz import require
from mediflow.data.models.user import Permission, Role, User
from mediflow.data.repositories.user_repository import (
    PermissionRepository,
    RoleRepository,
    UserRepository,
)

log = get_logger("services.user")


@dataclass(slots=True)
class UserDTO:
    id: int
    username: str
    full_name: str
    email: str | None
    phone: str | None
    is_active: bool
    must_change_password: bool
    role_ids: list[int] = field(default_factory=list)
    role_names: list[str] = field(default_factory=list)


@dataclass(slots=True)
class UserInput:
    username: str
    full_name: str
    email: str | None = None
    phone: str | None = None
    is_active: bool = True
    role_ids: list[int] = field(default_factory=list)


@dataclass(slots=True)
class RoleDTO:
    id: int
    name: str
    description: str | None
    is_system: bool
    permission_codes: set[str] = field(default_factory=set)

    @property
    def permission_count(self) -> int:
        return len(self.permission_codes)


@dataclass(slots=True)
class PermissionDTO:
    code: str
    module: str
    description: str | None


class UserService:
    def __init__(self, db: Database):
        self._db = db

    # -- users --------------------------------------------------------------
    def list_users(self, term: str = "") -> list[UserDTO]:
        term = (term or "").strip()
        with self._db.unit_of_work() as session:
            stmt = select(User).where(User.is_deleted.is_(False))
            if term:
                like = f"%{term}%"
                stmt = stmt.where(User.username.ilike(like) | User.full_name.ilike(like))
            stmt = stmt.order_by(User.full_name)
            return [self._user_dto(u) for u in session.execute(stmt).scalars().all()]

    def get_user(self, user_id: int) -> UserDTO:
        with self._db.unit_of_work() as session:
            user = UserRepository(session).get_or_raise(user_id)
            return self._user_dto(user)

    @require("user.manage")
    def create_user(self, data: UserInput) -> str:
        """Create a user and return the one-time temporary password."""
        username = (data.username or "").strip()
        if not username:
            raise ValidationError("Username is required.", field="username")
        if not (data.full_name or "").strip():
            raise ValidationError("Full name is required.", field="full_name")
        temp = generate_temporary_password()
        with self._db.unit_of_work() as session:
            repo = UserRepository(session)
            if repo.get_by_username(username, include_deleted=True) is not None:
                raise DuplicateError("That username is already taken.")
            user = User(
                username=username,
                password_hash=hash_password(temp),
                full_name=data.full_name.strip(),
                email=(data.email or "").strip() or None,
                phone=(data.phone or "").strip() or None,
                is_active=data.is_active,
                must_change_password=True,
            )
            self._assign_roles(session, user, data.role_ids)
            repo.add(user)
            session.flush()
            log.info("Created user '%s'", username)
        return temp

    @require("user.manage")
    def update_user(self, user_id: int, data: UserInput) -> None:
        with self._db.unit_of_work() as session:
            user = UserRepository(session).get_or_raise(user_id)
            if not (data.full_name or "").strip():
                raise ValidationError("Full name is required.", field="full_name")
            user.full_name = data.full_name.strip()
            user.email = (data.email or "").strip() or None
            user.phone = (data.phone or "").strip() or None
            if user.id == current_user_id.get() and not data.is_active:
                raise BusinessRuleError("You cannot deactivate your own account.")
            user.is_active = data.is_active
            self._assign_roles(session, user, data.role_ids)
            self._ensure_manager_remains(session)

    @require("user.manage")
    def reset_password(self, user_id: int) -> str:
        temp = generate_temporary_password()
        with self._db.unit_of_work() as session:
            user = UserRepository(session).get_or_raise(user_id)
            user.password_hash = hash_password(temp)
            user.must_change_password = True
            user.password_changed_at = utcnow()
            user.failed_login_count = 0
            user.locked_until = None
            log.info("Reset password for user '%s'", user.username)
        return temp

    @require("user.manage")
    def set_active(self, user_id: int, active: bool) -> None:
        with self._db.unit_of_work() as session:
            user = UserRepository(session).get_or_raise(user_id)
            if user.id == current_user_id.get() and not active:
                raise BusinessRuleError("You cannot deactivate your own account.")
            user.is_active = active
            if not active:
                self._ensure_manager_remains(session)

    @require("user.manage")
    def delete_user(self, user_id: int) -> None:
        if user_id == current_user_id.get():
            raise BusinessRuleError("You cannot delete your own account.")
        with self._db.unit_of_work() as session:
            user = UserRepository(session).get_or_raise(user_id)
            user.soft_delete()
            self._ensure_manager_remains(session)

    # -- roles --------------------------------------------------------------
    def list_roles(self) -> list[RoleDTO]:
        with self._db.unit_of_work() as session:
            stmt = select(Role).where(Role.is_deleted.is_(False)).order_by(Role.name)
            return [self._role_dto(r) for r in session.execute(stmt).scalars().all()]

    @require("user.manage")
    def create_role(self, name: str, description: str | None,
                    permission_codes: set[str]) -> int:
        name = (name or "").strip()
        if not name:
            raise ValidationError("Role name is required.", field="name")
        with self._db.unit_of_work() as session:
            repo = RoleRepository(session)
            if repo.get_by_name(name) is not None:
                raise DuplicateError("A role with that name already exists.")
            role = Role(name=name, description=(description or "").strip() or None,
                        is_system=False)
            self._assign_permissions(session, role, permission_codes)
            repo.add(role)
            session.flush()
            return role.id

    @require("user.manage")
    def update_role(self, role_id: int, description: str | None,
                    permission_codes: set[str]) -> None:
        with self._db.unit_of_work() as session:
            role = RoleRepository(session).get_or_raise(role_id)
            role.description = (description or "").strip() or None
            self._assign_permissions(session, role, permission_codes)
            # Removing user.manage from this role must not orphan the system.
            self._ensure_manager_remains(session)

    @require("user.manage")
    def delete_role(self, role_id: int) -> None:
        with self._db.unit_of_work() as session:
            role = RoleRepository(session).get_or_raise(role_id)
            if role.is_system:
                raise BusinessRuleError("System roles cannot be deleted.")
            if role.users:
                raise BusinessRuleError("Cannot delete a role that is assigned to users.")
            role.soft_delete()

    # -- permissions --------------------------------------------------------
    def list_permission_groups(self) -> list[tuple[str, list[PermissionDTO]]]:
        with self._db.unit_of_work() as session:
            perms = session.execute(
                select(Permission).order_by(Permission.module, Permission.code)
            ).scalars().all()
            groups: dict[str, list[PermissionDTO]] = {}
            for p in perms:
                groups.setdefault(p.module, []).append(
                    PermissionDTO(p.code, p.module, p.description))
            return list(groups.items())

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _ensure_manager_remains(session) -> None:
        """Refuse any change that would leave no active user able to manage users.

        Called inside the mutating unit of work, so raising rolls the whole
        change back. Guards deletion/deactivation of the last administrator and
        stripping ``user.manage`` from the only role that still grants it.
        """
        users = session.execute(
            select(User).where(User.is_deleted.is_(False), User.is_active.is_(True))
        ).scalars().all()
        if not any("user.manage" in u.all_permission_codes() for u in users):
            raise BusinessRuleError(
                "At least one active user must keep the Users & Roles "
                "management permission."
            )

    @staticmethod
    def _assign_roles(session, user: User, role_ids: list[int]) -> None:
        wanted = set(role_ids or [])
        roles = session.execute(
            select(Role).where(Role.id.in_(wanted))
        ).scalars().all() if wanted else []
        user.roles = list(roles)

    @staticmethod
    def _assign_permissions(session, role: Role, codes: set[str]) -> None:
        wanted = set(codes or [])
        perms = session.execute(
            select(Permission).where(Permission.code.in_(wanted))
        ).scalars().all() if wanted else []
        role.permissions = list(perms)

    @staticmethod
    def _user_dto(user: User) -> UserDTO:
        roles = sorted(user.roles, key=lambda r: r.name)
        return UserDTO(
            id=user.id, username=user.username, full_name=user.full_name,
            email=user.email, phone=user.phone, is_active=user.is_active,
            must_change_password=user.must_change_password,
            role_ids=[r.id for r in roles], role_names=[r.name for r in roles],
        )

    @staticmethod
    def _role_dto(role: Role) -> RoleDTO:
        return RoleDTO(
            id=role.id, name=role.name, description=role.description,
            is_system=role.is_system, permission_codes=role.permission_codes(),
        )
