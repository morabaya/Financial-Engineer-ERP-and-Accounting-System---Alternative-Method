from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Boolean, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import datetime
import enum

Base = declarative_base()

class AccountType(enum.Enum):
    ASSET = "أصول"
    LIABILITY = "خصوم"
    EQUITY = "حقوق ملكية"
    REVENUE = "إيرادات"
    EXPENSE = "مصاريف"

class Currency(Base):
    __tablename__ = 'currencies'

    id = Column(Integer, primary_key=True)
    code = Column(String(10), unique=True, nullable=False) # ILS, USD, JOD, EUR
    name_ar = Column(String(50), nullable=False)
    name_en = Column(String(50), nullable=False)
    symbol = Column(String(10), default="₪")
    is_base = Column(Boolean, default=False)
    rate_to_base = Column(Float, default=1.0) # Rate against ILS (e.g. 1 USD = 3.65 ILS)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name_ar": self.name_ar,
            "name_en": self.name_en,
            "symbol": self.symbol,
            "is_base": self.is_base,
            "rate_to_base": self.rate_to_base
        }

class Account(Base):
    __tablename__ = 'accounts'

    id = Column(Integer, primary_key=True)
    code = Column(String(20), unique=True, nullable=False) # 1, 11, 111, 1111
    name_ar = Column(String(150), nullable=False)
    name_en = Column(String(150))
    type = Column(Enum(AccountType), nullable=False)
    parent_id = Column(Integer, ForeignKey('accounts.id'), nullable=True)
    level = Column(Integer, default=1)
    is_leaf = Column(Boolean, default=True) # Only leaf accounts can be selected for journal entries
    currency = Column(String(10), default="ILS")
    is_active = Column(Boolean, default=True)
    description = Column(String(255))

    children = relationship("Account", backref="parent", remote_side=[id])

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name_ar": self.name_ar,
            "name_en": self.name_en or "",
            "type": self.type.value if hasattr(self.type, 'value') else str(self.type),
            "parent_id": self.parent_id,
            "level": self.level,
            "is_leaf": self.is_leaf,
            "currency": self.currency,
            "is_active": self.is_active,
            "description": self.description or ""
        }

class JournalEntry(Base):
    __tablename__ = 'journal_entries'

    id = Column(Integer, primary_key=True)
    entry_no = Column(String(50), unique=True, nullable=False) # JE-2026-0001
    date = Column(DateTime, default=datetime.datetime.utcnow)
    description = Column(String(255))
    reference_no = Column(String(50))
    source_module = Column(String(50), default="MANUAL") # MANUAL, VOUCHER, INVOICE, POS, BANK, LOAN, INVENTORY
    currency = Column(String(10), default="ILS")
    exchange_rate = Column(Float, default=1.0)
    is_posted = Column(Boolean, default=True)
    created_by = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    lines = relationship("JournalEntryLine", backref="entry", cascade="all, delete-orphan")

    def to_dict(self):
        total_debit = sum(l.debit for l in self.lines)
        total_credit = sum(l.credit for l in self.lines)
        return {
            "id": self.id,
            "entry_no": self.entry_no,
            "date": self.date.strftime("%Y-%m-%d %H:%M") if self.date else "",
            "description": self.description or "",
            "reference_no": self.reference_no or "",
            "source_module": self.source_module,
            "currency": self.currency,
            "exchange_rate": self.exchange_rate,
            "total_debit": round(total_debit, 2),
            "total_credit": round(total_credit, 2),
            "is_balanced": abs(total_debit - total_credit) < 0.01,
            "lines": [l.to_dict() for l in self.lines]
        }

class JournalEntryLine(Base):
    __tablename__ = 'journal_entry_lines'

    id = Column(Integer, primary_key=True)
    entry_id = Column(Integer, ForeignKey('journal_entries.id'), nullable=False)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    contact_id = Column(Integer, ForeignKey('contacts.id'), nullable=True) # Linked customer/vendor for subledger
    debit = Column(Float, default=0.0) # Base currency (ILS)
    credit = Column(Float, default=0.0) # Base currency (ILS)
    currency = Column(String(10), default="ILS")
    foreign_debit = Column(Float, default=0.0)
    foreign_credit = Column(Float, default=0.0)
    exchange_rate = Column(Float, default=1.0)
    note = Column(String(255))

    account = relationship("Account")
    contact = relationship("Contact", foreign_keys=[contact_id])

    def to_dict(self):
        return {
            "id": self.id,
            "entry_id": self.entry_id,
            "account_id": self.account_id,
            "account_code": self.account.code if self.account else "",
            "account_name": self.account.name_ar if self.account else "",
            "contact_id": self.contact_id,
            "contact_name": self.contact.name if self.contact else "",
            "debit": self.debit,
            "credit": self.credit,
            "currency": self.currency,
            "foreign_debit": self.foreign_debit,
            "foreign_credit": self.foreign_credit,
            "exchange_rate": self.exchange_rate,
            "note": self.note or ""
        }
