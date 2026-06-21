"""
procurement_agent/agent.py
──────────────────────────
Main entry point for Google ADK.

Chain: BuyerAgent → SupplierAgent → NegotiationAgent
Each agent calls the next one as a sub-agent after completing its phase.
No coordinator needed.
"""

import os
from dotenv import load_dotenv

# Load environment variables once at startup
load_dotenv()

# Each agent uses its own explicit API key from environment
# No global GOOGLE_API_KEY to avoid sub-agent inheritance conflicts

from .agents.buyer_agent import root_agent

__all__ = ["root_agent"]