import streamlit as st
import pandas as pd
from datetime import date, timedelta
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Port, Supplier, Product, Customer, Quotation, QuotItem, ShippingLine
from utils.export import export_proforma_invoice

st.set_page_config(page_title="Proforma Invoice — ATL Pricing", layout="wide")
st.title("Proforma invoice")

db: Session = SessionLocal()

# ── Session state — order line items list ─────────────────────────────────────
if "pi_lines" not in st.session_state:
    st.session_state["pi_lines"] = []   # list of dicts


def generate_pi_ref(cust_code: str) -> str:
    """OL + MMYY + CustCode  e.g. OL0426SEY001"""
    today = date.today()
    return f"OL{today.strftime('%m%y')}{cust_code.upper()}"


# ═══════════════════════════════════════════════════════════════════════════════
# TOP SECTION — Customer & PI settings (collapsed once lines exist)
# ═══════════════════════════════════════════════════════════════════════════════
with st.expander("PI settings — customer, incoterm, notes",
                  expanded=len(st.session_state["pi_lines"]) == 0):

    customers = db.query(Customer).order_by(Customer.cust_code).all()
    if not customers:
        st.warning("No customers yet. Add one in Customers first.")
        st.stop()

    cust_map = {c.cust_code: f"{c.cust_code} — {c.name}" for c in customers}
    sls      = db.query(ShippingLine).order_by(ShippingLine.sl_code).all()
    sl_map   = {s.sl_code: f"{s.sl_code} — {s.sl_name}" for s in sls}

    col1, col2, col3 = st.columns(3)
    with col1:
        sel_cust = st.selectbox("Customer *", list(cust_map.keys()),
                                 format_func=lambda x: cust_map[x],
                                 key="pi_cust")
        cust_obj = db.get(Customer, sel_cust)
        if cust_obj:
            st.caption(f"{cust_obj.address or ''}")
    with col2:
        incoterm      = st.selectbox("Incoterm", ["FOB", "CFR", "CIF", "EXW", "CPT"], key="pi_inco")
        validity_days = st.number_input("Validity (days)", min_value=1, max_value=365,
                                         value=30, key="pi_val")
    with col3:
        sl_sel   = st.selectbox("Shipping line (optional)",
                                 [""] + list(sl_map.keys()),
                                 format_func=lambda x: sl_map.get(x, "— none —") if x else "— none —",
                                 key="pi_sl")
        pi_notes = st.text_area("Notes", height=68, key="pi_notes")

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# PRODUCT SELECTION — Port → Supplier → Category → Products
# ═══════════════════════════════════════════════════════════════════════════════
st.subheader("Add products to order")

ports = db.query(Port).order_by(Port.port_code).all()
if not ports:
    st.warning("No ports configured.")
    st.stop()

port_map = {p.port_code: f"{p.port_code} — {p.port_name}" for p in ports}

col_p1, col_p2, col_p3 = st.columns(3)
with col_p1:
    sel_port = st.selectbox("Port of loading", list(port_map.keys()),
                             format_func=lambda x: port_map[x], key="pi_port")
with col_p2:
    suppliers = db.query(Supplier).filter(
        Supplier.port_code == sel_port
    ).order_by(Supplier.supplier_code).all()

    if not suppliers:
        st.warning(f"No suppliers for port {sel_port}.")
        st.stop()

    sup_map  = {s.supplier_code: f"{s.supplier_code} — {s.name}" for s in suppliers}
    sel_sup  = st.selectbox("Supplier", list(sup_map.keys()),
                             format_func=lambda x: sup_map[x], key="pi_sup")
with col_p3:
    all_cats = sorted({p.product_category for p in
                       db.query(Product).filter(Product.supplier_code == sel_sup).all()})
    sel_cats = st.multiselect("Category filter", all_cats, default=all_cats, key="pi_cats")

# ── Product table ─────────────────────────────────────────────────────────────
q = db.query(Product).filter(Product.supplier_code == sel_sup)
if sel_cats:
    q = q.filter(Product.product_category.in_(sel_cats))
products = q.order_by(Product.product_category, Product.item_code).all()

if not products:
    st.info("No products found for this selection.")
