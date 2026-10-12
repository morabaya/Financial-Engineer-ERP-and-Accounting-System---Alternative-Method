import datetime
from sqlalchemy.orm import Session
from app.models.invoices import Invoice, InvoiceItem
from app.models.inventory import Item, StockMovement
from app.models.contacts import Contact
from app.models.vouchers import AuditLog
from app.services.accounting_engine import create_accounting_entry, get_account_by_code

class InvoiceService:
    def __init__(self, db: Session):
        self.db = db

    def _generate_invoice_no(self, inv_type):
        prefixes = {
            'Sales': 'INV',
            'Purchase': 'PUR',
            'Sales_Return': 'SR',
            'Purchase_Return': 'PR'
        }
        prefix = prefixes.get(inv_type, 'INV')
        year = datetime.datetime.utcnow().year
        pattern = f"{prefix}-{year}-%"
        last_inv = self.db.query(Invoice).filter(Invoice.invoice_no.like(pattern)).order_by(Invoice.id.desc()).first()
        if not last_inv:
            return f"{prefix}-{year}-0001"
        try:
            parts = last_inv.invoice_no.split('-')
            last_no = int(parts[2]) if len(parts) >= 3 else int(parts[1])
            return f"{prefix}-{year}-{str(last_no + 1).zfill(4)}"
        except Exception:
            return f"{prefix}-{year}-0001"

    def get_all_invoices(self, inv_type=None, limit=100):
        query = self.db.query(Invoice)
        if inv_type:
            query = query.filter(Invoice.type == inv_type)
        return query.order_by(Invoice.id.desc()).limit(limit).all()

    def get_invoice_by_id(self, invoice_id):
        return self.db.query(Invoice).filter(Invoice.id == invoice_id).first()

    def create_invoice(self, inv_type, contact_id, items_data, payment_method="Credit", currency="ILS", rate=1.0, user_id=1, notes=None):
        """
        إنشاء الفاتورة المحاسبية مع:
        1. تطبيق قانون الضريبة الفلسطيني المعتمد (ضريبة القيمة المضافة 16%)
        2. توليد القيود المزدوجة المتطابقة آلياً
        3. تحريك المخزون وتكلفة البضاعة المباعة (COGS)
        4. ربط حسابات الذمم (الزبائن/الموردين)
        """
        inv_no = self._generate_invoice_no(inv_type)
        invoice = Invoice(
            invoice_no=inv_no,
            type=inv_type,
            contact_id=contact_id,
            payment_method=payment_method,
            currency=currency,
            exchange_rate=float(rate),
            user_id=user_id,
            notes=notes,
            status='Paid' if payment_method == 'Cash' else 'Unpaid'
        )
        self.db.add(invoice)
        self.db.flush()

        total_before_tax = 0.0
        total_tax = 0.0
        cogs_total = 0.0

        for item_data in items_data:
            item_id = item_data.get('item_id')
            qty = float(item_data.get('quantity', 1.0))
            price = float(item_data.get('unit_price', 0.0))
            discount = float(item_data.get('discount', 0.0))
            tax_rate = float(item_data.get('tax_rate', 0.16)) # 16% Palestinian VAT

            line_subtotal = (qty * price) - discount
            line_tax = round(line_subtotal * tax_rate, 2)
            line_total = round(line_subtotal + line_tax, 2)

            item_obj = self.db.query(Item).filter(Item.id == item_id).first() if item_id else None
            item_name = item_data.get('item_name') or (item_obj.name_ar if item_obj else 'بند عام')

            inv_item = InvoiceItem(
                invoice_id=invoice.id,
                item_id=item_id,
                item_name=item_name,
                quantity=qty,
                unit_price=price,
                discount=discount,
                tax_rate=tax_rate,
                tax_amount=line_tax,
                total=line_total
            )
            self.db.add(inv_item)

            total_before_tax += line_subtotal
            total_tax += line_tax

            # تحريك المخزون وحساب تكلفة البضاعة (COGS)
            if item_obj:
                cost_price = item_obj.purchase_price
                if inv_type == 'Sales':
                    item_obj.current_stock -= qty
                    cogs_total += (cost_price * qty)
                    # حركة مخزنية
                    mov = StockMovement(
                        item_id=item_obj.id,
                        warehouse_id=1,
                        quantity=-qty,
                        movement_type='Sale',
                        reference_no=inv_no,
                        cost_per_unit=cost_price,
                        total_cost=cost_price * qty,
                        user_id=user_id
                    )
                    self.db.add(mov)
                elif inv_type == 'Purchase':
                    item_obj.current_stock += qty
                    mov = StockMovement(
                        item_id=item_obj.id,
                        warehouse_id=1,
                        quantity=qty,
                        movement_type='Purchase',
                        reference_no=inv_no,
                        cost_per_unit=price,
                        total_cost=price * qty,
                        user_id=user_id
                    )
                    self.db.add(mov)
                elif inv_type == 'Sales_Return':
                    item_obj.current_stock += qty
                    cogs_total -= (cost_price * qty)
                    mov = StockMovement(
                        item_id=item_obj.id,
                        warehouse_id=1,
                        quantity=qty,
                        movement_type='Sales_Return',
                        reference_no=inv_no,
                        cost_per_unit=cost_price,
                        total_cost=cost_price * qty,
                        user_id=user_id
                    )
                    self.db.add(mov)
                elif inv_type == 'Purchase_Return':
                    item_obj.current_stock -= qty
                    mov = StockMovement(
                        item_id=item_obj.id,
                        warehouse_id=1,
                        quantity=-qty,
                        movement_type='Purchase_Return',
                        reference_no=inv_no,
                        cost_per_unit=price,
                        total_cost=price * qty,
                        user_id=user_id
                    )
                    self.db.add(mov)

        total_after_tax = round(total_before_tax + total_tax, 2)
        invoice.total_before_tax = round(total_before_tax, 2)
        invoice.tax_amount = round(total_tax, 2)
        invoice.total_after_tax = total_after_tax
        if payment_method == 'Cash':
            invoice.paid_amount = total_after_tax

        self.db.commit()

        # إنشاء القيود المحاسبية التلقائية بدقة مطلقة
        # الحسابات القياسية
        cash_acc = get_account_by_code(self.db, "1111")     # الصندوق
        cust_acc = get_account_by_code(self.db, "1121")     # الزبائن
        vend_acc = get_account_by_code(self.db, "2111")     # الموردين
        sales_acc = get_account_by_code(self.db, "411")     # إيرادات المبيعات
        vat_out_acc = get_account_by_code(self.db, "2121")  # ضريبة المخرجات 16%
        purch_acc = get_account_by_code(self.db, "512")     # مشتريات بضاعة
        vat_in_acc = get_account_by_code(self.db, "2122")   # ضريبة المدخلات 16%
        sales_ret_acc = get_account_by_code(self.db, "412") # مردودات المبيعات
        purch_ret_acc = get_account_by_code(self.db, "513") # مردودات المشتريات
        cogs_acc = get_account_by_code(self.db, "511")      # تكلفة المبيعات
        stock_acc = get_account_by_code(self.db, "1131")    # المخزون

        settlement_acc_id = cash_acc.id if payment_method == "Cash" else (cust_acc.id if "Sales" in inv_type else vend_acc.id)

        lines = []
        if inv_type == 'Sales':
            # من حـ/ العميل (أو الصندوق) -> إلى مذكورين: حـ/ المبيعات + حـ/ أمانات ضريبة 16%
            lines.append({'account_id': settlement_acc_id, 'contact_id': contact_id if payment_method != "Cash" else None, 'debit': total_after_tax, 'credit': 0.0, 'note': f"فاتورة مبيعات {inv_no}"})
            lines.append({'account_id': sales_acc.id, 'debit': 0.0, 'credit': round(total_before_tax, 2), 'note': "صافي المبيعات"})
            if total_tax > 0:
                lines.append({'account_id': vat_out_acc.id, 'debit': 0.0, 'credit': round(total_tax, 2), 'note': "ضريبة القيمة المضافة 16%"})

            create_accounting_entry(self.db, f"فاتورة مبيعات رقم {inv_no}", inv_no, lines, currency, rate, source_module="INVOICE", user_id=user_id)

            # قيد تكلفة البضاعة المباعة (COGS)
            if cogs_total > 0:
                cogs_lines = [
                    {'account_id': cogs_acc.id, 'debit': round(cogs_total, 2), 'credit': 0.0, 'note': f"تكلفة مبيعات فاتورة {inv_no}"},
                    {'account_id': stock_acc.id, 'debit': 0.0, 'credit': round(cogs_total, 2), 'note': "صرف بضاعة من المخزن"}
                ]
                create_accounting_entry(self.db, f"إثبات تكلفة البضاعة المباعة للفاتورة {inv_no}", f"COGS-{inv_no}", cogs_lines, currency, rate, source_module="INVENTORY", user_id=user_id)

        elif inv_type == 'Purchase':
            # من مذكورين: حـ/ المشتريات + حـ/ ضريبة المدخلات 16% -> إلى حـ/ المورد (أو الصندوق)
            lines.append({'account_id': purch_acc.id, 'debit': round(total_before_tax, 2), 'credit': 0.0, 'note': f"مشتريات فاتورة {inv_no}"})
            if total_tax > 0:
                lines.append({'account_id': vat_in_acc.id, 'debit': round(total_tax, 2), 'credit': 0.0, 'note': "ضريبة مدخلات 16%"})
            lines.append({'account_id': settlement_acc_id, 'contact_id': contact_id if payment_method != "Cash" else None, 'debit': 0.0, 'credit': total_after_tax, 'note': f"مستحق فاتورة مشتريات {inv_no}"})

            create_accounting_entry(self.db, f"فاتورة مشتريات رقم {inv_no}", inv_no, lines, currency, rate, source_module="INVOICE", user_id=user_id)

        elif inv_type == 'Sales_Return':
            # مردودات مبيعات: عكس قيد المبيعات
            lines.append({'account_id': sales_ret_acc.id, 'debit': round(total_before_tax, 2), 'credit': 0.0, 'note': f"مردود مبيعات {inv_no}"})
            if total_tax > 0:
                lines.append({'account_id': vat_out_acc.id, 'debit': round(total_tax, 2), 'credit': 0.0, 'note': "رد ضريبة القيمة المضافة"})
            lines.append({'account_id': settlement_acc_id, 'contact_id': contact_id, 'debit': 0.0, 'credit': total_after_tax, 'note': f"إشعار دائن لمردود مبيعات {inv_no}"})

            create_accounting_entry(self.db, f"مردود مبيعات رقم {inv_no}", inv_no, lines, currency, rate, source_module="INVOICE", user_id=user_id)

        elif inv_type == 'Purchase_Return':
            # مردودات مشتريات: عكس قيد المشتريات
            lines.append({'account_id': settlement_acc_id, 'contact_id': contact_id, 'debit': total_after_tax, 'credit': 0.0, 'note': f"إشعار مدين لمردود مشتريات {inv_no}"})
            lines.append({'account_id': purch_ret_acc.id, 'debit': 0.0, 'credit': round(total_before_tax, 2), 'note': "مردود مشتريات"})
            if total_tax > 0:
                lines.append({'account_id': vat_in_acc.id, 'debit': 0.0, 'credit': round(total_tax, 2), 'note': "رد ضريبة مدخلات"})

            create_accounting_entry(self.db, f"مردود مشتريات رقم {inv_no}", inv_no, lines, currency, rate, source_module="INVOICE", user_id=user_id)

        audit = AuditLog(
            user_id=user_id,
            action='CREATE_INVOICE',
            table_name='invoices',
            record_id=invoice.id,
            new_value=f"فاتورة {inv_no} ({inv_type}) بإجمالي {total_after_tax} {currency} شاملة الضريبة 16%"
        )
        self.db.add(audit)
        self.db.commit()

        return invoice.id
