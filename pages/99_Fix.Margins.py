"""
One-time fix page — corrects margin_pct values that were imported as decimals
(e.g. 0.2 instead of 20) and recomputes FOB prices for all affected products.
Delete this page from GitHub after running it once.
"""
import streamlit as st
import pandas as pd
from database import SessionLocal
from models import Product, ExchangeRate
from utils.pricing import compute_all, BASE_CURRENCY

st.set_page_config(page_title="Fix Margins — ATL Pricing", layout="wide")
st.title("One-time margin fix")
st.warning("Run this once to fix margin values imported as decimals. Delete this page after use.")

db = SessionLocal()

# Find all products where margin_pct looks like a decimal (< 1)
affected = db.query(Product).filter(Product.margin_pct < 1).all()

if not affected:
    st.success("No products with decimal margins found — all margins look correct.")
    db.close()
    st.stop()

st.error(f"Found **{len(affected)}** product(s) with margin stored as decimal (e.g. 0.2 instead of 20).")

# Preview
preview = []
for p in affected[:20]:
    corrected_margin = round(p.margin_pct * 100, 4)
    preview.append({
        "Item code":      p.item_code,
        "Name":           p.product_name,
        "Wrong margin %": p.margin_pct,
        "Correct margin %": corrected_margin,
        "Current FOB SGD":  round(p.fob_price_sgd, 4),
    })

st.write(f"Preview of first {min(20, len(affected))} affected products:")
st.dataframe(pd.DataFrame(preview), use_container_width=True, hide_index=True)
if len(affected) > 20:
    st.write(f"... and {len(affected) - 20} more")

st.divider()

if st.button("✅  Fix all affected products now", type="primary"):
    fixed  = 0
    errors = []
    progress = st.progress(0)

    for i, p in enumerate(affected):
        try:
            # Correct the margin
            correct_margin = round(p.margin_pct * 100, 4)

            # Get exchange rate
            rate_obj = db.get(ExchangeRate, p.exchange_rate_id) if p.exchange_rate_id else None
            rate_val = rate_obj.rate      if rate_obj else 1.0
            rate_dir = rate_obj.direction if rate_obj else "multiply"

            # Recompute all prices
            result = compute_all(
                p.cost_price,
                p.discount_pct,
                p.cost_additions,
                rate_val,
                rate_dir,
                correct_margin,
                cost_currency=p.cost_currency,
            )

            p.margin_pct    = correct_margin
            p.net_cost_orig = result["net_cost_orig"]
            p.net_cost_sgd  = result["net_cost_sgd"]
            p.fob_price_sgd = result["fob_price_sgd"]
            fixed += 1

            if (i + 1) % 100 == 0:
                db.commit()

            progress.progress((i + 1) / len(affected))

        except Exception as e:
            errors.append(f"{p.item_code}: {str(e)[:80]}")

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append(f"Final commit: {str(e)[:80]}")

    progress.empty()

    if errors:
        st.warning(f"Completed with {len(errors)} error(s):")
        for e in errors:
            st.write(f"• {e}")

    st.success(f"✅ Fixed **{fixed}** products. Margins and FOB prices are now correct.")
    st.info("You can now delete this page (99_Fix_Margins.py) from GitHub — it is no longer needed.")

db.close()

