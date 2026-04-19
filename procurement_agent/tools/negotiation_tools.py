"""
procurement_agent/tools/negotiation_db.py
──────────────────────────────────────────
SQLite access layer for negotiation.db.

Table: negotiation_rules
Columns:
    category, min_order_qty, max_order_qty,
    target_discount_pct, max_discount_pct, min_acceptable_discount_pct,
    price_tolerance_pct, max_negotiation_rounds, counter_offer_step_pct,
    delivery_tolerance_days, priority_weight_price,
    priority_weight_delivery, priority_weight_quantity,
    auto_award_threshold_score, walkaway_price_premium_pct

Three tools exposed to the negotiation agent:
    get_negotiation_rules()   — fetch rules for a category from DB
    compare_quotes()          — score and rank all quotes
    generate_award()          — produce final award summary
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
_DB_PATH   = os.path.join(_AGENT_DIR, "data", "negotiation.db")
TABLE      = "negotiation_rules"


@contextmanager
def _conn():
    if not os.path.exists(_DB_PATH):
        raise FileNotFoundError(
            f"Negotiation database not found at: {_DB_PATH}\n"
            "Run import_negotiation_data.py first."
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


# ══════════════════════════════════════════════════════════════════════
# Tool 1 — get_negotiation_rules
# ══════════════════════════════════════════════════════════════════════

def get_negotiation_rules(category: str) -> dict:
    """
    Fetches negotiation rules for a given category from the database.

    These rules govern how the negotiation agent should behave —
    how hard to push, how many rounds to allow, when to auto-award,
    and when to walk away.

    Args:
        category : One of: Electronics, MRO, Office Supplies,
                   Raw Materials, Packaging

    Returns:
        {
          status                      : "found" | "not_found"
          category                    : str
          target_discount_pct         : int   — discount % to aim for
          max_discount_pct            : int   — max we can ask for
          min_acceptable_discount_pct : int   — walk away below this
          price_tolerance_pct         : int   — % above target still ok
          max_negotiation_rounds      : int   — max back-and-forth rounds
          counter_offer_step_pct      : int   — push by this % each round
          delivery_tolerance_days     : int   — extra days still acceptable
          priority_weight_price       : float — scoring weight for price
          priority_weight_delivery    : float — scoring weight for delivery
          priority_weight_quantity    : float — scoring weight for quantity
          auto_award_threshold_score  : int   — score above this = auto award
          walkaway_price_premium_pct  : int   — reject if price this % above avg
        }
    """
    with _conn() as con:
        row = con.execute(
            f"SELECT * FROM {TABLE} WHERE LOWER(category) = LOWER(?)",
            (category,)
        ).fetchone()

    if not row:
        return {
            "status":  "not_found",
            "message": f"No negotiation rules found for category '{category}'. "
                       f"Valid categories: Electronics, MRO, Office Supplies, "
                       f"Raw Materials, Packaging.",
        }

    return {
        "status":                      "found",
        "category":                    row["category"],
        "min_order_qty":               row["min_order_qty"],
        "max_order_qty":               row["max_order_qty"],
        "target_discount_pct":         row["target_discount_pct"],
        "max_discount_pct":            row["max_discount_pct"],
        "min_acceptable_discount_pct": row["min_acceptable_discount_pct"],
        "price_tolerance_pct":         row["price_tolerance_pct"],
        "max_negotiation_rounds":      row["max_negotiation_rounds"],
        "counter_offer_step_pct":      row["counter_offer_step_pct"],
        "delivery_tolerance_days":     row["delivery_tolerance_days"],
        "priority_weight_price":       row["priority_weight_price"],
        "priority_weight_delivery":    row["priority_weight_delivery"],
        "priority_weight_quantity":    row["priority_weight_quantity"],
        "auto_award_threshold_score":  row["auto_award_threshold_score"],
        "walkaway_price_premium_pct":  row["walkaway_price_premium_pct"],
    }


# ══════════════════════════════════════════════════════════════════════
# Tool 2 — compare_quotes
# ══════════════════════════════════════════════════════════════════════

def compare_quotes(
    category: str,
    quotes: list[dict],
    required_delivery_days: int,
    required_quantity: int,
) -> dict:
    """
    Scores and ranks all supplier quotes using the negotiation rules
    from the database.

    Scoring formula (weights from negotiation_rules DB):
        score = (price_score  × priority_weight_price)
              + (delivery_score × priority_weight_delivery)
              + (quantity_score × priority_weight_quantity)

    Where:
        price_score    = (1 - unit_price / max_unit_price) × 100
        delivery_score = (1 - delivery_days / max_delivery_days) × 100
        quantity_score = (quantity_offered / required_quantity) × 100

    Flags applied per quote:
        auto_award    — score >= auto_award_threshold_score
        walkaway      — price > avg_price × (1 + walkaway_price_premium/100)
        needs_counter — discount < target_discount AND not walkaway

    Args:
        category               : Item category (used to fetch rules).
        quotes                 : List of quote dicts. Each must contain:
                                   supplier, quoted_price_per_unit,
                                   discount_applied_pct, delivery_days_committed,
                                   quantity_offered, status, rfq_id, quote_id
        required_delivery_days : Buyer's required delivery window.
        required_quantity      : Original quantity requested.

    Returns:
        {
          status            : "success" | "error"
          category          : str
          rules_applied     : dict  — rules used for scoring
          ranked_quotes     : list  — quotes sorted by score descending
          best_quote        : dict  — top ranked quote
          recommendation    : str   — "auto_award" | "counter_offer" | "walkaway_all"
          avg_price         : float — average quoted price across all suppliers
          counter_targets   : list  — suppliers worth sending counter-offers to
          walkaway_suppliers: list  — suppliers to reject
          formatted_output  : str   — markdown table, print verbatim
        }
    """
    if not quotes:
        return {"status": "error", "message": "No quotes provided."}

    # Fetch rules
    rules = get_negotiation_rules(category)
    if rules["status"] == "not_found":
        return {"status": "error", "message": rules["message"]}

    w_price    = rules["priority_weight_price"]
    w_delivery = rules["priority_weight_delivery"]
    w_quantity = rules["priority_weight_quantity"]
    auto_thresh    = rules["auto_award_threshold_score"]
    walkaway_prem  = rules["walkaway_price_premium_pct"]
    target_disc    = rules["target_discount_pct"]
    deliv_tol      = rules["delivery_tolerance_days"]

    # Compute normalisation bases
    max_price    = max(q["quoted_price_per_unit"] for q in quotes)
    max_delivery = max(q["delivery_days_committed"] for q in quotes) or 1
    avg_price    = round(
        sum(q["quoted_price_per_unit"] for q in quotes) / len(quotes), 2
    )
    walkaway_ceiling = round(avg_price * (1 + walkaway_prem / 100), 2)

    scored = []
    for q in quotes:
        price    = q["quoted_price_per_unit"]
        delivery = q["delivery_days_committed"]
        qty      = q["quantity_offered"]
        discount = q.get("discount_applied_pct", 0)

        price_score    = (1 - price / max_price) * 100          if max_price    else 0
        delivery_score = (1 - delivery / max_delivery) * 100    if max_delivery else 0
        quantity_score = min((qty / required_quantity) * 100, 100)

        total_score = round(
            price_score    * w_price
            + delivery_score * w_delivery
            + quantity_score * w_quantity,
            1
        )

        delivery_ok   = delivery <= (required_delivery_days + deliv_tol)
        is_walkaway   = price > walkaway_ceiling
        is_auto_award = total_score >= auto_thresh and not is_walkaway
        needs_counter = (
            discount < target_disc
            and not is_walkaway
            and not is_auto_award
        )
        is_counter_proposal = q.get("status") == "counter_proposal"

        scored.append({
            **q,
            "score":           total_score,
            "price_score":     round(price_score,    1),
            "delivery_score":  round(delivery_score, 1),
            "quantity_score":  round(quantity_score, 1),
            "delivery_ok":     delivery_ok,
            "is_walkaway":     is_walkaway,
            "is_auto_award":   is_auto_award,
            "needs_counter":   needs_counter,
            "is_counter_proposal": is_counter_proposal,
        })

    ranked = sorted(scored, key=lambda x: (-x["score"], x["is_walkaway"]))
    best   = ranked[0]

    counter_targets    = [q["supplier"] for q in ranked if q["needs_counter"]]
    walkaway_suppliers = [q["supplier"] for q in ranked if q["is_walkaway"]]

    if best["is_auto_award"]:
        recommendation = "auto_award"
    elif best["is_walkaway"]:
        recommendation = "walkaway_all"
    else:
        recommendation = "counter_offer"

    # Markdown comparison table
    lines = []
    lines.append("---")
    lines.append("## Quote comparison")
    lines.append("")

    table_rows = []
    for i, q in enumerate(ranked, 1):
        flag = ""
        if q["is_auto_award"]:    flag = "AUTO-AWARD"
        elif q["is_walkaway"]:    flag = "WALK AWAY"
        elif q["needs_counter"]:  flag = "COUNTER"
        elif q["is_counter_proposal"]: flag = "COUNTER-PROP"

        table_rows.append([
            i,
            q["supplier"],
            f"${q['quoted_price_per_unit']}",
            f"{q['discount_applied_pct']}%",
            f"{q['delivery_days_committed']}d",
            q["quantity_offered"],
            q["score"],
            flag,
        ])

    lines.append(tabulate(
        table_rows,
        headers=["#", "Supplier", "Price/Unit", "Discount", "Delivery",
                 "Qty", "Score", "Action"],
        tablefmt="pipe",
    ))
    lines.append("")
    lines.append(f"> Avg market price: **${avg_price}** | "
                 f"Walk-away ceiling: **${walkaway_ceiling}** | "
                 f"Auto-award threshold: **{auto_thresh} pts**")
    lines.append("")
    lines.append(f"> **Recommendation: {recommendation.upper().replace('_', ' ')}**")
    lines.append("")
    lines.append("---")

    return {
        "status":             "success",
        "category":           category,
        "rules_applied":      rules,
        "ranked_quotes":      ranked,
        "best_quote":         best,
        "recommendation":     recommendation,
        "avg_price":          avg_price,
        "walkaway_ceiling":   walkaway_ceiling,
        "counter_targets":    counter_targets,
        "walkaway_suppliers": walkaway_suppliers,
        "formatted_output":   "\n".join(lines),
    }


# ══════════════════════════════════════════════════════════════════════
# Tool 3 — generate_award
# ══════════════════════════════════════════════════════════════════════

def generate_award(
    rfq_id: str,
    winning_supplier: str,
    category: str,
    quantity: int,
    final_price_per_unit: float,
    discount_applied_pct: int,
    delivery_days_committed: int,
    quote_id: str,
    justification: str,
    negotiation_rounds: int = 0,
) -> dict:
    """
    Generates a formal procurement award document after negotiation
    is complete.

    Args:
        rfq_id                  : Original RFQ reference.
        winning_supplier        : Supplier being awarded the contract.
        category                : Item category.
        quantity                : Final agreed quantity.
        final_price_per_unit    : Final agreed price per unit (USD).
        discount_applied_pct    : Final discount applied.
        delivery_days_committed : Supplier's committed delivery (days).
        quote_id                : Winning quote reference.
        justification           : Reason for selecting this supplier.
        negotiation_rounds      : Number of rounds it took to reach agreement.

    Returns:
        {
          award_id              : str
          rfq_id                : str
          winning_supplier      : str
          category              : str
          quantity              : int
          final_price_per_unit  : float
          total_contract_value  : float
          discount_applied_pct  : int
          delivery_days_committed: int
          award_date            : str
          negotiation_rounds    : int
          justification         : str
          status                : "awarded"
          formatted_output      : str  — markdown, print verbatim
        }
    """
    award_id          = f"AWD-{uuid.uuid4().hex[:8].upper()}"
    total_value       = round(final_price_per_unit * quantity, 2)
    award_date        = datetime.now().strftime("%Y-%m-%d")
    issued_at         = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = []
    lines.append("---")
    lines.append("## Procurement award")
    lines.append("")

    award_rows = [
        ["Award ID",               award_id],
        ["RFQ Reference",          rfq_id],
        ["Quote Reference",        quote_id],
        ["Awarded To",             winning_supplier],
        ["Category",               category],
        ["Quantity",               quantity],
        ["**Final Price / Unit**", f"**${final_price_per_unit}**"],
        ["Discount Applied",       f"{discount_applied_pct}%"],
        ["**Total Contract Value**",f"**${total_value:,.2f}**"],
        ["Delivery Committed",     f"{delivery_days_committed} days"],
        ["Award Date",             award_date],
        ["Negotiation Rounds",     negotiation_rounds],
        ["Status",                 "AWARDED"],
        ["Issued At",              issued_at],
    ]
    lines.append(tabulate(award_rows, headers=["Field", "Value"], tablefmt="pipe"))
    lines.append("")
    lines.append(f"> **Justification:** {justification}")
    lines.append("")
    lines.append("---")

    return {
        "award_id":               award_id,
        "rfq_id":                 rfq_id,
        "quote_id":               quote_id,
        "winning_supplier":       winning_supplier,
        "category":               category,
        "quantity":               quantity,
        "final_price_per_unit":   final_price_per_unit,
        "total_contract_value":   total_value,
        "discount_applied_pct":   discount_applied_pct,
        "delivery_days_committed": delivery_days_committed,
        "award_date":             award_date,
        "negotiation_rounds":     negotiation_rounds,
        "justification":          justification,
        "status":                 "awarded",
        "formatted_output":       "\n".join(lines),
    }