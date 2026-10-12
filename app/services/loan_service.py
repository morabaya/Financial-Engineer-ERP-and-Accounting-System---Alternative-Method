import datetime
from sqlalchemy.orm import Session
from app.models.loans import Loan, LoanPaymentSchedule
from app.models.vouchers import AuditLog
from app.services.accounting_engine import create_accounting_entry, get_account_by_code

class LoanService:
    def __init__(self, db: Session):
        self.db = db

    def calculate_fixed_payment(self, principal, annual_rate, term_months):
        monthly_rate = (annual_rate / 100.0) / 12.0
        if monthly_rate == 0 or term_months == 0:
            return principal / (term_months or 1)
        payment = principal * (monthly_rate * (1 + monthly_rate)**term_months) / ((1 + monthly_rate)**term_months - 1)
        return round(payment, 2)

    def calculate_schedule_preview(self, amount, rate, term, loan_type="Fixed"):
        """حساب جدول السداد التقديري قبل حفظه"""
        amount = float(amount)
        rate = float(rate)
        term = int(term)
        monthly_rate = (rate / 100.0) / 12.0
        schedules = []
        remaining_balance = amount

        if loan_type == "Fixed":
            monthly_payment = self.calculate_fixed_payment(amount, rate, term)
            for i in range(1, term + 1):
                interest_payment = round(remaining_balance * monthly_rate, 2)
                principal_payment = round(monthly_payment - interest_payment, 2)
                if i == term:
                    principal_payment = round(remaining_balance, 2)
                    monthly_payment = round(principal_payment + interest_payment, 2)
                remaining_balance = max(0.0, round(remaining_balance - principal_payment, 2))
                schedules.append({
                    "payment_number": i,
                    "principal_amount": principal_payment,
                    "interest_amount": interest_payment,
                    "total_payment": monthly_payment,
                    "remaining_balance": remaining_balance
                })
        else: # Reducing (أقساط متناقصة - أصل دين ثابت وفائدة متناقصة)
            principal_per_month = round(amount / term, 2)
            for i in range(1, term + 1):
                interest_payment = round(remaining_balance * monthly_rate, 2)
                curr_principal = principal_per_month if i < term else remaining_balance
                total_payment = round(curr_principal + interest_payment, 2)
                remaining_balance = max(0.0, round(remaining_balance - curr_principal, 2))
                schedules.append({
                    "payment_number": i,
                    "principal_amount": curr_principal,
                    "interest_amount": interest_payment,
                    "total_payment": total_payment,
                    "remaining_balance": remaining_balance
                })

        return schedules

    def get_all_loans(self):
        return self.db.query(Loan).order_by(Loan.id.desc()).all()

    def get_loan_by_id(self, loan_id):
        return self.db.query(Loan).filter(Loan.id == loan_id).first()

    def create_loan(self, amount, rate, term, loan_type="Fixed", borrower_name="الشركة", bank_code="1112", user_id=1):
        """
        إنشاء القرض وإثبات دخول النقد للبنك:
        من حـ/ البنك (1112) -> إلى حـ/ قروض طويلة الأجل (221)
        """
        bank_acc = get_account_by_code(self.db, bank_code)
        loan_liability_acc = get_account_by_code(self.db, "221")

        loan = Loan(
            borrower_name=borrower_name,
            loan_amount=float(amount),
            interest_rate=float(rate),
            term_months=int(term),
            loan_type=loan_type,
            status='Active',
            bank_account_id=bank_acc.id
        )
        self.db.add(loan)
        self.db.flush()

        preview = self.calculate_schedule_preview(amount, rate, term, loan_type)
        start_date = datetime.datetime.utcnow()

        for s_data in preview:
            # تقريب تاريخ الاستحقاق شهرياً
            due_date = start_date + datetime.timedelta(days=30 * s_data["payment_number"])
            schedule = LoanPaymentSchedule(
                loan_id=loan.id,
                payment_number=s_data["payment_number"],
                due_date=due_date,
                principal_amount=s_data["principal_amount"],
                interest_amount=s_data["interest_amount"],
                total_payment=s_data["total_payment"],
                is_paid=0
            )
            self.db.add(schedule)

        # قيد استلام مبلغ التمويل في البنك
        entry_lines = [
            {'account_id': bank_acc.id, 'debit': float(amount), 'credit': 0.0, 'note': f"إيداع مبلغ القرض في {bank_acc.name_ar}"},
            {'account_id': loan_liability_acc.id, 'debit': 0.0, 'credit': float(amount), 'note': f"التزام قرض بنكي لصالح {borrower_name}"}
        ]
        create_accounting_entry(
            self.db, 
            f"إثبات استلام تمويل قرض بنكي بقيمة {amount:,.2f} شيكل", 
            f"LOAN-INIT-{loan.id}", 
            entry_lines, 
            source_module="LOAN", 
            user_id=user_id
        )

        audit = AuditLog(
            user_id=user_id,
            action="CREATE_LOAN",
            table_name="loans",
            record_id=loan.id,
            new_value=f"إنشاء قرض بمبلغ {amount} وفائدة {rate}% لمدة {term} شهر بنظام {loan_type}"
        )
        self.db.add(audit)
        self.db.commit()
        return loan.id

    def mark_payment_as_paid(self, schedule_id, bank_code="1112", user_id=1):
        """
        سداد قسط القرض:
        من مذكورين: حـ/ القرض (221) [أصل] + حـ/ مصاريف الفوائد (531) [فائدة] -> إلى حـ/ البنك (1112)
        """
        schedule = self.db.query(LoanPaymentSchedule).filter(LoanPaymentSchedule.id == schedule_id).first()
        if not schedule or schedule.is_paid == 1:
            return False

        schedule.is_paid = 1
        schedule.paid_date = datetime.datetime.utcnow()

        loan_liability_acc = get_account_by_code(self.db, "221")
        interest_acc = get_account_by_code(self.db, "531")
        bank_acc = get_account_by_code(self.db, bank_code)

        lines = [
            {'account_id': loan_liability_acc.id, 'debit': schedule.principal_amount, 'credit': 0.0, 'note': f"سداد أصل قسط قرض رقم {schedule.payment_number}"},
            {'account_id': interest_acc.id, 'debit': schedule.interest_amount, 'credit': 0.0, 'note': f"فوائد بنكية لقسط قرض رقم {schedule.payment_number}"},
            {'account_id': bank_acc.id, 'debit': 0.0, 'credit': schedule.total_payment, 'note': f"خصم قسط القرض رقم {schedule.payment_number} من حساب البنك"}
        ]
        create_accounting_entry(
            self.db, 
            f"سداد قسط القرض #{schedule.payment_number} (قرض ID {schedule.loan_id})", 
            f"LOAN-PAY-{schedule.id}", 
            lines, 
            source_module="LOAN", 
            user_id=user_id
        )

        # التحقق إذا اكتمل سداد كامل الأقساط لتغيير حالة القرض إلى Paid
        unpaid_count = self.db.query(LoanPaymentSchedule).filter(LoanPaymentSchedule.loan_id == schedule.loan_id, LoanPaymentSchedule.is_paid == 0).count()
        if unpaid_count == 0:
            loan = self.db.query(Loan).filter(Loan.id == schedule.loan_id).first()
            if loan:
                loan.status = 'Paid'

        self.db.commit()
        return True
