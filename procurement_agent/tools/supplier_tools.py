"""
procurement_agent/tools/supplier_db.py
───────────────────────────────────────
SQLite access layer for suppliers.db (supplier catalog).

Table: supplier_catalog
Columns:
    supplier                         — Alpha_Inc / Beta_Supplies / etc.
    category                         — Electronics / MRO / Office Supplies /
                                       Raw Materials / Packaging
    per_unit_price_usd               — list price per unit
    available_discount               — max discount % supplier can offer
    delivery_time_days               — standard lead time in days
    stock_availability_units         — units currently in stock
    production_capacity_units_month  — monthly production capacity
    delivery_feasibility             — High / Medium / Low

Two tools exposed to the supplier agent:
    check_capacity_and_delivery()  — reasons over qty + timeline
    generate_quote()               — produces final structured quotation
"""

import os
import uuid
import sqlite3
import math
from contextlib import contextmanager
from datetime import datetime
from tabulate import tabulate

_TOOLS_DIR = os.path.dirname(__file__)
_AGENT_DIR = os.path.dirname(_TOOLS_DIR)
_DB_PATH   = os.path.join(_AGENT_DIR, "data", "suppliers.db")
TABLE      = "supplier_catalog"

# Extra days added based on delivery feasibility rating
FEASIBILITY_BUFFER = {"High": 0, "Medium": 2, "Low": 5}


@contextmanager
def _conn():
    if not os.path.exists(_DB_PATH):
        raise FileNotFoundError(
            f"Supplier database not found at: {_DB_PATH}\n"
            "Run import_suppliers_to_sqlite.py first."
        )
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()


def _safe(val):
    try:
        return None if math.isnan(float(val)) else val
    except (TypeError, ValueError):
        return val


def _fetch_row(supplier_name: str, category: str):
    """Fetch one row from supplier_catalog. Returns None if not found."""
    with _conn() as con:
        return con.execute(
            f"""SELECT * FROM {TABLE}
                WHERE LOWER(supplier) = LOWER(?)
                  AND LOWER(category) = LOWER(?)""",
            (supplier_name, category)
        ).fetchone()


# ══════════════════════════════════════════════════════════════════════
# Tool 1 — check_capacity_and_delivery
# ══════════════════════════════════════════════════════════════════════

