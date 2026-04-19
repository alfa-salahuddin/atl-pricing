import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Customer

st.set_page_config(page_title="Customers — ATL Pricing", layout="wide")
st.title("Customers")

db: Session = SessionLocal()
try:

# ── Helper ──────────────────────────────────────────────────────────────────
def load_customers():
    return db.query(Customer).order_by(Customer.cust_code).all()

# ── Add / Edit form ──────────────────────────────────────────────────────────
with st.expander("➕  Add / edit customer", expanded=False):
    edit_code = st.text_input("Customer code *", key="cust_code_input").strip().upper()
    col1, col2 = st.columns(2)
    with col1:
        name    = st.text_input("Name *")
        email   = st.text_input("Email")
        country = st.text_input("Country *")
    with col2:
        contact = st.text_input("Contact person")
        phone   = st.text_input("Phone")
    address = st.text_area("Address", height=70)
    notes   = st.text_area("Notes", height=50)

    c1, c2 = st.columns([1, 5])
    with c1:
        save = st.button("Save", type="primary", use_container_width=True)
    with c2:
        if edit_code:
            existing = db.get(Customer, edit_code)
            if existing:
                st.info(f"Editing existing customer: {existing.name}")

    if save:
        if not edit_code or not name or not country:
            st.error("Customer code, name, and country are required.")
        else:
            existing = db.get(Customer, edit_code)
            if existing:
                existing.name           = name
                existing.email          = email
                existing.contact_person = contact
                existing.phone          = phone
                existing.address        = address
                existing.country        = country
                existing.notes          = notes
                db.commit()
                st.success(f"Customer {edit_code} updated.")
            else:
                db.add(Customer(
                    cust_code=edit_code, name=name, email=email,
                    contact_person=contact, phone=phone,
                    address=address, country=country, notes=notes,
                ))
                db.commit()
                st.success(f"Customer {edit_code} added.")
            st.rerun()

st.divider()

# ── Table ────────────────────────────────────────────────────────────────────
customers = load_customers()
if not customers:
    st.info("No customers yet. Add one above.")
else:
    df = pd.DataFrame([{
        "Code":    c.cust_code,
        "Name":    c.name,
        "Country": c.country,
        "Email":   c.email or "",
        "Contact": c.contact_person or "",
        "Phone":   c.phone or "",
    } for c in customers])

    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(f"{len(customers)} customer(s)")

    st.divider()
    st.subheader("Delete customer")
    del_code = st.selectbox("Select customer to delete", [""] + [c.cust_code for c in customers])
    if del_code and st.button("Delete", type="secondary"):
        db.delete(db.get(Customer, del_code))
        db.commit()
        st.success(f"Customer {del_code} deleted.")
        st.rerun()

pass
finally:
    db.close()
