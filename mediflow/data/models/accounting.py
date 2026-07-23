"""Accounting: chart of accounts and double-entry journal.

A journal entry has two or more lines; the sum of debits must equal the sum of
credits. Account balances are derived from the posted lines (debit − credit).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mediflow.core.constants import AccountType
from mediflow.data.base import Base
from mediflow.data.mixins import AuditMixin


class Account(Base, AuditMixin):
    __tablename__ = "accounts"

    code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    account_type: Mapped[str] = mapped_column(
        String(20), default=AccountType.ASSET.value, nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))

    lines: Mapped[list["JournalLine"]] = relationship(back_populates="account")


class JournalEntry(Base, AuditMixin):
    __tablename__ = "journal_entries"

    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(60))

    lines: Mapped[list["JournalLine"]] = relationship(
        back_populates="entry", cascade="all, delete-orphan"
    )


class JournalLine(Base, AuditMixin):
    __tablename__ = "journal_lines"

    entry_id: Mapped[int] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    debit: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    credit: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    memo: Mapped[str | None] = mapped_column(String(200))

    entry: Mapped[JournalEntry] = relationship(back_populates="lines")
    account: Mapped[Account] = relationship(back_populates="lines")
