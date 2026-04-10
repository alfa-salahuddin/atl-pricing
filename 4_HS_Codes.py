import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from database import SessionLocal
from models import HSCode

st.set_page_config(page_title="HS Codes — ATL Pricing", layout="wide")
st.title("HS codes  (Singapore)")

db: Session = SessionLocal()

with st.expander("➕  Add / edit HS code", expanded=False):
    hs       = st.text_input("HS code *  (8-digit Singapore code, e.g. 19059010)").strip()
    category = st.text_input("HS category *  (e.g. Food preparations)")
    desc     = st.text_input("Description *")
    remarks  = st.text_area("Remarks", height=60)

    if st.button("Save HS code", type="primary"):
        if not hs or not category or not desc:
            st.error("HS code, category, and description are required.")
        else:
            ex = db.get(HSCode, hs)
            if ex:
                ex.category = category; ex.description = desc; ex.remarks = remarks
            else:
                db.add(HSCode(hs_code=hs, category=category, description=desc, remarks=remarks))
            db.commit()
            st.success(f"HS code {hs} saved.")
            st.rerun()

st.divider()

# ── Search ───────────────────────────────────────────────────────────────────
search = st.text_input("Search by code or description", placeholder="e.g. 1905 or snack")

q = db.query(HSCode)
if search:
    like = f"%{search}%"
    q = q.filter(
        HSCode.hs_code.ilike(like) |
        HSCode.description.ilike(like) |
        HSCode.category.ilike(like)
    )
codes = q.order_by(HSCode.hs_code).all()

if codes:
    df = pd.DataFrame([{
        "HS code":     c.hs_code,
        "Category":   c.category,
        "Description":c.description,
        "Remarks":    c.remarks or "",
    } for c in codes])
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(f"{len(codes)} code(s) shown")

    st.divider()
    del_hs = st.selectbox("Delete HS code", [""] + [c.hs_code for c in codes])
    if del_hs and st.button("Delete", type="secondary"):
        db.delete(db.get(HSCode, del_hs))
        db.commit()
        st.success(f"HS code {del_hs} deleted.")
        st.rerun()
else:
    st.info("No HS codes found. Add one above." if not search else "No results for that search.")

db.close()
