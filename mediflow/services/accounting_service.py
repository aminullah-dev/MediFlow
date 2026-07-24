"""Accounting service: chart of accounts and double-entry journal."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func, select

from mediflow.core.constants import AccountType
from mediflow.core.exceptions import (
    BusinessRuleError,
    DuplicateError,
    ValidationError,
)
from mediflow.core.logging_config import get_logger
from mediflow.data.database import Database
from mediflow.services.authz import require
from mediflow.data.models.accounting import Account, JournalEntry, JournalLine

log = get_logger("services.accounting")

# Account types whose natural (positive) balance is on the debit side.
_DEBIT_NORMAL = (AccountType.ASSET.value, AccountType.EXPENSE.value)


@dataclass(slots=True)
class AccountDTO:
    id: int
    code: str
    name: str
    account_type: str
    balance: float


@dataclass(slots=True)
class LineInput:
    account_id: int
    debit: float = 0.0
    credit: float = 0.0
    memo: str | None = None


@dataclass(slots=True)
class EntryInput:
    entry_date: date
    description: str
    reference: str | None = None
    lines: list[LineInput] = field(default_factory=list)


@dataclass(slots=True)
class EntryDTO:
    id: int
    entry_date: date
    description: str
    reference: str | None
    amount: float


@dataclass(slots=True)
class EntryLineDTO:
    account_code: str
    account_name: str
    debit: float
    credit: float
    memo: str | None


@dataclass(slots=True)
class EntryDetailDTO:
    entry: EntryDTO
    lines: list[EntryLineDTO]


@dataclass(slots=True)
class AccountingSummary:
    income: float
    expense: float
    net: float


class AccountingService:
    def __init__(self, db: Database):
        self._db = db

    # -- chart of accounts --------------------------------------------------
    def list_accounts(self, *, active_only: bool = False) -> list[AccountDTO]:
        with self._db.unit_of_work() as session:
            balances = self._balances(session)
            stmt = select(Account).where(Account.is_deleted.is_(False))
            if active_only:
                stmt = stmt.where(Account.is_active.is_(True))
            stmt = stmt.order_by(Account.code)
            return [self._account_dto(a, balances.get(a.id, 0.0))
                    for a in session.execute(stmt).scalars().all()]

    @require("accounting.post")
    def create_account(self, code: str, name: str, account_type: AccountType) -> int:
        code = (code or "").strip()
        name = (name or "").strip()
        if not code:
            raise ValidationError("Account code is required.", field="code")
        if not name:
            raise ValidationError("Account name is required.", field="name")
        with self._db.unit_of_work() as session:
            # Check first rather than letting the UNIQUE constraint fire: a raw
            # IntegrityError is not a MediFlowError, so callers cannot map it to
            # a message and it surfaces as an unhandled error instead.
            existing = session.execute(
                select(Account).where(Account.code == code,
                                      Account.is_deleted.is_(False))
            ).scalars().first()
            if existing is not None:
                raise DuplicateError("An account with that code already exists.")
            account = Account(code=code, name=name, account_type=account_type.value)
            session.add(account)
            session.flush()
            return account.id

    @require("accounting.post")
    def delete_account(self, account_id: int) -> None:
        with self._db.unit_of_work() as session:
            account = session.get(Account, account_id)
            if account is None:
                return
            used = session.execute(
                select(func.count()).select_from(JournalLine).where(
                    JournalLine.account_id == account_id)
            ).scalar_one()
            if used:
                raise BusinessRuleError("Cannot delete an account that has journal lines.")
            account.soft_delete()

    # -- journal ------------------------------------------------------------
    @require("accounting.post")
    def create_entry(self, data: EntryInput) -> int:
        lines = [line for line in data.lines
                 if (line.debit or 0) > 0 or (line.credit or 0) > 0]
        if len(lines) < 2:
            raise ValidationError("An entry needs at least two lines.", field="lines")
        total_debit = round(sum(float(line.debit or 0) for line in lines), 2)
        total_credit = round(sum(float(line.credit or 0) for line in lines), 2)
        if total_debit <= 0:
            raise ValidationError("Entry total must be greater than zero.", field="lines")
        if total_debit != total_credit:
            raise BusinessRuleError(
                f"Debits ({total_debit}) must equal credits ({total_credit}).")
        if not (data.description or "").strip():
            raise ValidationError("A description is required.", field="description")

        with self._db.unit_of_work() as session:
            entry = JournalEntry(
                entry_date=data.entry_date,
                description=data.description.strip(),
                reference=(data.reference or "").strip() or None,
            )
            for line in lines:
                entry.lines.append(JournalLine(
                    account_id=line.account_id,
                    debit=round(float(line.debit or 0), 2),
                    credit=round(float(line.credit or 0), 2),
                    memo=(line.memo or "").strip() or None,
                ))
            session.add(entry)
            session.flush()
            log.info("Posted journal entry id=%s total=%s", entry.id, total_debit)
            return entry.id

    def list_entries(self, *, limit: int = 200) -> list[EntryDTO]:
        with self._db.unit_of_work() as session:
            stmt = (
                select(JournalEntry)
                .where(JournalEntry.is_deleted.is_(False))
                .order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc())
                .limit(limit)
            )
            rows = session.execute(stmt).scalars().all()
            return [self._entry_dto(e) for e in rows]

    def get_entry_detail(self, entry_id: int) -> EntryDetailDTO:
        with self._db.unit_of_work() as session:
            entry = session.get(JournalEntry, entry_id)
            if entry is None:
                raise ValidationError("Entry not found.")
            lines = [
                EntryLineDTO(
                    account_code=line.account.code if line.account else "",
                    account_name=line.account.name if line.account else "—",
                    debit=float(line.debit or 0),
                    credit=float(line.credit or 0),
                    memo=line.memo,
                )
                for line in entry.lines
            ]
            return EntryDetailDTO(entry=self._entry_dto(entry), lines=lines)

    # -- reporting ----------------------------------------------------------
    def summary(self) -> AccountingSummary:
        with self._db.unit_of_work() as session:
            balances = self._balances(session)
            type_by_id = {
                a.id: a.account_type
                for a in session.execute(select(Account)).scalars().all()
            }
            income = 0.0
            expense = 0.0
            for account_id, net in balances.items():
                atype = type_by_id.get(account_id)
                if atype == AccountType.INCOME.value:
                    income += -net          # credit-normal: credit increases income
                elif atype == AccountType.EXPENSE.value:
                    expense += net          # debit-normal
            income = round(income, 2)
            expense = round(expense, 2)
            return AccountingSummary(income=income, expense=expense,
                                     net=round(income - expense, 2))

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _balances(session) -> dict[int, float]:
        """Return {account_id: debit - credit} across all posted lines."""
        stmt = (
            select(JournalLine.account_id,
                   func.coalesce(func.sum(JournalLine.debit), 0),
                   func.coalesce(func.sum(JournalLine.credit), 0))
            .where(JournalLine.is_deleted.is_(False))
            .group_by(JournalLine.account_id)
        )
        result: dict[int, float] = {}
        for account_id, debit, credit in session.execute(stmt).all():
            result[account_id] = round(float(debit) - float(credit), 2)
        return result

    @staticmethod
    def _account_dto(account: Account, net: float) -> AccountDTO:
        # Present a positive balance on the account's natural side.
        balance = net if account.account_type in _DEBIT_NORMAL else -net
        return AccountDTO(
            id=account.id, code=account.code, name=account.name,
            account_type=account.account_type, balance=round(balance, 2),
        )

    @staticmethod
    def _entry_dto(entry: JournalEntry) -> EntryDTO:
        amount = round(sum(float(line.debit or 0) for line in entry.lines), 2)
        return EntryDTO(
            id=entry.id, entry_date=entry.entry_date, description=entry.description,
            reference=entry.reference, amount=amount,
        )
