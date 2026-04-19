import streamlit as st
import pandas as pd
from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database import SessionLocal
from models import (Port, Supplier, Product, Customer, Quotation,
                    QuotItem, ShippingLine)
from utils.export import export_proforma_invoice

st.set_page_config(page_title="Proforma Invoice — ATL Pricing", layout="wide")
st.title("Proforma invoice")

db: Session = SessionLocal()


# ── Helpers ───────────────────────────────────────────────────────────────────
def generate_pi_ref(cust_code: str) -> str:
    """OL + MMYY + CustCode  e.g. OL0426SEY001"""
    today = date.today()
    base  = f"OL{today.strftime('%y%m')}{cust_code.upper()}"
    # If ref already exists, append -2, -3 etc.
    existing = [q.quot_id for q in db.query(Quotation.quot_id)
                .filter(Quotation.quot_id.like(f"{base}%")).all()]
    if not existing:
        return base
    for suffix in range(2, 100):
        candidate = f"{base}-{suffix}"
        if candidate not in existing:
            return candidate
    return base


def get_product_map():
    return {p.item_code: p for p in db.query(Product).all()}


def get_export_rows(lines, prod_map):
    rows = []
    for line in lines:
        p = prod_map.get(line["item_code"])
        rows.append({
            "item_code":    line["item_code"],
            "product_name": line["product_name"],
            "packing":      line.get("packing", p.packing if p else ""),
            "uom":          line.get("uom", p.uom if p else ""),
            "origin":       line.get("origin", p.origin if p else ""),
            "fob_price_sgd":line["net_fob"],
            "qty_ctns":     line["qty_ctns"],
            "ctn_cbm":      line.get("ctn_cbm", p.ctn_cbm if p else 0) or 0,
            "ctn_weight":   line.get("ctn_weight", p.ctn_weight if p else 0) or 0,
        })
    return rows


def build_meta(quot, lines, db):
    cust_obj = db.get(Customer, quot.cust_code) if quot.cust_code else None
    port_obj = db.get(Port, quot.port_code)     if quot.port_code else None
    sl_obj   = db.get(ShippingLine, quot.sl_code) if quot.sl_code else None
    validity_date = quot.created_date + timedelta(days=quot.validity_days or 30)
    return {
        "quot_id":       quot.quot_id,
        "cust_name":     cust_obj.name     if cust_obj else "",
        "cust_address":  cust_obj.address  if cust_obj else "",
        "supplier_name": ", ".join(sorted({l["supplier_code"] for l in lines})),
        "port_name":     port_obj.port_name if port_obj else quot.port_code or "",
        "incoterm":      quot.incoterm or "",
        "validity_date": str(validity_date),
        "shipping_line": sl_obj.sl_name if sl_obj else "",
        "notes":         quot.notes or "",
    }


def lines_from_db(quot_id):
    """Load saved QuotItems into session-state line format."""
    prod_map = get_product_map()
    items    = db.query(QuotItem).filter(QuotItem.quot_id == quot_id).all()
    lines    = []
    for item in items:
        p = prod_map.get(item.item_code)
        base_fob = p.fob_price_sgd if p else item.fob_price_sgd
        discount = round(base_fob - item.fob_price_sgd, 2) if p else 0.0
        lines.append({
            "item_code":     item.item_code,
            "product_name":  p.product_name  if p else item.item_code,
            "packing":       p.packing        if p else "",
            "uom":           p.uom            if p else "",
            "origin":        p.origin         if p else "",
            "supplier_code": p.supplier_code  if p else "",
            "port_code":     "",
            "fob_price_sgd": base_fob,
            "item_discount": discount,
            "net_fob":       item.fob_price_sgd,
            "qty_ctns":      item.qty_ctns or 0,
            "ctn_cbm":       p.ctn_cbm        if p else 0,
            "ctn_weight":    p.ctn_weight      if p else 0,
        })
    return lines


# ── Session state init ────────────────────────────────────────────────────────
if "pi_lines"   not in st.session_state: st.session_state["pi_lines"]   = []
if "pi_mode"    not in st.session_state: st.session_state["pi_mode"]    = "new"
if "pi_edit_id" not in st.session_state: st.session_state["pi_edit_id"] = None


