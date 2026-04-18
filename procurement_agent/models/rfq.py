"""
RFQ (Request for Quotation) data model.
Three mandatory fields collected from the buyer:
  - Item_Category
  - Quantity
  - Delivery_Date
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class RFQ:
    """Request for Quotation sent to suppliers."""

    # ── Identification ───────────────────────────────────────────────
    rfq_id: str = ""

    # ── Mandatory fields (collected from buyer) ──────────────────────
    item_category: str = ""               # Item_Category
    quantity: Optional[int] = None        # Quantity
    delivery_date: Optional[str] = None   # Delivery_Date (YYYY-MM-DD string)

    def to_supplier_rfq_dict(self) -> dict:
        """Serialise RFQ into a clean dict to send to each supplier."""
        return {
            "rfq_id": self.rfq_id,
            "item_category": self.item_category,
            "quantity": self.quantity,
            "delivery_date": self.delivery_date,
        }