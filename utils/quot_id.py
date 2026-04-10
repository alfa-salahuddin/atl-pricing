"""
Auto-generate quotation reference numbers.
Format: ATL-PL-2026-001  (price list)
        ATL-PI-2026-001  (proforma invoice)
"""
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import select, func


def next_quot_id(db: Session, quot_type: str) -> str:
    from models import Quotation

    prefix = "ATL-PL" if quot_type == "price_list" else "ATL-PI"
    year   = date.today().year

    # Find the highest sequence number for this type and year
    like_pattern = f"{prefix}-{year}-%"
    result = db.execute(
        select(func.max(Quotation.quot_id)).where(
            Quotation.quot_id.like(like_pattern)
        )
    ).scalar()

    if result:
        try:
            last_seq = int(result.split("-")[-1])
        except (ValueError, IndexError):
            last_seq = 0
    else:
        last_seq = 0

    new_seq = last_seq + 1
    return f"{prefix}-{year}-{new_seq:03d}"

