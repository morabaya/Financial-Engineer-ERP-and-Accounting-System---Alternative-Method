from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.models.financials import Base
import datetime

class Voucher(Base):
    __tablename__ = 'vouchers'

    id = Column(Integer, primary_key=True)
    voucher_no = Column(String(50), unique=True, nullable=False) # R-0001 (Receipt), P-0001 (Payment), E-0001 (Journal)
    date = Column(DateTime, default=datetime.datetime.utcnow)
    type = Column(String(20)) # 'Receipt', 'Payment', 'Journal'
    description = Column(String(255))
    total_amount = Column(Float, nullable=False)
    currency = Column(String(10), default="ILS")
    exchange_rate = Column(Float, default=1.0)
    contact_id = Column(Integer, ForeignKey('contacts.id'), nullable=True)
    user_id = Column(Integer, default=1)

    contact = relationship("Contact", foreign_keys=[contact_id])
    lines = relationship("VoucherLine", backref="voucher", cascade="all, delete-orphan")

    def to_dict(self):
        type_ar = {"Receipt": "سند قبض", "Payment": "سند صرف", "Journal": "سند قيد"}.get(self.type, self.type)
        return {
            "id": self.id,
            "voucher_no": self.voucher_no,
            "date": self.date.strftime("%Y-%m-%d %H:%M") if self.date else "",
            "type": self.type,
            "type_ar": type_ar,
            "description": self.description or "",
            "total_amount": round(self.total_amount, 2),
            "currency": self.currency,
            "exchange_rate": self.exchange_rate,
            "contact_id": self.contact_id,
            "contact_name": self.contact.name if self.contact else "",
            "lines": [l.to_dict() for l in self.lines]
        }

class VoucherLine(Base):
    __tablename__ = 'voucher_lines'

    id = Column(Integer, primary_key=True)
    voucher_id = Column(Integer, ForeignKey('vouchers.id'), nullable=False)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    debit = Column(Float, default=0.0)
    credit = Column(Float, default=0.0)
    note = Column(String(255))

    account = relationship("Account")

    def to_dict(self):
        return {
            "id": self.id,
            "voucher_id": self.voucher_id,
            "account_id": self.account_id,
            "account_code": self.account.code if self.account else "",
            "account_name": self.account.name_ar if self.account else "",
            "debit": self.debit,
            "credit": self.credit,
            "note": self.note or ""
        }

class AuditLog(Base):
    __tablename__ = 'audit_logs'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, default=1)
    action = Column(String(50)) # 'CREATE', 'UPDATE', 'DELETE', 'POST'
    table_name = Column(String(50))
    record_id = Column(Integer)
    old_value = Column(String(2000))
    new_value = Column(String(2000))
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "action": self.action,
            "table_name": self.table_name,
            "record_id": self.record_id,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "timestamp": self.timestamp.strftime("%Y-%m-%d %H:%M:%S") if self.timestamp else ""
        }
