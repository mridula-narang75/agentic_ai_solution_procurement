"""
procurement_agent/tools/buyer_tools.py
──────────────────────────────────────
Tool functions for the Buyer Strategy Agent.

Uses tablefmt="pipe" so tables render correctly as markdown
in the ADK web UI.
"""

import uuid
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Union, Optional
from tabulate import tabulate

from ..models.rfq import RFQ
from .dataset_loader import lookup_supplier_history as _db_lookup

SUPPLIERS = [
    "Alpha_Inc",
    "Beta_Supplies",
    "Delta_Logistics",
    "Epsilon_Group",
    "Gamma_Co",
]

SUPPLIER_NUMBER_MAP = {
    "1": "Alpha_Inc",
    "2": "Beta_Supplies",
    "3": "Delta_Logistics",
    "4": "Epsilon_Group",
    "5": "Gamma_Co",
}


def calculate_delivery_date(delivery_specification: Union[str, int]) -> str:
    """Calculates delivery date from number of days or string like '21 days'."""
    if isinstance(delivery_specification, int):
        days = delivery_specification
    else:
        match = re.search(r'(\d+)', str(delivery_specification))
        if match:
            days = int(match.group(1))
        else:
            raise ValueError(f"Could not extract days from: {delivery_specification}")
    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")


def get_supplier_summary(item_category: str) -> Dict[str, Any]:
    """
    Fetches KPIs for all 5 suppliers and returns a decision-focused comparison.
    
    Identifies and highlights:
      - Cheapest Supplier (lowest price per unit)
      - Fastest Supplier (shortest delivery time)
      - Best Discount Supplier (highest discount)
      - Best Overall Trade-off (balanced scoring)

    Args:
        item_category: Category filter for KPI lookup.

    Returns:
        {
          "all_suppliers": [list of supplier dicts with highlights],
          "recommended_supplier": str (best overall choice),
          "formatted_output": str (markdown — ready to print verbatim)
        }
    """
    # Fetch all supplier KPIs
    all_kpis = {s: _db_lookup(s, item_category) for s in SUPPLIERS}
    
    # Analyze each supplier
    supplier_data = []
    for i, supplier in enumerate(SUPPLIERS, 1):
        kpi = all_kpis[supplier]
        supplier_data.append({
            "number": i,
            "supplier": supplier,
            "price": kpi.get("avg_unit_price") or 0,
            "delivery_days": kpi.get("avg_lead_time_days") or 999,
            "discount": kpi.get("avg_discount_pct") or 0,
            "performance_score": kpi.get("performance_score") or 0,
            "on_time_delivery": kpi.get("on_time_delivery_rate") or 0,
            "defect_rate": kpi.get("avg_defect_rate_pct") or 0,
            "compliance": kpi.get("compliance_rate") or 0,
            "total_orders": kpi.get("total_orders") or 0,
            "full_kpi": kpi,
        })
    
    # Find highlights
    cheapest = min(supplier_data, key=lambda x: x["price"])
    fastest = min(supplier_data, key=lambda x: x["delivery_days"])
    best_discount = max(supplier_data, key=lambda x: x["discount"])
    
    # Calculate simple trade-off score (lower is better for price/delivery, higher for discount)
    # Normalize and weight: 50% price, 30% delivery, 20% discount
    for s in supplier_data:
        price_score = s["price"] / cheapest["price"] if cheapest["price"] > 0 else 1
        delivery_score = s["delivery_days"] / fastest["delivery_days"] if fastest["delivery_days"] > 0 else 1
        discount_score = 1 - (s["discount"] / 100)  # lower is better
        
        s["trade_off_score"] = (price_score * 0.5) + (delivery_score * 0.3) + (discount_score * 0.2)
    
    best_overall = min(supplier_data, key=lambda x: x["trade_off_score"])
    
    # Build formatted output
    lines = []
    lines.append("---")
    lines.append("## 📊 Supplier Comparison")
    lines.append("")
    
    # ── Key Highlights (Top Summary) ──────────────────────────────────────
    lines.append("### 🎯 Quick Highlights")
    lines.append("")
    lines.append(f"💰 **Lowest Price:** {cheapest['supplier']} – **${cheapest['price']}/unit**")
    lines.append(f"⚡ **Fastest Delivery:** {fastest['supplier']} – **{fastest['delivery_days']} days**")
    lines.append(f"🎁 **Best Discount:** {best_discount['supplier']} – **{best_discount['discount']}%**")
    lines.append(f"⭐ **Best Overall:** {best_overall['supplier']} – *Balanced price & delivery*")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # ── Main Comparison Table ──────────────────────────────────────
    lines.append("### 📋 All Suppliers")
    lines.append("")
    
    comparison_rows = []
    for s in supplier_data:
        tags = []
        if s["supplier"] == cheapest["supplier"]:
            tags.append("💰 Lowest Price")
        if s["supplier"] == fastest["supplier"]:
            tags.append("⚡ Fastest")
        if s["supplier"] == best_discount["supplier"]:
            tags.append("🎁 Best Discount")
        if s["supplier"] == best_overall["supplier"]:
            tags.append("⭐ Best Overall")
        
        tag_str = " | ".join(tags) if tags else ""
        
        comparison_rows.append([
            s["number"],
            s["supplier"],
            f"${s['price']}",
            f"{s['delivery_days']}d",
            f"{s['discount']}%",
            tag_str,
        ])
    
    lines.append(tabulate(
        comparison_rows,
        headers=["#", "Supplier", "Price/Unit", "Delivery", "Discount", "Highlights"],
        tablefmt="pipe",
    ))
    
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("### 📈 Supplier Rankings by Trade-Off Score")
    lines.append("")
    
    # Sort suppliers by trade_off_score (lower is better)
    ranked_suppliers = sorted(supplier_data, key=lambda x: x["trade_off_score"])
    
    rank_rows = []
    for rank, s in enumerate(ranked_suppliers, 1):
        rank_rows.append([
            rank,
            s["number"],
            s["supplier"],
            f"{s['trade_off_score']:.3f}",
            f"${s['price']}",
            f"{s['delivery_days']}d",
            f"{s['discount']}%",
        ])
    
    lines.append(tabulate(
        rank_rows,
        headers=["Rank", "#", "Supplier", "Trade-Off Score", "Price/Unit", "Delivery", "Discount"],
        tablefmt="pipe",
    ))
    
    lines.append("")
    lines.append("> **Trade-Off Score** = Price 50% + Delivery 30% + Discount 20% (lower is better)")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"**To publish RFQ with {best_overall['supplier']}, type `publish` or `yes`.**")
    lines.append("")
    lines.append("Or type a number `1`–`5` to select a different supplier.")
    lines.append("")
    
    return {
        "all_suppliers": supplier_data,
        "recommended_supplier": best_overall["supplier"],
        "formatted_output": "\n".join(lines),
    }


