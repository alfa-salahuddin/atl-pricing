import streamlit as st
import pandas as pd
from sqlalchemy import func, desc
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Product, Supplier, Currency, ExchangeRate, HSCode
from utils.pricing import compute_all, BASE_CURRENCY

st.set_page_config(page_title="Products — ATL Pricing", layout="wide")
st.title("Products master")

db: Session = SessionLocal()

# ── Reference data ────────────────────────────────────────────────────────────
suppliers  = db.query(Supplier).order_by(Supplier.supplier_code).all()
currencies = db.query(Currency).order_by(Currency.currency_code).all()
hs_codes   = db.query(HSCode).order_by(HSCode.hs_code).all()
rates      = db.query(ExchangeRate).order_by(ExchangeRate.rate_date.desc()).all()

sup_map    = {s.supplier_code: f"{s.supplier_code} — {s.name}" for s in suppliers}
curr_codes = [c.currency_code for c in currencies]
hs_map     = {"": "— none —", **{h.hs_code: f"{h.hs_code} — {h.description}" for h in hs_codes}}

def rate_label(r):
    return f"{r.base_currency} → {r.target_currency}  {r.rate}  ({r.direction})  [{r.rate_date}]"

rate_options = {str(r.id): rate_label(r) for r in rates}


# ── Auto item code generator ──────────────────────────────────────────────────
def next_item_code() -> str:
    """
    Returns next ATL item code.
    Finds the highest existing ATLxxxx number and adds 1.
    Handles 4-digit (ATL1001–ATL9999) then 5-digit (ATL10000+).
    """
    # Get all item codes starting with ATL
    all_codes = [p.item_code for p in db.query(Product.item_code)
                 .filter(Product.item_code.like("ATL%")).all()]
    max_num = 2599  # default starting point
    for code in all_codes:
        try:
            num = int(code[3:])  # strip 'ATL' prefix
            if num > max_num:
                max_num = num
        except ValueError:
            continue
    return f"ATL{max_num + 1}"


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_add, tab_edit, tab_view = st.tabs(["Add product", "Edit / delete product", "View all products"])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — ADD PRODUCT
# ═══════════════════════════════════════════════════════════════════════════════
with tab_add:
    st.subheader("Add new product")

    # Success banner after save
    if "add_saved_code" in st.session_state:
        st.success(f"✅ Item **{st.session_state['add_saved_code']}** successfully saved  "
                   f"(FOB SGD {st.session_state.get('add_saved_fob', 0):.2f}). "
                   f"All fields have been cleared — ready to add the next product.")
        del st.session_state["add_saved_code"]
        if "add_saved_fob" in st.session_state:
            del st.session_state["add_saved_fob"]

    # ── Clone existing product ───────────────────────────────────────────────
    with st.expander("Clone an existing product", expanded=False):
        st.caption("Search for any existing product, edit the fields, then save as a new item code.")
        clone_search = st.text_input("Search by product name", placeholder="e.g. Twisties",
                                      key="clone_search")
        if clone_search:
            matches = db.query(Product).filter(
                Product.product_name.ilike(f"%{clone_search}%")
            ).order_by(Product.product_name).limit(30).all()

            if not matches:
                st.info("No products found.")
            else:
                clone_map = {p.item_code: f"{p.item_code} — {p.product_name} [{p.supplier_code}]"
                             for p in matches}
                clone_sel = st.selectbox("Select product to clone", [""] + list(clone_map.keys()),
                                          format_func=lambda x: clone_map.get(x, "— select —") if x else "— select —",
                                          key="clone_sel")
                if clone_sel:
                    src = db.get(Product, clone_sel)
                    st.info(f"Fields below are pre-filled from **{src.item_code}**. "
                            f"Edit anything you need, then click Save Product. "
                            f"A new item code will be assigned automatically.")
                    if st.button("Load this product into form", type="primary", key="clone_load"):
                        st.session_state["clone_cat"]    = src.product_category
                        st.session_state["clone_name"]   = src.product_name
                        st.session_state["clone_pack"]   = src.packing
                        st.session_state["clone_uom"]    = src.uom
                        st.session_state["clone_orig"]   = src.origin
                        st.session_state["clone_hs"]     = src.hs_code or ""
                        st.session_state["clone_sup"]    = src.supplier_code
                        st.session_state["clone_curr"]   = src.cost_currency
                        st.session_state["clone_rate"]   = str(src.exchange_rate_id) if src.exchange_rate_id else ""
                        st.session_state["clone_cost"]   = float(src.cost_price)
                        st.session_state["clone_disc"]   = float(src.discount_pct)
                        st.session_state["clone_add"]    = float(src.cost_additions)
                        st.session_state["clone_margin"] = float(src.margin_pct)
                        st.session_state["clone_cbm"]    = float(src.ctn_cbm or 0)
                        st.session_state["clone_wt"]     = float(src.ctn_weight or 0)
                        st.session_state["clone_active"] = True
                        st.rerun()

    st.divider()

    # ── Auto item code preview ────────────────────────────────────────────────
    suggested_code = next_item_code()
    st.info(f"Next item code will be: **{suggested_code}** (auto-assigned on save)")

    # Show clone-active notice
    if st.session_state.get("clone_active"):
        st.warning("Cloning mode — fields pre-filled from an existing product. "
                   "Edit as needed and click Save Product to create a new item.")
        if st.button("Clear clone / start fresh", key="clone_clear"):
            for k in list(st.session_state.keys()):
                if k.startswith("clone_"):
                    del st.session_state[k]
            st.rerun()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**Product details**")
        prod_cat  = st.text_input("Product category *", placeholder="e.g. Snacks, Cleaning, Diapers",
                             value=st.session_state.get("clone_cat",""), key="form_cat")
        prod_name = st.text_input("Product name *", value=st.session_state.get("clone_name",""), key="form_name")
        packing   = st.text_input("Packing *", placeholder="e.g. 24 x 60g / ctn",
                             value=st.session_state.get("clone_pack",""), key="form_pack")
        uom       = st.text_input("UOM *", placeholder="e.g. CTN",
                           value=st.session_state.get("clone_uom",""), key="form_uom")
        origin    = st.text_input("Origin *", placeholder="e.g. Malaysia",
                             value=st.session_state.get("clone_orig",""), key="form_orig")
        clone_hs_val = st.session_state.get("clone_hs", "")
        hs_keys      = list(hs_map.keys())
        hs_idx       = hs_keys.index(clone_hs_val) if clone_hs_val in hs_keys else 0
        hs_sel       = st.selectbox("HS code (optional)", hs_keys,
                                     index=hs_idx,
                                     format_func=lambda x: hs_map[x],
                                     key="form_hs")

    with col2:
        st.markdown("**Supplier & costing**")
        clone_sup_val = st.session_state.get("clone_sup", "")
        sup_keys      = [""] + list(sup_map.keys())
        sup_idx       = sup_keys.index(clone_sup_val) if clone_sup_val in sup_keys else 0
        sup_sel       = st.selectbox("Supplier *", sup_keys,
                                      index=sup_idx,
                                      format_func=lambda x: sup_map.get(x, "— select supplier —") if x else "— select supplier —",
                                      key="form_sup")
        clone_curr_val = st.session_state.get("clone_curr", "")
        curr_idx       = curr_codes.index(clone_curr_val) if clone_curr_val in curr_codes else 0
        cost_curr      = st.selectbox("Cost currency *",
                                       curr_codes if curr_codes else [""],
                                       index=curr_idx,
                                       key="form_curr")

        # Exchange rate — SGD auto, others require selection
        if cost_curr == BASE_CURRENCY:
            st.success("SGD cost — exchange rate is 1.00 (automatic, no selection needed)")
            rate_sel = None
        else:
            # Filter rates relevant to selected currency
            relevant_rates = {
                str(r.id): rate_label(r) for r in rates
                if r.base_currency == cost_curr or r.target_currency == cost_curr
            }
            if relevant_rates:
                clone_rate_val = st.session_state.get("clone_rate", "")
                rate_keys      = list(relevant_rates.keys())
                rate_idx       = rate_keys.index(clone_rate_val) if clone_rate_val in rate_keys else 0
                rate_sel = st.selectbox(
                    f"Exchange rate ({cost_curr} → SGD) *",
                    rate_keys,
                    index=rate_idx,
                    format_func=lambda x: relevant_rates.get(x, "— select —"),
                    key="form_rate",
                )
            else:
                st.warning(f"No exchange rate found for {cost_curr} → SGD. Add one in Reference Data first.")
                rate_sel = None

    with col3:
        st.markdown("**Pricing**")
        cost_price = st.number_input("Cost price *",      min_value=0.0, step=0.01, format="%.4f",
                               value=st.session_state.get("clone_cost", 0.0), key="form_cost")
        discount   = st.number_input("Discount %",        min_value=0.0, max_value=100.0, step=0.5,
                               value=st.session_state.get("clone_disc", 0.0), key="form_disc")
        additions  = st.number_input("Cost additions",    min_value=0.0, step=0.01, format="%.4f",
                               value=st.session_state.get("clone_add", 0.0), key="form_add")
        margin     = st.number_input("Margin % *",        min_value=0.0, max_value=99.0, step=0.5,
                               value=st.session_state.get("clone_margin", 18.0), key="form_margin")
        ctn_cbm    = st.number_input("CTN CBM (optional)", min_value=0.0, step=0.0001, format="%.4f",
                               value=st.session_state.get("clone_cbm", 0.0), key="form_cbm")
        ctn_wt     = st.number_input("CTN weight kg (optional)", min_value=0.0, step=0.01,
                               value=st.session_state.get("clone_wt", 0.0), key="form_wt")

    # ── Live FOB price preview ────────────────────────────────────────────────
    st.divider()
    st.markdown("**FOB price preview**")

    if cost_curr == BASE_CURRENCY:
        rate_val = 1.0
        rate_dir = "multiply"
        rate_ok  = True
    elif rate_sel:
        r_obj    = db.get(ExchangeRate, int(rate_sel))
        rate_val = r_obj.rate
        rate_dir = r_obj.direction
        rate_ok  = True
    else:
        rate_val = 0.0
        rate_dir = "multiply"
        rate_ok  = False

    if rate_ok and cost_price > 0:
        result = compute_all(cost_price, discount, additions, rate_val, rate_dir, margin, cost_currency=cost_curr)
        c1p, c2p, c3p, c4p = st.columns(4)
        with c1p:
            st.metric("Net cost (orig currency)", f"{cost_curr} {result['net_cost_orig']:.4f}")
        with c2p:
            st.metric("Net cost SGD", f"SGD {result['net_cost_sgd']:.4f}")
        with c3p:
            st.metric("Margin %", f"{margin}%")
        with c4p:
            st.metric("FOB price SGD", f"SGD {result['fob_price_sgd']:.4f}")

        # Formula breakdown
        with st.expander("Show calculation breakdown"):
            st.code(f"""
Cost price          = {cost_curr} {cost_price:.4f}
Discount            = {discount}%
Cost additions      = {cost_curr} {additions:.4f}
Net cost (orig)     = {cost_price} × (1 - {discount}/100) + {additions} = {cost_curr} {result['net_cost_orig']:.4f}
Exchange rate       = {rate_val} ({rate_dir})
Net cost SGD        = {result['net_cost_sgd']:.4f}
Margin (markup)     = {margin}%
FOB price (raw)     = {result['net_cost_sgd']:.4f} × (1 + {margin}/100) = SGD {round(result['net_cost_sgd'] * (1 + margin/100), 4):.4f}
FOB price SGD       = SGD {result['fob_price_sgd']:.2f}  (rounded up to nearest 0.10)
            """)
    elif cost_price == 0:
        st.info("Enter a cost price to see the FOB price preview.")
    else:
        st.warning("Select an exchange rate to see the FOB price preview.")

    st.divider()

    # ── Save button ───────────────────────────────────────────────────────────
    if st.button("Save product", type="primary", use_container_width=False):
        # Validate required fields
        missing = []
        if not prod_cat:  missing.append("Product category")
        if not prod_name: missing.append("Product name")
        if not packing:   missing.append("Packing")
        if not uom:       missing.append("UOM")
        if not origin:    missing.append("Origin")
        if not sup_sel:   missing.append("Supplier")
        if not cost_curr: missing.append("Cost currency")
        if cost_price <= 0: missing.append("Cost price (must be > 0)")
        if cost_curr != BASE_CURRENCY and not rate_sel:
            missing.append(f"Exchange rate for {cost_curr}")

        if missing:
            st.error("Please fill in: " + ", ".join(missing))
        else:
            # Auto-assign item code at save time
            item_code = next_item_code()

            if cost_curr == BASE_CURRENCY:
                rate_val = 1.0; rate_dir = "multiply"; rate_id = None
            else:
                r_obj    = db.get(ExchangeRate, int(rate_sel))
                rate_val = r_obj.rate; rate_dir = r_obj.direction; rate_id = int(rate_sel)

            result = compute_all(cost_price, discount, additions, rate_val, rate_dir, margin, cost_currency=cost_curr)

            db.add(Product(
                item_code        = item_code,
                product_category = prod_cat,
                hs_code          = hs_sel or None,
                product_name     = prod_name,
                packing          = packing,
                uom              = uom,
                origin           = origin,
                supplier_code    = sup_sel,
                cost_currency    = cost_curr,
                cost_price       = cost_price,
                discount_pct     = discount,
                cost_additions   = additions,
                net_cost_orig    = result["net_cost_orig"],
                exchange_rate_id = rate_id,
                net_cost_sgd     = result["net_cost_sgd"],
                ctn_cbm          = ctn_cbm or None,
                ctn_weight       = ctn_wt  or None,
                margin_pct       = margin,
                fob_price_sgd    = result["fob_price_sgd"],
            ))
            db.commit()
            st.session_state["add_saved_code"] = item_code
            st.session_state["add_saved_fob"]  = result["fob_price_sgd"]
            # Clear all add-form and clone fields
            for key in list(st.session_state.keys()):
                if key.startswith("add_") or key.startswith("clone_") or key.startswith("form_"):
                    del st.session_state[key]
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — EDIT / DELETE PRODUCT
# ═══════════════════════════════════════════════════════════════════════════════
with tab_edit:
    st.subheader("Find product to edit or delete")

    # Success banner
    if "edit_saved_code" in st.session_state:
        st.success(f"✅ Item **{st.session_state['edit_saved_code']}** "
                   f"({st.session_state.get('edit_saved_name','')}) successfully saved. "
                   f"All fields have been cleared.")
        del st.session_state["edit_saved_code"]
        if "edit_saved_name" in st.session_state:
            del st.session_state["edit_saved_name"]

    # Search
    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        search_sup  = st.selectbox("Filter by supplier", ["All"] + list(sup_map.keys()),
                                    format_func=lambda x: sup_map.get(x, "All suppliers") if x != "All" else "All suppliers",
                                    key="edit_sup")
    with col_s2:
        search_code = st.text_input("Search by item code", placeholder="e.g. ATL1001", key="edit_code")
    with col_s3:
        search_name = st.text_input("Search by product name", placeholder="e.g. Twisties", key="edit_name")

    q = db.query(Product)
    if search_sup != "All":
        q = q.filter(Product.supplier_code == search_sup)
    if search_code:
        q = q.filter(Product.item_code.ilike(f"%{search_code}%"))
    if search_name:
        q = q.filter(Product.product_name.ilike(f"%{search_name}%"))

    results = q.order_by(Product.item_code).limit(100).all()

    if not results:
        st.info("No products found. Try adjusting the search filters.")
    else:
        st.caption(f"{len(results)} product(s) found (max 100 shown)")

        result_map = {p.item_code: f"{p.item_code} — {p.product_name}" for p in results}
        sel_item   = st.selectbox("Select product to edit or delete",
                                   [""] + list(result_map.keys()),
                                   format_func=lambda x: result_map.get(x, "— select —") if x else "— select a product —")

        if sel_item:
            prod = db.get(Product, sel_item)

            edit_tab, del_tab = st.tabs(["Edit", "Delete"])

            # ── EDIT ─────────────────────────────────────────────────────────
            with edit_tab:
                st.markdown(f"**Editing: {prod.item_code} — {prod.product_name}**")

                ec1, ec2, ec3 = st.columns(3)
                with ec1:
                    e_cat   = st.text_input("Product category *", value=prod.product_category, key="e_cat")
                    e_name  = st.text_input("Product name *",     value=prod.product_name,     key="e_name")
                    e_pack  = st.text_input("Packing *",          value=prod.packing,           key="e_pack")
                    e_uom   = st.text_input("UOM *",              value=prod.uom,               key="e_uom")
                    e_orig  = st.text_input("Origin *",           value=prod.origin,            key="e_orig")
                    e_hs    = st.selectbox("HS code",
                                           list(hs_map.keys()),
                                           index=list(hs_map.keys()).index(prod.hs_code) if prod.hs_code in hs_map else 0,
                                           format_func=lambda x: hs_map[x], key="e_hs")

                with ec2:
                    e_sup   = st.selectbox("Supplier *",
                                           list(sup_map.keys()),
                                           index=list(sup_map.keys()).index(prod.supplier_code) if prod.supplier_code in sup_map else 0,
                                           format_func=lambda x: sup_map[x], key="e_sup")
                    e_curr  = st.selectbox("Cost currency *",
                                           curr_codes,
                                           index=curr_codes.index(prod.cost_currency) if prod.cost_currency in curr_codes else 0,
                                           key="e_curr")

                    if e_curr == BASE_CURRENCY:
                        st.success("SGD — exchange rate auto = 1.00")
                        e_rate = None
                    else:
                        rel_rates = {str(r.id): rate_label(r) for r in rates
                                     if r.base_currency == e_curr or r.target_currency == e_curr}
                        cur_rate_id = str(prod.exchange_rate_id) if prod.exchange_rate_id else ""
                        rate_keys   = list(rel_rates.keys())
                        rate_idx    = rate_keys.index(cur_rate_id) if cur_rate_id in rate_keys else 0
                        if rel_rates:
                            e_rate = st.selectbox(f"Exchange rate ({e_curr} → SGD) *",
                                                   rate_keys,
                                                   index=rate_idx,
                                                   format_func=lambda x: rel_rates.get(x, x),
                                                   key="e_rate")
                        else:
                            st.warning(f"No exchange rate for {e_curr}. Add in Reference Data.")
                            e_rate = None

                with ec3:
                    e_cost  = st.number_input("Cost price *",    value=float(prod.cost_price),    step=0.01, format="%.4f", key="e_cost")
                    e_disc  = st.number_input("Discount %",      value=float(prod.discount_pct),  step=0.5,  key="e_disc")
                    e_add   = st.number_input("Cost additions",  value=float(prod.cost_additions), step=0.01, format="%.4f", key="e_add")
                    e_marg  = st.number_input("Margin % *",      value=float(prod.margin_pct),    step=0.5,  key="e_marg")
                    e_cbm   = st.number_input("CTN CBM",         value=float(prod.ctn_cbm or 0),  step=0.0001, format="%.4f", key="e_cbm")
                    e_wt    = st.number_input("CTN weight kg",   value=float(prod.ctn_weight or 0), step=0.01, key="e_wt")

                # Live FOB preview while editing
                if e_curr == BASE_CURRENCY:
                    er_val = 1.0; er_dir = "multiply"
                elif e_rate:
                    er_obj = db.get(ExchangeRate, int(e_rate))
                    er_val = er_obj.rate; er_dir = er_obj.direction
                else:
                    er_val = 0.0; er_dir = "multiply"

                if e_cost > 0 and (e_curr == BASE_CURRENCY or e_rate):
                    e_result = compute_all(e_cost, e_disc, e_add, er_val, er_dir, e_marg, cost_currency=e_curr)
                    ep1, ep2, ep3 = st.columns(3)
                    with ep1:
                        st.metric("Net cost SGD",  f"SGD {e_result['net_cost_sgd']:.4f}")
                    with ep2:
                        st.metric("Margin",        f"{e_marg}%")
                    with ep3:
                        st.metric("FOB price SGD", f"SGD {e_result['fob_price_sgd']:.4f}")

                if st.button("Save changes", type="primary", key="save_edit"):
                    if e_curr == BASE_CURRENCY:
                        er_val = 1.0; er_dir = "multiply"; er_id = None
                    elif e_rate:
                        er_obj = db.get(ExchangeRate, int(e_rate))
                        er_val = er_obj.rate; er_dir = er_obj.direction; er_id = int(e_rate)
                    else:
                        st.error("Exchange rate required for non-SGD currency.")
                        st.stop()

                    e_result = compute_all(e_cost, e_disc, e_add, er_val, er_dir, e_marg, cost_currency=e_curr)

                    prod.product_category = e_cat
                    prod.hs_code          = e_hs or None
                    prod.product_name     = e_name
                    prod.packing          = e_pack
                    prod.uom              = e_uom
                    prod.origin           = e_orig
                    prod.supplier_code    = e_sup
                    prod.cost_currency    = e_curr
                    prod.cost_price       = e_cost
                    prod.discount_pct     = e_disc
                    prod.cost_additions   = e_add
                    prod.net_cost_orig    = e_result["net_cost_orig"]
                    prod.exchange_rate_id = er_id
                    prod.net_cost_sgd     = e_result["net_cost_sgd"]
                    prod.ctn_cbm          = e_cbm or None
                    prod.ctn_weight       = e_wt  or None
                    prod.margin_pct       = e_marg
                    prod.fob_price_sgd    = e_result["fob_price_sgd"]

                    db.commit()
                    st.session_state["edit_saved_code"] = sel_item
                    st.session_state["edit_saved_name"] = prod.product_name
                    st.rerun()

            # ── DELETE ────────────────────────────────────────────────────────
            with del_tab:
                st.error("⚠️ Deleting a product is permanent and cannot be undone.")
                st.write(f"**Item code:** {prod.item_code}")
                st.write(f"**Name:** {prod.product_name}")
                st.write(f"**Supplier:** {prod.supplier_code}")
                st.write(f"**Category:** {prod.product_category}")

                confirm_text = st.text_input(
                    f"Type **{prod.item_code}** to confirm deletion",
                    placeholder=f"Type {prod.item_code} here",
                    key="del_confirm"
                )
                if st.button("Delete product", type="secondary", key="del_btn"):
                    if confirm_text.strip().upper() == prod.item_code.upper():
                        db.delete(prod)
                        db.commit()
                        st.success(f"Product **{sel_item}** deleted.")
                        st.rerun()
                    else:
                        st.error(f"Confirmation text doesn't match. Type exactly: {prod.item_code}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — VIEW ALL PRODUCTS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_view:
    st.subheader("All products")

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        f_sup = st.selectbox("Filter by supplier", ["All"] + list(sup_map.keys()),
                              format_func=lambda x: sup_map.get(x, "All") if x != "All" else "All suppliers",
                              key="view_sup")
    with col_f2:
        categories = sorted({p.product_category for p in db.query(Product).all()})
        f_cat      = st.selectbox("Filter by category", ["All"] + categories, key="view_cat")

    q = db.query(Product)
    if f_sup != "All":
        q = q.filter(Product.supplier_code == f_sup)
    if f_cat != "All":
        q = q.filter(Product.product_category == f_cat)
    products = q.order_by(Product.item_code).all()

    if products:
        df = pd.DataFrame([{
            "Item code":  p.item_code,
            "Category":   p.product_category,
            "Name":       p.product_name,
            "Packing":    p.packing,
            "Supplier":   p.supplier_code,
            "Currency":   p.cost_currency,
            "Cost":       round(p.cost_price, 4),
            "Net SGD":    round(p.net_cost_sgd, 4),
            "Margin %":   p.margin_pct,
            "FOB SGD":    round(p.fob_price_sgd, 4),
            "CTN CBM":    p.ctn_cbm or "",
            "Updated":    str(p.last_updated)[:10],
        } for p in products])
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption(f"{len(products)} product(s)")
    else:
        st.info("No products found.")

db.close()
