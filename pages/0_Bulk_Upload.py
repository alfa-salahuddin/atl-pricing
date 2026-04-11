import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Product, Customer, Supplier, ExchangeRate, Currency
from utils.upload import validate_and_parse, get_template_dataframe, dataframe_to_excel_bytes
from utils.pricing import compute_all

st.set_page_config(page_title="Bulk Upload — ATL Pricing", layout="wide")
st.title("Bulk upload")

db: Session = SessionLocal()

tab_prod, tab_cust = st.tabs(["New products", "Customers"])

# ── NEW PRODUCTS ──────────────────────────────────────────────────────────────
with tab_prod:
    st.subheader("Bulk add new products")

    # ── Show current reference data so user can verify ────────────────────────
    with st.expander("View available suppliers, currencies and exchange rates", expanded=False):
        suppliers = db.query(Supplier).all()
        currencies = db.query(Currency).all()
        rates = db.query(ExchangeRate).order_by(ExchangeRate.rate_date.desc()).all()

        c1, c2, c3 = st.columns(3)
        with c1:
            st.write("**Suppliers**")
            if suppliers:
                for s in suppliers:
                    st.write(f"• `{s.supplier_code}` — {s.name}")
            else:
                st.warning("No suppliers yet — add in Suppliers page first")

        with c2:
            st.write("**Currencies**")
            if currencies:
                for c in currencies:
                    st.write(f"• `{c.currency_code}` — {c.currency_name}")
            else:
                st.warning("No currencies yet — add in Reference Data first")

        with c3:
            st.write("**Exchange rates**")
            if rates:
                for r in rates:
                    st.write(f"• `{r.base_currency}` → `{r.target_currency}` = {r.rate} ({r.direction}) [{r.rate_date}]")
            else:
                st.warning("No exchange rates yet — add in Reference Data first")

    st.divider()

    # ── Download template ─────────────────────────────────────────────────────
    template_df = get_template_dataframe("new_products")
    template_bytes = dataframe_to_excel_bytes(template_df, sheet_name="New Products")
    st.download_button(
        "Download new products template (.xlsx)",
        data=template_bytes,
        file_name="ATL_New_Products_Template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.info("""
**Template column guide:**
- `item_code` — unique code for the product (e.g. TW-CHK-60G)
- `product_category` — e.g. Snacks, Cleaning, Diapers
- `product_name` — full product name
- `packing` — e.g. 24 x 60g / ctn
- `uom` — e.g. CTN
- `origin` — e.g. Malaysia
- `supplier_code` — must match exactly a code from the Suppliers list above
- `cost_currency` — must match exactly a code from the Currencies list above (e.g. MYR)
- `cost_price` — unit cost from supplier
- `margin_pct` — your margin e.g. 18 for 18%
- `discount_pct`, `cost_additions`, `ctn_cbm`, `ctn_weight`, `hs_code` — optional
    """)

    st.divider()

    # ── Upload ────────────────────────────────────────────────────────────────
    uploaded_prod = st.file_uploader(
        "Upload filled new products template",
        type=["xlsx"],
        key="prod_upload"
    )

    if uploaded_prod:
        file_bytes = uploaded_prod.read()
        rows, errors = validate_and_parse(file_bytes, "new_products")

        st.write(f"**Rows read from file:** {len(rows)}")

        if errors:
            st.error("The file has errors — fix and re-upload:")
            for e in errors:
                st.write(f"• {e}")
            st.stop()

        if not rows:
            st.warning("No data rows found in the file. Make sure you have filled in data below the header row.")
            st.stop()

        # ── Validate each row against database ────────────────────────────────
        rates_all = db.query(ExchangeRate).order_by(ExchangeRate.rate_date.desc()).all()

        def best_rate(cost_currency: str):
            for r in rates_all:
                if r.base_currency == cost_currency and r.target_currency == "SGD":
                    return r
                if r.target_currency == cost_currency and r.base_currency == "SGD":
                    return r
            return None

        valid_rows = []
        skipped_rows = []

        for row in rows:
            item_code = str(row["item_code"]).strip().upper()
            issues = []

            # Check duplicate
            if db.get(Product, item_code):
                issues.append(f"Item code `{item_code}` already exists in Products")

            # Check supplier exists
            sup_code = str(row.get("supplier_code") or "").strip().upper()
            if sup_code:
                row["supplier_code"] = sup_code
            sup = db.get(Supplier, sup_code) if sup_code else None
            if not sup:
                issues.append(f"Supplier code `{sup_code}` not found — add it in Suppliers first")

            # Check currency exists
            curr_code = str(row.get("cost_currency") or "").strip().upper()
            if curr_code:
                row["cost_currency"] = curr_code

            # Check exchange rate
            rate_obj = best_rate(curr_code) if curr_code else None
            if curr_code and curr_code != "SGD" and not rate_obj:
                issues.append(f"No exchange rate found for `{curr_code}` → SGD — add it in Reference Data → Exchange Rates")

            if issues:
                skipped_rows.append({"item_code": item_code, "issues": issues})
            else:
                row["item_code"] = item_code
                row["_rate_obj"] = rate_obj
                valid_rows.append(row)

        # ── Show skipped rows ─────────────────────────────────────────────────
        if skipped_rows:
            st.warning(f"{len(skipped_rows)} row(s) have issues and will be skipped:")
            for s in skipped_rows:
                st.write(f"**{s['item_code']}:**")
                for issue in s["issues"]:
                    st.write(f"  • {issue}")

        # ── Show valid rows preview ───────────────────────────────────────────
        if not valid_rows:
            st.error("No valid rows to import. Fix the issues above and re-upload.")
            st.stop()

        preview = []
        for row in valid_rows:
            r = row["_rate_obj"]
            # If currency is SGD, rate = 1 multiply
            rate_val = r.rate if r else 1.0
            rate_dir = r.direction if r else "multiply"

            result = compute_all(
                float(row.get("cost_price") or 0),
                float(row.get("discount_pct") or 0),
                float(row.get("cost_additions") or 0),
                rate_val,
                rate_dir,
                float(row.get("margin_pct") or 0),
            )
            row["_computed"] = result
            preview.append({
                "Item code":   row["item_code"],
                "Name":        row.get("product_name", ""),
                "Category":    row.get("product_category", ""),
                "Supplier":    row.get("supplier_code", ""),
                "Cost":        f"{row.get('cost_currency','')} {float(row.get('cost_price',0)):.4f}",
                "Net SGD":     round(result["net_cost_sgd"], 4),
                "Margin %":    row.get("margin_pct", ""),
                "FOB SGD":     round(result["fob_price_sgd"], 4),
            })

        st.success(f"**{len(valid_rows)} product(s) ready to import.** Review below then click Confirm.")
        st.dataframe(pd.DataFrame(preview), use_container_width=True, hide_index=True)

        st.divider()
        if st.button("✅  Confirm and import products", type="primary", use_container_width=False):
            imported = 0
            import_errors = []
            for row in valid_rows:
                try:
                    r = row["_rate_obj"]
                    result = row["_computed"]
                    db.add(Product(
                        item_code=row["item_code"],
                        product_category=row.get("product_category", ""),
                        hs_code=row.get("hs_code") or None,
                        product_name=row.get("product_name", ""),
                        packing=row.get("packing", ""),
                        uom=row.get("uom", ""),
                        origin=row.get("origin", ""),
                        supplier_code=row.get("supplier_code", ""),
                        cost_currency=row.get("cost_currency", ""),
                        cost_price=float(row.get("cost_price") or 0),
                        discount_pct=float(row.get("discount_pct") or 0),
                        cost_additions=float(row.get("cost_additions") or 0),
                        net_cost_orig=result["net_cost_orig"],
                        exchange_rate_id=r.id if r else None,
                        net_cost_sgd=result["net_cost_sgd"],
                        ctn_cbm=float(row["ctn_cbm"]) if row.get("ctn_cbm") else None,
                        ctn_weight=float(row["ctn_weight"]) if row.get("ctn_weight") else None,
                        margin_pct=float(row.get("margin_pct") or 0),
                        fob_price_sgd=result["fob_price_sgd"],
                    ))
                    imported += 1
                except Exception as e:
                    import_errors.append(f"{row['item_code']}: {str(e)}")

            if import_errors:
                db.rollback()
                st.error("Import failed. Errors:")
                for e in import_errors:
                    st.write(f"• {e}")
            else:
                db.commit()
                st.success(f"✅  {imported} product(s) imported successfully!")
                st.balloons()
                st.info("Go to the Products page to verify your imported products.")

# ── CUSTOMERS ─────────────────────────────────────────────────────────────────
with tab_cust:
    st.subheader("Bulk load customers")

    cust_template_df = get_template_dataframe("customers")
    cust_template_bytes = dataframe_to_excel_bytes(cust_template_df, sheet_name="Customers")
    st.download_button(
        "Download customers template (.xlsx)",
        data=cust_template_bytes,
        file_name="ATL_Customers_Template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.divider()
    uploaded_cust = st.file_uploader(
        "Upload filled customers template",
        type=["xlsx"],
        key="cust_upload"
    )

    if uploaded_cust:
        rows, errors = validate_and_parse(uploaded_cust.read(), "customers")

        st.write(f"**Rows read from file:** {len(rows)}")

        if errors:
            st.error("Fix the following errors and re-upload:")
            for e in errors:
                st.write(f"• {e}")
            st.stop()

        if not rows:
            st.warning("No data rows found in the file.")
            st.stop()

        skipped = []
        valid_rows = []
        for row in rows:
            code = str(row["cust_code"]).strip().upper()
            if db.get(Customer, code):
                skipped.append(f"`{code}` already exists")
            else:
                row["cust_code"] = code
                valid_rows.append(row)

        if skipped:
            st.warning("Skipped (already exist): " + ", ".join(skipped))

        if not valid_rows:
            st.error("No new customers to import.")
            st.stop()

        st.success(f"**{len(valid_rows)} customer(s) ready to import.**")
        preview_df = pd.DataFrame([{
            "Code":    r["cust_code"],
            "Name":    r.get("name", ""),
            "Country": r.get("country", ""),
            "Email":   r.get("email") or "",
            "Contact": r.get("contact_person") or "",
        } for r in valid_rows])
        st.dataframe(preview_df, use_container_width=True, hide_index=True)

        if st.button("✅  Confirm and import customers", type="primary"):
            imported = 0
            import_errors = []
            for row in valid_rows:
                try:
                    db.add(Customer(
                        cust_code=row["cust_code"],
                        name=row.get("name", ""),
                        address=row.get("address"),
                        email=row.get("email"),
                        contact_person=row.get("contact_person"),
                        phone=row.get("phone"),
                        country=row.get("country", ""),
                    ))
                    imported += 1
                except Exception as e:
                    import_errors.append(f"{row['cust_code']}: {str(e)}")

            if import_errors:
                db.rollback()
                st.error("Import failed:")
                for e in import_errors:
                    st.write(f"• {e}")
            else:
                db.commit()
                st.success(f"✅  {imported} customer(s) imported successfully!")
                st.balloons()

db.close()
