import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Product, Customer, Supplier, ExchangeRate, Currency
from utils.upload import validate_and_parse, get_template_dataframe, dataframe_to_excel_bytes
from utils.pricing import compute_all, BASE_CURRENCY

st.set_page_config(page_title="Bulk Upload — ATL Pricing", layout="wide")
st.title("Bulk upload")

db: Session = SessionLocal()

tab_prod, tab_cust = st.tabs(["New products", "Customers"])

# ── NEW PRODUCTS ──────────────────────────────────────────────────────────────
with tab_prod:
    st.subheader("Bulk add new products")

    with st.expander("View available suppliers, currencies and exchange rates", expanded=False):
        suppliers  = db.query(Supplier).all()
        currencies = db.query(Currency).all()
        rates      = db.query(ExchangeRate).order_by(ExchangeRate.rate_date.desc()).all()

        c1, c2, c3 = st.columns(3)
        with c1:
            st.write("**Suppliers**")
            if suppliers:
                for s in suppliers:
                    st.write(f"• `{s.supplier_code}` — {s.name}")
            else:
                st.warning("No suppliers yet")
        with c2:
            st.write("**Currencies**")
            if currencies:
                for c in currencies:
                    st.write(f"• `{c.currency_code}` — {c.currency_name}")
            else:
                st.warning("No currencies yet")
        with c3:
            st.write("**Exchange rates**")
            st.write(f"• `SGD` → `SGD` = 1.00 multiply *(auto)*")
            if rates:
                for r in rates:
                    st.write(f"• `{r.base_currency}` → `{r.target_currency}` = {r.rate} ({r.direction}) [{r.rate_date}]")
            else:
                st.warning("No exchange rates yet")

    st.divider()

    template_df    = get_template_dataframe("new_products")
    template_bytes = dataframe_to_excel_bytes(template_df, sheet_name="New Products")
    st.download_button(
        "Download new products template (.xlsx)",
        data=template_bytes,
        file_name="ATL_New_Products_Template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.divider()

    uploaded_prod = st.file_uploader(
        "Upload filled new products template",
        type=["xlsx"],
        key="prod_upload",
    )

    if uploaded_prod:
        file_bytes   = uploaded_prod.read()
        rows, errors = validate_and_parse(file_bytes, "new_products")

        st.write(f"**Rows read from file:** {len(rows)}")

        if errors:
            st.warning(f"{len(errors)} validation error(s):")
            for e in errors[:20]:
                st.write(f"• {e}")
            if len(errors) > 20:
                st.write(f"... and {len(errors) - 20} more")

        if not rows:
            st.error("No valid rows to import.")
            st.stop()

        # Load reference data
        rates_all    = db.query(ExchangeRate).order_by(ExchangeRate.rate_date.desc()).all()
        sup_codes    = {s.supplier_code for s in db.query(Supplier).all()}
        curr_codes     = {c.currency_code for c in db.query(Currency).all()}
        existing_items = {p.item_code for p in db.query(Product).all()}
        from models import HSCode
        valid_hs_codes = {h.hs_code for h in db.query(HSCode).all()}

        def best_rate(cost_currency: str):
            if cost_currency.upper() == BASE_CURRENCY:
                return None
            for r in rates_all:
                if r.base_currency == cost_currency.upper() and r.target_currency == BASE_CURRENCY:
                    return r
                if r.target_currency == cost_currency.upper() and r.base_currency == BASE_CURRENCY:
                    return r
            return None

        valid_rows   = []
        skipped_rows = []

        for row in rows:
            item_code = str(row.get("item_code") or "").strip().upper()
            issues    = []

            if not item_code:
                issues.append("item_code is blank")
            elif item_code in existing_items:
                issues.append(f"Already exists in database — skipped")

            sup_code  = str(row.get("supplier_code") or "").strip().upper()
            row["supplier_code"] = sup_code
            if sup_code not in sup_codes:
                issues.append(f"Supplier `{sup_code}` not found")

            curr_code = str(row.get("cost_currency") or "").strip().upper()
            row["cost_currency"] = curr_code
            if curr_code not in curr_codes:
                issues.append(f"Currency `{curr_code}` not found")

            rate_obj  = best_rate(curr_code)
            if curr_code and curr_code != BASE_CURRENCY and rate_obj is None:
                issues.append(f"No exchange rate for `{curr_code}` → SGD")

            if issues:
                skipped_rows.append({"item_code": item_code, "issues": issues})
            else:
                row["item_code"] = item_code
                row["_rate_obj"] = rate_obj
                valid_rows.append(row)

        if skipped_rows:
            st.warning(f"{len(skipped_rows)} row(s) will be skipped:")
            # Show first 20 skipped rows only
            for s in skipped_rows[:20]:
                reasons = " | ".join(s["issues"])
                st.write(f"• **{s['item_code']}**: {reasons}")
            if len(skipped_rows) > 20:
                st.write(f"... and {len(skipped_rows) - 20} more skipped rows")

        if not valid_rows:
            st.error("No valid rows to import after validation.")
            st.stop()

        # Build preview
        preview = []
        for row in valid_rows:
            r        = row["_rate_obj"]
            rate_val = r.rate      if r else 1.0
            rate_dir = r.direction if r else "multiply"
            result   = compute_all(
                float(row.get("cost_price")     or 0),
                float(row.get("discount_pct")   or 0),
                float(row.get("cost_additions") or 0),
                rate_val, rate_dir,
                float(row.get("margin_pct")     or 0),
                cost_currency=row.get("cost_currency", ""),
            )
            row["_computed"] = result
            preview.append({
                "Item code":  row["item_code"],
                "Name":       row.get("product_name", ""),
                "Category":   row.get("product_category", ""),
                "Supplier":   row.get("supplier_code", ""),
                "Currency":   row.get("cost_currency", ""),
                "Cost price": float(row.get("cost_price") or 0),
                "Net SGD":    round(result["net_cost_sgd"], 4),
                "Margin %":   row.get("margin_pct", ""),
                "FOB SGD":    round(result["fob_price_sgd"], 4),
            })

        st.success(f"**{len(valid_rows)} product(s) ready to import.**")
        if skipped_rows:
            st.info(f"{len(skipped_rows)} row(s) will be skipped (see warnings above).")

        st.dataframe(pd.DataFrame(preview), use_container_width=True, hide_index=True)
        st.divider()

        if st.button("✅  Confirm and import products", type="primary"):
            imported      = 0
            failed        = []
            BATCH_SIZE    = 50

            progress      = st.progress(0)
            status_text   = st.empty()

            for i, row in enumerate(valid_rows):
                try:
                    r      = row["_rate_obj"]
                    result = row["_computed"]
                    db.add(Product(
                        item_code        = row["item_code"],
                        product_category = row.get("product_category", ""),
                        hs_code          = row.get("hs_code") if row.get("hs_code") and row.get("hs_code") in valid_hs_codes else None,
                        product_name     = row.get("product_name", ""),
                        packing          = row.get("packing", ""),
                        uom              = row.get("uom", ""),
                        origin           = row.get("origin", ""),
                        supplier_code    = row.get("supplier_code", ""),
                        cost_currency    = row.get("cost_currency", ""),
                        cost_price       = float(row.get("cost_price")     or 0),
                        discount_pct     = float(row.get("discount_pct")   or 0),
                        cost_additions   = float(row.get("cost_additions") or 0),
                        net_cost_orig    = result["net_cost_orig"],
                        exchange_rate_id = r.id if r else None,
                        net_cost_sgd     = result["net_cost_sgd"],
                        ctn_cbm          = float(row["ctn_cbm"])    if row.get("ctn_cbm")    else None,
                        ctn_weight       = float(row["ctn_weight"])  if row.get("ctn_weight")  else None,
                        margin_pct       = float(row.get("margin_pct") or 0),
                        fob_price_sgd    = result["fob_price_sgd"],
                    ))

                    # Commit in batches of 50
                    if (i + 1) % BATCH_SIZE == 0:
                        try:
                            db.commit()
                        except Exception as e:
                            db.rollback()
                            failed.append(f"Batch ending at row {i+1}: {str(e)[:120]}")

                    # Update progress bar
                    progress.progress((i + 1) / len(valid_rows))
                    status_text.text(f"Importing... {i + 1} of {len(valid_rows)}")

                except Exception as e:
                    failed.append(f"{row['item_code']}: {str(e)[:120]}")

            # Commit any remaining rows
            try:
                db.commit()
            except Exception as e:
                db.rollback()
                failed.append(f"Final batch: {str(e)[:120]}")

            progress.empty()
            status_text.empty()

            if failed:
                st.warning(f"Import completed with some errors — {len(failed)} row(s) failed:")
                for f in failed[:10]:
                    st.write(f"• {f}")
            
            # Recount actual imported rows from DB
            new_count = db.query(Product).count()
            st.success(f"✅ Import complete! Total products in database: **{new_count}**")
            st.balloons()
            st.info("Go to the Products page to verify your imported products.")

# ── CUSTOMERS ─────────────────────────────────────────────────────────────────
with tab_cust:
    st.subheader("Bulk load customers")

    cust_template_df    = get_template_dataframe("customers")
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
        key="cust_upload",
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
            st.warning("No data rows found.")
            st.stop()

        existing_custs = {c.cust_code for c in db.query(Customer).all()}
        skipped        = []
        valid_rows     = []

        for row in rows:
            code = str(row.get("cust_code") or "").strip().upper()
            if code in existing_custs:
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
        st.dataframe(pd.DataFrame([{
            "Code":    r["cust_code"],
            "Name":    r.get("name", ""),
            "Country": r.get("country", ""),
            "Email":   r.get("email") or "",
            "Contact": r.get("contact_person") or "",
        } for r in valid_rows]), use_container_width=True, hide_index=True)

        if st.button("✅  Confirm and import customers", type="primary"):
            imported      = 0
            import_errors = []
            for row in valid_rows:
                try:
                    db.add(Customer(
                        cust_code      = row["cust_code"],
                        name           = row.get("name", ""),
                        address        = row.get("address"),
                        email          = row.get("email"),
                        contact_person = row.get("contact_person"),
                        phone          = row.get("phone"),
                        country        = row.get("country", ""),
                    ))
                    imported += 1
                except Exception as e:
                    import_errors.append(f"{row['cust_code']}: {str(e)[:80]}")

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
