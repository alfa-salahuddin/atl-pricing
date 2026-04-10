import streamlit as st
from database import engine, Base
from models import (Customer, Supplier, Port, ShippingLine, Currency,
                    ExchangeRate, HSCode, Product, Quotation, QuotItem, PriceChangeLog)
from sqlalchemy.orm import Session
from database import SessionLocal

# ── One-time DB setup ────────────────────────────────────────────────────────
Base.metadata.create_all(bind=engine)

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ATL Pricing",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar branding ─────────────────────────────────────────────────────────
st.sidebar.markdown("## 📦 ATL Pricing")
st.sidebar.markdown("**Alfa Tradelinks Pte Ltd**")
st.sidebar.divider()
st.sidebar.markdown("""
**Master data**
- Customers
- Suppliers
- Reference Data
- HS Codes
- Products

**Processes**
- Update Prices
- Price List
- Proforma Invoice

**System**
- Backup
""")

# ── Home dashboard ───────────────────────────────────────────────────────────
st.title("ATL Pricing")
st.caption("Alfa Tradelinks Pte Ltd — Internal pricing and quotation system")

db: Session = SessionLocal()

col1, col2, col3, col4 = st.columns(4)

with col1:
    n = db.query(Customer).count()
    st.metric("Customers", n)

with col2:
    n = db.query(Supplier).count()
    st.metric("Suppliers", n)

with col3:
    n = db.query(Product).count()
    st.metric("Products", n)

with col4:
    n = db.query(Quotation).count()
    st.metric("Quotations", n)

st.divider()

# Recent quotations
st.subheader("Recent quotations")
from models import Quotation
from sqlalchemy import desc

recent = db.query(Quotation).order_by(desc(Quotation.created_date)).limit(10).all()
if recent:
    import pandas as pd
    df = pd.DataFrame([{
        "Reference":  q.quot_id,
        "Type":       "Price list" if q.quot_type == "price_list" else "Proforma invoice",
        "Customer":   q.cust_code or "—",
        "Supplier":   q.supplier_code,
        "Port":       q.port_code,
        "Incoterm":   q.incoterm or "—",
        "Date":       str(q.created_date),
    } for q in recent])
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("No quotations yet. Use the Price List or Proforma Invoice pages to create one.")

db.close()
