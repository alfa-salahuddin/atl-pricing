import streamlit as st
import pandas as pd
from datetime import date
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Product, Supplier, Currency, ExchangeRate, HSCode
from utils.pricing import compute_all

st.set_page_config(page_title="Products — ATL Pricing", layout="wide")
st.title("Products master")

db: Session = SessionLocal()

suppliers  = db.query(Supplier).order_by(Supplier.supplier_code).all()
currencies = db.query(Currency).order_by(Currency.currency_code).all()
hs_codes   = db.query(HSCode).order_by(HSCode.hs_code).all()
rates      = db.query(ExchangeRate).order_by(ExchangeRate.rate_date.desc()).all()

sup_map  = {s.supplier_code: s.name for s in suppliers}
curr_codes = [c.currency_code for c in currencies]
hs_map   = {"": "— none —", **{h.hs_code: f"{h.hs_code} — {h.description}" for h in hs_codes}}

def rate_label(r: ExchangeRate) -> str:
    return f"{r.base_currency}→{r.target_currency}  {r.rate}  ({r.direction})  [{r.rate_date}]"

rate_options = {str(r.id): rate_label(r) for r in rates}

# ── Add / Edit form ──────────────────────────────────────────────────────────
with st.expander("➕  Add / edit product", expanded=False):
    item_code = st.text_input("Item code *").strip().upper()

    col1, col2, col3 = st.columns(3)
    with col1:
        prod_cat  = st.text_input("Product category *  (e.g. Snacks, Cleaning, Diapers)")
        prod_name = st.text_input("Product name *")
        packing   = st.text_input("Packing *  (e.g. 24 x 60g / ctn)")
        uom       = st.text_input("UOM *  (e.g. CTN)")
        origin    = st.text_input("Origin *  (e.g. Malaysia)")
    with col2:
        sup_sel   = st.selectbox("Supplier *", [""] + list(sup_map.keys()),
                                  format_func=lambda x: sup_map.get(x, "— select —") if x else "— select —")
        hs_sel    = st.selectbox("HS code", list(hs_map.keys()),
                                  format_func=lambda x: hs_map[x])
        cost_curr = st.selectbox("Cost currency *", curr_codes if curr_codes else [""])
        rate_sel  = st.selectbox("Exchange rate *", [""] + list(rate_options.keys()),
                                  format_func=lambda x: rate_options.get(x, "— select —") if x else "— select —")
        margin    = st.number_input("Margin % *", min_value=0.0, max_value=99.0, value=18.0, step=0.5)
    with col3:
        cost_price = st.number_input("Cost price *", min_value=0.0, value=0.0, step=0.01, format="%.4f")
        discount   = st.number_input("Discount %", min_value=0.0, max_value=100.0, value=0.0, step=0.5)
        additions  = st.number_input("Cost additions", min_value=0.0, value=0.0, step=0.01, format="%.4f")
        ctn_cbm    = st.number_input("CTN CBM", min_value=0.0, value=0.0, step=0.0001, format="%.4f")
        ctn_wt     = st.number_input("CTN weight (kg)", min_value=0.0, value=0.0, step=0.01)

    # Live FOB preview
    if rate_sel and cost_price > 0:
        r_obj  = db.get(ExchangeRate, int(rate_sel))
        result = compute_all(cost_price, discount, additions, r_obj.rate, r_obj.direction, margin)
        st.info(
            f"**Preview:**  "
            f"Net cost ({cost_curr}) = **{result['net_cost_orig']:.4f}**  →  "
            f"Net cost SGD = **{result['net_cost_sgd']:.4f}**  →  "
            f"**FOB SGD = {result['fob_price_sgd']:.4f}**"
        )

    if st.button("Save product", type="primary"):
        if not item_code or not prod_name or not sup_sel or not cost_curr or not rate_sel:
            st.error("Item code, name, supplier, currency, and exchange rate are required.")
        else:
            r_obj  = db.get(ExchangeRate, int(rate_sel))
            result = compute_all(cost_price, discount, additions, r_obj.rate, r_obj.direction, margin)
            kwargs = dict(
                product_category=prod_cat, hs_code=hs_sel or None, product_name=prod_name,
                packing=packing, uom=uom, origin=origin, supplier_code=sup_sel,
                cost_currency=cost_curr, cost_price=cost_price, discount_pct=discount,
                cost_additions=additions, net_cost_orig=result["net_cost_orig"],
                exchange_rate_id=int(rate_sel), net_cost_sgd=result["net_cost_sgd"],
                ctn_cbm=ctn_cbm or None, ctn_weight=ctn_wt or None,
                margin_pct=margin, fob_price_sgd=result["fob_price_sgd"],
            )
            ex = db.get(Product, item_code)
            if ex:
                for k, v in kwargs.items():
                    setattr(ex, k, v)
            else:
                db.add(Product(item_code=item_code, **kwargs))
            db.commit()
            st.success(f"Product {item_code} saved.")
            st.rerun()

st.divider()

# ── Filter + Table ───────────────────────────────────────────────────────────
col_f1, col_f2 = st.columns(2)
with col_f1:
    f_sup = st.selectbox("Filter by supplier", ["All"] + list(sup_map.keys()),
                          format_func=lambda x: sup_map.get(x, "All suppliers") if x != "All" else "All suppliers")
with col_f2:
    categories = sorted({p.product_category for p in db.query(Product).all()})
    f_cat = st.selectbox("Filter by category", ["All"] + categories)

q = db.query(Product)
if f_sup != "All":
    q = q.filter(Product.supplier_code == f_sup)
if f_cat != "All":
    q = q.filter(Product.product_category == f_cat)
products = q.order_by(Product.item_code).all()

if products:
    df = pd.DataFrame([{
        "Item code":    p.item_code,
        "Category":    p.product_category,
        "Name":        p.product_name,
        "Packing":     p.packing,
        "Supplier":    p.supplier_code,
        "Cost":        f"{p.cost_currency} {p.cost_price:.4f}",
        "Net SGD":     round(p.net_cost_sgd, 4),
        "Margin %":    p.margin_pct,
        "FOB SGD":     round(p.fob_price_sgd, 4),
        "CTN CBM":     p.ctn_cbm or "",
        "Updated":     str(p.last_updated)[:10],
    } for p in products])
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(f"{len(products)} product(s)")

    st.divider()
    del_item = st.selectbox("Delete product", [""] + [p.item_code for p in products])
    if del_item and st.button("Delete", type="secondary"):
        db.delete(db.get(Product, del_item))
        db.commit()
        st.success(f"Product {del_item} deleted.")
        st.rerun()
else:
    st.info("No products found.")

db.close()
