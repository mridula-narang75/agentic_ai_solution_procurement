"""
Main agent entry point for Google ADK.
Exposes root_agent at package level.
"""

from .agents.buyer_agent import root_agent

__all__ = ["root_agent"]
