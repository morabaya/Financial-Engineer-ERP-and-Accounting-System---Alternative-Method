from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Boolean, Enum
from sqlalchemy.orm import relationship
from app.models.financials import Base
import datetime
import enum

class ContactType(enum.Enum):
    CUSTOMER = "عميل"
    SUPPLIER = "مورد"
    EMPLOYEE = "موظف"

class Contact(Base):
    __tablename__ = 'contacts'

    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    type = Column(Enum(ContactType), nullable=False)
    tax_number = Column(String(50))  # رقم المشتغل المرخص / الرقم الضريبي الفلسطيني
    phone = Column(String(50))
    email = Column(String(100))
    address = Column(String(255))
    city = Column(String(50), default="رام الله")
    currency = Column(String(10), default="ILS")
    
    # Linked Chart of Accounts sub-ledger
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=True)
    credit_limit = Column(Float, default=0.0)
    current_balance = Column(Float, default=0.0)  # مدين موجب، دائن سالب
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    account = relationship("Account", foreign_keys=[account_id])

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value if hasattr(self.type, 'value') else str(self.type),
            "tax_number": self.tax_number or "",
            "phone": self.phone or "",
            "email": self.email or "",
            "address": self.address or "",
            "city": self.city or "",
            "currency": self.currency,
            "account_id": self.account_id,
            "credit_limit": self.credit_limit,
            "current_balance": self.current_balance,
            "is_active": self.is_active
        }
