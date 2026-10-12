import datetime
from sqlalchemy.orm import Session
from app.models.banking import Check, CheckStatus, BankReconciliation
from app.models.vouchers import AuditLog
from app.services.accounting_engine import create_accounting_entry, get_account_by_code

class BankingService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_checks(self, status=None, check_type=None, limit=100):
        query = self.db.query(Check)
        if status:
            if isinstance(status, str):
                query = query.filter(Check.status == CheckStatus[status] if status in CheckStatus.__members__ else Check.status == status)
            else:
                query = query.filter(Check.status == status)
        if check_type:
            query = query.filter(Check.type == check_type)
        return query.order_by(Check.due_date.asc()).limit(limit).all()

    def receive_check(self, check_no, drawer_name, amount, currency, due_date, contact_id, bank_name="بنك فلسطين", rate=1.0, user_id=1):
        """
        استلام شيك وارد من عميل (تحت التحصيل):
        من حـ/ شيكات برسم التحصيل (1115) -> إلى حـ/ العميل (1121)
        """
        check = Check(
            check_number=check_no,
            drawer_name=drawer_name,
            bank_name=bank_name,
            amount=float(amount),
            currency=currency,
            due_date=due_date,
            status=CheckStatus.UNDER_COLLECTION,
            type='Incoming',
            contact_id=contact_id,
            exchange_rate=float(rate)
        )
        self.db.add(check)
        self.db.flush()

        under_coll_acc = get_account_by_code(self.db, "1115")
        cust_acc = get_account_by_code(self.db, "1121")

        base_amount = round(float(amount) * float(rate), 2)
        lines = [
            {'account_id': under_coll_acc.id, 'debit': base_amount, 'credit': 0.0, 'note': f"شيك رقم {check_no} برسم التحصيل"},
            {'account_id': cust_acc.id, 'contact_id': contact_id, 'debit': 0.0, 'credit': base_amount, 'note': f"سداد بشيك رقم {check_no} مستحق {due_date.strftime('%Y-%m-%d') if isinstance(due_date, datetime.date) else due_date}"}
        ]
        create_accounting_entry(
            self.db, 
            f"استلام شيك وارد رقم {check_no} من {drawer_name}", 
            f"CHK-IN-{check_no}", 
            lines, 
            currency=currency, 
            rate=rate, 
            source_module="BANK", 
            user_id=user_id
        )

        audit = AuditLog(
            user_id=user_id,
            action="RECEIVE_CHECK",
            table_name="checks",
            record_id=check.id,
            new_value=f"استلام شيك وارد {check_no} بمبلغ {amount} {currency} تاريخ استحقاق {due_date}"
        )
        self.db.add(audit)
        self.db.commit()
        return check.id

    def issue_check(self, check_no, beneficiary_name, amount, currency, due_date, vendor_id, bank_account_code="1112", rate=1.0, user_id=1):
        """
        تحرير شيك صادر لمورد (شيكات صادرة مؤجلة):
        من حـ/ المورد (2111) -> إلى حـ/ شيكات صادرة مؤجلة (213)
        """
        bank_acc = get_account_by_code(self.db, bank_account_code)
        check = Check(
            check_number=check_no,
            drawer_name="الشركة",
            bank_name=bank_acc.name_ar,
            amount=float(amount),
            currency=currency,
            due_date=due_date,
            status=CheckStatus.DUE,
            type='Outgoing',
            contact_id=vendor_id,
            account_id=bank_acc.id,
            exchange_rate=float(rate)
        )
        self.db.add(check)
        self.db.flush()

        vend_acc = get_account_by_code(self.db, "2111")
        outgoing_check_acc = get_account_by_code(self.db, "213")

        base_amount = round(float(amount) * float(rate), 2)
        lines = [
            {'account_id': vend_acc.id, 'contact_id': vendor_id, 'debit': base_amount, 'credit': 0.0, 'note': f"دفعة بشيك صادر رقم {check_no} لصالح {beneficiary_name}"},
            {'account_id': outgoing_check_acc.id, 'debit': 0.0, 'credit': base_amount, 'note': f"شيك صادر رقم {check_no} مسحوب على {bank_acc.name_ar}"}
        ]
        create_accounting_entry(
            self.db, 
            f"تحرير شيك صادر رقم {check_no} لصالح {beneficiary_name}", 
            f"CHK-OUT-{check_no}", 
            lines, 
            currency=currency, 
            rate=rate, 
            source_module="BANK", 
            user_id=user_id
        )

        self.db.commit()
        return check.id

    def clear_check(self, check_id, bank_account_code="1112", actual_rate=None, user_id=1):
        """
        تحصيل/صرف الشيك في الحساب البنكي ومعالجة فروقات أسعار الصرف آلياً
        """
        check = self.db.query(Check).filter(Check.id == check_id).first()
        if not check:
            raise ValueError("الشيك غير موجود!")

        rate = float(actual_rate) if actual_rate else float(check.exchange_rate)
        bank_acc = get_account_by_code(self.db, bank_account_code)
        under_coll_acc = get_account_by_code(self.db, "1115")
        outgoing_check_acc = get_account_by_code(self.db, "213")
        gain_acc = get_account_by_code(self.db, "421")
        loss_acc = get_account_by_code(self.db, "533")

        orig_base_amount = round(check.amount * check.exchange_rate, 2)
        new_base_amount = round(check.amount * rate, 2)
        diff = round(new_base_amount - orig_base_amount, 2)

        lines = []
        if check.type == 'Incoming':
            # شيك وارد تم تحصيله: من حـ/ البنك إلى حـ/ شيكات برسم التحصيل + فروقات الصرف
            lines.append({'account_id': bank_acc.id, 'debit': new_base_amount, 'credit': 0.0, 'note': f"إيداع تحصيل شيك {check.check_number}"})
            lines.append({'account_id': under_coll_acc.id, 'debit': 0.0, 'credit': orig_base_amount, 'note': f"تسوية شيك برسم التحصيل {check.check_number}"})
            if diff > 0:
                lines.append({'account_id': gain_acc.id, 'debit': 0.0, 'credit': diff, 'note': "أرباح فروقات صرف شيك"})
            elif diff < 0:
                lines.append({'account_id': loss_acc.id, 'debit': abs(diff), 'credit': 0.0, 'note': "خسائر فروقات صرف شيك"})

        else: # Outgoing
            # شيك صادر تم صرفه من حسابنا: من حـ/ شيكات صادرة إلى حـ/ البنك
            lines.append({'account_id': outgoing_check_acc.id, 'debit': orig_base_amount, 'credit': 0.0, 'note': f"صرف شيك صادر {check.check_number}"})
            lines.append({'account_id': bank_acc.id, 'debit': 0.0, 'credit': new_base_amount, 'note': f"خصم قيمة شيك {check.check_number} من رصيد البنك"})
            if diff > 0:
                lines.append({'account_id': loss_acc.id, 'debit': diff, 'credit': 0.0, 'note': "خسائر صرف شيك صادر بارتفاع العملة"})
            elif diff < 0:
                lines.append({'account_id': gain_acc.id, 'debit': 0.0, 'credit': abs(diff), 'note': "أرباح صرف شيك صادر بانخفاض العملة"})

        create_accounting_entry(
            self.db, 
            f"تحصيل/صرف الشيك رقم {check.check_number}", 
            f"CLEAR-{check.check_number}", 
            lines, 
            currency=check.currency, 
            rate=rate, 
            source_module="BANK", 
            user_id=user_id
        )

        check.status = CheckStatus.PAID
        self.db.commit()
        return True

    def return_check(self, check_id, reason="رصيد غير كافٍ", user_id=1):
        """
        إرجاع الشيك: إعادة فتح الذمة على العميل
        """
        check = self.db.query(Check).filter(Check.id == check_id).first()
        if not check:
            raise ValueError("الشيك غير موجود!")

        under_coll_acc = get_account_by_code(self.db, "1115")
        cust_acc = get_account_by_code(self.db, "1121")
        base_amount = round(check.amount * check.exchange_rate, 2)

        lines = [
            {'account_id': cust_acc.id, 'contact_id': check.contact_id, 'debit': base_amount, 'credit': 0.0, 'note': f"ارتجاع شيك رقم {check.check_number} - سبب: {reason}"},
            {'account_id': under_coll_acc.id, 'debit': 0.0, 'credit': base_amount, 'note': f"إلغاء شيك مرتجع {check.check_number}"}
        ]
        create_accounting_entry(
            self.db, 
            f"إثبات ارتجاع الشيك رقم {check.check_number}", 
            f"RET-{check.check_number}", 
            lines, 
            currency=check.currency, 
            rate=check.exchange_rate, 
            source_module="BANK", 
            user_id=user_id
        )

        check.status = CheckStatus.RETURNED
        check.notes = f"مرتجع: {reason}"
        self.db.commit()
        return True

    def endorse_check(self, check_id, vendor_id, user_id=1):
        """
        تجيير الشيك الوارد لصالح مورد سداداً للذمة
        من حـ/ المورد (2111) -> إلى حـ/ شيكات برسم التحصيل (1115)
        """
        check = self.db.query(Check).filter(Check.id == check_id).first()
        if not check:
            raise ValueError("الشيك غير موجود!")
        if check.type != 'Incoming':
            raise ValueError("يمكن تجيير الشيكات الواردة فقط!")

        vend_acc = get_account_by_code(self.db, "2111")
        under_coll_acc = get_account_by_code(self.db, "1115")
        base_amount = round(check.amount * check.exchange_rate, 2)

        lines = [
            {'account_id': vend_acc.id, 'contact_id': vendor_id, 'debit': base_amount, 'credit': 0.0, 'note': f"سداد بتجيير شيك وارد رقم {check.check_number}"},
            {'account_id': under_coll_acc.id, 'debit': 0.0, 'credit': base_amount, 'note': f"تجيير شيك {check.check_number} وخروجه من العهدة"}
        ]
        create_accounting_entry(
            self.db, 
            f"تجيير الشيك رقم {check.check_number}", 
            f"END-{check.check_number}", 
            lines, 
            currency=check.currency, 
            rate=check.exchange_rate, 
            source_module="BANK", 
            user_id=user_id
        )

        check.status = CheckStatus.ENDORSED
        self.db.commit()
        return True
