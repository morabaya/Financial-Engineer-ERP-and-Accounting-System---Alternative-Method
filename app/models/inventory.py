from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.models.financials import Base
import datetime

class Item(Base):
    __tablename__ = 'items'

    id = Column(Integer, primary_key=True)
    sku = Column(String(50), unique=True, nullable=False)
    name_ar = Column(String(100), nullable=False)
    name_en = Column(String(100))
    category = Column(String(100), default="عام")
    unit = Column(String(50), default="قطعة")
    purchase_price = Column(Float, default=0.0) # ILS
    sale_price = Column(Float, default=0.0) # ILS
    tax_rate = Column(Float, default=0.16) # Palestinian VAT 16%
    current_stock = Column(Float, default=0.0)
    min_stock_level = Column(Float, default=5.0)

    movements = relationship("StockMovement", backref="item", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "sku": self.sku,
            "name_ar": self.name_ar,
            "name_en": self.name_en or "",
            "category": self.category or "عام",
            "unit": self.unit or "قطعة",
            "purchase_price": round(self.purchase_price, 2),
            "sale_price": round(self.sale_price, 2),
            "tax_rate": self.tax_rate,
            "current_stock": self.current_stock,
            "min_stock_level": self.min_stock_level,
            "is_low_stock": self.current_stock <= self.min_stock_level
        }

class Warehouse(Base):
    __tablename__ = 'warehouses'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    location = Column(String(255))
    is_default = Column(Integer, default=0)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "location": self.location or "",
            "is_default": bool(self.is_default)
        }

class StockMovement(Base):
    __tablename__ = 'stock_movements'

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey('items.id'), nullable=False)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=False)
    quantity = Column(Float, nullable=False) # Positive for In, Negative for Out
    movement_type = Column(String(50)) # 'Purchase', 'Sale', 'Adjustment', 'Transfer'
    reference_no = Column(String(50))
    cost_per_unit = Column(Float, default=0.0)
    total_cost = Column(Float, default=0.0)
    date = Column(DateTime, default=datetime.datetime.utcnow)
    user_id = Column(Integer, default=1)

    warehouse = relationship("Warehouse")

    def to_dict(self):
        return {
            "id": self.id,
            "item_id": self.item_id,
            "item_name": self.item.name_ar if self.item else "",
            "warehouse_id": self.warehouse_id,
            "warehouse_name": self.warehouse.name if self.warehouse else "",
            "quantity": self.quantity,
            "movement_type": self.movement_type,
            "reference_no": self.reference_no or "",
            "cost_per_unit": self.cost_per_unit,
            "total_cost": self.total_cost,
            "date": self.date.strftime("%Y-%m-%d %H:%M") if self.date else ""
        }
