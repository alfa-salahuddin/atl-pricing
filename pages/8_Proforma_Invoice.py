import streamlit as st
import pandas as pd
from datetime import date, timedelta
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Port, Supplier, Product, Customer, Quotation, QuotItem, ShippingLine
from utils.export import export_proforma_invoice
from utils.quot_id import next_quot_id

st.set_page_config(page_title="Proforma Invoice — ATL Pricing", layout="wide")
st.title("Proforma invoice")

db: Session = SessionLocal()

# ── Customer ─────────────────────────────────────────────────────────────────
st.subheader("Step 1 — Select customer")
customers = db.query(Customer).order_by(Customer.cust_code).all()
if not customers:
    st.warning("No customers configured. Go to Customers to add one first.")
    st.stop()

cust_map = {c.cust_code: f"{c.cust_code} — {c.name}" for c in customers}
sel_cust = st.selectbox("Customer", list(cust_map.keys()), format_func=lambda x: cust_map[x])
cust_obj = db.get(Customer, sel_cust)

if cust_obj:
    with st.expander("Customer details", expanded=False):
        st.write(f"**Name:** {cust_obj.name}")
        st.write(f"**Address:** {cust_obj.address or '—'}")
        st.write(f"**Contact:** {cust_obj.contact_person or '—'}  |  {cust_obj.phone or '—'}")
        st.write(f"**Email:** {cust_obj.email or '—'}")

# ── Port ─────────────────────────────────────────────────────────────────────
st.subheader("Step 2 — Select port of loading")
ports    = db.query(Port).order_by(Port.port_code).all()
port_map = {p.port_code: f"{p.port_code} — {p.port_name}" for p in ports}
sel_port = st.selectbox("Port of loading", list(port_map.keys()), format_func=lambda x: port_map[x])

# ── Supplier ──────────────────────────────────────────────────────────────────
st.subheader("Step 3 — Select supplier")
suppliers = db.query(Supplier).filter(Supplier.port_code == sel_port).order_by(Supplier.supplier_code).all()
if not suppliers:
    st.warning(f"No suppliers for port {sel_port}.")
    st.stop()

sup_map = {s.supplier_code: f"{s.supplier_code} — {s.name}" for s in suppliers}
sel_sup = st.selectbox("Supplier", list(sup_map.keys()), format_func=lambda x: sup_map[x])

# ── Category filter ───────────────────────────────────────────────────────────
st.subheader("Step 4 — Filter by category (optional)")
all_cats = sorted({p.product_category for p in
                   db.query(Product).filter(Product.supplier_code == sel_sup).all()})
sel_cats = st.multiselect("Categories", all_cats, default=all_cats)

# ── Product selection ─────────────────────────────────────────────────────────
st.subheader("Step 5 — Select products and enter quantities")
q = db.query(Product).filter(Product.supplier_code == sel_sup)
if sel_cats:
    q = q.filter(Product.product_category.in_(sel_cats))
products = q.order_by(Product.product_category, Product.item_code).all()

if not products:
    st.info("No products found.")
    st.stop()

col_a, _ = st.columns([1, 5])
with col_a:
    select_all = st.button("Select all", use_container_width=True)

if "pi_selected" not in st.session_state or select_all:
    st.session_state["pi_selected"] = {p.item_code: True for p in products}

df_pi = pd.DataFrame([{
    "Select":      st.session_state["pi_selected"].get(p.item_code, False),
    "Item code":   p.item_code,
    "Category":    p.product_category,
    "Name":        p.product_name,
    "Packing":     p.packing,
    "UOM":         p.uom,
    "FOB SGD":     round(p.fob_price_sgd, 4),
    "Qty (ctns)":  0,
    "CTN CBM":     p.ctn_cbm or 0,
} for p in products])

edited = st.data_editor(
    df_pi,
    column_config={
        "Select":     st.column_config.CheckboxColumn("Select", default=True),
        "Qty (ctns)": st.column_config.NumberColumn("Qty (ctns)", min_value=0, step=1),
    },
    use_container_width=True,
    hide_index=True,
    num_rows="fixed",
)

selected_rows = edited[edited["Select"] == True]
st.caption(f"{len(selected_rows)} product(s) selected")

# ── PI settings ──────────────────────────────────────────────────────────────
st.divider()
st.subheader("Step 6 — PI settings")

sls    = db.query(ShippingLine).order_by(ShippingLine.sl_code).all()
sl_map = {s.sl_code: f"{s.sl_code} — {s.sl_name}" for s in sls}

col1, col2, col3 = st.columns(3)
with col1:
    incoterm      = st.selectbox("Incoterm", ["FOB", "CFR", "CIF", "EXW", "CPT"])
    validity_days = st.number_input("Validity (days)", min_value=1, max_value=365, value=30)
with col2:
    sl_sel  = st.selectbox("Shipping line (optional)", [""] + list(sl_map.keys()),
                            format_func=lambda x: sl_map.get(x, "— none —") if x else "— none —")
with col3:
    pi_notes = st.text_area("Notes", height=80)

validity_date = date.today() + timedelta(days=validity_days)

# ── Generate ──────────────────────────────────────────────────────────────────
if st.button("Generate proforma invoice", type="primary", disabled=len(selected_rows) == 0):
    quot_id  = next_quot_id(db, "pi")
    sup_obj  = db.get(Supplier, sel_sup)
    port_obj = db.get(Port, sel_port)

    # Save quotation
    quot = Quotation(
        quot_id=quot_id, quot_type="pi",
        cust_code=sel_cust, port_code=sel_port, supplier_code=sel_sup,
        incoterm=incoterm, validity_days=validity_days,
        sl_code=sl_sel or None, created_date=date.today(), notes=pi_notes,
    )
    db.add(quot)

    rows = []
    for _, row in selected_rows.iterrows():
        prod = db.get(Product, row["Item code"])
        qty  = int(row["Qty (ctns)"])
        db.add(QuotItem(quot_id=quot_id, item_code=prod.item_code,
                         qty_ctns=qty, fob_price_sgd=prod.fob_price_sgd))
        rows.append({
            "item_code":     prod.item_code,
            "product_name":  prod.product_name,
            "packing":       prod.packing,
            "uom":           prod.uom,
            "origin":        prod.origin,
            "fob_price_sgd": round(prod.fob_price_sgd, 4),
            "qty_ctns":      qty,
            "ctn_cbm":       prod.ctn_cbm or 0,
        })
    db.commit()

    sl_name = sl_map.get(sl_sel, "") if sl_sel else ""
    meta = {
        "quot_id":       quot_id,
        "cust_name":     cust_obj.name,
        "cust_address":  cust_obj.address or "",
        "supplier_name": sup_obj.name,
        "port_name":     port_obj.port_name,
        "incoterm":      incoterm,
        "validity_date": str(validity_date),
        "shipping_line": sl_name,
        "notes":         pi_notes,
    }

    xlsx_bytes = export_proforma_invoice(rows, meta)

    st.success(f"Proforma invoice **{quot_id}** generated — {len(rows)} line(s).")
    st.download_button(
        label=f"Download {quot_id}.xlsx",
        data=xlsx_bytes,
        file_name=f"{quot_id}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )

db.close()
