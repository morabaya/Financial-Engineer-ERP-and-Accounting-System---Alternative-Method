import datetime
from app.models.financials import Base
from sqlalchemy import Column, Integer, Float, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship

class Loan(Base):
    __tablename__ = 'loans'

    id = Column(Integer, primary_key=True)
    borrower_name = Column(String(150), default="الشركة")
    loan_amount = Column(Float, nullable=False)
    interest_rate = Column(Float, nullable=False) # Annual rate in percent e.g. 5.5 for 5.5%
    term_months = Column(Integer, nullable=False)
    start_date = Column(DateTime, default=datetime.datetime.utcnow)
    loan_type = Column(String(50), default='Fixed') # 'Fixed' (فائدة ثابتة), 'Reducing' (فائدة متناقصة)
    status = Column(String(20), default='Active') # 'Active', 'Paid'
    bank_account_id = Column(Integer, ForeignKey('accounts.id'), nullable=True)

    schedules = relationship("LoanPaymentSchedule", backref="loan", cascade="all, delete-orphan")
    bank_account = relationship("Account")

    def to_dict(self):
        paid_count = sum(1 for s in self.schedules if s.is_paid == 1)
        total_interest = sum(s.interest_amount for s in self.schedules)
        return {
            "id": self.id,
            "borrower_name": self.borrower_name,
            "loan_amount": round(self.loan_amount, 2),
            "interest_rate": self.interest_rate,
            "term_months": self.term_months,
            "start_date": self.start_date.strftime("%Y-%m-%d") if self.start_date else "",
            "loan_type": self.loan_type,
            "status": self.status,
            "total_interest": round(total_interest, 2),
            "total_repayment": round(self.loan_amount + total_interest, 2),
            "paid_installments": paid_count,
            "total_installments": self.term_months,
            "schedules": [s.to_dict() for s in self.schedules]
        }

class LoanPaymentSchedule(Base):
    __tablename__ = 'loan_payment_schedules'

    id = Column(Integer, primary_key=True)
    loan_id = Column(Integer, ForeignKey('loans.id'))
    payment_number = Column(Integer)
    due_date = Column(DateTime)
    principal_amount = Column(Float)
    interest_amount = Column(Float)
    total_payment = Column(Float)
    is_paid = Column(Integer, default=0) # 0: Unpaid, 1: Paid
    paid_date = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "loan_id": self.loan_id,
            "payment_number": self.payment_number,
            "due_date": self.due_date.strftime("%Y-%m-%d") if self.due_date else "",
            "principal_amount": round(self.principal_amount, 2),
            "interest_amount": round(self.interest_amount, 2),
            "total_payment": round(self.total_payment, 2),
            "is_paid": bool(self.is_paid),
            "paid_date": self.paid_date.strftime("%Y-%m-%d") if self.paid_date else ""
        }
