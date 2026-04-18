"""
import_to_sqlite.py
───────────────────
Imports the Kaggle Procurement KPI Analysis Dataset CSV into SQLite.

Run this ONCE from the folder containing your CSV:
    python import_to_sqlite.py

Creates:  procurement.db
Table:    procurement_kpi  (raw data, as-is from CSV)
Table:    supplier_kpi     (derived per-supplier KPIs used by agents)

Dataset columns (777 rows, 11 columns):
    PO_ID, Supplier, Order_Date, Delivery_Date, Item_Category,
    Order_Status, Quantity, Unit_Price, Negotiated_Price,
    Defective_Units, Compliance
"""

import sqlite3
import pandas as pd
import os
import sys

CSV_PATH = "Procurement KPI Analysis Dataset.csv"
DB_PATH  = "procurement.db"

# ── Step 1: Load CSV ──────────────────────────────────────────────────────────

print(f"\n[1/5] Reading CSV: {CSV_PATH}")
if not os.path.exists(CSV_PATH):
    print(f"\n❌  File not found: {CSV_PATH}")
    print("    Run this script from the same folder as the CSV.")
    sys.exit(1)

df = pd.read_csv(CSV_PATH)
print(f"      ✓ {len(df):,} rows × {len(df.columns)} columns")
print(f"      Columns: {list(df.columns)}")

# ── Step 2: Compute derived columns ───────────────────────────────────────────

print("[2/5] Computing derived KPI columns...")

df["Order_Date"]    = pd.to_datetime(df["Order_Date"],    errors="coerce")
df["Delivery_Date"] = pd.to_datetime(df["Delivery_Date"], errors="coerce")

# Lead time in days (Order → Delivery)
df["Lead_Time_Days"] = (df["Delivery_Date"] - df["Order_Date"]).dt.days

# Discount % = how much was negotiated off the unit price
df["Discount_Pct"] = (
    (df["Unit_Price"] - df["Negotiated_Price"]) / df["Unit_Price"] * 100
).round(2)

# Defect rate % = defective units as % of order quantity
df["Defect_Rate_Pct"] = (
    df["Defective_Units"] / df["Quantity"] * 100
).round(2)

# On-time flag: Delivered orders with a valid lead time
df["Is_Delivered"] = (df["Order_Status"] == "Delivered").astype(int)
df["Is_Compliant"] = (df["Compliance"] == "Yes").astype(int)

print("      ✓ Added: Lead_Time_Days, Discount_Pct, Defect_Rate_Pct, Is_Delivered, Is_Compliant")

# ── Step 3: Write raw table ───────────────────────────────────────────────────

print(f"[3/5] Writing raw data to SQLite: {DB_PATH}")
conn = sqlite3.connect(DB_PATH)

df.to_sql("procurement_kpi", conn, if_exists="replace", index=False)
print(f"      ✓ Table 'procurement_kpi': {len(df):,} rows")

# ── Step 4: Build supplier_kpi summary table ──────────────────────────────────

print("[4/5] Building supplier_kpi summary table...")

supplier_kpi = df.groupby("Supplier").agg(
    total_orders        = ("PO_ID",            "count"),
    avg_unit_price      = ("Unit_Price",        "mean"),
    min_unit_price      = ("Unit_Price",        "min"),
    max_unit_price      = ("Unit_Price",        "max"),
    avg_negotiated_price= ("Negotiated_Price",  "mean"),
    avg_discount_pct    = ("Discount_Pct",      "mean"),
    avg_lead_time_days  = ("Lead_Time_Days",    "mean"),
    min_lead_time_days  = ("Lead_Time_Days",    "min"),
    avg_defect_rate_pct = ("Defect_Rate_Pct",   "mean"),
    total_quantity      = ("Quantity",          "sum"),
    avg_quantity        = ("Quantity",          "mean"),
    delivered_count     = ("Is_Delivered",      "sum"),
    compliant_count     = ("Is_Compliant",      "sum"),
).reset_index()

# Rates
supplier_kpi["on_time_delivery_rate"] = (
    supplier_kpi["delivered_count"] / supplier_kpi["total_orders"] * 100
).round(1)

supplier_kpi["compliance_rate"] = (
    supplier_kpi["compliant_count"] / supplier_kpi["total_orders"] * 100
).round(1)

# Round numeric columns
for col in ["avg_unit_price","min_unit_price","max_unit_price",
            "avg_negotiated_price","avg_discount_pct",
            "avg_lead_time_days","avg_defect_rate_pct","avg_quantity"]:
    supplier_kpi[col] = supplier_kpi[col].round(2)

# Performance score: OTD 50% + (100-defect) 30% + compliance 20%
supplier_kpi["performance_score"] = (
    supplier_kpi["on_time_delivery_rate"] * 0.50
    + (100 - supplier_kpi["avg_defect_rate_pct"].fillna(3)).clip(0, 100) * 0.30
    + supplier_kpi["compliance_rate"] * 0.20
).round(1)

# Max concession = 1.3× avg discount (what agents use in negotiation)
supplier_kpi["max_concession_pct"] = (supplier_kpi["avg_discount_pct"] * 1.3).round(2)

supplier_kpi.to_sql("supplier_kpi", conn, if_exists="replace", index=False)
print(f"      ✓ Table 'supplier_kpi': {len(supplier_kpi)} suppliers")
print()
print("      Supplier summary:")
print(supplier_kpi[[
    "Supplier","total_orders","avg_unit_price","avg_discount_pct",
    "avg_lead_time_days","avg_defect_rate_pct","on_time_delivery_rate",
    "compliance_rate","performance_score"
]].to_string(index=False))

# ── Step 5: Verify ────────────────────────────────────────────────────────────

print("\n[5/5] Verifying...")
cur = conn.cursor()

for tbl in ["procurement_kpi", "supplier_kpi"]:
    cur.execute(f"SELECT COUNT(*) FROM {tbl}")
    n = cur.fetchone()[0]
    cur.execute(f"PRAGMA table_info({tbl})")
    cols = [r[1] for r in cur.fetchall()]
    print(f"      ✓ {tbl}: {n} rows, {len(cols)} columns")

conn.close()

print("\n" + "─" * 60)
print(f"✅  Done!  →  {os.path.abspath(DB_PATH)}")
print()
print("Next step:")
print("  Move procurement.db into:  procurement_agent/data/procurement.db")
print("  Replace dataset_loader.py with dataset_loader_sqlite.py")
