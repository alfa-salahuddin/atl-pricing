# ATL Pricing — Alfa Tradelinks Pte Ltd

Internal pricing and quotation system for FMCG export operations.

## What it does

- Manages master data: customers, suppliers, ports, shipping lines, currencies, exchange rates, HS codes, products
- Computes FOB prices automatically from supplier cost, exchange rate, and margin
- Generates price lists and proforma invoices, exported as formatted Excel files
- Supports bulk supplier price updates via Excel template upload
- All data stored in Supabase PostgreSQL — persistent and accessible from any device

---

## Tech stack

| Layer | Technology |
|---|---|
| UI | Streamlit |
| Database | Supabase PostgreSQL |
| ORM | SQLAlchemy |
| Validation | Pydantic |
| Excel I/O | pandas + openpyxl |
| Hosting | Streamlit Community Cloud |

---

## Local development setup

### 1. Clone the repo
```bash
git clone https://github.com/alfa-salahuddin/atl-pricing.git
cd atl-pricing
```

### 2. Create and activate a virtual environment
```bash
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set up Supabase credentials
Copy the secrets template and fill in your Supabase connection string:
```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```
Edit `.streamlit/secrets.toml` and replace `[YOUR-PASSWORD]` and `[YOUR-PROJECT-REF]` with your actual Supabase values.

### 5. Run the app
```bash
streamlit run app.py
```
The app will open at `http://localhost:8501`.
On first run, all database tables are created automatically.

---

## Streamlit Community Cloud deployment

1. Push this repo to GitHub (already done if you're reading this)
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Click **New app**
4. Select repo: `alfa-salahuddin/atl-pricing`
5. Branch: `main`
6. Main file path: `app.py`
7. App URL: `atl-pricing` (optional — becomes `atl-pricing.streamlit.app`)
8. Click **Advanced settings** → **Secrets** → paste:
   ```
   DATABASE_URL = "postgresql://postgres:[password]@db.[ref].supabase.co:5432/postgres"
   ```
9. Click **Deploy**

---

## Project structure

```
atl-pricing/
├── app.py                  ← Main entry point + home dashboard
├── database.py             ← Supabase connection + SQLAlchemy engine
├── models.py               ← All database table definitions
├── requirements.txt        ← Python dependencies
├── .gitignore
├── pages/
│   ├── 1_Customers.py
│   ├── 2_Suppliers.py
│   ├── 3_Reference_Data.py ← Ports, Shipping Lines, Currencies, Exchange Rates
│   ├── 4_HS_Codes.py
│   ├── 5_Products.py
│   ├── 6_Update_Prices.py  ← Excel template upload for supplier price updates
│   ├── 7_Price_List.py
│   ├── 8_Proforma_Invoice.py
│   └── 9_Backup.py
├── utils/
│   ├── pricing.py          ← FOB price computation logic
│   ├── export.py           ← Excel export (price list + PI)
│   ├── upload.py           ← Excel template validation + parsing
│   └── quot_id.py          ← Auto-generate quotation reference numbers
└── .streamlit/
    └── secrets.toml.example
```

---

## FOB price formula

```
net_cost_orig  = cost_price × (1 − discount_pct/100) + cost_additions
net_cost_sgd   = net_cost_orig × rate    [if direction = multiply]
               = net_cost_orig / rate    [if direction = divide]
fob_price_sgd  = net_cost_sgd / (1 − margin_pct/100)
```

---

## Excel upload templates

Three templates are downloadable from within the app:

| Template | Purpose |
|---|---|
| Supplier price update | Update cost prices for existing products |
| New products | Bulk-add new products to the master |
| Customers | Bulk-load customer records |

---

## Quotation reference format

- Price list: `ATL-PL-2026-001`
- Proforma invoice: `ATL-PI-2026-001`

Sequence resets each calendar year.

---

## Phase 2 (planned)

- PDF supplier price import (pdfplumber)
- Branded PDF output with ATL letterhead (WeasyPrint + Jinja2)
- Live exchange rate auto-fetch (exchangerate-api.com)
- Email delivery of price lists and PIs
- Quotation history view