# ═══════════════════════════════════════════════════════════════════════════════
# MODE SELECTOR
# ═══════════════════════════════════════════════════════════════════════════════
mode_choice = st.radio(
    "What would you like to do?",
    ["1. Enter new proforma", "2. Edit / delete existing proforma"],
    horizontal=True,
    key="pi_mode_radio",
)
mode = "new" if "1." in mode_choice else "edit"
st.divider()


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED — product selection panel (used in both new and edit modes)
# ═══════════════════════════════════════════════════════════════════════════════
def product_selection_panel(line_key: str):
    """Renders the port→supplier→category→product table.
       Appends selected rows to st.session_state[line_key]."""
    ports = db.query(Port).order_by(Port.port_code).all()
    if not ports:
        st.warning("No ports configured.")
        return

    port_map = {p.port_code: f"{p.port_code} — {p.port_name}" for p in ports}
    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        sel_port = st.selectbox("Port of loading", list(port_map.keys()),
                                 format_func=lambda x: port_map[x], key=f"{line_key}_port")
    with col_p2:
        suppliers = db.query(Supplier).filter(
            Supplier.port_code == sel_port
        ).order_by(Supplier.supplier_code).all()
        if not suppliers:
            st.warning(f"No suppliers for port {sel_port}.")
            return
        sup_map  = {s.supplier_code: f"{s.supplier_code} — {s.name}" for s in suppliers}
        sel_sup  = st.selectbox("Supplier", list(sup_map.keys()),
                                 format_func=lambda x: sup_map[x], key=f"{line_key}_sup")
    with col_p3:
        all_cats = sorted({p.product_category for p in
                           db.query(Product).filter(Product.supplier_code == sel_sup).all()})
        sel_cats = st.multiselect("Category filter", all_cats, default=all_cats,
                                   key=f"{line_key}_cats")

    q = db.query(Product).filter(Product.supplier_code == sel_sup)
    if sel_cats:
        q = q.filter(Product.product_category.in_(sel_cats))
    products = q.order_by(Product.product_category, Product.item_code).all()

    if not products:
        st.info("No products found.")
        return

    prod_map = {p.item_code: p for p in products}
    df_sel   = pd.DataFrame([{
        "Select":        False,
        "Item code":     p.item_code,
        "Category":      p.product_category,
        "Product name":  p.product_name,
        "Packing":       p.packing,
        "UOM":           p.uom,
        "Cost SGD":      round(p.net_cost_sgd, 4),
        "Margin %":      round(p.margin_pct, 2),
        "FOB SGD":       round(p.fob_price_sgd, 2),
        "Qty (ctns)":    0,
        "Item discount": 0.0,
        "Net FOB SGD":   round(p.fob_price_sgd, 2),
    } for p in products])

    edited = st.data_editor(
        df_sel,
        column_config={
            "Select":        st.column_config.CheckboxColumn("Select", default=False),
            "Cost SGD":      st.column_config.NumberColumn("Cost SGD",       format="%.4f", disabled=True),
            "Margin %":      st.column_config.NumberColumn("Margin %",        min_value=0.0, max_value=99.0,
                                                            step=0.5, format="%.2f",
                                                            help="Edit margin for this order only — product master not changed"),
            "FOB SGD":       st.column_config.NumberColumn("FOB SGD (master)",format="%.2f", disabled=True),
            "Qty (ctns)":    st.column_config.NumberColumn("Qty (ctns)",      min_value=0, step=1),
            "Item discount": st.column_config.NumberColumn("Item disc (SGD)", min_value=0.0, step=0.0001,
                                                            format="%.4f"),
            "Net FOB SGD":   st.column_config.NumberColumn("Net FOB SGD",    format="%.2f", disabled=True),
        },
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        key=f"{line_key}_editor",
    )
    # Recompute FOB from cost using edited margin, then apply discount
    import math
    def calc_fob(row):
        cost    = float(row.get("Cost SGD", 0))
        margin  = float(row.get("Margin %", 0))
        disc    = float(row.get("Item discount", 0))
        raw_fob = cost * (1 + margin / 100)
        rounded = math.ceil(round(raw_fob * 10, 8)) / 10   # round up to 0.10
        return max(0.0, round(rounded - disc, 4))
    edited["Net FOB SGD"] = edited.apply(calc_fob, axis=1)
    selected = edited[(edited["Select"] == True) & (edited["Qty (ctns)"] > 0)]

    if st.button("➕  Add to order", type="primary",
                  disabled=len(selected) == 0, key=f"{line_key}_add"):
        added = 0
        for _, row in selected.iterrows():
            p       = prod_map.get(row["Item code"])
            cost_sgd   = float(row.get("Cost SGD", 0))
            edit_margin= float(row.get("Margin %", 0))
            import math
            raw_fob    = cost_sgd * (1 + edit_margin / 100)
            fob_rounded= math.ceil(round(raw_fob * 10, 8)) / 10
            net_fob    = max(0.0, round(fob_rounded - float(row["Item discount"]), 4))
            existing = next((l for l in st.session_state[line_key]
                             if l["item_code"] == row["Item code"]), None)
            if existing:
                existing["qty_ctns"]      = int(row["Qty (ctns)"])
                existing["item_discount"] = float(row["Item discount"])
                existing["order_margin"]  = float(row.get("Margin %", p.margin_pct if p else 0))
                existing["net_fob"]       = net_fob
            else:
                st.session_state[line_key].append({
                    "item_code":     row["Item code"],
                    "product_name":  row["Product name"],
                    "packing":       row["Packing"],
                    "uom":           row["UOM"],
                    "origin":        p.origin if p else "",
                    "supplier_code": sel_sup,
                    "port_code":     sel_port,
                    "fob_price_sgd": float(row["FOB SGD"]),
                    "cost_sgd":      float(row.get("Cost SGD", p.net_cost_sgd if p else 0)),
                    "order_margin":  float(row.get("Margin %", p.margin_pct if p else 0)),
                    "item_discount": float(row["Item discount"]),
                    "net_fob":       net_fob,
                    "qty_ctns":      int(row["Qty (ctns)"]),
                    "ctn_cbm":       p.ctn_cbm    if p else 0,
                    "ctn_weight":    p.ctn_weight  if p else 0,
                })
            added += 1
        if added:
            st.success(f"✅ {added} line(s) added. Select another supplier to continue adding.")
            st.rerun()


