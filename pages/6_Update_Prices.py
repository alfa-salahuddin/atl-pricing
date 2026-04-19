import streamlit as st
import pandas as pd
from datetime import datetime
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Product, ExchangeRate, PriceChangeLog
from utils.upload import validate_and_parse, get_template_dataframe, dataframe_to_excel_bytes
from utils.pricing import compute_all

st.set_page_config(page_title="Update Prices — ATL Pricing", layout="wide")
st.title("Update supplier prices")

db: Session = SessionLocal()
try:

# ── Download template ────────────────────────────────────────────────────────
st.subheader("Step 1 — Download the price update template")
st.write("Fill in the template with the new prices from your supplier, then upload below.")

template_df    = get_template_dataframe("supplier_price_update")
template_bytes = dataframe_to_excel_bytes(template_df, sheet_name="Supplier Price Update")
st.download_button(
    label="Download template (.xlsx)",
    data=template_bytes,
    file_name="ATL_Supplier_Price_Update_Template.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

st.divider()

# ── Upload & validate ────────────────────────────────────────────────────────
st.subheader("Step 2 — Upload your filled template")
uploaded = st.file_uploader("Upload price update file (.xlsx)", type=["xlsx"])

if uploaded:
    rows, errors = validate_and_parse(uploaded.read(), "supplier_price_update")

    if errors:
        st.error("The file has errors — please fix and re-upload:")
        for e in errors:
            st.write(f"• {e}")
    else:
        st.success(f"{len(rows)} row(s) validated. Review changes below before confirming.")

        # Build preview
        preview_rows = []
        unmatched    = []

        for row in rows:
            prod = db.get(Product, row["item_code"])
            if not prod:
                unmatched.append(row["item_code"])
                continue

            # Get current exchange rate for this product
            rate_obj = db.get(ExchangeRate, prod.exchange_rate_id) if prod.exchange_rate_id else None
            if not rate_obj:
                unmatched.append(f"{row['item_code']} (no exchange rate linked)")
                continue

            new_cost     = float(row["cost_price"])
            new_disc     = float(row.get("discount_pct") or 0)
            new_add      = float(row.get("cost_additions") or 0)
            new_computed = compute_all(new_cost, new_disc, new_add, rate_obj.rate, rate_obj.direction, prod.margin_pct)

            preview_rows.append({
                "item_code":       row["item_code"],
                "product_name":    prod.product_name,
                "old_cost":        prod.cost_price,
                "new_cost":        new_cost,
                "old_fob_sgd":     round(prod.fob_price_sgd, 4),
                "new_fob_sgd":     round(new_computed["fob_price_sgd"], 4),
                "cost_currency":   row["cost_currency"],
                "discount_pct":    new_disc,
                "cost_additions":  new_add,
                "net_cost_orig":   new_computed["net_cost_orig"],
                "net_cost_sgd":    new_computed["net_cost_sgd"],
                "notes":           row.get("notes") or "",
            })

        if unmatched:
            st.warning(f"The following item codes were not found in the product master and will be skipped: {', '.join(unmatched)}")

        if preview_rows:
            df_preview = pd.DataFrame([{
                "Item code":     r["item_code"],
                "Product":       r["product_name"],
                "Old cost":      r["old_cost"],
                "New cost":      r["new_cost"],
                "Currency":      r["cost_currency"],
                "Old FOB SGD":   r["old_fob_sgd"],
                "New FOB SGD":   r["new_fob_sgd"],
                "Change":        round(r["new_fob_sgd"] - r["old_fob_sgd"], 4),
            } for r in preview_rows])

            st.dataframe(df_preview, use_container_width=True, hide_index=True)
            st.caption(f"{len(preview_rows)} product(s) will be updated")

            st.divider()
            st.subheader("Step 3 — Confirm and save")
            if st.button("Confirm and save all changes", type="primary"):
                for r in preview_rows:
                    prod = db.get(Product, r["item_code"])

                    # Log the change
                    db.add(PriceChangeLog(
                        item_code=r["item_code"],
                        changed_date=datetime.now(),
                        old_cost_price=prod.cost_price,
                        new_cost_price=r["new_cost"],
                        old_fob_sgd=r["old_fob_sgd"],
                        new_fob_sgd=r["new_fob_sgd"],
                        source="excel_upload",
                        notes=r["notes"],
                    ))

                    # Update the product
                    prod.cost_price     = r["new_cost"]
                    prod.discount_pct   = r["discount_pct"]
                    prod.cost_additions = r["cost_additions"]
                    prod.net_cost_orig  = r["net_cost_orig"]
                    prod.net_cost_sgd   = r["net_cost_sgd"]
                    prod.fob_price_sgd  = r["new_fob_sgd"]
                    prod.cost_currency  = r["cost_currency"]

                db.commit()
                st.success(f"✅  {len(preview_rows)} product(s) updated successfully.")
                st.balloons()

pass
finally:
    db.close()