def check_capacity_and_delivery(
    supplier_name: str,
    category: str,
    quantity: int,
    required_delivery_days: int,
) -> dict:
    """
    Reasons over whether a supplier can meet the RFQ on quantity
    and delivery timeline. Determines if a counter-proposal is needed.

    Reasoning logic:

      QUANTITY CHECK:
        stock >= quantity              → fulfil from stock
        production_capacity >= qty     → fulfil via production
        neither but stock/capacity > 0 → partial fulfil only
        both = 0                       → cannot fulfil at all

      DELIVERY CHECK:
        effective_delivery = delivery_time_days + feasibility_buffer
        (High = +0 days, Medium = +2 days, Low = +5 days)
        effective_delivery <= required  → can meet timeline
        else                            → timeline missed, flag gap

      OVERALL STATUS:
        "can_fulfil"       — full qty + delivery met
        "counter_proposal" — partial qty OR delivery missed
        "cannot_fulfil"    — nothing available at all

    Args:
        supplier_name          : Supplier to evaluate.
        category               : Item category from RFQ.
        quantity               : Units requested.
        required_delivery_days : Buyer's maximum delivery window (days).

    Returns:
        {
          status                  : "can_fulfil" | "counter_proposal" |
                                    "cannot_fulfil" | "not_found"
          supplier                : str
          category                : str
          quantity_requested      : int
          quantity_can_offer      : int
          fulfilment_source       : "stock" | "production" | "partial" | "none"
          stock_available         : int
          production_capacity     : int
          delivery_feasibility    : str
          standard_delivery_days  : int
          effective_delivery_days : int
          can_meet_delivery       : bool
          delivery_gap_days       : int
          needs_counter_proposal  : bool
          counter_reason          : str
          message                 : str
        }
    """
    row = _fetch_row(supplier_name, category)
    if not row:
        return {
            "status":   "not_found",
            "message":  f"No catalog entry for {supplier_name} / {category}.",
            "supplier": supplier_name,
            "category": category,
        }

    stock        = int(row["stock_availability_units"])
    capacity     = int(row["production_capacity_units_month"])
    feasib       = row["delivery_feasibility"]
    std_delivery = int(row["delivery_time_days"])

    # Quantity reasoning
    if stock >= quantity:
        qty_offered = quantity
        source      = "stock"
    elif capacity >= quantity:
        qty_offered = quantity
        source      = "production"
    elif stock > 0 or capacity > 0:
        qty_offered = max(stock, capacity)
        source      = "partial"
    else:
        qty_offered = 0
        source      = "none"

    # Delivery reasoning
    buffer         = FEASIBILITY_BUFFER.get(feasib, 2)
    effective_days = std_delivery + buffer
    can_meet_del   = effective_days <= required_delivery_days
    delivery_gap   = max(0, effective_days - required_delivery_days)

    # Overall status
    if qty_offered == 0:
        status  = "cannot_fulfil"
        counter = False
        reason  = "No stock or production capacity available."
    elif qty_offered < quantity or not can_meet_del:
        status  = "counter_proposal"
        counter = True
        parts   = []
        if qty_offered < quantity:
            parts.append(
                f"can only offer {qty_offered} of {quantity} units"
            )
        if not can_meet_del:
            parts.append(
                f"earliest delivery is {effective_days} days "
                f"({delivery_gap}d beyond required {required_delivery_days}d)"
            )
        reason = "; ".join(parts).capitalize() + "."
    else:
        status  = "can_fulfil"
        counter = False
        reason  = ""

    if status == "can_fulfil":
        msg = (f"{supplier_name} can fully fulfil {quantity} units of "
               f"{category} within {effective_days} days from {source}.")
    elif status == "counter_proposal":
        msg = f"{supplier_name} submitting counter-proposal: {reason}"
    else:
        msg = f"{supplier_name} cannot fulfil this order. {reason}"

    return {
        "status":                  status,
        "supplier":                supplier_name,
        "category":                category,
        "quantity_requested":      quantity,
        "quantity_can_offer":      qty_offered,
        "fulfilment_source":       source,
        "stock_available":         stock,
        "production_capacity":     capacity,
        "delivery_feasibility":    feasib,
        "standard_delivery_days":  std_delivery,
        "effective_delivery_days": effective_days,
        "can_meet_delivery":       can_meet_del,
        "delivery_gap_days":       delivery_gap,
        "needs_counter_proposal":  counter,
        "counter_reason":          reason,
        "message":                 msg,
    }


# ══════════════════════════════════════════════════════════════════════
# Tool 2 — generate_quote
# ══════════════════════════════════════════════════════════════════════

