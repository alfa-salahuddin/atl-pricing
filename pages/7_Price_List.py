import streamlit as st
import pandas as pd
from datetime import date, timedelta
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Port, Supplier, Product, Quotation, QuotItem
from utils.export import export_price_list
from utils.quot_id import next_quot_id

st.set_page_config(page_title="Price List — ATL Pricing", layout="wide")
st.title("Price list")

db: Session = SessionLocal()
try:

# ── Step 1: Port of loading ──────────────────────────────────────────────────
st.subheader("Step 1 — Select port of loading")
ports = db.query(Port).order_by(Port.port_code).all()
if not ports:
    st.warning("No ports configured. Go to Reference Data → Ports to add ports first.")
    st.stop()

port_map = {p.port_code: f"{p.port_code} — {p.port_name} ({p.country})" for p in ports}
sel_port = st.selectbox("Port of loading", list(port_map.keys()),
                         format_func=lambda x: port_map[x])

# ── Step 2: Supplier ─────────────────────────────────────────────────────────
st.subheader("Step 2 — Select supplier")
suppliers = db.query(Supplier).filter(Supplier.port_code == sel_port).order_by(Supplier.supplier_code).all()

if not suppliers:
    st.warning(f"No suppliers linked to port {sel_port}. Update supplier records to assign a port.")
    st.stop()

sup_map  = {s.supplier_code: f"{s.supplier_code} — {s.name}" for s in suppliers}
sel_sup  = st.selectbox("Supplier", list(sup_map.keys()), format_func=lambda x: sup_map[x])

# ── Step 3: Category filter ──────────────────────────────────────────────────
st.subheader("Step 3 — Filter by product category (optional)")
all_cats = sorted({p.product_category for p in
                   db.query(Product).filter(Product.supplier_code == sel_sup).all()})

sel_cats = st.multiselect("Product categories", all_cats, default=all_cats,
                           placeholder="Select one or more categories")

# ── Step 4: Product selection ────────────────────────────────────────────────
st.subheader("Step 4 — Select products")

q = db.query(Product).filter(Product.supplier_code == sel_sup)
if sel_cats:
    q = q.filter(Product.product_category.in_(sel_cats))
products = q.order_by(Product.product_category, Product.item_code).all()

if not products:
    st.info("No products found for this selection.")
    st.stop()

col_a, col_b = st.columns([1, 5])
with col_a:
    select_all = st.button("Select all", use_container_width=True)

# Track selection in session state
if "pl_selected" not in st.session_state or select_all:
    st.session_state["pl_selected"] = {p.item_code: True for p in products}

df_select = pd.DataFrame([{
    "Select":       st.session_state["pl_selected"].get(p.item_code, False),
    "Item code":    p.item_code,
    "Category":     p.product_category,
    "Product name": p.product_name,
    "Packing":      p.packing,
    "UOM":          p.uom,
    "Origin":       p.origin,
    "FOB SGD":      round(p.fob_price_sgd, 4),
    "CTN CBM":      p.ctn_cbm or "",
    "Weight (kg)":  p.ctn_weight or "",
} for p in products])

edited = st.data_editor(
    df_select,
    column_config={"Select": st.column_config.CheckboxColumn("Select", default=True)},
    use_container_width=True,
    hide_index=True,
    num_rows="fixed",
)

selected_codes = edited[edited["Select"] == True]["Item code"].tolist()
st.caption(f"{len(selected_codes)} product(s) selected")

# ── Step 5: Export options ───────────────────────────────────────────────────
st.divider()
st.subheader("Step 5 — Export settings")

col1, col2, col3 = st.columns(3)
with col1:
    incoterm     = st.selectbox("Incoterm", ["FOB", "CFR", "CIF", "EXW", "CPT"])
with col2:
    validity_days = st.number_input("Validity (days)", min_value=1, max_value=365, value=30)
with col3:
    pl_notes = st.text_input("Notes (optional)")

validity_date = date.today() + timedelta(days=validity_days)

# ── Generate ─────────────────────────────────────────────────────────────────
if st.button("Generate price list", type="primary", disabled=len(selected_codes) == 0):
    sel_products = [p for p in products if p.item_code in selected_codes]
    sup_obj      = db.get(Supplier, sel_sup)
    port_obj     = db.get(Port, sel_port)
    quot_id      = next_quot_id(db, "price_list")

    # Save quotation record
    quot = Quotation(
        quot_id=quot_id, quot_type="price_list",
        port_code=sel_port, supplier_code=sel_sup,
        incoterm=incoterm, validity_days=validity_days,
        created_date=date.today(), notes=pl_notes,
    )
    db.add(quot)
    for p in sel_products:
        db.add(QuotItem(quot_id=quot_id, item_code=p.item_code, fob_price_sgd=p.fob_price_sgd))
    db.commit()

    # Build rows for Excel
    rows = [{
        "item_code":     p.item_code,
        "product_name":  p.product_name,
        "packing":       p.packing,
        "uom":           p.uom,
        "origin":        p.origin,
        "fob_price_sgd": round(p.fob_price_sgd, 4),
        "ctn_cbm":       p.ctn_cbm,
        "ctn_weight":    p.ctn_weight,
    } for p in sel_products]

    meta = {
        "quot_id":       quot_id,
        "supplier_name": sup_obj.name,
        "port_name":     port_obj.port_name,
        "incoterm":      incoterm,
        "validity_date": str(validity_date),
        "notes":         pl_notes,
    }

    xlsx_bytes = export_price_list(rows, meta)

    st.success(f"Price list **{quot_id}** generated — {len(sel_products)} product(s).")
    st.download_button(
        label=f"Download {quot_id}.xlsx",
        data=xlsx_bytes,
        file_name=f"{quot_id}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )

pass
finally:
    db.close()