def order_lines_panel(line_key: str):
    """Renders the live order lines table with totals and remove options."""
    lines = st.session_state[line_key]
    if not lines:
        st.info("No lines added yet.")
        return

    st.subheader(f"Order lines — {len(lines)} item(s)")
    total_amount = total_cbm = total_ctns = 0
    display_rows = []
    for i, line in enumerate(lines):
        amount   = round(line["net_fob"] * line["qty_ctns"], 2)
        line_cbm = round((line["ctn_cbm"] or 0) * line["qty_ctns"], 4)
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
            "Margin %":     line.get("order_margin", line.get("fob_price_sgd", 0)),
            "FOB SGD":      round(line["fob_price_sgd"], 2),
            "Discount":     round(line["item_discount"], 4),
            "Net FOB":      round(line["net_fob"], 4),
            "Amount SGD":   amount,
            "CBM":          line_cbm,
        })

    st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)

    col_t1, col_t2, col_t3, col_t4 = st.columns(4)
    col_t1.metric("Lines",      len(lines))
    col_t2.metric("Total ctns", total_ctns)
    col_t3.metric("Total CBM",  f"{round(total_cbm, 4)}")
    col_t4.metric("Total SGD",  f"SGD {round(total_amount, 2):,.2f}")

    col_r1, col_r2 = st.columns([3, 7])
    with col_r1:
        remove_opts = {l["item_code"]: f"{l['item_code']} — {l['product_name']}" for l in lines}
        remove_sel  = st.selectbox("Remove a line", [""] + list(remove_opts.keys()),
                                    format_func=lambda x: remove_opts.get(x, "— select —") if x else "— select to remove —",
                                    key=f"{line_key}_remove")
    with col_r2:
        st.write("")
        if remove_sel and st.button("Remove line", key=f"{line_key}_remove_btn"):
            st.session_state[line_key] = [l for l in lines if l["item_code"] != remove_sel]
            st.rerun()

    if st.button("🗑  Clear all lines", key=f"{line_key}_clear"):
        st.session_state[line_key] = []
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# MODE 1 — NEW PROFORMA
# ═══════════════════════════════════════════════════════════════════════════════
if mode == "new":
    if "new_pi_lines" not in st.session_state:
        st.session_state["new_pi_lines"] = []

    # PI settings
    with st.expander("PI settings — customer, incoterm, notes",
                      expanded=len(st.session_state["new_pi_lines"]) == 0):
        customers = db.query(Customer).order_by(Customer.cust_code).all()
        if not customers:
            st.warning("No customers yet.")
            st.stop()

        cust_map = {c.cust_code: f"{c.cust_code} — {c.name}" for c in customers}
        sls      = db.query(ShippingLine).order_by(ShippingLine.sl_code).all()
        sl_map   = {s.sl_code: f"{s.sl_code} — {s.sl_name}" for s in sls}

        c1, c2, c3 = st.columns(3)
        with c1:
            sel_cust = st.selectbox("Customer *", list(cust_map.keys()),
                                     format_func=lambda x: cust_map[x], key="new_pi_cust")
            cust_obj = db.get(Customer, sel_cust)
            if cust_obj and cust_obj.address:
                st.caption(cust_obj.address)
        with c2:
            new_inco = st.selectbox("Incoterm", ["FOB","CFR","CIF","EXW","CPT"], key="new_pi_inco")
            new_val  = st.number_input("Validity (days)", 1, 365, 30, key="new_pi_val")
        with c3:
            new_sl   = st.selectbox("Shipping line (optional)", [""] + list(sl_map.keys()),
                                     format_func=lambda x: sl_map.get(x,"— none —") if x else "— none —",
                                     key="new_pi_sl")
            new_notes= st.text_area("Notes", height=68, key="new_pi_notes")

    st.divider()
    st.subheader("Add products to order")
    product_selection_panel("new_pi_lines")
    st.divider()
    order_lines_panel("new_pi_lines")

    lines = st.session_state["new_pi_lines"]
    if lines:
        st.divider()
        st.subheader("Generate proforma invoice")
        cust_obj = db.get(Customer, st.session_state.get("new_pi_cust", ""))
        if cust_obj:
            pi_ref = generate_pi_ref(cust_obj.cust_code)
            st.info(f"Order reference: **{pi_ref}**")

        if st.button("Generate proforma invoice", type="primary",
                      disabled=not cust_obj or not lines):
            incoterm_v = st.session_state.get("new_pi_inco", "FOB")
            val_days_v = int(st.session_state.get("new_pi_val", 30))
            sl_v       = st.session_state.get("new_pi_sl", "")
            notes_v    = st.session_state.get("new_pi_notes", "")
            val_date   = date.today() + timedelta(days=val_days_v)
            port_code  = lines[0]["port_code"]
            sup_code   = lines[0]["supplier_code"]

            quot = Quotation(
                quot_id       = pi_ref,
                quot_type     = "pi",
                cust_code     = cust_obj.cust_code,
                port_code     = port_code,
                supplier_code = sup_code,
                incoterm      = incoterm_v,
                validity_days = val_days_v,
                sl_code       = sl_v or None,
                created_date  = date.today(),
                notes         = notes_v,
            )
            db.add(quot)
            for line in lines:
                db.add(QuotItem(
                    quot_id       = pi_ref,
                    item_code     = line["item_code"],
                    qty_ctns      = line["qty_ctns"],
                    fob_price_sgd = line["net_fob"],
                    override_price= line["net_fob"] if line["item_discount"] > 0 else None,
                ))
            try:
                db.commit()
            except Exception as e:
                db.rollback()
                st.error(f"Could not save: {e}")
                st.stop()

            prod_map  = get_product_map()
            meta      = build_meta(quot, lines, db)
            meta["supplier_name"] = ", ".join(sorted({l["supplier_code"] for l in lines}))
            xlsx      = export_proforma_invoice(get_export_rows(lines, prod_map), meta)

            st.success(f"✅ Proforma **{pi_ref}** saved.")
            st.download_button(
                f"Download {pi_ref}.xlsx", data=xlsx,
                file_name=f"{pi_ref}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
            )
            st.session_state["new_pi_lines"] = []


