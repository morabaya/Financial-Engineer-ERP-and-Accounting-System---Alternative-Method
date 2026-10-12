from sqlalchemy.orm import Session
from app.models.inventory import Item, Warehouse, StockMovement
from app.models.vouchers import AuditLog
from app.services.accounting_engine import create_accounting_entry, get_account_by_code

class InventoryService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_items(self):
        return self.db.query(Item).order_by(Item.name_ar.asc()).all()

    def get_item_by_id(self, item_id):
        return self.db.query(Item).filter(Item.id == item_id).first()

    def create_item(self, sku, name_ar, name_en=None, category="عام", unit="قطعة", purchase_price=0.0, sale_price=0.0, initial_stock=0.0, min_stock=5.0, user_id=1):
        existing = self.db.query(Item).filter(Item.sku == sku).first()
        if existing:
            raise ValueError(f"رمز الصنف (SKU) '{sku}' مستخدم بالفعل!")

        item = Item(
            sku=sku,
            name_ar=name_ar,
            name_en=name_en,
            category=category,
            unit=unit,
            purchase_price=float(purchase_price),
            sale_price=float(sale_price),
            current_stock=float(initial_stock),
            min_stock_level=float(min_stock)
        )
        self.db.add(item)
        self.db.flush()

        if float(initial_stock) > 0:
            mov = StockMovement(
                item_id=item.id,
                warehouse_id=1,
                quantity=float(initial_stock),
                movement_type='Initial',
                reference_no=f"INIT-{sku}",
                cost_per_unit=float(purchase_price),
                total_cost=float(initial_stock) * float(purchase_price),
                user_id=user_id
            )
            self.db.add(mov)

        audit = AuditLog(
            user_id=user_id,
            action="CREATE_ITEM",
            table_name="items",
            record_id=item.id,
            new_value=f"إضافة الصنف {name_ar} (SKU: {sku}) بسعر بيع {sale_price} ورصيد افتتاحي {initial_stock}"
        )
        self.db.add(audit)
        self.db.commit()
        return item.id

    def update_stock(self, item_id, warehouse_id, quantity, m_type, ref_no=None, cost_per_unit=None, user_id=1):
        item = self.db.query(Item).filter(Item.id == item_id).first()
        if not item:
            raise ValueError("الصنف غير موجود!")

        unit_cost = float(cost_per_unit) if cost_per_unit is not None else item.purchase_price
        total_cost = abs(float(quantity)) * unit_cost

        movement = StockMovement(
            item_id=item_id,
            warehouse_id=warehouse_id,
            quantity=float(quantity),
            movement_type=m_type,
            reference_no=ref_no,
            cost_per_unit=unit_cost,
            total_cost=total_cost,
            user_id=user_id
        )
        self.db.add(movement)
        item.current_stock += float(quantity)
        self.db.commit()
        return movement.id

    def perform_inventory_count(self, item_id, warehouse_id, actual_qty, user_id=1):
        """
        جرد المخزون الفعلي وتسجيل فروقات الجرد وقيد التسوية المحاسبية
        """
        item = self.db.query(Item).filter(Item.id == item_id).first()
        if not item:
            raise ValueError("الصنف غير موجود!")

        diff = round(float(actual_qty) - item.current_stock, 2)
        if diff != 0:
            self.update_stock(item_id, warehouse_id, diff, 'Adjustment', ref_no=f"COUNT-{item.sku}", user_id=user_id)
            
            stock_acc = get_account_by_code(self.db, "1131") # المخزون
            diff_cost = abs(diff) * item.purchase_price

            if diff < 0: # عجز جرد: مدين مصروف خسائر الجرد، دائن المخزون
                loss_acc = get_account_by_code(self.db, "525")
                lines = [
                    {'account_id': loss_acc.id, 'debit': round(diff_cost, 2), 'credit': 0.0, 'note': f"عجز جرد مخزني لصنف {item.name_ar} ({abs(diff)} وحدة)"},
                    {'account_id': stock_acc.id, 'debit': 0.0, 'credit': round(diff_cost, 2), 'note': "تخفيض المخزون بفارق الجرد"}
                ]
            else: # فائض جرد: مدين المخزون، دائن إيرادات متنوعة
                gain_acc = get_account_by_code(self.db, "422")
                lines = [
                    {'account_id': stock_acc.id, 'debit': round(diff_cost, 2), 'credit': 0.0, 'note': f"زيادة المخزون بفائض الجرد لصنف {item.name_ar}"},
                    {'account_id': gain_acc.id, 'debit': 0.0, 'credit': round(diff_cost, 2), 'note': f"فائض جرد مخزني ({diff} وحدة)"}
                ]

            if diff_cost > 0:
                create_accounting_entry(
                    self.db, 
                    f"تسوية جرد مخزني للصنف {item.name_ar} ({item.sku})", 
                    f"ADJ-{item.sku}", 
                    lines, 
                    source_module="INVENTORY", 
                    user_id=user_id
                )

        return diff
