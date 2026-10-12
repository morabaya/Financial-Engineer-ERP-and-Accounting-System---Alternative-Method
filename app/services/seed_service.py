import hashlib
from sqlalchemy.orm import Session
from app.models.financials import Account, AccountType, Currency
from app.models.contacts import Contact, ContactType
from app.models.inventory import Warehouse, Item
from app.models.users import User, Role

def seed_database(db: Session):
    """تهيئة قاعدة البيانات بالبيانات التأسيسية القياسية للنظام المحاسبي"""
    
    # 1. تهيئة العملات (العملة الأساسية: الشيكل ILS)
    currencies_data = [
        {"code": "ILS", "name_ar": "شيكل إسرائيلي جديد", "name_en": "Israeli New Shekel", "symbol": "₪", "is_base": True, "rate_to_base": 1.0},
        {"code": "USD", "name_ar": "دولار أمريكي", "name_en": "US Dollar", "symbol": "$", "is_base": False, "rate_to_base": 3.65},
        {"code": "JOD", "name_ar": "دينار أردني", "name_en": "Jordanian Dinar", "symbol": "JD", "is_base": False, "rate_to_base": 5.15},
        {"code": "EUR", "name_ar": "يورو أوروبي", "name_en": "Euro", "symbol": "€", "is_base": False, "rate_to_base": 3.95},
    ]
    for c_data in currencies_data:
        curr = db.query(Currency).filter(Currency.code == c_data["code"]).first()
        if not curr:
            curr = Currency(**c_data)
            db.add(curr)
    db.commit()

    # 2. تهيئة دليل الحسابات القياسي المتكامل (Chart of Accounts)
    coa_data = [
        # --- الأصول (ASSETS) ---
        {"code": "1", "name_ar": "الأصول", "name_en": "Assets", "type": AccountType.ASSET, "level": 1, "is_leaf": False, "parent_code": None},
        {"code": "11", "name_ar": "الأصول المتداولة", "name_en": "Current Assets", "type": AccountType.ASSET, "level": 2, "is_leaf": False, "parent_code": "1"},
        {"code": "111", "name_ar": "النقدية والبنوك", "name_en": "Cash & Banks", "type": AccountType.ASSET, "level": 3, "is_leaf": False, "parent_code": "11"},
        {"code": "1111", "name_ar": "الصندوق الرئيسي (كاش)", "name_en": "Main Cashbox", "type": AccountType.ASSET, "level": 4, "is_leaf": True, "parent_code": "111"},
        {"code": "1112", "name_ar": "بنك فلسطين - جاري شيكل", "name_en": "Bank of Palestine - ILS", "type": AccountType.ASSET, "level": 4, "is_leaf": True, "parent_code": "111"},
        {"code": "1113", "name_ar": "بنك فلسطين - جاري دولار", "name_en": "Bank of Palestine - USD", "type": AccountType.ASSET, "level": 4, "is_leaf": True, "parent_code": "111"},
        {"code": "1114", "name_ar": "البنك العربي - جاري دينار", "name_en": "Arab Bank - JOD", "type": AccountType.ASSET, "level": 4, "is_leaf": True, "parent_code": "111"},
        {"code": "1115", "name_ar": "شيكات برسم التحصيل", "name_en": "Checks Under Collection", "type": AccountType.ASSET, "level": 4, "is_leaf": True, "parent_code": "111"},
        
        {"code": "112", "name_ar": "الذمم المدينة والعملاء", "name_en": "Accounts Receivable", "type": AccountType.ASSET, "level": 3, "is_leaf": False, "parent_code": "11"},
        {"code": "1121", "name_ar": "حسابات الزبائن والعملاء", "name_en": "Customers Ledger", "type": AccountType.ASSET, "level": 4, "is_leaf": True, "parent_code": "112"},
        {"code": "1122", "name_ar": "سلف وعهد الموظفين", "name_en": "Staff Advances", "type": AccountType.ASSET, "level": 4, "is_leaf": True, "parent_code": "112"},
        
        {"code": "113", "name_ar": "المخزون السلعي", "name_en": "Inventory", "type": AccountType.ASSET, "level": 3, "is_leaf": False, "parent_code": "11"},
        {"code": "1131", "name_ar": "مخزون بضاعة المستودع الرئيسي", "name_en": "Main Warehouse Stock", "type": AccountType.ASSET, "level": 4, "is_leaf": True, "parent_code": "113"},
        
        {"code": "12", "name_ar": "الأصول غير المتداولة (الثابتة)", "name_en": "Fixed Assets", "type": AccountType.ASSET, "level": 2, "is_leaf": False, "parent_code": "1"},
        {"code": "121", "name_ar": "الأثاث والديكور والتجهيزات", "name_en": "Furniture & Fixtures", "type": AccountType.ASSET, "level": 3, "is_leaf": True, "parent_code": "12"},
        {"code": "122", "name_ar": "أجهزة الكمبيوتر والتقنية", "name_en": "Computer Equipment", "type": AccountType.ASSET, "level": 3, "is_leaf": True, "parent_code": "12"},
        {"code": "123", "name_ar": "مجمع إهتلاك الأصول الثابتة", "name_en": "Accumulated Depreciation", "type": AccountType.ASSET, "level": 3, "is_leaf": True, "parent_code": "12"},

        # --- الخصوم والالتزامات (LIABILITIES) ---
        {"code": "2", "name_ar": "الخصوم والالتزامات", "name_en": "Liabilities", "type": AccountType.LIABILITY, "level": 1, "is_leaf": False, "parent_code": None},
        {"code": "21", "name_ar": "الخصوم المتداولة", "name_en": "Current Liabilities", "type": AccountType.LIABILITY, "level": 2, "is_leaf": False, "parent_code": "2"},
        {"code": "211", "name_ar": "الذمم الدائنة والموردين", "name_en": "Accounts Payable", "type": AccountType.LIABILITY, "level": 3, "is_leaf": False, "parent_code": "21"},
        {"code": "2111", "name_ar": "حسابات الموردين التجاريين", "name_en": "Vendors Ledger", "type": AccountType.LIABILITY, "level": 4, "is_leaf": True, "parent_code": "211"},
        
        {"code": "212", "name_ar": "الضرائب والرسوم المستحقة", "name_en": "Accrued Taxes", "type": AccountType.LIABILITY, "level": 3, "is_leaf": False, "parent_code": "21"},
        {"code": "2121", "name_ar": "أمانات ضريبة القيمة المضافة 16% (مخرجات)", "name_en": "VAT Output Payable 16%", "type": AccountType.LIABILITY, "level": 4, "is_leaf": True, "parent_code": "212"},
        {"code": "2122", "name_ar": "ضريبة القيمة المضافة مدخلات قابلة للاسترداد", "name_en": "VAT Input Recoverable", "type": AccountType.LIABILITY, "level": 4, "is_leaf": True, "parent_code": "212"},
        {"code": "2123", "name_ar": "ضريبة الدخل والرواتب المقتطعة", "name_en": "Income Tax Withholding", "type": AccountType.LIABILITY, "level": 4, "is_leaf": True, "parent_code": "212"},
        
        {"code": "213", "name_ar": "شيكات صادرة مؤجلة الدفع", "name_en": "Post-Dated Checks Outgoing", "type": AccountType.LIABILITY, "level": 3, "is_leaf": True, "parent_code": "21"},
        {"code": "22", "name_ar": "الخصوم غير المتداولة (طويلة الأجل)", "name_en": "Long-term Liabilities", "type": AccountType.LIABILITY, "level": 2, "is_leaf": False, "parent_code": "2"},
        {"code": "221", "name_ar": "قروض وتسهيلات بنكية طويلة الأجل", "name_en": "Long-term Bank Loans", "type": AccountType.LIABILITY, "level": 3, "is_leaf": True, "parent_code": "22"},

        # --- حقوق الملكية (EQUITY) ---
        {"code": "3", "name_ar": "حقوق الملكية", "name_en": "Equity", "type": AccountType.EQUITY, "level": 1, "is_leaf": False, "parent_code": None},
        {"code": "31", "name_ar": "رأس المال المدفوع", "name_en": "Paid-in Capital", "type": AccountType.EQUITY, "level": 2, "is_leaf": True, "parent_code": "3"},
        {"code": "32", "name_ar": "الأرباح المحتجزة / المدورة", "name_en": "Retained Earnings", "type": AccountType.EQUITY, "level": 2, "is_leaf": True, "parent_code": "3"},
        {"code": "33", "name_ar": "جاري الشركاء والمسحوبات الشخصية", "name_en": "Partner Drawings", "type": AccountType.EQUITY, "level": 2, "is_leaf": True, "parent_code": "3"},
        {"code": "34", "name_ar": "أرباح وخسائر العام الحالي", "name_en": "Current Period P&L", "type": AccountType.EQUITY, "level": 2, "is_leaf": True, "parent_code": "3"},

        # --- الإيرادات (REVENUE) ---
        {"code": "4", "name_ar": "الإيرادات", "name_en": "Revenues", "type": AccountType.REVENUE, "level": 1, "is_leaf": False, "parent_code": None},
        {"code": "41", "name_ar": "إيرادات النشاط التشغيلي", "name_en": "Operating Revenues", "type": AccountType.REVENUE, "level": 2, "is_leaf": False, "parent_code": "4"},
        {"code": "411", "name_ar": "إيرادات المبيعات", "name_en": "Sales Revenue", "type": AccountType.REVENUE, "level": 3, "is_leaf": True, "parent_code": "41"},
        {"code": "412", "name_ar": "مردودات ومسموحات المبيعات", "name_en": "Sales Returns & Allowances", "type": AccountType.REVENUE, "level": 3, "is_leaf": True, "parent_code": "41"},
        {"code": "413", "name_ar": "الخصم المسموح به", "name_en": "Sales Discounts Given", "type": AccountType.REVENUE, "level": 3, "is_leaf": True, "parent_code": "41"},
        
        {"code": "42", "name_ar": "إيرادات أخرى وفرق العملة", "name_en": "Other Revenues", "type": AccountType.REVENUE, "level": 2, "is_leaf": False, "parent_code": "4"},
        {"code": "421", "name_ar": "أرباح فروقات أسعار الصرف", "name_en": "Foreign Exchange Gains", "type": AccountType.REVENUE, "level": 3, "is_leaf": True, "parent_code": "42"},
        {"code": "422", "name_ar": "إيرادات وعوائد استثنائية", "name_en": "Miscellaneous Income", "type": AccountType.REVENUE, "level": 3, "is_leaf": True, "parent_code": "42"},

        # --- المصروفات وتكلفة البضاعة (EXPENSES) ---
        {"code": "5", "name_ar": "المصروفات وتكلفة النشاط", "name_en": "Expenses", "type": AccountType.EXPENSE, "level": 1, "is_leaf": False, "parent_code": None},
        {"code": "51", "name_ar": "تكلفة البضاعة المباعة (المشتريات)", "name_en": "Cost of Goods Sold", "type": AccountType.EXPENSE, "level": 2, "is_leaf": False, "parent_code": "5"},
        {"code": "511", "name_ar": "تكلفة المبيعات (COGS)", "name_en": "Cost of Sales", "type": AccountType.EXPENSE, "level": 3, "is_leaf": True, "parent_code": "51"},
        {"code": "512", "name_ar": "مشتريات بضاعة بغرض البيع", "name_en": "Goods Purchases", "type": AccountType.EXPENSE, "level": 3, "is_leaf": True, "parent_code": "51"},
        {"code": "513", "name_ar": "مردودات ومسموحات المشتريات", "name_en": "Purchase Returns", "type": AccountType.EXPENSE, "level": 3, "is_leaf": True, "parent_code": "51"},
        {"code": "514", "name_ar": "الخصم المكتسب", "name_en": "Purchase Discounts Received", "type": AccountType.EXPENSE, "level": 3, "is_leaf": True, "parent_code": "51"},
        
        {"code": "52", "name_ar": "المصروفات التشغيلية والعمومية", "name_en": "Operating Expenses", "type": AccountType.EXPENSE, "level": 2, "is_leaf": False, "parent_code": "5"},
        {"code": "521", "name_ar": "رواتب وأجور الموظفين", "name_en": "Salaries & Wages", "type": AccountType.EXPENSE, "level": 3, "is_leaf": True, "parent_code": "52"},
        {"code": "522", "name_ar": "إيجار المعارض والمكاتب", "name_en": "Rent Expense", "type": AccountType.EXPENSE, "level": 3, "is_leaf": True, "parent_code": "52"},
        {"code": "523", "name_ar": "كهرباء ومياه وإنترنت", "name_en": "Utilities & Communication", "type": AccountType.EXPENSE, "level": 3, "is_leaf": True, "parent_code": "52"},
        {"code": "524", "name_ar": "مصاريف شحن وتوزيع ومحروقات", "name_en": "Shipping & Transport", "type": AccountType.EXPENSE, "level": 3, "is_leaf": True, "parent_code": "52"},
        {"code": "525", "name_ar": "مصاريف صيانة ونظافة وضيافة", "name_en": "Office Maintenance & Hospitality", "type": AccountType.EXPENSE, "level": 3, "is_leaf": True, "parent_code": "52"},
        
        {"code": "53", "name_ar": "المصروفات المالية والخسائر", "name_en": "Financial Expenses", "type": AccountType.EXPENSE, "level": 2, "is_leaf": False, "parent_code": "5"},
        {"code": "531", "name_ar": "فوائد بنكية وقروض", "name_en": "Bank & Loan Interest Expense", "type": AccountType.EXPENSE, "level": 3, "is_leaf": True, "parent_code": "53"},
        {"code": "532", "name_ar": "عمولات ورسوم مصرفية", "name_en": "Bank Service Charges", "type": AccountType.EXPENSE, "level": 3, "is_leaf": True, "parent_code": "53"},
        {"code": "533", "name_ar": "خسائر فروقات أسعار الصرف", "name_en": "Foreign Exchange Losses", "type": AccountType.EXPENSE, "level": 3, "is_leaf": True, "parent_code": "53"}
    ]

    # حفظ الحسابات بالترتيب مع ربط الأب
    code_to_id = {}
    for item in coa_data:
        acc = db.query(Account).filter(Account.code == item["code"]).first()
        parent_id = code_to_id.get(item["parent_code"]) if item["parent_code"] else None
        if not acc:
            acc = Account(
                code=item["code"],
                name_ar=item["name_ar"],
                name_en=item["name_en"],
                type=item["type"],
                level=item["level"],
                is_leaf=item["is_leaf"],
                parent_id=parent_id,
                currency="ILS",
                is_active=True
            )
            db.add(acc)
            db.flush()
        else:
            # تحديث الأب وخصائص الحساب
            acc.name_ar = item["name_ar"]
            acc.name_en = item["name_en"]
            acc.is_leaf = item["is_leaf"]
            acc.parent_id = parent_id
            db.flush()
        code_to_id[item["code"]] = acc.id
    db.commit()

    # 3. تهيئة المستودع الافتراضي
    wh = db.query(Warehouse).first()
    if not wh:
        wh = Warehouse(name="المستودع الرئيسي - رام الله", location="المنطقة الصناعية، رام الله", is_default=1)
        db.add(wh)
        db.commit()

    # 4. تهيئة جهات التعامل الافتراضية
    cust_acc = db.query(Account).filter(Account.code == "1121").first()
    vend_acc = db.query(Account).filter(Account.code == "2111").first()

    default_contacts = [
        {"name": "زبون نقدي عام", "type": ContactType.CUSTOMER, "tax_number": "000000000", "phone": "0599000000", "city": "رام الله", "account_id": cust_acc.id if cust_acc else None},
        {"name": "شركة القدس للتجارة العامة", "type": ContactType.CUSTOMER, "tax_number": "901234567", "phone": "0599123456", "city": "القدس", "account_id": cust_acc.id if cust_acc else None},
        {"name": "شركة الموردين الدولية للتوريدات", "type": ContactType.SUPPLIER, "tax_number": "987654321", "phone": "0598765432", "city": "نابلس", "account_id": vend_acc.id if vend_acc else None},
    ]
    for c_info in default_contacts:
        contact = db.query(Contact).filter(Contact.name == c_info["name"]).first()
        if not contact:
            contact = Contact(**c_info)
            db.add(contact)
    db.commit()

    # 5. تهيئة أصناف تجريبية بالمخزن
    sample_items = [
        {"sku": "PRD-001", "name_ar": "شاشة كمبيوتر Dell 27 بوصة IPS 4K", "category": "إلكترونيات", "purchase_price": 850.0, "sale_price": 1200.0, "current_stock": 25.0, "min_stock_level": 5.0},
        {"sku": "PRD-002", "name_ar": "لابتوب HP ProBook Core i7 16GB", "category": "أجهزة حاسوب", "purchase_price": 2800.0, "sale_price": 3500.0, "current_stock": 10.0, "min_stock_level": 3.0},
        {"sku": "PRD-003", "name_ar": "طابعة فواتير حرارية حرارية USB/LAN", "category": "نقطة بيع POS", "purchase_price": 320.0, "sale_price": 480.0, "current_stock": 30.0, "min_stock_level": 5.0},
        {"sku": "PRD-004", "name_ar": "قارئ باركود ليزري لاسلكي 2D", "category": "نقطة بيع POS", "purchase_price": 120.0, "sale_price": 220.0, "current_stock": 40.0, "min_stock_level": 8.0},
    ]
    for itm_info in sample_items:
        itm = db.query(Item).filter(Item.sku == itm_info["sku"]).first()
        if not itm:
            itm = Item(**itm_info)
            db.add(itm)
    db.commit()

    # 6. تهيئة الأدوار والمستخدمين
    roles_list = [
        {"name": "Admin", "description": "مدير النظام بكامل الصلاحيات المالية والإدارية"},
        {"name": "Accountant", "description": "محاسب: إنشاء السندات، قيود اليومية، التقارير المالية"},
        {"name": "Cashier", "description": "كاشير: نقطة البيع وفواتير المبيعات وسندات القبض النقدية"}
    ]
    for r_data in roles_list:
        role = db.query(Role).filter(Role.name == r_data["name"]).first()
        if not role:
            role = Role(**r_data)
            db.add(role)
    db.commit()

    admin_role = db.query(Role).filter(Role.name == "Admin").first()
    admin_user = db.query(User).filter(User.username == "admin").first()
    if not admin_user:
        # Default password: admin123 (SHA-256 for simplicity)
        pwd_hash = hashlib.sha256("admin123".encode()).hexdigest()
        admin_user = User(
            username="admin",
            password_hash=pwd_hash,
            full_name="المدير المالي الرئيسي",
            email="admin@financial-engineer.local",
            language="ar",
            is_active=1
        )
        if admin_role:
            admin_user.roles.append(admin_role)
        db.add(admin_user)
        db.commit()

    return True
