import re
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.services.voucher_service import VoucherService
from app.services.invoice_service import InvoiceService
from app.services.reporting_service import ReportingService
from app.services.loan_service import LoanService
from app.services.inventory_service import InventoryService
from app.models.contacts import Contact
from app.models.inventory import Item

class AIFinancialBridge:
    def __init__(self, db: Session):
        self.db = db
        self.vouchers = VoucherService(db)
        self.invoices = InvoiceService(db)
        self.reports = ReportingService(db)
        self.loans = LoanService(db)
        self.inventory = InventoryService(db)

    def process_natural_language(self, user_query: str) -> dict:
        """
        معالج الأوامر الذكي باللغة الطبيعية (Arabic/English NLP & Function Calling):
        يحول نية المستخدم مباشرة إلى إجراءات مالية أو تقارير تحليلية فورية.
        """
        query = user_query.strip().lower()

        # 1. طلب تقرير ميزان المراجعة
        if "ميزان المراجعة" in query or "trial balance" in query:
            tb = self.reports.get_trial_balance()
            acc_list = tb.get("accounts", [])[:5]
            summary_lines = [f"• {a['name']} ({a['code']}): مدين {a['net_debit']:,} | دائن {a['net_credit']:,} ₪" for a in acc_list]
            msg = (
                f"📊 <b>ميزان المراجعة:</b><br>"
                f"• إجمالي المدين: <b>{tb['total_debit']:,.2f} ₪</b><br>"
                f"• إجمالي الدائن: <b>{tb['total_credit']:,.2f} ₪</b><br>"
                f"• حالة التوازن: {'✅ متوازن تماماً' if tb['is_balanced'] else '⚠️ غير متوازن'}<br><br>"
                f"<b>أبرز الحسابات:</b><br>" + "<br>".join(summary_lines)
            )
            return {"reply": msg, "data": tb}

        # 2. طلب قائمة الدخل / الأرباح والخسائر
        if "قائمة الدخل" in query or "الأرباح" in query or "صافي الربح" in query or "income statement" in query or "p&l" in query:
            inc = self.reports.get_income_statement()
            msg = (
                f"📈 <b>قائمة الدخل والأرباح:</b><br>"
                f"• إجمالي المبيعات والإيرادات: <b>{inc['total_revenue']:,.2f} ₪</b><br>"
                f"• تكلفة المبيعات (COGS): <b>{inc['cogs']:,.2f} ₪</b><br>"
                f"• مجمل الربح: <b>{inc['gross_profit']:,.2f} ₪</b><br>"
                f"• المصروفات التشغيلية: <b>{inc['operating_expenses']:,.2f} ₪</b><br>"
                f"• المصروفات المالية والفوائد: <b>{inc['financial_expenses']:,.2f} ₪</b><br>"
                f"━━━━━━━━━━━━━━━<br>"
                f"• <b>صافي الربح النهائي: {inc['net_profit']:,.2f} ₪</b> {'🎉' if inc['net_profit'] >= 0 else '🔻'}"
            )
            return {"reply": msg, "data": inc}

        # 3. طلب الميزانية العمومية / المركز المالي
        if "الميزانية" in query or "المركز المالي" in query or "balance sheet" in query:
            bs = self.reports.get_balance_sheet()
            msg = (
                f"🏛️ <b>الميزانية العمومية:</b><br>"
                f"• إجمالي الأصول: <b>{bs['total_assets']:,.2f} ₪</b><br>"
                f"• إجمالي الخصوم: <b>{bs['total_liabilities']:,.2f} ₪</b><br>"
                f"• حقوق الملكية (مع أرباح الفترة): <b>{bs['total_equity']:,.2f} ₪</b><br>"
                f"• الخصوم + حقوق الملكية: <b>{bs['total_liabilities_and_equity']:,.2f} ₪</b><br>"
                f"• المعادلة المحاسبية: {'✅ الأصول = الخصوم + حقوق الملكية (متطابقة)' if bs['is_balanced'] else '⚠️ يوجد فارق: ' + str(bs['difference'])}"
            )
            return {"reply": msg, "data": bs}

        # 4. تحليل: أكبر المدينين / الذمم المدينة
        if "أعلى المدينين" in query or "أكبر العملاء" in query or "الديون" in query or "debtors" in query:
            top_debtors = self.db.query(Contact).filter(Contact.current_balance > 0).order_by(desc(Contact.current_balance)).limit(5).all()
            if not top_debtors:
                return {"reply": "لا توجد ذمم مدينة مستحقة على العملاء حالياً."}
            lines = [f"{i+1}. {c.name}: <b>{c.current_balance:,.2f} ₪</b> (هاتف: {c.phone or 'غير مسجل'})" for i, c in enumerate(top_debtors)]
            return {"reply": "📋 <b>أعلى العملاء المدينين للشركة:</b><br>" + "<br>".join(lines)}

        # 5. تنبيهات المخزون / النواقص
        if "نواقص" in query or "مخزون منخفض" in query or "أوشكت على النفاد" in query or "low stock" in query:
            low_items = self.db.query(Item).filter(Item.current_stock <= Item.min_stock_level).all()
            if not low_items:
                return {"reply": "✅ جميع الأصناف في المستودع مستوياتها آمنة وفوق حد إعادة الطلب."}
            lines = [f"• {it.name_ar} (SKU: {it.sku}): متوفر <b>{it.current_stock}</b> فقط (حد الأمان: {it.min_stock_level})" for it in low_items]
            return {"reply": "⚠️ <b>أصناف وصلت للحد الأدنى من المخزون:</b><br>" + "<br>".join(lines)}

        # 6. تنفيذ سند صرف ذكي (سند صرف بمبلغ X لـ Y)
        if "سند صرف" in query or "payment voucher" in query:
            amount_match = re.search(r'(\d+(?:\.\d+)?)', query)
            amount = float(amount_match.group(1)) if amount_match else 250.0

            # تصنيف الحساب المستهدف ذكياً
            target_acc = "525" # مصاريف عامة افتراضياً
            desc = "مصروف تشغيلي عبر المساعد الذكي"
            if "إيجار" in query or "ايجار" in query:
                target_acc = "522"
                desc = "سداد إيجار مقر"
            elif "راتب" in query or "رواتب" in query:
                target_acc = "521"
                desc = "صرف رواتب وأجور"
            elif "كهرباء" in query or "مياه" in query or "انترنت" in query:
                target_acc = "523"
                desc = "سداد فواتير خدمات ومرافق"
            elif "صيانة" in query:
                target_acc = "525"
                desc = "مصاريف صيانة ونظافة"

            v_lines = [
                {'account_code': target_acc, 'debit': amount, 'credit': 0.0},
                {'account_code': "1111", 'debit': 0.0, 'credit': amount} # الصندوق الرئيسي
            ]
            v_id = self.vouchers.create_voucher(
                v_type="Payment",
                description=desc,
                lines_data=v_lines,
                total_amount=amount,
                currency="ILS"
            )
            v_obj = self.vouchers.get_voucher_by_id(v_id)
            return {
                "reply": f"✅ <b>تم إنشاء وترحيل سند الصرف بنجاح!</b><br>• رقم السند: <b>{v_obj.voucher_no}</b><br>• المبلغ: <b>{amount:,.2f} ₪</b><br>• البيان: {desc}<br>• القيد المحاسبي: مدين حـ/ المصروف، دائن حـ/ الصندوق."
            }

        # 7. تنفيذ سند قبض ذكي (سند قبض بمبلغ X)
        if "سند قبض" in query or "receipt voucher" in query:
            amount_match = re.search(r'(\d+(?:\.\d+)?)', query)
            amount = float(amount_match.group(1)) if amount_match else 500.0

            v_lines = [
                {'account_code': "1111", 'debit': amount, 'credit': 0.0}, # الصندوق
                {'account_code': "1121", 'debit': 0.0, 'credit': amount}  # العملاء
            ]
            v_id = self.vouchers.create_voucher(
                v_type="Receipt",
                description="دفعة مقبوضة من عميل عبر المساعد الذكي",
                lines_data=v_lines,
                total_amount=amount,
                currency="ILS"
            )
            v_obj = self.vouchers.get_voucher_by_id(v_id)
            return {
                "reply": f"✅ <b>تم إنشاء وترحيل سند القبض بنجاح!</b><br>• رقم السند: <b>{v_obj.voucher_no}</b><br>• المبلغ: <b>{amount:,.2f} ₪</b><br>• القيد المحاسبي: مدين حـ/ الصندوق، دائن حـ/ العملاء."
            }

        # 8. حاسبة قروض استرشادية
        if "قرض" in query or "loan" in query:
            amount_match = re.findall(r'(\d+)', query)
            amount = float(amount_match[0]) if len(amount_match) > 0 else 50000.0
            months = int(amount_match[1]) if len(amount_match) > 1 else 24
            rate = float(amount_match[2]) if len(amount_match) > 2 else 5.0

            sched = self.loans.calculate_schedule_preview(amount, rate, months, "Fixed")
            if sched:
                first_installment = sched[0]["total_payment"]
                total_interest = sum(s["interest_amount"] for s in sched)
                return {
                    "reply": (
                        f"💳 <b>حساب جدول سداد القرض:</b><br>"
                        f"• مبلغ القرض: <b>{amount:,.2f} ₪</b><br>"
                        f"• المدة: <b>{months} شهر</b> | الفائدة السنوية: <b>{rate}%</b><br>"
                        f"• القسط الشهري الثابت: <b>{first_installment:,.2f} ₪</b><br>"
                        f"• إجمالي الفوائد المستحقة: <b>{total_interest:,.2f} ₪</b><br>"
                        f"• إجمالي المبلغ المسدد: <b>{(amount + total_interest):,.2f} ₪</b>"
                    )
                }

        # الإجابة الافتراضية التوجيهية
        return {
            "reply": (
                "👋 أهلاً بك في <b>المساعد المالي الذكي (Financial AI)</b>.<br>"
                "يمكنك توجيه أوامر مباشرة مثل:<br>"
                "• <i>«أريد ميزان المراجعة»</i> أو <i>«قائمة الدخل»</i> أو <i>«الميزانية العمومية»</i><br>"
                "• <i>«أنشئ سند صرف بمبلغ 350 شيكل لمصروف الصيانة»</i><br>"
                "• <i>«أنشئ سند قبض بمبلغ 1200 شيكل»</i><br>"
                "• <i>«من هم أعلى العملاء المدينين؟»</i> أو <i>«ما هي نواقص المخزون؟»</i><br>"
                "• <i>«احسب قرض 20000 لمدة 12 شهر بفائدة 6%»</i>"
            )
        }

    def handle_intent(self, intent, params):
        if intent == "create_voucher":
            return self.vouchers.create_voucher(
                v_type=params.get("type"),
                description=params.get("description"),
                lines_data=params.get("lines"),
                total_amount=params.get("amount"),
                currency=params.get("currency", "ILS"),
                rate=params.get("rate", 1.0)
            )
        elif intent == "get_report":
            report_type = params.get("report_type")
            if report_type == "trial_balance":
                return self.reports.get_trial_balance()
            elif report_type == "income_statement":
                return self.reports.get_income_statement(params.get("start"), params.get("end"))
            elif report_type == "balance_sheet":
                return self.reports.get_balance_sheet()
        return {"error": "Unknown intent"}
