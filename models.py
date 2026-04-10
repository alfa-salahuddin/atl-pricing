from datetime import datetime, date
from typing import Optional
from sqlalchemy import (
    String, Integer, Float, Date, DateTime,
    ForeignKey, UniqueConstraint, Text, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


# ---------------------------------------------------------------------------
# Reference / lookup tables
# ---------------------------------------------------------------------------

class Currency(Base):
    __tablename__ = "currencies"

    currency_code: Mapped[str] = mapped_column(String(10), primary_key=True)
    currency_name: Mapped[str] = mapped_column(String(100))


class Port(Base):
    __tablename__ = "ports"

    port_code:  Mapped[str] = mapped_column(String(20), primary_key=True)
    port_name:  Mapped[str] = mapped_column(String(100))
    country:    Mapped[str] = mapped_column(String(100))

    suppliers: Mapped[list["Supplier"]] = relationship(back_populates="port")


class ShippingLine(Base):
    __tablename__ = "shipping_lines"

    sl_code: Mapped[str] = mapped_column(String(20), primary_key=True)
    sl_name: Mapped[str] = mapped_column(String(100))


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    __table_args__ = (
        UniqueConstraint("rate_date", "base_currency", "target_currency"),
    )

    id:              Mapped[int]  = mapped_column(Integer, primary_key=True, autoincrement=True)
    rate_date:       Mapped[date] = mapped_column(Date)
    base_currency:   Mapped[str]  = mapped_column(String(10), ForeignKey("currencies.currency_code"))
    target_currency: Mapped[str]  = mapped_column(String(10), ForeignKey("currencies.currency_code"))
    rate:            Mapped[float]= mapped_column(Float)
    direction:       Mapped[str]  = mapped_column(String(10))   # 'multiply' | 'divide'


class HSCode(Base):
    __tablename__ = "hs_codes"

    hs_code:     Mapped[str]           = mapped_column(String(20),  primary_key=True)
    category:    Mapped[str]           = mapped_column(String(100))
    description: Mapped[str]           = mapped_column(String(255))
    remarks:     Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------------
# Master data tables
# ---------------------------------------------------------------------------

class Customer(Base):
    __tablename__ = "customers"

    cust_code:      Mapped[str]           = mapped_column(String(20),  primary_key=True)
    name:           Mapped[str]           = mapped_column(String(200))
    address:        Mapped[Optional[str]] = mapped_column(Text,        nullable=True)
    email:          Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    contact_person: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    phone:          Mapped[Optional[str]] = mapped_column(String(50),  nullable=True)
    country:        Mapped[str]           = mapped_column(String(100))
    notes:          Mapped[Optional[str]] = mapped_column(Text,        nullable=True)

    quotations: Mapped[list["Quotation"]] = relationship(back_populates="customer")


class Supplier(Base):
    __tablename__ = "suppliers"

    supplier_code:  Mapped[str]           = mapped_column(String(20),  primary_key=True)
    name:           Mapped[str]           = mapped_column(String(200))
    address:        Mapped[Optional[str]] = mapped_column(Text,        nullable=True)
    email:          Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    contact_person: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    phone:          Mapped[Optional[str]] = mapped_column(String(50),  nullable=True)
    port_code:      Mapped[Optional[str]] = mapped_column(String(20),  ForeignKey("ports.port_code"), nullable=True)
    country:        Mapped[str]           = mapped_column(String(100))
    notes:          Mapped[Optional[str]] = mapped_column(Text,        nullable=True)

    port:     Mapped[Optional["Port"]]   = relationship(back_populates="suppliers")
    products: Mapped[list["Product"]]    = relationship(back_populates="supplier")


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

class Product(Base):
    __tablename__ = "products"

    item_code:        Mapped[str]           = mapped_column(String(50),  primary_key=True)
    product_category: Mapped[str]           = mapped_column(String(100))
    hs_code:          Mapped[Optional[str]] = mapped_column(String(20),  ForeignKey("hs_codes.hs_code"), nullable=True)
    product_name:     Mapped[str]           = mapped_column(String(255))
    packing:          Mapped[str]           = mapped_column(String(100))
    uom:              Mapped[str]           = mapped_column(String(20))
    origin:           Mapped[str]           = mapped_column(String(100))
    supplier_code:    Mapped[str]           = mapped_column(String(20),  ForeignKey("suppliers.supplier_code"))
    cost_currency:    Mapped[str]           = mapped_column(String(10),  ForeignKey("currencies.currency_code"))
    cost_price:       Mapped[float]         = mapped_column(Float)
    discount_pct:     Mapped[float]         = mapped_column(Float, default=0.0)
    cost_additions:   Mapped[float]         = mapped_column(Float, default=0.0)
    net_cost_orig:    Mapped[float]         = mapped_column(Float, default=0.0)   # computed
    exchange_rate_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("exchange_rates.id"), nullable=True)
    net_cost_sgd:     Mapped[float]         = mapped_column(Float, default=0.0)   # computed
    ctn_cbm:          Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ctn_weight:       Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    margin_pct:       Mapped[float]           = mapped_column(Float, default=0.0)
    fob_price_sgd:    Mapped[float]           = mapped_column(Float, default=0.0)  # computed
    last_updated:     Mapped[datetime]        = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    supplier:      Mapped["Supplier"]             = relationship(back_populates="products")
    hs:            Mapped[Optional["HSCode"]]     = relationship()
    exchange_rate: Mapped[Optional["ExchangeRate"]] = relationship()
    quot_items:    Mapped[list["QuotItem"]]       = relationship(back_populates="product")
    price_logs:    Mapped[list["PriceChangeLog"]] = relationship(back_populates="product")


