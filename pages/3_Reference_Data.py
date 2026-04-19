import streamlit as st
import pandas as pd
from datetime import date, timedelta
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Port, ShippingLine, Currency, ExchangeRate

st.set_page_config(page_title="Reference Data — ATL Pricing", layout="wide")
st.title("Reference data")

db: Session = SessionLocal()
try:

tab_ports, tab_sl, tab_curr, tab_fx = st.tabs(["Ports", "Shipping lines", "Currencies", "Exchange rates"])

# ── PORTS ────────────────────────────────────────────────────────────────────
with tab_ports:
    with st.expander("➕  Add / edit port", expanded=False):
        pc = st.text_input("Port code *  (e.g. SGSIN, MYPKG)").strip().upper()
        pn = st.text_input("Port name *")
        py = st.text_input("Country *")
        if st.button("Save port", type="primary"):
            if not pc or not pn or not py:
                st.error("All fields required.")
            else:
                ex = db.get(Port, pc)
                if ex:
                    ex.port_name = pn; ex.country = py
                else:
                    db.add(Port(port_code=pc, port_name=pn, country=py))
                db.commit(); st.success(f"Port {pc} saved."); st.rerun()

    ports = db.query(Port).order_by(Port.port_code).all()
    if ports:
        st.dataframe(pd.DataFrame([{"Code": p.port_code, "Port name": p.port_name, "Country": p.country}
                                    for p in ports]), use_container_width=True, hide_index=True)
        del_p = st.selectbox("Delete port", [""] + [p.port_code for p in ports], key="del_port")
        if del_p and st.button("Delete port", type="secondary"):
            db.delete(db.get(Port, del_p)); db.commit(); st.rerun()
    else:
        st.info("No ports yet.")

# ── SHIPPING LINES ───────────────────────────────────────────────────────────
with tab_sl:
    with st.expander("➕  Add / edit shipping line", expanded=False):
        sc = st.text_input("Shipping line code *").strip().upper()
        sn = st.text_input("Shipping line name *")
        if st.button("Save shipping line", type="primary"):
            if not sc or not sn:
                st.error("Both fields required.")
            else:
                ex = db.get(ShippingLine, sc)
                if ex:
                    ex.sl_name = sn
                else:
                    db.add(ShippingLine(sl_code=sc, sl_name=sn))
                db.commit(); st.success(f"Shipping line {sc} saved."); st.rerun()

    sls = db.query(ShippingLine).order_by(ShippingLine.sl_code).all()
    if sls:
        st.dataframe(pd.DataFrame([{"Code": s.sl_code, "Name": s.sl_name} for s in sls]),
                     use_container_width=True, hide_index=True)
        del_s = st.selectbox("Delete shipping line", [""] + [s.sl_code for s in sls], key="del_sl")
        if del_s and st.button("Delete shipping line", type="secondary"):
            db.delete(db.get(ShippingLine, del_s)); db.commit(); st.rerun()
    else:
        st.info("No shipping lines yet.")

# ── CURRENCIES ───────────────────────────────────────────────────────────────
with tab_curr:
    with st.expander("➕  Add currency", expanded=False):
        cc = st.text_input("Currency code *  (e.g. SGD, MYR, USD)").strip().upper()
        cn = st.text_input("Currency name *  (e.g. Singapore Dollar)")
        if st.button("Save currency", type="primary"):
            if not cc or not cn:
                st.error("Both fields required.")
            else:
                ex = db.get(Currency, cc)
                if ex:
                    ex.currency_name = cn
                else:
                    db.add(Currency(currency_code=cc, currency_name=cn))
                db.commit(); st.success(f"Currency {cc} saved."); st.rerun()

    currs = db.query(Currency).order_by(Currency.currency_code).all()
    if currs:
        st.dataframe(pd.DataFrame([{"Code": c.currency_code, "Name": c.currency_name} for c in currs]),
                     use_container_width=True, hide_index=True)
        del_c = st.selectbox("Delete currency", [""] + [c.currency_code for c in currs], key="del_curr")
        if del_c and st.button("Delete currency", type="secondary"):
            db.delete(db.get(Currency, del_c)); db.commit(); st.rerun()
    else:
        st.info("No currencies yet. Add SGD first.")

# ── EXCHANGE RATES ───────────────────────────────────────────────────────────
with tab_fx:
    currs = db.query(Currency).order_by(Currency.currency_code).all()
    curr_codes = [c.currency_code for c in currs]

    with st.expander("➕  Add exchange rate", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            fx_date  = st.date_input("Rate date *", value=date.today())
            fx_base  = st.selectbox("Base currency *", curr_codes, key="fx_base")
        with col2:
            fx_tgt   = st.selectbox("Target currency *",
                                     [c for c in curr_codes if c != fx_base] if curr_codes else [],
                                     key="fx_tgt")
            fx_rate  = st.number_input("Rate *", min_value=0.0, value=1.0, step=0.0001, format="%.6f")
        with col3:
            fx_dir   = st.selectbox("Direction *", ["multiply", "divide"],
                                     help="'multiply': net_cost × rate = SGD  |  'divide': net_cost ÷ rate = SGD")
        if st.button("Save exchange rate", type="primary"):
            if not fx_base or not fx_tgt or fx_rate <= 0:
                st.error("All fields required and rate must be > 0.")
            else:
                # Upsert by date + base + target
                existing = db.query(ExchangeRate).filter(
                    ExchangeRate.rate_date       == fx_date,
                    ExchangeRate.base_currency   == fx_base,
                    ExchangeRate.target_currency == fx_tgt,
                ).first()
                if existing:
                    existing.rate = fx_rate; existing.direction = fx_dir
                else:
                    db.add(ExchangeRate(rate_date=fx_date, base_currency=fx_base,
                                        target_currency=fx_tgt, rate=fx_rate, direction=fx_dir))
                db.commit()
                st.success("Exchange rate saved.")
                st.rerun()

    # Rate table with stale warning
    rates = db.query(ExchangeRate).order_by(ExchangeRate.rate_date.desc()).all()
    if rates:
        today = date.today()
        rate_data = []
        for r in rates:
            age   = (today - r.rate_date).days
            stale = age > 7
            rate_data.append({
                "Date":   str(r.rate_date),
                "Base":   r.base_currency,
                "Target": r.target_currency,
                "Rate":   r.rate,
                "Dir":    r.direction,
                "Age (days)": age,
                "Status": "⚠️ Stale" if stale else "✅ Current",
            })
        df_fx = pd.DataFrame(rate_data)
        st.dataframe(df_fx, use_container_width=True, hide_index=True)

        stale_count = sum(1 for r in rate_data if r["Status"].startswith("⚠️"))
        if stale_count:
            st.warning(f"{stale_count} rate(s) are older than 7 days. Please update before generating prices.")
    else:
        st.info("No exchange rates yet.")

pass
finally:
    db.close()