def format_rfq_confirmation(result: Dict[str, Any]) -> str:
    """Formats the final RFQ confirmation as markdown tables for top 3 suppliers."""
    lines = []
    lines.append("---")
    lines.append("## ✅ RFQ Published Successfully")
    lines.append("")
    
    # ── Prominent RFQ ID Display ──────────────────────────────────────
    lines.append(f"### 🎟️ RFQ ID: `{result.get('rfq_id', 'N/A')}`")
    lines.append("")

    summary_rows = [
        ["Status",            "PUBLISHED"],
        ["Item Category",     result.get("item_category", "N/A")],
        ["Quantity",          str(result.get("quantity", "N/A"))],
        ["Delivery Date",     result.get("delivery_date", "N/A")],
        ["Timestamp",         result.get("timestamp", "N/A")],
        ["Published To",      "Top 3 Suppliers"],
    ]
    lines.append(tabulate(summary_rows, headers=["Field", "Value"], tablefmt="pipe"))

    # ── Top 3 Suppliers Table ──────────────────────────────────────
    lines.append("")
    lines.append("### 📬 Sent to Top 3 Suppliers")
    lines.append("")
    
    top_suppliers = result.get("top_3_suppliers", [])
    if top_suppliers:
        suppliers_rows = []
        for rank, supplier_info in enumerate(top_suppliers, 1):
            kpi = supplier_info.get("kpi", {})
            suppliers_rows.append([
                rank,
                supplier_info.get("supplier", "N/A"),
                f"${kpi.get('avg_unit_price', 'N/A')}",
                f"{kpi.get('avg_lead_time_days', 'N/A')}d",
                f"{kpi.get('performance_score', 'N/A')}",
            ])
        
        lines.append(tabulate(
            suppliers_rows,
            headers=["Rank", "Supplier", "Price/Unit", "Delivery", "Performance"],
            tablefmt="pipe"
        ))
    
    # ── Detailed KPI for each supplier ──────────────────────────────────────
    for rank, supplier_info in enumerate(top_suppliers, 1):
        lines.append("")
        lines.append(f"### 📊 Supplier {rank}: {supplier_info.get('supplier', 'N/A')}")
        lines.append("")
        
        kpi = supplier_info.get("kpi", {})
        kpi_rows = [
            ["Performance Score",   kpi.get("performance_score", "N/A")],
            ["On-Time Delivery",    f"{kpi.get('on_time_delivery_rate', 'N/A')}%"],
            ["Avg Defect Rate",     f"{kpi.get('avg_defect_rate_pct', 'N/A')}%"],
            ["Compliance Rate",     f"{kpi.get('compliance_rate', 'N/A')}%"],
            ["Avg Unit Price",      f"${kpi.get('avg_unit_price', 'N/A')}"],
            ["Avg Discount Given",  f"{kpi.get('avg_discount_pct', 'N/A')}%"],
            ["Avg Lead Time",       f"{kpi.get('avg_lead_time_days', 'N/A')} days"],
            ["Historical Orders",   kpi.get("total_orders", "N/A")],
        ]
        lines.append(tabulate(kpi_rows, headers=["KPI", "Value"], tablefmt="pipe"))

    lines.append("")
    lines.append("---")
    return "\n".join(lines)


