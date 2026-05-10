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

# Set the buyer agent API key as the main API key
# (sub-agents will use the same context)
os.environ["GOOGLE_API_KEY"] = os.environ.get("BUYER_AGENT_API_KEY", "")

from .agents.buyer_agent import root_agent

__all__ = ["root_agent"]