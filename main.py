import datetime
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

# Import all models to ensure complete metadata registration
from app.models import (
    Base, Account, AccountType, Currency, Contact, 
    Voucher, Invoice, Item, Check, Loan, User
)

from app.services.seed_service import seed_database
from app.services.voucher_service import VoucherService
from app.services.invoice_service import InvoiceService
from app.services.reporting_service import ReportingService
from app.services.inventory_service import InventoryService
from app.services.banking_service import BankingService
from app.services.loan_service import LoanService
from app.services.ai_bridge import AIFinancialBridge
from app.services.user_service import UserService

app = Flask(__name__)
app.secret_key = 'financial_engineer_secret_key_prod_2026'

# Database Setup
engine = create_engine('sqlite:///accounting_system.db', connect_args={'check_same_thread': False})
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)

# Auto-seed initial data on startup if accounts are empty
with SessionLocal() as db_session:
    account_count = db_session.query(Account).count()
    if account_count == 0:
        seed_database(db_session)

@app.before_request
def create_session():
    request.db = SessionLocal()

@app.after_request
def close_session(response):
    if hasattr(request, 'db'):
        request.db.close()
    return response

# ==========================================
#              PAGE ROUTES
# ==========================================

@app.route('/')
@app.route('/dashboard')
def index():
    return render_template('base.html')

@app.route('/pos')
def pos():
    return render_template('pos.html')

@app.route('/vouchers')
def vouchers():
    return render_template('vouchers.html')

@app.route('/invoices')
def invoices():
    return render_template('invoices.html')

@app.route('/inventory')
def inventory():
    return render_template('inventory.html')

@app.route('/reports')
def reports():
    return render_template('reports.html')

@app.route('/loans')
def loans():
    return render_template('loans.html')

@app.route('/dashboard_view')
def dashboard_view():
    return render_template('dashboard_view.html')

@app.route('/accounts_view')
def accounts_view():
    return render_template('accounts_view.html')

@app.route('/checks_view')
def checks_view():
    return render_template('checks_view.html')

@app.route('/settings')
def settings():
    return """
    <div class="container-fluid p-4">
        <h3><i class="fas fa-cog"></i> إعدادات النظام المالي</h3>
        <hr>
        <div class="row g-3">
            <div class="col-md-6">
                <div class="card p-3 shadow-sm">
                    <h5>العملة الأساسية والضرائب</h5>
                    <p class="text-muted">العملة الأساسية: <b>شيكل إسرائيلي (ILS ₪)</b></p>
                    <p class="text-muted">نسبة ضريبة القيمة المضافة الفلسطينية: <b>16%</b></p>
                </div>
            </div>
            <div class="col-md-6">
                <div class="card p-3 shadow-sm">
                    <h5>التهيئة وقاعدة البيانات</h5>
                    <button class="btn btn-outline-warning" onclick="fetch('/api/system/seed', {method:'POST'}).then(r=>r.json()).then(d=>alert(d.message))">
                        إعادة تهيئة دليل الحسابات الافتراضي
                    </button>
                </div>
            </div>
        </div>
    </div>
    """

# ==========================================
#          DASHBOARD & STATS APIS
# ==========================================

@app.route('/api/dashboard/stats')
def dashboard_stats():
    """مؤشرات الأداء المالي الرئيسية (KPIs)"""
    db = request.db
    reporting = ReportingService(db)

    # 1. النقدية والبنوك
    cash_accs = db.query(Account).filter(Account.code.in_(["1111", "1112", "1113", "1114"])).all()
    total_cash = 0.0
    for acc in cash_accs:
        gl = reporting.get_general_ledger(acc.id)
        if isinstance(gl, dict) and "closing_balance" in gl:
            total_cash += gl["closing_balance"]

    # 2. رصيد ذمم العملاء (Receivables)
    total_receivables = db.query(func.sum(Contact.current_balance)).filter(Contact.current_balance > 0).scalar() or 0.0

    # 3. إجمالي قيمة المخزون
    items = db.query(Item).all()
    inventory_val = sum(it.current_stock * it.purchase_price for it in items)

    # 4. الشيكات برسم التحصيل
    checks_under_coll = db.query(func.sum(Check.amount)).filter(Check.status == "UNDER_COLLECTION").scalar() or 0.0

    # 5. صافي الأرباح وقائمة الدخل
    income_stmt = reporting.get_income_statement()

    return jsonify({
        "total_cash": round(total_cash, 2),
        "total_receivables": round(total_receivables, 2),
        "inventory_value": round(inventory_val, 2),
        "checks_under_collection": round(checks_under_coll, 2),
        "total_revenue": income_stmt["total_revenue"],
        "net_profit": income_stmt["net_profit"],
        "operating_expenses": income_stmt["operating_expenses"]
    })

# ==========================================
#         CHART OF ACCOUNTS APIS
# ==========================================

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    accounts = request.db.query(Account).order_by(Account.code.asc()).all()
    return jsonify([acc.to_dict() for acc in accounts])

@app.route('/api/currencies', methods=['GET'])
def get_currencies():
    currencies = request.db.query(Currency).all()
    return jsonify([c.to_dict() for c in currencies])