def generate_quote(
    supplier_name: str,
    category: str,
    quantity: int,
    rfq_id: str,
    required_delivery_days: int,
    quantity_to_offer: int = None,
) -> dict:
    """
    Generates a formal structured quotation matching the procurement spec.

    Call this AFTER check_capacity_and_delivery().
    Pass quantity_to_offer if a counter-proposal is needed.

    Discount logic:
      Full order fulfilled on time → full available_discount applied
      Counter-proposal             → half discount only

    Args:
        supplier_name          : Supplier generating the quote.
        category               : Item category.
        quantity               : Original quantity requested in RFQ.
        rfq_id                 : RFQ ID from the buyer.
        required_delivery_days : Buyer's required delivery window.
        quantity_to_offer      : Override for counter-proposals.
                                 If None, uses full quantity.

    Returns:
        Structured quotation matching the spec:
        {
          supplier               : str
          rfq_id                 : str
          quote_id               : str
          quoted_price_per_unit  : float
          discount_applied_pct   : int
          total_quoted_price     : float
          delivery_days_committed: int
          quantity_offered       : int
          remarks                : str
          status                 : "submitted" | "counter_proposal"
          formatted_output       : str  — markdown table, print verbatim
        }
    """
    row = _fetch_row(supplier_name, category)
    if not row:
        return {
            "status":  "not_found",
            "message": f"No catalog entry for {supplier_name} / {category}.",
        }

    unit_price   = float(row["per_unit_price_usd"])
    max_discount = int(row["available_discount"])
    std_delivery = int(row["delivery_time_days"])
    feasib       = row["delivery_feasibility"]
    stock        = int(row["stock_availability_units"])
    capacity     = int(row["production_capacity_units_month"])

    buffer         = FEASIBILITY_BUFFER.get(feasib, 2)
    effective_days = std_delivery + buffer
    qty_offered    = quantity_to_offer if quantity_to_offer is not None else quantity
    is_counter     = qty_offered < quantity or effective_days > required_delivery_days

    # Full discount for full fulfilment, half for counter-proposal
    discount_applied = max_discount if not is_counter else max(1, max_discount // 2)
    disc_unit_price  = round(unit_price * (1 - discount_applied / 100), 2)
    total_price      = round(disc_unit_price * qty_offered, 2)
    list_total       = round(unit_price * qty_offered, 2)
    savings          = round(list_total - total_price, 2)
    quote_id         = f"QT-{uuid.uuid4().hex[:8].upper()}"
    quote_status     = "counter_proposal" if is_counter else "submitted"

    # Build remarks
    parts = []
    if not is_counter:
        src = "stock" if stock >= quantity else "production"
        parts.append(f"Can fulfil full order of {quantity} units from {src}.")
        parts.append(f"Offering {discount_applied}% discount for this order.")
    else:
        if qty_offered < quantity:
            parts.append(
                f"Can only offer {qty_offered} of {quantity} units "
                f"(stock: {stock}, capacity: {capacity}/month)."
            )
        if effective_days > required_delivery_days:
            parts.append(
                f"Earliest delivery is {effective_days} days "
                f"(required: {required_delivery_days} days)."
            )
        parts.append(
            f"Offering {discount_applied}% discount on counter-proposal."
        )
    remarks = " ".join(parts)

    # Structured quotation — matches spec exactly
    structured_quote = {
        "supplier":                supplier_name,
        "rfq_id":                  rfq_id,
        "quote_id":                quote_id,
        "quoted_price_per_unit":   disc_unit_price,
        "discount_applied_pct":    discount_applied,
        "total_quoted_price":      total_price,
        "delivery_days_committed": effective_days,
        "quantity_offered":        qty_offered,
        "remarks":                 remarks,
        "status":                  quote_status,
    }

    # Markdown table for display
    lines = []
    lines.append("---")
    lines.append(f"## 📋 Quotation — {supplier_name}")
    if is_counter:
        lines.append(
            "> ⚠️ **Counter-proposal** — "
            "supplier cannot fully meet original RFQ terms."
        )
    lines.append("")

    rows = [
        ["Quote ID",               quote_id],
        ["RFQ Reference",          rfq_id],
        ["Supplier",               supplier_name],
        ["Category",               category],
        ["Quantity Requested",     quantity],
        ["**Quantity Offered**",   f"**{qty_offered}**"],
        ["List Unit Price",        f"${unit_price}"],
        ["Discount Applied",       f"{discount_applied}%"],
        ["**Quoted Price / Unit**",f"**${disc_unit_price}**"],
        ["List Total",             f"${list_total}"],
        ["**Total Quoted Price**", f"**${total_price}**"],
        ["Savings vs List",        f"${savings}"],
        ["Delivery Committed",     f"{effective_days} days"],
        ["Buyer Required Delivery",f"{required_delivery_days} days"],
        ["Delivery Feasibility",   feasib],
        ["Quote Status",           quote_status.upper()],
        ["Quote Valid For",        "14 days"],
        ["Issued At",              datetime.now().strftime("%Y-%m-%d %H:%M")],
    ]
    lines.append(tabulate(rows, headers=["Field", "Value"], tablefmt="pipe"))
    lines.append("")
    lines.append(f"> **Remarks:** {remarks}")
    lines.append("")
    lines.append("---")

    return {
        **structured_quote,
        "unit_price_usd":       unit_price,
        "list_total_usd":       list_total,
        "savings_usd":          savings,
        "delivery_feasibility": feasib,
        "formatted_output":     "\n".join(lines),
    }