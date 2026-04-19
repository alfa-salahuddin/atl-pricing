import streamlit as st

st.set_page_config(
    page_title="ATL Pricing",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Database connection with visible error reporting ─────────────────────────
try:
    from database import engine, Base, SessionLocal
    from models import (Customer, Supplier, Port, ShippingLine, Currency,
                        ExchangeRate, HSCode, Product, Quotation, QuotItem,
                        PriceChangeLog)
    Base.metadata.create_all(bind=engine)
except Exception as e:
    st.error("**Database connection failed.** See error below:")
    st.code(str(e), language="text")
    st.info("""
**Checklist:**
1. Go to Streamlit → Settings → Secrets
2. Make sure DATABASE_URL is on one line with no line breaks
3. Use the Transaction Pooler URL from Supabase (port 6543)
4. Format must be exactly:
   `DATABASE_URL = "postgresql://postgres.PROJECTREF:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres?sslmode=require"`
    """)
    st.stop()

# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.markdown("## 📦 ATL Pricing")
st.sidebar.markdown("**Alfa Tradelinks Pte Ltd**")
st.sidebar.divider()

# ── Home dashboard ───────────────────────────────────────────────────────────
st.title("ATL Pricing")
st.caption("Alfa Tradelinks Pte Ltd — Internal pricing and quotation system")

db = SessionLocal()

try:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Customers",  db.query(Customer).count())
    with col2:
        st.metric("Suppliers",  db.query(Supplier).count())
    with col3:
        st.metric("Products",   db.query(Product).count())
    with col4:
        st.metric("Quotations", db.query(Quotation).count())

    st.divider()
    st.subheader("Recent quotations")

    from sqlalchemy import desc
    import pandas as pd

    recent = db.query(Quotation).order_by(desc(Quotation.created_date)).limit(10).all()
    if recent:
        df = pd.DataFrame([{
            "Reference": q.quot_id,
            "Type":      "Price list" if q.quot_type == "price_list" else "Proforma invoice",
            "Customer":  q.cust_code or "—",
            "Supplier":  q.supplier_code,
            "Port":      q.port_code,
            "Incoterm":  q.incoterm or "—",
            "Date":      str(q.created_date),
        } for q in recent])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No quotations yet. Use Price List or Proforma Invoice to create one.")

finally:
    db.close()