# ==========================================
#             CONTACTS APIS
# ==========================================

@app.route('/api/contacts', methods=['GET', 'POST'])
def manage_contacts():
    db = request.db
    if request.method == 'POST':
        data = request.json or {}
        name = data.get('name')
        if not name:
            return jsonify({"error": "اسم جهة التعامل مطلوب"}), 400

        c_type = data.get('type', 'عميل')
        contact = Contact(
            name=name,
            type=c_type,
            tax_number=data.get('tax_number'),
            phone=data.get('phone'),
            email=data.get('email'),
            city=data.get('city', 'رام الله'),
            credit_limit=float(data.get('credit_limit', 0.0))
        )
        db.add(contact)
        db.commit()
        return jsonify({"message": "تم إضافة جهة التعامل بنجاح", "id": contact.id}), 201

    c_type = request.args.get('type')
    query = db.query(Contact)
    if c_type:
        query = query.filter(Contact.type == c_type)
    contacts = query.order_by(Contact.name.asc()).all()
    return jsonify([c.to_dict() for c in contacts])

# ==========================================
#             VOUCHERS APIS
# ==========================================

@app.route('/api/vouchers', methods=['GET', 'POST'])
def manage_vouchers():
    service = VoucherService(request.db)
    if request.method == 'POST':
        data = request.json or {}
        try:
            v_id = service.create_voucher(
                v_type=data.get('type', 'Receipt'),
                description=data.get('description', ''),
                lines_data=data.get('lines', []),
                total_amount=float(data.get('total_amount', 0.0)),
                currency=data.get('currency', 'ILS'),
                rate=float(data.get('exchange_rate', 1.0)),
                contact_id=data.get('contact_id')
            )
            voucher = service.get_voucher_by_id(v_id)
            return jsonify({"message": "تم إصدار وترحيل السند بنجاح", "voucher": voucher.to_dict()}), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    v_type = request.args.get('type')
    vouchers_list = service.get_all_vouchers(v_type=v_type)
    return jsonify([v.to_dict() for v in vouchers_list])

# ==========================================
#             INVOICES & POS APIS
# ==========================================

@app.route('/api/invoices', methods=['GET', 'POST'])
def manage_invoices():
    service = InvoiceService(request.db)
    if request.method == 'POST':
        data = request.json or {}
        try:
            inv_id = service.create_invoice(
                inv_type=data.get('type', 'Sales'),
                contact_id=data.get('contact_id'),
                items_data=data.get('items', []),
                payment_method=data.get('payment_method', 'Cash'),
                currency=data.get('currency', 'ILS'),
                rate=float(data.get('exchange_rate', 1.0)),
                notes=data.get('notes')
            )
            inv = service.get_invoice_by_id(inv_id)
            return jsonify({"message": "تم إصدار الفاتورة وترحيل القيود وتحديث المخزون بنجاح", "invoice": inv.to_dict()}), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    inv_type = request.args.get('type')
    invoices_list = service.get_all_invoices(inv_type=inv_type)
    return jsonify([inv.to_dict() for inv in invoices_list])

# ==========================================
#            INVENTORY APIS
# ==========================================

@app.route('/api/inventory/items', methods=['GET', 'POST'])
def manage_inventory():
    service = InventoryService(request.db)
    if request.method == 'POST':
        data = request.json or {}
        try:
            item_id = service.create_item(
                sku=data.get('sku'),
                name_ar=data.get('name_ar'),
                name_en=data.get('name_en'),
                category=data.get('category', 'عام'),
                unit=data.get('unit', 'قطعة'),
                purchase_price=float(data.get('purchase_price', 0.0)),
                sale_price=float(data.get('sale_price', 0.0)),
                initial_stock=float(data.get('initial_stock', 0.0)),
                min_stock=float(data.get('min_stock_level', 5.0))
            )
            return jsonify({"message": "تم إضافة الصنف بنجاح", "id": item_id}), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    items = service.get_all_items()
    return jsonify([it.to_dict() for it in items])

@app.route('/api/inventory/count', methods=['POST'])
def inventory_count():
    service = InventoryService(request.db)
    data = request.json or {}
    try:
        diff = service.perform_inventory_count(
            item_id=int(data.get('item_id')),
            warehouse_id=int(data.get('warehouse_id', 1)),
            actual_qty=float(data.get('actual_qty', 0.0))
        )
        return jsonify({"message": f"تمت تسوية الجرد المخزني. الفارق المسجل: {diff} وحدة", "difference": diff})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ==========================================
#          BANKING & CHECKS APIS
# ==========================================

