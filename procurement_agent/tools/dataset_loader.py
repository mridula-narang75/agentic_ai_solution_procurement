"""
procurement_agent/tools/dataset_loader.py
─────────────────────────────────────────
Reads from SQLite (procurement.db) built from the Kaggle dataset.

Real suppliers in this dataset:
    Alpha_Inc, Beta_Supplies, Delta_Logistics, Epsilon_Group, Gamma_Co

Real categories:
    Office Supplies, MRO, Packaging, Raw Materials, Electronics

Tables:
    procurement_kpi   — raw order-level data (777 rows)
    supplier_kpi      — pre-aggregated per-supplier KPIs (5 rows)
"""

import os
import sqlite3
import math
from contextlib import contextmanager

# ── Resolve path to data/procurement.db ───────────────────────────────────────
# tools/ is one level below procurement_agent/, data/ is also one level below.
# So we go: tools/ → procurement_agent/ → data/
_TOOLS_DIR       = os.path.dirname(__file__)          # .../procurement_agent/tools/
_AGENT_DIR       = os.path.dirname(_TOOLS_DIR)        # .../procurement_agent/
_DB_PATH         = os.path.join(_AGENT_DIR, "data", "procurement.db")


@contextmanager
def _conn():
    """Open SQLite connection, yield it, close cleanly."""
    if not os.path.exists(_DB_PATH):
        raise FileNotFoundError(
            f"Database not found at: {_DB_PATH}\n"
            "Make sure procurement.db is inside procurement_agent/data/"
        )
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()


def _safe(val):
    """Return None instead of NaN so the agent never crashes on missing data."""
    try:
        return None if math.isnan(float(val)) else val
    except (TypeError, ValueError):
        return val


# ══════════════════════════════════════════════════════════════════════════════
# Tool 1 — used by BuyerStrategyAgent
# ══════════════════════════════════════════════════════════════════════════════

