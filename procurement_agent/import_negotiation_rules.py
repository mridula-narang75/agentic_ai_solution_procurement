"""
import_negotiation_data.py
──────────────────────────
Imports negotiation_rules.csv into a new SQLite database: negotiation.db

Run this ONCE from inside procurement_agent/:
    python import_negotiation_data.py

Creates:
    data/negotiation.db
    Table: negotiation_rules  (5 rows — one per category)

Columns:
    category, min_order_qty, max_order_qty,
    target_discount_pct, max_discount_pct, min_acceptable_discount_pct,
    price_tolerance_pct, max_negotiation_rounds, counter_offer_step_pct,
    delivery_tolerance_days, priority_weight_price,
    priority_weight_delivery, priority_weight_quantity,
    auto_award_threshold_score, walkaway_price_premium_pct
"""

import sqlite3
import pandas as pd
import os
import sys

CSV_PATH = os.path.join("data", "negotiation_rules.csv")
DB_PATH  = os.path.join("data", "negotiation.db")
TABLE    = "negotiation_rules"

# ── Step 1: Read CSV ──────────────────────────────────────────────────
print(f"\n[1/4] Reading: {CSV_PATH}")
if not os.path.exists(CSV_PATH):
    print(f"\n❌  Not found: {CSV_PATH}")
    print("    Make sure negotiation_rules.csv is inside procurement_agent/data/")
    sys.exit(1)

df = pd.read_csv(CSV_PATH)
print(f"      ✓ {len(df)} rows × {len(df.columns)} columns")
print(f"      Categories: {list(df['category'])}")

# ── Step 2: Write to negotiation.db ──────────────────────────────────
print(f"[2/4] Writing to {DB_PATH} ...")
conn = sqlite3.connect(DB_PATH)
df.to_sql(TABLE, conn, if_exists="replace", index=False)
print(f"      ✓ Table '{TABLE}': {len(df)} rows")

# ── Step 3: Verify ────────────────────────────────────────────────────
print("[3/4] Verifying...")
cur = conn.cursor()
cur.execute(f"SELECT COUNT(*) FROM {TABLE}")
count = cur.fetchone()[0]
cur.execute(f"PRAGMA table_info({TABLE})")
cols = [(r[1], r[2]) for r in cur.fetchall()]
print(f"      ✓ Row count: {count}")
print(f"      ✓ Columns ({len(cols)}):")
for name, dtype in cols:
    print(f"             {name:40s} {dtype}")

# ── Step 4: Sample output ─────────────────────────────────────────────
print("\n[4/4] Sample data:")
cur.execute(f"SELECT * FROM {TABLE}")
rows = cur.fetchall()
col_names = [c[0] for c in cols]
for row in rows:
    print(f"\n      {row[0]}:")
    for name, val in zip(col_names[1:], row[1:]):
        print(f"        {name:40s} {val}")

conn.close()

print(f"\n✅  Done! → {os.path.abspath(DB_PATH)}")
print("\n      Three databases now in data/:")
print("        procurement.db    — historical KPI data (777 orders)")
print("        suppliers.db      — supplier catalog (pricing, stock, capacity)")
print("        negotiation.db    — negotiation rules per category")