import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import date
from sqlalchemy.orm import Session
from database import SessionLocal
from models import (Customer, Supplier, Port, ShippingLine, Currency,
                    ExchangeRate, HSCode, Product, Quotation, QuotItem, PriceChangeLog)

st.set_page_config(page_title="Backup — ATL Pricing", layout="wide")
st.title("Data backup")

st.write("Export all data to a single Excel workbook. Run this regularly to keep a safe copy of your data.")

db: Session = SessionLocal()
try:

def q_to_df(records) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    cols = [c.name for c in records[0].__table__.columns]
    return pd.DataFrame([{c: getattr(r, c) for c in cols} for r in records])

if st.button("Download full backup", type="primary"):
    tables = {
        "Customers":        db.query(Customer).all(),
        "Suppliers":        db.query(Supplier).all(),
        "Ports":            db.query(Port).all(),
        "Shipping Lines":   db.query(ShippingLine).all(),
        "Currencies":       db.query(Currency).all(),
        "Exchange Rates":   db.query(ExchangeRate).all(),
        "HS Codes":         db.query(HSCode).all(),
        "Products":         db.query(Product).all(),
        "Quotations":       db.query(Quotation).all(),
        "Quotation Items":  db.query(QuotItem).all(),
        "Price Change Log": db.query(PriceChangeLog).all(),
    }

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet_name, records in tables.items():
            df = q_to_df(records)
            if df.empty:
                df = pd.DataFrame(columns=["(no data)"])
            df.to_excel(writer, sheet_name=sheet_name[:31], index=False)

    st.download_button(
        label=f"Save backup — ATL_Pricing_Backup_{date.today()}.xlsx",
        data=buf.getvalue(),
        file_name=f"ATL_Pricing_Backup_{date.today()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )
    st.success("Backup ready. Click the button above to save the file.")

st.divider()
st.subheader("What's in the backup")
st.write("The backup contains one sheet per data table: Customers, Suppliers, Ports, Shipping Lines, Currencies, Exchange Rates, HS Codes, Products, Quotations, Quotation Items, Price Change Log.")
st.info("Tip: Save a backup before any major bulk upload or data change.")

pass
finally:
    db.close()
