"""
import_suppliers_to_sqlite.py
──────────────────────────────
Imports procurement_inventory_prices.csv (actually an Excel file)
into a NEW database: suppliers.db

Run this ONCE from inside procurement_agent/:
    python import_suppliers_to_sqlite.py

Creates:
    data/suppliers.db
    Table: supplier_catalog  (25 rows — 5 suppliers × 5 categories)

Columns in the file:
    Supplier, Category, Per Unit Price (USD), Available Discount (%),
    Delivery Time (days), Stock Availability (units),
    Production Capacity (units/month), Delivery Feasibility
"""

import sqlite3
import pandas as pd
import os
import sys

EXCEL_PATH = "procurement_inventory_prices.csv"   # it's actually an xlsx
DB_PATH    = os.path.join("data", "suppliers.db")
TABLE      = "supplier_catalog"

# ── Step 1: Read the file ─────────────────────────────────────────────
print(f"\n[1/4] Reading: {EXCEL_PATH}")
if not os.path.exists(EXCEL_PATH):
    print(f"\n❌  Not found: {EXCEL_PATH}")
    print("    Run this script from inside procurement_agent/")
    sys.exit(1)

df = pd.read_excel(EXCEL_PATH, engine="openpyxl")
print(f"      ✓ {len(df)} rows × {len(df.columns)} columns")
print(f"      Columns: {list(df.columns)}")

# ── Step 2: Clean column names for SQL ───────────────────────────────
print("[2/4] Cleaning column names...")

df.columns = (
    df.columns
      .str.strip()
      .str.lower()
      .str.replace(r"[^a-z0-9]+", "_", regex=True)
      .str.strip("_")
)

clean_cols = list(df.columns)
print(f"      ✓ Clean columns: {clean_cols}")

# ── Step 3: Write to suppliers.db ─────────────────────────────────────
os.makedirs("data", exist_ok=True)
print(f"[3/4] Writing to {DB_PATH} ...")

conn = sqlite3.connect(DB_PATH)
df.to_sql(TABLE, conn, if_exists="replace", index=False)
print(f"      ✓ Table '{TABLE}': {len(df)} rows")

# ── Step 4: Verify ────────────────────────────────────────────────────
print("[4/4] Verifying...")
cur = conn.cursor()

cur.execute(f"SELECT COUNT(*) FROM {TABLE}")
count = cur.fetchone()[0]

cur.execute(f"PRAGMA table_info({TABLE})")
cols = [(r[1], r[2]) for r in cur.fetchall()]

print(f"      ✓ Row count : {count}")
print(f"      ✓ Columns   :")
for name, dtype in cols:
    print(f"             {name:45s} {dtype}")

print("\n      Sample data (first 5 rows):")
cur.execute(f"SELECT * FROM {TABLE} LIMIT 5")
rows = cur.fetchall()
col_names = [c[0] for c in cols]
for row in rows:
    print("      " + " | ".join(f"{n}: {v}" for n, v in zip(col_names, row)))

conn.close()

print(f"\n✅  Done! → {os.path.abspath(DB_PATH)}")
print("\n      suppliers.db is separate from procurement.db")
print("      procurement.db  — historical KPI data (777 orders)")
print("      suppliers.db    — supplier catalog (pricing, stock, capacity)")