def publish_rfq(
    item_category: str,
    quantity: int,
    delivery_days: Union[int, str],
    selected_supplier: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Publishes an RFQ to the top 3 suppliers based on trade-off score.

    Args:
        item_category     : Category of item being procured.
                            Real categories: Electronics, Raw Materials,
                            Packaging, MRO, Office Supplies
        quantity          : Number of units required.
        delivery_days     : Number of days for delivery (e.g. 21 or "within 21 days").
        selected_supplier : Optional supplier override. If provided, still publishes to top 3.

    Returns:
        Dict with rfq_id, top 3 suppliers with KPIs, and formatted_output (markdown).
    """
    delivery_date = calculate_delivery_date(delivery_days)

    # Fetch all KPIs and calculate trade-off scores
    all_kpis = {s: _db_lookup(s, item_category) for s in SUPPLIERS}
    
    supplier_data = []
    for supplier in SUPPLIERS:
        kpi = all_kpis[supplier]
        supplier_data.append({
            "supplier": supplier,
            "kpi": kpi,
            "price": kpi.get("avg_unit_price") or 0,
            "delivery": kpi.get("avg_lead_time_days") or 999,
            "discount": kpi.get("avg_discount_pct") or 0,
            "performance": kpi.get("performance_score") or 0,
        })
    
    # Calculate trade-off scores (same as in get_supplier_summary)
    best_price = min(s["price"] for s in supplier_data) if supplier_data else 1
    best_delivery = min(s["delivery"] for s in supplier_data) if supplier_data else 1
    
    for s in supplier_data:
        price_score = s["price"] / best_price if best_price > 0 else 1
        delivery_score = s["delivery"] / best_delivery if best_delivery > 0 else 1
        discount_score = 1 - (s["discount"] / 100)
        
        s["trade_off_score"] = (price_score * 0.5) + (delivery_score * 0.3) + (discount_score * 0.2)
    
    # Get top 3 suppliers by trade-off score
    top_3 = sorted(supplier_data, key=lambda x: x["trade_off_score"])[:3]
    
    # Generate RFQ
    rfq = RFQ(
        rfq_id=f"RFQ-{uuid.uuid4().hex[:8].upper()}",
        item_category=item_category,
        quantity=quantity,
        delivery_date=delivery_date,
    )

    # Format top 3 suppliers data
    top_3_suppliers = []
    for supplier_info in top_3:
        top_3_suppliers.append({
            "supplier": supplier_info["supplier"],
            "kpi": {
                "performance_score":     supplier_info["kpi"].get("performance_score"),
                "on_time_delivery_rate": supplier_info["kpi"].get("on_time_delivery_rate"),
                "avg_defect_rate_pct":   supplier_info["kpi"].get("avg_defect_rate_pct"),
                "compliance_rate":       supplier_info["kpi"].get("compliance_rate"),
                "avg_unit_price":        supplier_info["kpi"].get("avg_unit_price"),
                "avg_discount_pct":      supplier_info["kpi"].get("avg_discount_pct"),
                "avg_lead_time_days":    supplier_info["kpi"].get("avg_lead_time_days"),
                "total_orders":          supplier_info["kpi"].get("total_orders"),
            },
        })

    result = {
        "rfq_id":               rfq.rfq_id,
        "status":               "published",
        "item_category":        item_category,
        "quantity":             quantity,
        "delivery_date":        delivery_date,
        "timestamp":            datetime.now().isoformat(),
        "top_3_suppliers":      top_3_suppliers,
    }

    result["formatted_output"] = format_rfq_confirmation(result)
    return result