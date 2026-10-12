from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Enum
from sqlalchemy.orm import relationship
from app.models.financials import Base
import datetime
import enum

class CheckStatus(enum.Enum):
    UNDER_COLLECTION = "تحت التحصيل"
    DUE = "مستحق"
    PAID = "مدفوع"
    RETURNED = "مرتجع"
    ENDORSED = "مجير"

class Check(Base):
    __tablename__ = 'checks'

    id = Column(Integer, primary_key=True)
    check_number = Column(String(50), nullable=False)
    bank_name = Column(String(100))
    drawer_name = Column(String(100)) # اسم الساحب
    amount = Column(Float, nullable=False)
    currency = Column(String(10), default="ILS")
    exchange_rate = Column(Float, default=1.0)
    due_date = Column(DateTime, nullable=False)
    status = Column(Enum(CheckStatus), default=CheckStatus.UNDER_COLLECTION)
    type = Column(String(20)) # 'Incoming' (وارد), 'Outgoing' (صادر)
    contact_id = Column(Integer, ForeignKey('contacts.id'), nullable=True) # Customer/Vendor
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=True) # Linked Bank/Cash Account
    date_created = Column(DateTime, default=datetime.datetime.utcnow)
    notes = Column(String(255))

    contact = relationship("Contact", foreign_keys=[contact_id])
    account = relationship("Account", foreign_keys=[account_id])

    def to_dict(self):
        return {
            "id": self.id,
            "check_number": self.check_number,
            "bank_name": self.bank_name or "",
            "drawer_name": self.drawer_name or "",
            "amount": self.amount,
            "currency": self.currency,
            "exchange_rate": self.exchange_rate,
            "due_date": self.due_date.strftime("%Y-%m-%d") if self.due_date else "",
            "status": self.status.value if hasattr(self.status, 'value') else str(self.status),
            "type": self.type,
            "contact_id": self.contact_id,
            "contact_name": self.contact.name if self.contact else "",
            "account_id": self.account_id,
            "account_name": self.account.name_ar if self.account else "",
            "notes": self.notes or ""
        }

class BankReconciliation(Base):
    __tablename__ = 'bank_reconciliations'

    id = Column(Integer, primary_key=True)
    bank_account_id = Column(Integer, ForeignKey('accounts.id'))
    statement_date = Column(DateTime, default=datetime.datetime.utcnow)
    statement_balance = Column(Float, default=0.0)
    book_balance = Column(Float, default=0.0)
    difference = Column(Float, default=0.0)
    user_id = Column(Integer, default=1)
    notes = Column(String(255))

    bank_account = relationship("Account")

    def to_dict(self):
        return {
            "id": self.id,
            "bank_account_id": self.bank_account_id,
            "bank_name": self.bank_account.name_ar if self.bank_account else "",
            "statement_date": self.statement_date.strftime("%Y-%m-%d") if self.statement_date else "",
            "statement_balance": self.statement_balance,
            "book_balance": self.book_balance,
            "difference": self.difference,
            "is_matched": abs(self.difference) < 0.01,
            "notes": self.notes or ""
        }