# ---------------------------------------------------------------------------
# Quotations / Price lists
# ---------------------------------------------------------------------------

class Quotation(Base):
    __tablename__ = "quotations"

    quot_id:       Mapped[str]           = mapped_column(String(30), primary_key=True)   # ATL-Q-2026-001
    quot_type:     Mapped[str]           = mapped_column(String(20))                      # 'price_list' | 'pi'
    cust_code:     Mapped[Optional[str]] = mapped_column(String(20), ForeignKey("customers.cust_code"), nullable=True)
    port_code:     Mapped[str]           = mapped_column(String(20), ForeignKey("ports.port_code"))
    supplier_code: Mapped[str]           = mapped_column(String(20), ForeignKey("suppliers.supplier_code"))
    incoterm:      Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    validity_days: Mapped[Optional[int]] = mapped_column(Integer,    nullable=True)
    sl_code:       Mapped[Optional[str]] = mapped_column(String(20), ForeignKey("shipping_lines.sl_code"), nullable=True)
    created_date:  Mapped[date]          = mapped_column(Date, default=date.today)
    notes:         Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    customer: Mapped[Optional["Customer"]]  = relationship(back_populates="quotations")
    items:    Mapped[list["QuotItem"]]       = relationship(back_populates="quotation", cascade="all, delete-orphan")


class QuotItem(Base):
    __tablename__ = "quot_items"

    id:             Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    quot_id:        Mapped[str]           = mapped_column(String(30), ForeignKey("quotations.quot_id"))
    item_code:      Mapped[str]           = mapped_column(String(50), ForeignKey("products.item_code"))
    qty_ctns:       Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fob_price_sgd:  Mapped[float]         = mapped_column(Float)          # snapshot at quote time
    override_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    quotation: Mapped["Quotation"] = relationship(back_populates="items")
    product:   Mapped["Product"]   = relationship(back_populates="quot_items")


# ---------------------------------------------------------------------------
# Price change log
# ---------------------------------------------------------------------------

class PriceChangeLog(Base):
    __tablename__ = "price_change_log"

    id:             Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_code:      Mapped[str]           = mapped_column(String(50), ForeignKey("products.item_code"))
    changed_date:   Mapped[datetime]      = mapped_column(DateTime, default=func.now())
    old_cost_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    new_cost_price: Mapped[float]           = mapped_column(Float)
    old_fob_sgd:    Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    new_fob_sgd:    Mapped[float]           = mapped_column(Float)
    source:         Mapped[str]             = mapped_column(String(30), default="manual")  # 'manual' | 'excel_upload'
    notes:          Mapped[Optional[str]]   = mapped_column(Text, nullable=True)

    product: Mapped["Product"] = relationship(back_populates="price_logs")