else:
    # Build display dataframe with qty and discount fields
    prod_map = {p.item_code: p for p in products}

    df_sel = pd.DataFrame([{
        "Select":          False,
        "Item code":       p.item_code,
        "Category":        p.product_category,
        "Product name":    p.product_name,
        "Packing":         p.packing,
        "UOM":             p.uom,
        "FOB SGD":         round(p.fob_price_sgd, 2),
        "Qty (ctns)":      0,
        "Item discount":   0.0,
        "Net FOB SGD":     round(p.fob_price_sgd, 2),
    } for p in products])

    col_btn1, col_btn2 = st.columns([1, 8])
    with col_btn1:
        if st.button("Select all", key="pi_selall"):
            for key in list(st.session_state.keys()):
                if key.startswith("pi_chk_"):
                    st.session_state[key] = True

    edited = st.data_editor(
        df_sel,
        column_config={
            "Select":        st.column_config.CheckboxColumn("Select", default=False),
            "FOB SGD":       st.column_config.NumberColumn("FOB SGD", format="%.2f", disabled=True),
            "Qty (ctns)":    st.column_config.NumberColumn("Qty (ctns)", min_value=0, step=1),
            "Item discount": st.column_config.NumberColumn("Item discount (SGD)", min_value=0.0,
                                                            step=0.10, format="%.2f",
                                                            help="Subtracted from FOB price for this order only"),
            "Net FOB SGD":   st.column_config.NumberColumn("Net FOB SGD", format="%.2f", disabled=True),
        },
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        key="pi_editor",
    )

    # Recalculate Net FOB live
    edited["Net FOB SGD"] = (edited["FOB SGD"] - edited["Item discount"]).round(2)

    # ── Add to order button ───────────────────────────────────────────────────
    selected_rows = edited[(edited["Select"] == True) & (edited["Qty (ctns)"] > 0)]

    col_add1, col_add2 = st.columns([2, 8])
    with col_add1:
        add_clicked = st.button("➕  Add to order", type="primary",
                                 disabled=len(selected_rows) == 0,
                                 use_container_width=True)

    if add_clicked:
        added = 0
        for _, row in selected_rows.iterrows():
            item_code = row["Item code"]
            prod      = prod_map.get(item_code)
            if not prod:
                continue

            # Check if already in order — update qty if so
            existing = next((l for l in st.session_state["pi_lines"]
                             if l["item_code"] == item_code), None)
            net_fob = max(0.0, round(prod.fob_price_sgd - float(row["Item discount"]), 2))

            if existing:
                existing["qty_ctns"]      = int(row["Qty (ctns)"])
                existing["item_discount"] = float(row["Item discount"])
                existing["net_fob"]       = net_fob
            else:
                st.session_state["pi_lines"].append({
                    "item_code":      item_code,
                    "product_name":   prod.product_name,
                    "packing":        prod.packing,
                    "uom":            prod.uom,
                    "origin":         prod.origin,
                    "supplier_code":  prod.supplier_code,
                    "port_code":      sel_port,
                    "fob_price_sgd":  prod.fob_price_sgd,
                    "item_discount":  float(row["Item discount"]),
                    "net_fob":        net_fob,
                    "qty_ctns":       int(row["Qty (ctns)"]),
                    "ctn_cbm":        prod.ctn_cbm or 0,
                    "ctn_weight":     prod.ctn_weight or 0,
                })
            added += 1
        if added:
            st.success(f"✅ {added} line(s) added to order. You can continue adding products from other suppliers.")
            st.rerun()

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# ORDER LINES — live list at bottom
# ═══════════════════════════════════════════════════════════════════════════════
lines = st.session_state["pi_lines"]

if not lines:
    st.info("No lines added yet. Select products above and click 'Add to order'.")
