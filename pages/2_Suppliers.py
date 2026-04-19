import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Supplier, Port

st.set_page_config(page_title="Suppliers — ATL Pricing", layout="wide")
st.title("Suppliers")

db: Session = SessionLocal()

ports = db.query(Port).order_by(Port.port_code).all()
port_options = {p.port_code: f"{p.port_code} — {p.port_name}" for p in ports}

# ── Add / Edit form ──────────────────────────────────────────────────────────
with st.expander("➕  Add / edit supplier", expanded=False):
    sup_code = st.text_input("Supplier code *").strip().upper()
    col1, col2 = st.columns(2)
    with col1:
        name      = st.text_input("Name *")
        email     = st.text_input("Email")
        country   = st.text_input("Country *")
    with col2:
        contact   = st.text_input("Contact person")
        phone     = st.text_input("Phone")
        port_sel  = st.selectbox("Port of loading", [""] + list(port_options.keys()),
                                  format_func=lambda x: port_options.get(x, "— select —") if x else "— select —")
    address = st.text_area("Address", height=70)
    notes   = st.text_area("Notes", height=50)

    c1, c2 = st.columns([1, 5])
    with c1:
        save = st.button("Save", type="primary", use_container_width=True)
    with c2:
        if sup_code:
            existing = db.get(Supplier, sup_code)
            if existing:
                st.info(f"Editing: {existing.name}")

    if save:
        if not sup_code or not name or not country:
            st.error("Supplier code, name, and country are required.")
        else:
            existing = db.get(Supplier, sup_code)
            kwargs = dict(
                name=name, email=email, contact_person=contact,
                phone=phone, address=address, country=country,
                port_code=port_sel or None, notes=notes,
            )
            if existing:
                for k, v in kwargs.items():
                    setattr(existing, k, v)
                db.commit()
                st.success(f"Supplier {sup_code} updated.")
            else:
                db.add(Supplier(supplier_code=sup_code, **kwargs))
                db.commit()
                st.success(f"Supplier {sup_code} added.")
            st.rerun()

st.divider()

# ── Filter + Table ───────────────────────────────────────────────────────────
filter_port = st.selectbox("Filter by port of loading", ["All"] + list(port_options.keys()),
                            format_func=lambda x: port_options.get(x, "All ports") if x != "All" else "All ports")

q = db.query(Supplier)
if filter_port != "All":
    q = q.filter(Supplier.port_code == filter_port)
suppliers = q.order_by(Supplier.supplier_code).all()

if not suppliers:
    st.info("No suppliers found.")
else:
    df = pd.DataFrame([{
        "Code":    s.supplier_code,
        "Name":    s.name,
        "Port":    s.port_code or "",
        "Country": s.country,
        "Email":   s.email or "",
        "Contact": s.contact_person or "",
    } for s in suppliers])
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(f"{len(suppliers)} supplier(s)")

    st.divider()
    st.subheader("Delete supplier")
    del_code = st.selectbox("Select supplier to delete", [""] + [s.supplier_code for s in suppliers])
    if del_code and st.button("Delete", type="secondary"):
        db.delete(db.get(Supplier, del_code))
        db.commit()
        st.success(f"Supplier {del_code} deleted.")
        st.rerun()

db.close()
