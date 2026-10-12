import datetime
from sqlalchemy.orm import Session
from app.models.vouchers import Voucher, VoucherLine, AuditLog
from app.models.financials import Account
from app.services.accounting_engine import create_accounting_entry, get_account_by_code

class VoucherService:
    def __init__(self, db: Session):
        self.db = db

    def _generate_voucher_no(self, v_type):
        prefixes = {'Receipt': 'R', 'Payment': 'P', 'Journal': 'E', 'Entry': 'E'}
        prefix = prefixes.get(v_type, 'V')
        year = datetime.datetime.utcnow().year
        pattern = f"{prefix}-{year}-%"
        last_voucher = self.db.query(Voucher).filter(Voucher.voucher_no.like(pattern)).order_by(Voucher.id.desc()).first()
        if not last_voucher:
            return f"{prefix}-{year}-0001"
        try:
            parts = last_voucher.voucher_no.split('-')
            last_no = int(parts[2]) if len(parts) >= 3 else int(parts[1])
            return f"{prefix}-{year}-{str(last_no + 1).zfill(4)}"
        except Exception:
            return f"{prefix}-{year}-0001"

    def get_all_vouchers(self, v_type=None, limit=100):
        query = self.db.query(Voucher)
        if v_type:
            query = query.filter(Voucher.type == v_type)
        return query.order_by(Voucher.id.desc()).limit(limit).all()

    def get_voucher_by_id(self, voucher_id):
        return self.db.query(Voucher).filter(Voucher.id == voucher_id).first()

    def create_voucher(self, v_type, description, lines_data, total_amount, currency="ILS", rate=1.0, contact_id=None, user_id=1):
        """
        إنشاء سند قبض (R)، أو سند صرف (P)، أو سند قيد (E):
        - التحقق من توازن الأطراف
        - ربط الحسابات المحاسبية بدقة
        - ترحيل القيد في محرك اليومية العامة
        - تسجيل حركة التدقيق
        """
        v_no = self._generate_voucher_no(v_type)
        voucher = Voucher(
            voucher_no=v_no,
            type=v_type,
            description=description,
            total_amount=float(total_amount),
            currency=currency,
            exchange_rate=float(rate),
            contact_id=contact_id,
            user_id=user_id
        )
        self.db.add(voucher)
        self.db.flush()

        prepared_accounting_lines = []
        for line in lines_data:
            # التأكد من الحساب (بالرمز أو المعرف)
            acc_id = line.get('account_id')
            if not acc_id and line.get('account_code'):
                acc = get_account_by_code(self.db, line['account_code'])
                acc_id = acc.id
            elif isinstance(acc_id, str) and not acc_id.isdigit():
                acc = get_account_by_code(self.db, acc_id)
                acc_id = acc.id

            v_line = VoucherLine(
                voucher_id=voucher.id,
                account_id=acc_id,
                debit=float(line.get('debit', 0.0)),
                credit=float(line.get('credit', 0.0)),
                note=line.get('note', '')
            )
            self.db.add(v_line)

            prepared_accounting_lines.append({
                'account_id': acc_id,
                'contact_id': line.get('contact_id', contact_id),
                'debit': float(line.get('debit', 0.0)),
                'credit': float(line.get('credit', 0.0)),
                'currency': currency,
                'exchange_rate': rate,
                'note': line.get('note', description)
            })

        # إنشاء وترحيل القيد المحاسبي المتوازن في اليومية العامة
        create_accounting_entry(
            db=self.db,
            description=f"[{v_no}] {description}",
            reference_no=v_no,
            lines_data=prepared_accounting_lines,
            currency=currency,
            rate=rate,
            source_module="VOUCHER",
            user_id=user_id
        )

        audit = AuditLog(
            user_id=user_id,
            action='CREATE_VOUCHER',
            table_name='vouchers',
            record_id=voucher.id,
            new_value=f"تم إصدار {v_no} ({v_type}) بقيمة {total_amount} {currency} - البيان: {description}"
        )
        self.db.add(audit)
        self.db.commit()
        return voucher.id
