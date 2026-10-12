import datetime
from sqlalchemy.orm import Session
from app.models.financials import Account, JournalEntry, JournalEntryLine
from app.models.contacts import Contact
from app.models.vouchers import AuditLog

def get_account_by_code(db: Session, code: str) -> Account:
    """ابحث عن حساب بواسطة رمزه المحاسبي"""
    acc = db.query(Account).filter(Account.code == str(code)).first()
    if not acc:
        raise ValueError(f"الحساب رقم '{code}' غير موجود في دليل الحسابات!")
    return acc

def generate_entry_number(db: Session) -> str:
    """توليد رقم تسلسلي فريد لسند القيد المحاسبي"""
    year = datetime.datetime.utcnow().year
    prefix = f"JE-{year}"
    last_entry = db.query(JournalEntry).filter(JournalEntry.entry_no.like(f"{prefix}-%")).order_by(JournalEntry.id.desc()).first()
    if not last_entry:
        return f"{prefix}-00001"
    try:
        last_seq = int(last_entry.entry_no.split('-')[2])
        return f"{prefix}-{str(last_seq + 1).zfill(5)}"
    except Exception:
        return f"{prefix}-00001"

def create_accounting_entry(
    db: Session, 
    description: str, 
    reference_no: str, 
    lines_data: list, 
    currency: str = "ILS", 
    rate: float = 1.0, 
    source_module: str = "MANUAL", 
    entry_date: datetime.datetime = None, 
    user_id: int = 1
) -> int:
    """
    محرك القيود المزدوجة المتطابق مع المعايير المحاسبية العالمية:
    - التحقق الصارم من توازن القيد (المدين = الدائن)
    - التحقق من وجود الحسابات وكونها حسابات فرعية نشطة (Leaf Accounts)
    - تسجيل العملة وسعر الصرف والمبالغ بالعملة الأجنبية والأساسية
    - تحديث رصيد دفتر الأستاذ المساعد للجهات (Customers/Suppliers)
    - تسجيل سجل تدقيق مالي غير قابل للحذف (Audit Log)
    """
    if not lines_data or len(lines_data) < 2:
        raise ValueError("يجب أن يحتوي القيد المحاسبي على طرفين على الأقل (مدين ودائن).")

    total_debit = 0.0
    total_credit = 0.0
    validated_lines = []

    for idx, line in enumerate(lines_data):
        # استخراج وتحديد الحساب
        acc_identifier = line.get('account_id') or line.get('account_code')
        if not acc_identifier:
            raise ValueError(f"السطر رقم {idx+1}: لم يتم تحديد الحساب.")
        
        if isinstance(acc_identifier, str) and not acc_identifier.isdigit() and len(acc_identifier) <= 6:
            account = get_account_by_code(db, acc_identifier)
        elif str(acc_identifier).isdigit():
            # قد يكون ID أو Code، نبحث أولاً بالـ ID ثم بالـ Code
            account = db.query(Account).filter(Account.id == int(acc_identifier)).first()
            if not account:
                account = db.query(Account).filter(Account.code == str(acc_identifier)).first()
        else:
            account = get_account_by_code(db, str(acc_identifier))

        if not account:
            raise ValueError(f"الحساب رقم {acc_identifier} غير موجود في شجرة الحسابات.")
        
        if not account.is_active:
            raise ValueError(f"الحساب '{account.name_ar}' ({account.code}) موقوف وغير نشط حالياً.")

        if not account.is_leaf:
            raise ValueError(f"لا يمكن الترحيل لحساب رئيسي: '{account.name_ar}' ({account.code}). الرجاء اختيار حساب فرعي تحليلي.")

        debit = round(float(line.get('debit', 0.0)), 2)
        credit = round(float(line.get('credit', 0.0)), 2)

        if debit < 0 or credit < 0:
            raise ValueError(f"لا يمكن إدخال مبالغ سالبة في القيد (السطر {idx+1}).")
        
        if debit == 0 and credit == 0:
            continue # تجاهل الأسطر الصفرية

        line_currency = line.get('currency', currency)
        line_rate = float(line.get('exchange_rate', rate))
        foreign_debit = float(line.get('foreign_debit', debit if line_currency == 'ILS' else debit / line_rate))
        foreign_credit = float(line.get('foreign_credit', credit if line_currency == 'ILS' else credit / line_rate))

        total_debit += debit
        total_credit += credit

        validated_lines.append({
            "account": account,
            "account_id": account.id,
            "contact_id": line.get('contact_id'),
            "debit": debit,
            "credit": credit,
            "currency": line_currency,
            "exchange_rate": line_rate,
            "foreign_debit": foreign_debit,
            "foreign_credit": foreign_credit,
            "note": line.get('note', '')
        })

    # التحقق من توازن القيد المحاسبي
    if abs(total_debit - total_credit) > 0.005:
        raise ValueError(f"القيد المحاسبي غير متوازن! إجمالي المدين ({total_debit:,.2f}) لا يساوي إجمالي الدائن ({total_credit:,.2f}). الفرق: {abs(total_debit - total_credit):,.2f}")

    entry_no = generate_entry_number(db)
    entry = JournalEntry(
        entry_no=entry_no,
        date=entry_date or datetime.datetime.utcnow(),
        description=description,
        reference_no=reference_no,
        source_module=source_module,
        currency=currency,
        exchange_rate=rate,
        is_posted=True,
        created_by=user_id
    )
    db.add(entry)
    db.flush()

    for vl in validated_lines:
        entry_line = JournalEntryLine(
            entry_id=entry.id,
            account_id=vl["account_id"],
            contact_id=vl["contact_id"],
            debit=vl["debit"],
            credit=vl["credit"],
            currency=vl["currency"],
            exchange_rate=vl["exchange_rate"],
            foreign_debit=vl["foreign_debit"],
            foreign_credit=vl["foreign_credit"],
            note=vl["note"]
        )
        db.add(entry_line)

        # تحديث رصيد جهة التعامل إذا تم ربطها
        if vl["contact_id"]:
            contact = db.query(Contact).filter(Contact.id == vl["contact_id"]).first()
            if contact:
                # الزيادة في المدين ترفع الرصيد المستحق على العميل، والدائن يخفضه
                contact.current_balance += (vl["debit"] - vl["credit"])

    # تسجيل سجل الرقابة والتدقيق (Audit Log)
    audit = AuditLog(
        user_id=user_id,
        action="POST_JOURNAL_ENTRY",
        table_name="journal_entries",
        record_id=entry.id,
        new_value=f"تم إنشاء القيد {entry_no}: {description} بقيمة {total_debit:,.2f} {currency}"
    )
    db.add(audit)
    db.commit()

    return entry.id