def lookup_supplier_history(supplier_name: str, category: str | None = None) -> dict:
    """
    Looks up a supplier's real historical KPIs from the procurement database.

    Queries the supplier_kpi summary table built from 777 purchase orders.

    Real suppliers  : Alpha_Inc, Beta_Supplies, Delta_Logistics,
                      Epsilon_Group, Gamma_Co
    Real categories : Office Supplies, MRO, Packaging,
                      Raw Materials, Electronics

    Args:
        supplier_name : Full or partial name (case-insensitive).
                        e.g. "Alpha", "alpha_inc", "Delta"
        category      : Optional Item_Category filter for category-specific KPIs.

    Returns:
        {
          status                 : "found" | "not_found"
          supplier_name          : matched name from DB
          total_orders           : number of POs in dataset
          on_time_delivery_rate  : % of orders with Delivered status
          avg_defect_rate_pct    : avg defective units as % of quantity
          compliance_rate        : % of orders marked Compliant
          avg_lead_time_days     : avg days from Order_Date to Delivery_Date
          avg_unit_price         : average Unit_Price across all orders
          avg_discount_pct       : avg % discount off list price (Unit → Negotiated)
          performance_score      : composite 0-100 (OTD 50% + quality 30% + compliance 20%)
        }
    """
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM supplier_kpi WHERE LOWER(Supplier) LIKE ?",
            (f"%{supplier_name.lower()}%",)
        ).fetchone()

    if not row:
        return {
            "status":                "not_found",
            "message":               (
                f"'{supplier_name}' not found in dataset. "
                "Real suppliers: Alpha_Inc, Beta_Supplies, Delta_Logistics, "
                "Epsilon_Group, Gamma_Co. Using safe defaults."
            ),
            "supplier_name":          supplier_name,
            "total_orders":           0,
            "on_time_delivery_rate":  70.0,
            "avg_defect_rate_pct":    7.0,
            "compliance_rate":        80.0,
            "avg_lead_time_days":     11.0,
            "avg_unit_price":         None,
            "avg_discount_pct":       8.0,
            "performance_score":      72.0,
        }

    # Optional: re-query raw table filtered by category
    if category:
        with _conn() as con:
            raw = con.execute("""
                SELECT
                    COUNT(*)                              AS total_orders,
                    AVG(Unit_Price)                       AS avg_unit_price,
                    AVG(Discount_Pct)                     AS avg_discount_pct,
                    AVG(Lead_Time_Days)                   AS avg_lead_time_days,
                    AVG(Defect_Rate_Pct)                  AS avg_defect_rate_pct,
                    SUM(Is_Delivered) * 100.0 / COUNT(*)  AS on_time_delivery_rate,
                    SUM(Is_Compliant) * 100.0 / COUNT(*)  AS compliance_rate
                FROM procurement_kpi
                WHERE LOWER(Supplier)      LIKE ?
                  AND LOWER(Item_Category) LIKE ?
            """, (f"%{supplier_name.lower()}%", f"%{category.lower()}%")).fetchone()

        if raw and raw["total_orders"]:
            otd    = _safe(raw["on_time_delivery_rate"]) or 70.0
            defect = _safe(raw["avg_defect_rate_pct"])   or 7.0
            comp   = _safe(raw["compliance_rate"])        or 80.0
            perf   = round(otd * 0.50 + max(0, 100 - defect) * 0.30 + comp * 0.20, 1)
            return {
                "status":                "found",
                "supplier_name":          dict(row)["Supplier"],
                "category_filter":        category,
                "total_orders":           raw["total_orders"],
                "on_time_delivery_rate":  round(otd, 1),
                "avg_defect_rate_pct":    round(defect, 2),
                "compliance_rate":        round(comp, 1),
                "avg_lead_time_days":     round(_safe(raw["avg_lead_time_days"]) or 11.0, 1),
                "avg_unit_price":         round(_safe(raw["avg_unit_price"]) or 0, 2),
                "avg_discount_pct":       round(_safe(raw["avg_discount_pct"]) or 8.0, 2),
                "performance_score":      perf,
            }

    return {
        "status":                "found",
        "supplier_name":          dict(row)["Supplier"],
        "total_orders":           row["total_orders"],
        "on_time_delivery_rate":  round(_safe(row["on_time_delivery_rate"]) or 70.0, 1),
        "avg_defect_rate_pct":    round(_safe(row["avg_defect_rate_pct"])   or 7.0,  2),
        "compliance_rate":        round(_safe(row["compliance_rate"])        or 80.0, 1),
        "avg_lead_time_days":     round(_safe(row["avg_lead_time_days"])     or 11.0, 1),
        "avg_unit_price":         round(_safe(row["avg_unit_price"])         or 0.0,  2),
        "avg_discount_pct":       round(_safe(row["avg_discount_pct"])       or 8.0,  2),
        "performance_score":      round(_safe(row["performance_score"])      or 72.0, 1),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Tool 2 — used by SupplierAgent
# ══════════════════════════════════════════════════════════════════════════════

def get_supplier_quote_context(supplier_name: str, category: str | None = None) -> dict:
    """
    Retrieves a supplier's historical pricing range and delivery context
    so the SupplierAgent can generate realistic, data-grounded quotes.

    Derived from actual Unit_Price, Negotiated_Price, and Lead_Time_Days
    columns in the dataset.

    Args:
        supplier_name : Full or partial name (case-insensitive).
        category      : Optional Item_Category to get category-specific pricing.

    Returns:
        {
          avg_unit_price       : average list price historically
          min_unit_price       : lowest observed price (quote floor)
          max_unit_price       : highest observed price (quote ceiling)
          avg_negotiated_price : what was actually paid after negotiation
          avg_lead_time_days   : typical delivery window
          avg_quantity         : typical order size
          avg_discount_pct     : average % negotiated off list price
          suggested_markup_pct : recommended input for generate_supplier_quote()
        }
    """
    where_parts = ["LOWER(Supplier) LIKE ?"]
    params      = [f"%{supplier_name.lower()}%"]

    if category:
        where_parts.append("LOWER(Item_Category) LIKE ?")
        params.append(f"%{category.lower()}%")

    where = " AND ".join(where_parts)

    with _conn() as con:
        row = con.execute(f"""
            SELECT
                COUNT(*)                AS total_orders,
                AVG(Unit_Price)         AS avg_unit_price,
                MIN(Unit_Price)         AS min_unit_price,
                MAX(Unit_Price)         AS max_unit_price,
                AVG(Negotiated_Price)   AS avg_negotiated_price,
                AVG(Lead_Time_Days)     AS avg_lead_time_days,
                MIN(Lead_Time_Days)     AS min_lead_time_days,
                AVG(Quantity)           AS avg_quantity,
                AVG(Discount_Pct)       AS avg_discount_pct
            FROM procurement_kpi
            WHERE {where}
        """, params).fetchone()

    if not row or not row["total_orders"]:
        return {
            "status":               "not_found",
            "message":              f"No pricing data for '{supplier_name}'. Using defaults.",
            "avg_unit_price":        None,
            "min_unit_price":        None,
            "max_unit_price":        None,
            "avg_negotiated_price":  None,
            "avg_lead_time_days":    11.0,
            "avg_quantity":          1000,
            "avg_discount_pct":      8.0,
            "suggested_markup_pct":  22.0,
        }

    avg_disc         = _safe(row["avg_discount_pct"]) or 8.0
    suggested_markup = round(max(10.0, 30.0 - avg_disc), 1)

    return {
        "status":               "found",
        "total_orders":          row["total_orders"],
        "avg_unit_price":        round(_safe(row["avg_unit_price"])       or 0, 2),
        "min_unit_price":        round(_safe(row["min_unit_price"])       or 0, 2),
        "max_unit_price":        round(_safe(row["max_unit_price"])       or 0, 2),
        "avg_negotiated_price":  round(_safe(row["avg_negotiated_price"]) or 0, 2),
        "avg_lead_time_days":    round(_safe(row["avg_lead_time_days"])   or 11.0, 1),
        "min_lead_time_days":    _safe(row["min_lead_time_days"]),
        "avg_quantity":          round(_safe(row["avg_quantity"])         or 1000),
        "avg_discount_pct":      round(avg_disc, 2),
        "suggested_markup_pct":  suggested_markup,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Tool 3 — used by NegotiationAgent
# ══════════════════════════════════════════════════════════════════════════════

def get_supplier_concession_limit(supplier_name: str, category: str | None = None) -> dict:
    """
    Derives the maximum price concession a supplier is likely to grant,
    based on their real historical discount behaviour in the dataset.

    Discount_Pct = (Unit_Price - Negotiated_Price) / Unit_Price × 100
    This is the actual discount recorded in every purchase order.

    Leverage logic:
      HIGH   — compliance_rate < 75% OR avg_defect_rate > 10%
      LOW    — compliance_rate > 95% AND avg_defect_rate < 3%
      MEDIUM — everything else

    Args:
        supplier_name : Full or partial name (case-insensitive).
        category      : Optional category filter.

    Returns:
        {
          max_concession_pct        : cap for concession_pct in negotiate_price()
          avg_discount_pct          : historical average discount given
          negotiation_leverage      : "high" / "medium" / "low"
          avg_lead_time_days        : use for delivery commitment in contract
          compliance_rate           : supplier compliance track record
          recommended_payment_terms : e.g. "Net 30" derived from lead time
        }
    """
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM supplier_kpi WHERE LOWER(Supplier) LIKE ?",
            (f"%{supplier_name.lower()}%",)
        ).fetchone()

    if not row:
        return {
            "status":                    "not_found",
            "message":                   f"'{supplier_name}' not found. Using conservative defaults.",
            "max_concession_pct":         8.0,
            "avg_discount_pct":           5.0,
            "negotiation_leverage":       "medium",
            "avg_lead_time_days":         11.0,
            "compliance_rate":            80.0,
            "recommended_payment_terms":  "Net 30",
        }

    disc   = _safe(row["avg_discount_pct"])   or 8.0
    comp   = _safe(row["compliance_rate"])     or 80.0
    defect = _safe(row["avg_defect_rate_pct"]) or 7.0
    lead   = _safe(row["avg_lead_time_days"])  or 11.0
    max_c  = _safe(row["max_concession_pct"])  or round(disc * 1.3, 2)

    if comp < 75 or defect > 10:
        leverage = "high"
    elif comp > 95 and defect < 3:
        leverage = "low"
    else:
        leverage = "medium"

    if lead < 8:
        payment_terms = "Net 15"
    elif lead < 14:
        payment_terms = "Net 30"
    else:
        payment_terms = "Net 45"

    return {
        "status":                    "found",
        "supplier_name":              dict(row)["Supplier"],
        "total_orders":               row["total_orders"],
        "avg_discount_pct":           round(disc,   2),
        "max_concession_pct":         round(max_c,  2),
        "negotiation_leverage":       leverage,
        "avg_lead_time_days":         round(lead,   1),
        "compliance_rate":            round(comp,   1),
        "avg_defect_rate_pct":        round(defect, 2),
        "on_time_delivery_rate":      round(_safe(row["on_time_delivery_rate"]) or 70.0, 1),
        "recommended_payment_terms":  payment_terms,
    }