else:
    st.subheader(f"Order lines — {len(lines)} item(s)")

    # Summary table
    total_amount = 0.0
    total_cbm    = 0.0
    total_ctns   = 0

    display_rows = []
    for i, line in enumerate(lines):
        amount      = round(line["net_fob"] * line["qty_ctns"], 2)
        line_cbm    = round(line["ctn_cbm"] * line["qty_ctns"], 4)
        total_amount += amount
        total_cbm    += line_cbm
        total_ctns   += line["qty_ctns"]
        display_rows.append({
            "#":            i + 1,
            "Item code":    line["item_code"],
            "Product":      line["product_name"],
            "Supplier":     line["supplier_code"],
            "Packing":      line["packing"],
            "UOM":          line["uom"],
            "Qty (ctns)":   line["qty_ctns"],
            "FOB SGD":      round(line["fob_price_sgd"], 2),
            "Discount":     round(line["item_discount"], 2),
            "Net FOB SGD":  round(line["net_fob"], 2),
            "Amount SGD":   amount,
            "CBM":          line_cbm,
        })

    df_lines = pd.DataFrame(display_rows)
    st.dataframe(df_lines, use_container_width=True, hide_index=True)

    # Totals
    col_t1, col_t2, col_t3, col_t4 = st.columns(4)
    with col_t1:
        st.metric("Total lines",   len(lines))
    with col_t2:
        st.metric("Total ctns",    total_ctns)
    with col_t3:
        st.metric("Total CBM",     f"{round(total_cbm, 4)}")
    with col_t4:
        st.metric("Total SGD",     f"SGD {round(total_amount, 2):,.2f}")

    # Remove a line
    col_r1, col_r2 = st.columns([3, 7])
    with col_r1:
        remove_options = {l["item_code"]: f"{l['item_code']} — {l['product_name']}" for l in lines}
        remove_sel     = st.selectbox("Remove a line", [""] + list(remove_options.keys()),
                                       format_func=lambda x: remove_options.get(x, "— select —") if x else "— select to remove —",
                                       key="pi_remove")
    with col_r2:
        if remove_sel and st.button("Remove line", type="secondary"):
            st.session_state["pi_lines"] = [l for l in lines if l["item_code"] != remove_sel]
            st.rerun()

    # Clear all
    if st.button("🗑  Clear all lines", type="secondary"):
        st.session_state["pi_lines"] = []
        st.rerun()

    st.divider()

    # ── Generate PI ───────────────────────────────────────────────────────────
    st.subheader("Generate proforma invoice")

    cust_obj = db.get(Customer, st.session_state.get("pi_cust", ""))

    if cust_obj:
        pi_ref = generate_pi_ref(cust_obj.cust_code)
        st.info(f"Order reference: **{pi_ref}**")
    else:
        st.warning("Select a customer in the PI settings above.")

    if st.button("Generate proforma invoice", type="primary",
                  disabled=not cust_obj or len(lines) == 0):

        incoterm_val      = st.session_state.get("pi_inco", "FOB")
        validity_days_val = int(st.session_state.get("pi_val", 30))
        sl_val            = st.session_state.get("pi_sl", "")
        notes_val         = st.session_state.get("pi_notes", "")
        validity_date     = date.today() + timedelta(days=validity_days_val)

        # Use port and supplier from first line (multi-supplier — record per line)
        first_line  = lines[0]
        port_code   = first_line["port_code"]
        sup_code    = first_line["supplier_code"]

        # Save quotation header
        quot = Quotation(
            quot_id       = pi_ref,
            quot_type     = "pi",
            cust_code     = cust_obj.cust_code,
            port_code     = port_code,
            supplier_code = sup_code,
            incoterm      = incoterm_val,
            validity_days = validity_days_val,
            sl_code       = sl_val or None,
            created_date  = date.today(),
            notes         = notes_val,
        )
        db.add(quot)

        # Save line items
        export_rows = []
        for line in lines:
            db.add(QuotItem(
                quot_id        = pi_ref,
                item_code      = line["item_code"],
                qty_ctns       = line["qty_ctns"],
                fob_price_sgd  = line["net_fob"],
                override_price = line["net_fob"] if line["item_discount"] > 0 else None,
            ))
            port_obj = db.get(Port, line["port_code"])
            export_rows.append({
                "item_code":    line["item_code"],
                "product_name": line["product_name"],
                "packing":      line["packing"],
                "uom":          line["uom"],
                "origin":       line["origin"],
                "fob_price_sgd":line["net_fob"],
                "qty_ctns":     line["qty_ctns"],
                "ctn_cbm":      line["ctn_cbm"],
                "ctn_weight":   line["ctn_weight"],
            })

        try:
            db.commit()
        except Exception as e:
            db.rollback()
            st.error(f"Could not save: {e}")
            st.stop()

        # Build meta for export
        sls      = db.query(ShippingLine).all()
        sl_map_l = {s.sl_code: s.sl_name for s in sls}
        port_obj = db.get(Port, port_code)

        meta = {
            "quot_id":       pi_ref,
            "cust_name":     cust_obj.name,
            "cust_address":  cust_obj.address or "",
            "supplier_name": ", ".join(sorted({l["supplier_code"] for l in lines})),
            "port_name":     port_obj.port_name if port_obj else port_code,
            "incoterm":      incoterm_val,
            "validity_date": str(validity_date),
            "shipping_line": sl_map_l.get(sl_val, ""),
            "notes":         notes_val,
        }

        xlsx_bytes = export_proforma_invoice(export_rows, meta)

        st.success(f"✅ Proforma invoice **{pi_ref}** generated and saved.")
        st.download_button(
            label     = f"Download {pi_ref}.xlsx",
            data      = xlsx_bytes,
            file_name = f"{pi_ref}.xlsx",
            mime      = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type      = "primary",
        )

        # Clear order lines after successful generation
        st.session_state["pi_lines"] = []

db.close()