@app.route('/api/banking/checks', methods=['GET', 'POST'])
def manage_checks():
    service = BankingService(request.db)
    if request.method == 'POST':
        data = request.json or {}
        try:
            c_type = data.get('type', 'Incoming')
            due_date = datetime.datetime.strptime(data.get('due_date'), "%Y-%m-%d")
            if c_type == 'Incoming':
                check_id = service.receive_check(
                    check_no=data.get('check_number'),
                    drawer_name=data.get('drawer_name', 'زبون'),
                    amount=float(data.get('amount', 0.0)),
                    currency=data.get('currency', 'ILS'),
                    due_date=due_date,
                    contact_id=data.get('contact_id'),
                    bank_name=data.get('bank_name', 'بنك فلسطين'),
                    rate=float(data.get('exchange_rate', 1.0))
                )
            else:
                check_id = service.issue_check(
                    check_no=data.get('check_number'),
                    beneficiary_name=data.get('beneficiary_name', 'مورد'),
                    amount=float(data.get('amount', 0.0)),
                    currency=data.get('currency', 'ILS'),
                    due_date=due_date,
                    vendor_id=data.get('contact_id'),
                    rate=float(data.get('exchange_rate', 1.0))
                )
            return jsonify({"message": "تم تسجيل الشيك وترحيل قيده بنجاح", "id": check_id}), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    status = request.args.get('status')
    c_type = request.args.get('type')
    checks = service.get_all_checks(status=status, check_type=c_type)
    return jsonify([c.to_dict() for c in checks])

@app.route('/api/banking/checks/<int:check_id>/action', methods=['POST'])
def check_action(check_id):
    service = BankingService(request.db)
    data = request.json or {}
    action = data.get('action') # 'clear', 'return', 'endorse'
    try:
        if action == 'clear':
            service.clear_check(check_id, actual_rate=data.get('actual_rate'))
            return jsonify({"message": "تم تحصيل/صرف الشيك بالبنك بنجاح"})
        elif action == 'return':
            service.return_check(check_id, reason=data.get('reason', 'رصيد غير كافٍ'))
            return jsonify({"message": "تم إثبات ارتجاع الشيك وإعادة الذمة بنجاح"})
        elif action == 'endorse':
            vendor_id = int(data.get('vendor_id'))
            service.endorse_check(check_id, vendor_id=vendor_id)
            return jsonify({"message": "تم تجيير الشيك بنجاح لصالح المورد"})
        else:
            return jsonify({"error": "إجراء غير معروف"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ==========================================
#               LOANS APIS
# ==========================================

@app.route('/api/loans', methods=['GET', 'POST'])
def manage_loans():
    service = LoanService(request.db)
    if request.method == 'POST':
        data = request.json or {}
        try:
            loan_id = service.create_loan(
                amount=float(data.get('loan_amount')),
                rate=float(data.get('interest_rate')),
                term=int(data.get('term_months')),
                loan_type=data.get('loan_type', 'Fixed'),
                borrower_name=data.get('borrower_name', 'الشركة')
            )
            return jsonify({"message": "تم إنشاء القرض واعتماد جدول السداد وترحيل قيد الاستلام بنجاح", "id": loan_id}), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    loans_list = service.get_all_loans()
    return jsonify([l.to_dict() for l in loans_list])

@app.route('/api/loans/preview', methods=['POST'])
def loan_preview():
    service = LoanService(request.db)
    data = request.json or {}
    try:
        sched = service.calculate_schedule_preview(
            amount=data.get('loan_amount', 0),
            rate=data.get('interest_rate', 0),
            term=data.get('term_months', 1),
            loan_type=data.get('loan_type', 'Fixed')
        )
        return jsonify({"schedule": sched})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/loans/schedule/<int:schedule_id>/pay', methods=['POST'])
def pay_loan_installment(schedule_id):
    service = LoanService(request.db)
    try:
        success = service.mark_payment_as_paid(schedule_id)
        if success:
            return jsonify({"message": "تم سداد قسط القرض وترحيل قيد السداد والفوائد بنجاح"})
        return jsonify({"error": "تعذر سداد القسط أو تم سداده مسبقاً"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ==========================================
#             REPORTS APIS
# ==========================================

@app.route('/api/reports/<rep_type>')
def get_report(rep_type):
    reporting = ReportingService(request.db)
    if rep_type == 'trial_balance':
        return jsonify(reporting.get_trial_balance())
    elif rep_type == 'income_statement':
        return jsonify(reporting.get_income_statement())
    elif rep_type == 'balance_sheet':
        return jsonify(reporting.get_balance_sheet())
    elif rep_type == 'comparative':
        return jsonify(reporting.get_comparative_monthly_report())
    elif rep_type == 'journal':
        return jsonify(reporting.get_general_journal())
    elif rep_type == 'ledger':
        acc = request.args.get('account', '1111')
        return jsonify(reporting.get_general_ledger(acc))
    return jsonify({"error": "التقرير غير موجود"}), 404

# ==========================================
#            AI ASSISTANT API
# ==========================================

@app.route('/api/ai/process', methods=['POST'])
def ai_process():
    data = request.json or {}
    user_query = data.get('query', '')
    bridge = AIFinancialBridge(request.db)
    response = bridge.process_natural_language(user_query)
    return jsonify(response)

# ==========================================
#          SYSTEM ADMINISTRATION
# ==========================================

@app.route('/api/system/seed', methods=['POST'])
def reseed_database():
    seed_database(request.db)
    return jsonify({"message": "تم تهيئة دليل الحسابات والبيانات التأسيسية بنجاح"})

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
