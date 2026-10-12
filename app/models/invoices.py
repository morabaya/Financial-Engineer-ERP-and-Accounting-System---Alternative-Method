from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.models.financials import Base
import datetime

class Invoice(Base):
    __tablename__ = 'invoices'

    id = Column(Integer, primary_key=True)
    invoice_no = Column(String(50), unique=True, nullable=False)
    date = Column(DateTime, default=datetime.datetime.utcnow)
    type = Column(String(30)) # 'Sales', 'Purchase', 'Sales_Return', 'Purchase_Return'
    contact_id = Column(Integer, ForeignKey('contacts.id'), nullable=True) # Linked to Customer/Vendor
    total_before_tax = Column(Float, default=0.0)
    tax_amount = Column(Float, default=0.0)
    total_after_tax = Column(Float, default=0.0)
    paid_amount = Column(Float, default=0.0)
    status = Column(String(30), default='Unpaid') # 'Paid', 'Unpaid', 'Partially_Paid', 'Cancelled'
    payment_method = Column(String(30), default='Credit') # 'Cash', 'Credit', 'Check', 'Bank'
    currency = Column(String(10), default="ILS")
    exchange_rate = Column(Float, default=1.0)
    user_id = Column(Integer, default=1)
    notes = Column(String(255))

    contact = relationship("Contact", foreign_keys=[contact_id])
    items = relationship("InvoiceItem", backref="invoice", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "invoice_no": self.invoice_no,
            "date": self.date.strftime("%Y-%m-%d %H:%M") if self.date else "",
            "type": self.type,
            "contact_id": self.contact_id,
            "contact_name": self.contact.name if self.contact else "زبون نقدي / غير محدد",
            "total_before_tax": round(self.total_before_tax, 2),
            "tax_amount": round(self.tax_amount, 2),
            "total_after_tax": round(self.total_after_tax, 2),
            "paid_amount": round(self.paid_amount, 2),
            "remaining_amount": round(self.total_after_tax - self.paid_amount, 2),
            "status": self.status,
            "payment_method": self.payment_method,
            "currency": self.currency,
            "exchange_rate": self.exchange_rate,
            "notes": self.notes or "",
            "items": [item.to_dict() for item in self.items]
        }

class InvoiceItem(Base):
    __tablename__ = 'invoice_items'

    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey('invoices.id'), nullable=False)
    item_id = Column(Integer, ForeignKey('items.id'), nullable=True)
    item_name = Column(String(150))
    quantity = Column(Float, nullable=False, default=1.0)
    unit_price = Column(Float, nullable=False, default=0.0)
    discount = Column(Float, default=0.0)
    tax_rate = Column(Float, default=0.16) # Palestinian VAT 16%
    tax_amount = Column(Float, default=0.0)
    total = Column(Float, nullable=False, default=0.0)

    item = relationship("Item", foreign_keys=[item_id])

    def to_dict(self):
        return {
            "id": self.id,
            "item_id": self.item_id,
            "item_name": self.item.name_ar if self.item else (self.item_name or ""),
            "sku": self.item.sku if self.item else "",
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "discount": self.discount,
            "tax_rate": self.tax_rate,
            "tax_amount": round(self.tax_amount, 2),
            "total": round(self.total, 2)
        }
