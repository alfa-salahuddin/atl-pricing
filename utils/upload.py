"""
Excel template upload helpers.
Validates headers, parses rows, and returns clean data or error lists.
"""
import pandas as pd
from io import BytesIO


TEMPLATE_HEADERS = {
    "supplier_price_update": [
        "item_code", "supplier_code", "cost_currency",
        "cost_price", "discount_pct", "cost_additions",
        "effective_date", "notes",
    ],
    "new_products": [
        "item_code", "product_category", "hs_code", "product_name",
        "packing", "uom", "origin", "supplier_code",
        "cost_currency", "cost_price", "discount_pct",
        "cost_additions", "ctn_cbm", "ctn_weight", "margin_pct",
    ],
    "customers": [
        "cust_code", "name", "address", "email",
        "contact_person", "phone", "country",
    ],
}

REQUIRED_FIELDS = {
    "supplier_price_update": ["item_code", "supplier_code", "cost_currency", "cost_price", "effective_date"],
    "new_products":          ["item_code", "product_category", "product_name", "packing", "uom",
                               "origin", "supplier_code", "cost_currency", "cost_price", "margin_pct"],
    "customers":             ["cust_code", "name", "country"],
}


def validate_and_parse(file_bytes: bytes, template_type: str) -> tuple[list[dict], list[str]]:
    """
    Reads an uploaded Excel file and validates it against the expected template.
    Returns:
        (rows, errors)
        rows:   list of dicts (one per data row), empty if errors exist
        errors: list of human-readable error strings
    """
    errors = []
    rows   = []

    try:
        df = pd.read_excel(BytesIO(file_bytes), dtype=str)
    except Exception as e:
        return [], [f"Could not read file: {e}"]

    # Normalise column names
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    expected = TEMPLATE_HEADERS.get(template_type, [])
    missing_cols = [h for h in expected if h not in df.columns]
    if missing_cols:
        return [], [f"Missing columns: {', '.join(missing_cols)}. Please download the latest template."]

    required = REQUIRED_FIELDS.get(template_type, [])

    for idx, row in df.iterrows():
        row_num = idx + 2  # Excel row number (1-indexed header + 1)
        row_errors = []

        # Check required fields
        for field in required:
            val = row.get(field, "")
            if pd.isna(val) or str(val).strip() == "" or str(val).lower() == "nan":
                row_errors.append(f"Row {row_num}: '{field}' is required")

        if row_errors:
            errors.extend(row_errors)
            continue

        # Clean and type-cast
        clean = {}
        for col in expected:
            val = row.get(col, "")
            if pd.isna(val) or str(val).lower() == "nan":
                clean[col] = None
            else:
                clean[col] = str(val).strip()

        # Cast numeric fields
        numeric_fields = ["cost_price", "discount_pct", "cost_additions", "ctn_cbm", "ctn_weight", "margin_pct"]
        for f in numeric_fields:
            if f in clean and clean[f] is not None:
                try:
                    clean[f] = float(clean[f])
                except ValueError:
                    errors.append(f"Row {row_num}: '{f}' must be a number, got '{clean[f]}'")
                    clean[f] = None

        rows.append(clean)

    return rows, errors


def get_template_dataframe(template_type: str) -> pd.DataFrame:
    """Returns an empty DataFrame with the correct headers for download."""
    headers = TEMPLATE_HEADERS.get(template_type, [])
    return pd.DataFrame(columns=headers)


def dataframe_to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Template") -> bytes:
    """Converts a DataFrame to Excel bytes for download."""
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        # Auto-size columns
        ws = writer.sheets[sheet_name]
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            ws.column_dimensions[col[0].column_letter].width = max(max_len + 4, 14)
    return buf.getvalue()