# ═══════════════════════════════════════════════════════════════════════════════
# MODE 2 — EDIT / DELETE EXISTING PROFORMA
# ═══════════════════════════════════════════════════════════════════════════════
else:
    st.subheader("Find existing proforma")

    # Date filter
    col_d1, col_d2, col_d3 = st.columns(3)
    with col_d1:
        date_from = st.date_input("From date", value=date.today().replace(day=1), key="edit_from")
    with col_d2:
        date_to   = st.date_input("To date",   value=date.today(),               key="edit_to")
    with col_d3:
        customers = db.query(Customer).order_by(Customer.cust_code).all()
        cust_map  = {"All": "All customers",
                     **{c.cust_code: f"{c.cust_code} — {c.name}" for c in customers}}
        f_cust    = st.selectbox("Filter by customer", list(cust_map.keys()),
                                  format_func=lambda x: cust_map[x], key="edit_cust_filter")

    # Query proformas
    q = db.query(Quotation).filter(
        Quotation.quot_type   == "pi",
        Quotation.created_date >= date_from,
        Quotation.created_date <= date_to,
    ).order_by(desc(Quotation.created_date))
    if f_cust != "All":
        q = q.filter(Quotation.cust_code == f_cust)
    proformas = q.all()

    if not proformas:
        st.info("No proformas found for the selected date range.")
        st.stop()

    # List proformas
    pf_rows = []
    for pf in proformas:
        cust = db.get(Customer, pf.cust_code) if pf.cust_code else None
        items = db.query(QuotItem).filter(QuotItem.quot_id == pf.quot_id).all()
        total = sum((i.fob_price_sgd or 0) * (i.qty_ctns or 0) for i in items)
        pf_rows.append({
            "Reference":   pf.quot_id,
            "Date":        str(pf.created_date),
            "Customer":    cust.name if cust else pf.cust_code or "",
            "Lines":       len(items),
            "Total SGD":   round(total, 2),
            "Incoterm":    pf.incoterm or "",
        })

    st.dataframe(pd.DataFrame(pf_rows), use_container_width=True, hide_index=True)
    st.caption(f"{len(proformas)} proforma(s) found")

    # Select one to work on
    pf_map  = {pf.quot_id: f"{pf.quot_id}  ({str(pf.created_date)})  — {pf.cust_code or ''}"
               for pf in proformas}
    sel_pf  = st.selectbox("Select proforma to edit or delete", [""] + list(pf_map.keys()),
                            format_func=lambda x: pf_map.get(x, "— select —") if x else "— select a proforma —",
                            key="edit_sel_pf")

    if not sel_pf:
        st.stop()

    quot     = db.get(Quotation, sel_pf)
    cust_obj = db.get(Customer,  quot.cust_code) if quot.cust_code else None

    edit_pf_tab, del_pf_tab = st.tabs(["Edit proforma", "Delete proforma"])

    # ── EDIT ─────────────────────────────────────────────────────────────────
    with edit_pf_tab:
        st.markdown(f"**Editing: {quot.quot_id}**")

        # Load existing lines into session state (only once per selection)
        edit_key = f"edit_pi_lines_{sel_pf}"
        if edit_key not in st.session_state:
            st.session_state[edit_key] = lines_from_db(sel_pf)

        # PI header fields
        sls    = db.query(ShippingLine).order_by(ShippingLine.sl_code).all()
        sl_map = {s.sl_code: f"{s.sl_code} — {s.sl_name}" for s in sls}

        with st.expander("Edit PI header", expanded=False):
            customers = db.query(Customer).order_by(Customer.cust_code).all()
            cust_map2 = {c.cust_code: f"{c.cust_code} — {c.name}" for c in customers}
            ec1, ec2, ec3 = st.columns(3)
            with ec1:
                e_cust  = st.selectbox("Customer", list(cust_map2.keys()),
                                        index=list(cust_map2.keys()).index(quot.cust_code)
                                        if quot.cust_code in cust_map2 else 0,
                                        format_func=lambda x: cust_map2[x], key=f"e_cust_{sel_pf}")
            with ec2:
                e_inco  = st.selectbox("Incoterm", ["FOB","CFR","CIF","EXW","CPT"],
                                        index=["FOB","CFR","CIF","EXW","CPT"].index(quot.incoterm)
                                        if quot.incoterm in ["FOB","CFR","CIF","EXW","CPT"] else 0,
                                        key=f"e_inco_{sel_pf}")
                e_val   = st.number_input("Validity (days)", 1, 365,
                                           value=quot.validity_days or 30, key=f"e_val_{sel_pf}")
            with ec3:
                sl_keys = [""] + list(sl_map.keys())
                e_sl    = st.selectbox("Shipping line", sl_keys,
                                        index=sl_keys.index(quot.sl_code)
                                        if quot.sl_code in sl_keys else 0,
                                        format_func=lambda x: sl_map.get(x,"— none —") if x else "— none —",
                                        key=f"e_sl_{sel_pf}")
                e_notes = st.text_area("Notes", value=quot.notes or "", height=68,
                                        key=f"e_notes_{sel_pf}")

            if st.button("Save header changes", key=f"save_header_{sel_pf}"):
                quot.cust_code    = e_cust
                quot.incoterm     = e_inco
                quot.validity_days= e_val
                quot.sl_code      = e_sl or None
                quot.notes        = e_notes
                db.commit()
                st.success("Header updated.")

        st.divider()
        st.subheader("Add more products")
        product_selection_panel(edit_key)

        st.divider()
        order_lines_panel(edit_key)

        lines = st.session_state[edit_key]
        if lines:
            st.divider()
            if st.button("💾  Save all line changes & re-download", type="primary",
                          key=f"save_lines_{sel_pf}"):
                # Delete old items and reinsert
                db.query(QuotItem).filter(QuotItem.quot_id == sel_pf).delete()
                for line in lines:
                    db.add(QuotItem(
                        quot_id       = sel_pf,
                        item_code     = line["item_code"],
                        qty_ctns      = line["qty_ctns"],
                        fob_price_sgd = line["net_fob"],
                        override_price= line["net_fob"] if line["item_discount"] > 0 else None,
                    ))
                try:
                    db.commit()
                except Exception as e:
                    db.rollback()
                    st.error(f"Save failed: {e}")
                    st.stop()

                prod_map = get_product_map()
                meta     = build_meta(quot, lines, db)
                meta["supplier_name"] = ", ".join(sorted({l["supplier_code"] for l in lines}))
                xlsx     = export_proforma_invoice(get_export_rows(lines, prod_map), meta)

                st.success(f"✅ Proforma **{sel_pf}** updated.")
                st.download_button(
                    f"Download {sel_pf}.xlsx", data=xlsx,
                    file_name=f"{sel_pf}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary",
                )

    # ── DELETE ────────────────────────────────────────────────────────────────
    with del_pf_tab:
        st.error("⚠️ Deleting a proforma is permanent and cannot be undone.")
        items    = db.query(QuotItem).filter(QuotItem.quot_id == sel_pf).all()
        cust_obj = db.get(Customer, quot.cust_code) if quot.cust_code else None
        st.write(f"**Reference:**  {quot.quot_id}")
        st.write(f"**Customer:**   {cust_obj.name if cust_obj else quot.cust_code}")
        st.write(f"**Date:**       {quot.created_date}")
        st.write(f"**Line items:** {len(items)}")

        confirm = st.text_input(
            f"Type **{quot.quot_id}** to confirm deletion",
            placeholder=f"Type {quot.quot_id}",
            key=f"del_pf_confirm_{sel_pf}",
        )
        if st.button("Delete proforma", type="secondary", key=f"del_pf_btn_{sel_pf}"):
            if confirm.strip().upper() == quot.quot_id.upper():
                db.query(QuotItem).filter(QuotItem.quot_id == sel_pf).delete()
                db.delete(quot)
                db.commit()
                # Clear session state for this PI
                if edit_key in st.session_state:
                    del st.session_state[edit_key]
                st.success(f"Proforma **{sel_pf}** deleted.")
                st.rerun()
            else:
                st.error(f"Text doesn't match. Type exactly: {quot.quot_id}")

db.close()
