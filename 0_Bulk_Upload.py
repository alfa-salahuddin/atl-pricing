import streamlit as st
import pandas as pd
from datetime import datetime
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Product, Customer, ExchangeRate
from utils.upload import validate_and_parse, get_template_dataframe, dataframe_to_excel_bytes
from utils.pricing import compute_all

st.set_page_config(page_title="Bulk Upload — ATL Pricing", layout="wide")
st.title("Bulk upload")

db: Session = SessionLocal()

tab_prod, tab_cust = st.tabs(["New products", "Customers"])

# ── NEW PRODUCTS ─────────────────────────────────────────────────────────────
with tab_prod:
    st.subheader("Bulk add new products")
    st.write("Use this to load multiple new products at once — e.g. when onboarding a new supplier range.")

    template_df    = get_template_dataframe("new_products")
    template_bytes = dataframe_to_excel_bytes(template_df, sheet_name="New Products")
    st.download_button(
        "Download new products template (.xlsx)",
        data=template_bytes,
        file_name="ATL_New_Products_Template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.divider()
    uploaded_prod = st.file_uploader("Upload filled new products template", type=["xlsx"], key="prod_upload")

    if uploaded_prod:
        rows, errors = validate_and_parse(uploaded_prod.read(), "new_products")

        if errors:
            st.error("Fix the following errors and re-upload:")
            for e in errors:
                st.write(f"• {e}")
        else:
            # Validate against existing data
            issues     = []
            valid_rows = []
            # Get latest exchange rate for each currency pair to SGD for auto-linking
            rates = db.query(ExchangeRate).order_by(ExchangeRate.rate_date.desc()).all()

            def best_rate_for_currency(cost_currency: str):
                """Find the most recent rate that converts cost_currency to SGD."""
                for r in rates:
                    if r.base_currency == cost_currency and r.target_currency == "SGD":
                        return r
                    if r.target_currency == cost_currency and r.base_currency == "SGD":
                        return r
                return None

            for row in rows:
                item_code = row["item_code"].upper()
                if db.get(Product, item_code):
                    issues.append(f"Item code {item_code} already exists — skipped.")
                    continue

                rate_obj = best_rate_for_currency(row["cost_currency"])
                if not rate_obj:
                    issues.append(f"Item {item_code}: no exchange rate found for {row['cost_currency']} → SGD. Add it in Reference Data first.")
                    continue

                row["_rate_obj"]  = rate_obj
                row["item_code"]  = item_code
                valid_rows.append(row)

            if issues:
                st.warning("The following rows will be skipped:")
                for i in issues:
                    st.write(f"• {i}")

            if valid_rows:
                # Preview
                preview = []
                for row in valid_rows:
                    r      = row["_rate_obj"]
                    result = compute_all(
                        float(row["cost_price"]),
                        float(row.get("discount_pct") or 0),
                        float(row.get("cost_additions") or 0),
                        r.rate, r.direction,
                        float(row["margin_pct"]),
                    )
                    preview.append({
                        "Item code":   row["item_code"],
                        "Name":        row["product_name"],
                        "Supplier":    row["supplier_code"],
                        "Category":    row["product_category"],
                        "Cost":        f"{row['cost_currency']} {float(row['cost_price']):.4f}",
                        "Net SGD":     round(result["net_cost_sgd"], 4),
                        "Margin %":    row["margin_pct"],
                        "FOB SGD":     round(result["fob_price_sgd"], 4),
                    })

                st.success(f"{len(valid_rows)} product(s) ready to import.")
                st.dataframe(pd.DataFrame(preview), use_container_width=True, hide_index=True)

                if st.button("Confirm and import products", type="primary"):
                    for row in valid_rows:
                        r      = row["_rate_obj"]
                        result = compute_all(
                            float(row["cost_price"]),
                            float(row.get("discount_pct") or 0),
                            float(row.get("cost_additions") or 0),
                            r.rate, r.direction,
                            float(row["margin_pct"]),
                        )
                        db.add(Product(
                            item_code=row["item_code"],
                            product_category=row["product_category"],
                            hs_code=row.get("hs_code") or None,
                            product_name=row["product_name"],
                            packing=row["packing"],
                            uom=row["uom"],
                            origin=row["origin"],
                            supplier_code=row["supplier_code"],
                            cost_currency=row["cost_currency"],
                            cost_price=float(row["cost_price"]),
                            discount_pct=float(row.get("discount_pct") or 0),
                            cost_additions=float(row.get("cost_additions") or 0),
                            net_cost_orig=result["net_cost_orig"],
                            exchange_rate_id=r.id,
                            net_cost_sgd=result["net_cost_sgd"],
                            ctn_cbm=float(row["ctn_cbm"]) if row.get("ctn_cbm") else None,
                            ctn_weight=float(row["ctn_weight"]) if row.get("ctn_weight") else None,
                            margin_pct=float(row["margin_pct"]),
                            fob_price_sgd=result["fob_price_sgd"],
                        ))
                    db.commit()
                    st.success(f"✅  {len(valid_rows)} product(s) imported successfully.")
                    st.balloons()

# ── CUSTOMERS ────────────────────────────────────────────────────────────────
with tab_cust:
    st.subheader("Bulk load customers")
    st.write("Use this to import your existing customer list in one go.")

    cust_template_df    = get_template_dataframe("customers")
    cust_template_bytes = dataframe_to_excel_bytes(cust_template_df, sheet_name="Customers")
    st.download_button(
        "Download customers template (.xlsx)",
        data=cust_template_bytes,
        file_name="ATL_Customers_Template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.divider()
    uploaded_cust = st.file_uploader("Upload filled customers template", type=["xlsx"], key="cust_upload")

    if uploaded_cust:
        rows, errors = validate_and_parse(uploaded_cust.read(), "customers")

        if errors:
            st.error("Fix the following errors and re-upload:")
            for e in errors:
                st.write(f"• {e}")
        else:
            skipped    = []
            valid_rows = []
            for row in rows:
                code = row["cust_code"].upper()
                if db.get(Customer, code):
                    skipped.append(f"{code} already exists — skipped.")
                else:
                    row["cust_code"] = code
                    valid_rows.append(row)

            if skipped:
                st.warning("Skipped (already exist): " + ", ".join(skipped))

            if valid_rows:
                st.success(f"{len(valid_rows)} customer(s) ready to import.")
                preview_df = pd.DataFrame([{
                    "Code":    r["cust_code"],
                    "Name":    r["name"],
                    "Country": r["country"],
                    "Email":   r.get("email") or "",
                    "Contact": r.get("contact_person") or "",
                } for r in valid_rows])
                st.dataframe(preview_df, use_container_width=True, hide_index=True)

                if st.button("Confirm and import customers", type="primary"):
                    for row in valid_rows:
                        db.add(Customer(
                            cust_code=row["cust_code"],
                            name=row["name"],
                            address=row.get("address"),
                            email=row.get("email"),
                            contact_person=row.get("contact_person"),
                            phone=row.get("phone"),
                            country=row["country"],
                        ))
                    db.commit()
                    st.success(f"✅  {len(valid_rows)} customer(s) imported.")
                    st.balloons()

db.close()
