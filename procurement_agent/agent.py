"""
procurement_agent/agent.py
──────────────────────────
Main entry point for Google ADK.

Chain: BuyerAgent → SupplierAgent → NegotiationAgent
Each agent calls the next one as a sub-agent after completing its phase.
No coordinator needed.
"""

from .agents.buyer_agent import root_agent

__all__ = ["root_agent"]