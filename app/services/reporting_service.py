from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.financials import Account, JournalEntry, JournalEntryLine, AccountType
from app.models.contacts import Contact
import datetime

class ReportingService:
    def __init__(self, db: Session):
        self.db = db

    def get_general_journal(self, start_date=None, end_date=None, limit=200):
        query = self.db.query(JournalEntry)
        if start_date:
            query = query.filter(JournalEntry.date >= start_date)
        if end_date:
            query = query.filter(JournalEntry.date <= end_date)

        entries = query.order_by(JournalEntry.date.desc(), JournalEntry.id.desc()).limit(limit).all()
        return [entry.to_dict() for entry in entries]

    def get_general_ledger(self, account_identifier, start_date=None, end_date=None):
        """كشف حساب دفتر الأستاذ العام مع رصيد افتتاحي ورصيد تراكمي"""
        if isinstance(account_identifier, str) and not account_identifier.isdigit():
            account = self.db.query(Account).filter(Account.code == account_identifier).first()
        else:
            account = self.db.query(Account).filter(Account.id == int(account_identifier)).first()
            if not account:
                account = self.db.query(Account).filter(Account.code == str(account_identifier)).first()

        if not account:
            return {"error": "الحساب غير موجود"}

        # الرصيد الافتتاحي قبل start_date
        opening_balance = 0.0
        if start_date:
            prev_lines = self.db.query(
                func.sum(JournalEntryLine.debit).label("debit"),
                func.sum(JournalEntryLine.credit).label("credit")
            ).join(JournalEntry).filter(
                JournalEntryLine.account_id == account.id,
                JournalEntry.date < start_date
            ).first()
            if prev_lines and prev_lines[0] is not None:
                opening_balance = float(prev_lines[0] or 0.0) - float(prev_lines[1] or 0.0)

        query = self.db.query(JournalEntryLine).join(JournalEntry).filter(
            JournalEntryLine.account_id == account.id
        )
        if start_date:
            query = query.filter(JournalEntry.date >= start_date)
        if end_date:
            query = query.filter(JournalEntry.date <= end_date)

        lines = query.order_by(JournalEntry.date.asc(), JournalEntry.id.asc()).all()

        running_balance = opening_balance
        items = []
        for line in lines:
            running_balance += (line.debit - line.credit)
            items.append({
                "date": line.entry.date.strftime("%Y-%m-%d %H:%M"),
                "entry_no": line.entry.entry_no,
                "ref": line.entry.reference_no,
                "desc": line.entry.description,
                "note": line.note or "",
                "debit": line.debit,
                "credit": line.credit,
                "balance": round(running_balance, 2)
            })

        return {
            "account_code": account.code,
            "account_name": account.name_ar,
            "account_type": account.type.value if hasattr(account.type, 'value') else str(account.type),
            "opening_balance": round(opening_balance, 2),
            "closing_balance": round(running_balance, 2),
            "lines": items
        }

    def get_contact_statement(self, contact_id, start_date=None, end_date=None):
        """كشف حساب ذمة تفصيلي لعميل أو مورد"""
        contact = self.db.query(Contact).filter(Contact.id == contact_id).first()
        if not contact:
            return {"error": "جهة التعامل غير موجودة"}

        query = self.db.query(JournalEntryLine).join(JournalEntry).filter(
            JournalEntryLine.contact_id == contact.id
        )
        if start_date:
            query = query.filter(JournalEntry.date >= start_date)
        if end_date:
            query = query.filter(JournalEntry.date <= end_date)

        lines = query.order_by(JournalEntry.date.asc()).all()

        running_balance = 0.0
        items = []
        for line in lines:
            running_balance += (line.debit - line.credit)
            items.append({
                "date": line.entry.date.strftime("%Y-%m-%d"),
                "entry_no": line.entry.entry_no,
                "desc": line.entry.description,
                "debit": line.debit,
                "credit": line.credit,
                "balance": round(running_balance, 2)
            })

        return {
            "contact_name": contact.name,
            "contact_type": contact.type.value if hasattr(contact.type, 'value') else str(contact.type),
            "tax_number": contact.tax_number or "",
            "phone": contact.phone or "",
            "current_balance": round(contact.current_balance, 2),
            "lines": items
        }

    def get_trial_balance(self):
        """ميزان المراجعة بالأرصدة والمجاميع المتطابق مع شجرة الحسابات"""
        accounts = self.db.query(Account).filter(Account.is_leaf == True).order_by(Account.code.asc()).all()
        results = []
        total_debit = 0.0
        total_credit = 0.0

        for acc in accounts:
            sums = self.db.query(
                func.sum(JournalEntryLine.debit).label("debit"),
                func.sum(JournalEntryLine.credit).label("credit")
            ).filter(JournalEntryLine.account_id == acc.id).first()

            d = float(sums[0] or 0.0)
            c = float(sums[1] or 0.0)

            if d > 0 or c > 0:
                net = d - c
                total_debit += d
                total_credit += c
                results.append({
                    "code": acc.code,
                    "name": acc.name_ar,
                    "type": acc.type.value if hasattr(acc.type, 'value') else str(acc.type),
                    "total_debit": round(d, 2),
                    "total_credit": round(c, 2),
                    "net_debit": round(net, 2) if net > 0 else 0.0,
                    "net_credit": round(abs(net), 2) if net < 0 else 0.0
                })

        return {
            "accounts": results,
            "total_debit": round(total_debit, 2),
            "total_credit": round(total_credit, 2),
            "is_balanced": abs(total_debit - total_credit) < 0.01
        }

    def get_income_statement(self, start_date=None, end_date=None):
        """قائمة الدخل والأرباح والخسائر الشاملة"""
        def get_category_total(acc_type, prefix_code=None):
            q = self.db.query(func.sum(JournalEntryLine.debit), func.sum(JournalEntryLine.credit))\
                .join(Account).join(JournalEntry).filter(Account.type == acc_type)
            if prefix_code:
                q = q.filter(Account.code.like(f"{prefix_code}%"))
            if start_date:
                q = q.filter(JournalEntry.date >= start_date)
            if end_date:
                q = q.filter(JournalEntry.date <= end_date)
            res = q.first()
            debit = float(res[0] or 0.0)
            credit = float(res[1] or 0.0)
            return debit, credit

        # المبيعات والإيرادات: الطبيعة دائنة (Credit - Debit)
        sales_d, sales_c = get_category_total(AccountType.REVENUE, "41")
        other_rev_d, other_rev_c = get_category_total(AccountType.REVENUE, "42")
        total_revenue = round((sales_c - sales_d) + (other_rev_c - other_rev_d), 2)

        # تكلفة البضاعة المباعة: الطبيعة مدينة (Debit - Credit)
        cogs_d, cogs_c = get_category_total(AccountType.EXPENSE, "51")
        total_cogs = round(cogs_d - cogs_c, 2)

        # مجمل الربح
        gross_profit = round(total_revenue - total_cogs, 2)

        # المصاريف التشغيلية والإدارية
        op_d, op_c = get_category_total(AccountType.EXPENSE, "52")
        operating_expenses = round(op_d - op_c, 2)

        # المصاريف المالية والفوائد
        fin_d, fin_c = get_category_total(AccountType.EXPENSE, "53")
        financial_expenses = round(fin_d - fin_c, 2)

        total_expenses = round(total_cogs + operating_expenses + financial_expenses, 2)
        net_profit = round(gross_profit - operating_expenses - financial_expenses, 2)

        return {
            "total_revenue": total_revenue,
            "sales_revenue": round(sales_c - sales_d, 2),
            "other_revenue": round(other_rev_c - other_rev_d, 2),
            "cogs": total_cogs,
            "gross_profit": gross_profit,
            "operating_expenses": operating_expenses,
            "financial_expenses": financial_expenses,
            "total_expenses": total_expenses,
            "net_profit": net_profit
        }

    def get_balance_sheet(self):
        """الميزانية العمومية والمركز المالي (الأصول = الخصوم + حقوق الملكية)"""
        def get_type_balance(acc_type):
            res = self.db.query(
                func.sum(JournalEntryLine.debit),
                func.sum(JournalEntryLine.credit)
            ).join(Account).filter(Account.type == acc_type).first()
            d = float(res[0] or 0.0)
            c = float(res[1] or 0.0)
            return d, c

        # الأصول: مدين - دائن
        assets_d, assets_c = get_type_balance(AccountType.ASSET)
        total_assets = round(assets_d - assets_c, 2)

        # الخصوم: دائن - مدين
        liab_d, liab_c = get_type_balance(AccountType.LIABILITY)
        total_liabilities = round(liab_c - liab_d, 2)

        # حقوق الملكية: دائن - مدين
        eq_d, eq_c = get_type_balance(AccountType.EQUITY)
        base_equity = round(eq_c - eq_d, 2)

        # صافي أرباح الفترة تضاف إلى حقوق الملكية
        income_stmt = self.get_income_statement()
        current_profit = income_stmt["net_profit"]
        total_equity = round(base_equity + current_profit, 2)

        diff = round(total_assets - (total_liabilities + total_equity), 2)

        return {
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "total_equity": total_equity,
            "current_profit": current_profit,
            "total_liabilities_and_equity": round(total_liabilities + total_equity, 2),
            "difference": diff,
            "is_balanced": abs(diff) < 0.05
        }

    def get_comparative_monthly_report(self, year=None):
        """تقرير الأداء المالي المقارن شهرياً لسنة كاملة (تجميع عالي الأداء من الخادم)"""
        current_year = year or datetime.datetime.utcnow().year
        monthly_data = []

        for month in range(1, 13):
            start = datetime.datetime(current_year, month, 1)
            if month == 12:
                end = datetime.datetime(current_year + 1, 1, 1)
            else:
                end = datetime.datetime(current_year, month + 1, 1)

            # إيرادات الشهر
            rev_res = self.db.query(func.sum(JournalEntryLine.credit - JournalEntryLine.debit))\
                .join(Account).join(JournalEntry).filter(
                    Account.type == AccountType.REVENUE,
                    JournalEntry.date >= start,
                    JournalEntry.date < end
                ).scalar() or 0.0

            # مصاريف الشهر
            exp_res = self.db.query(func.sum(JournalEntryLine.debit - JournalEntryLine.credit))\
                .join(Account).join(JournalEntry).filter(
                    Account.type == AccountType.EXPENSE,
                    JournalEntry.date >= start,
                    JournalEntry.date < end
                ).scalar() or 0.0

            rev = round(float(rev_res), 2)
            exp = round(float(exp_res), 2)
            monthly_data.append({
                "month": month,
                "month_name": f"شهر {month}",
                "revenue": rev,
                "expenses": exp,
                "net_profit": round(rev - exp, 2)
            })

        return {
            "year": current_year,
            "months": monthly_data
        }
