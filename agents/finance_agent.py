"""Dedicated finance and markets agent."""

from agents.research_agent import ResearchAgent


class FinanceAgent(ResearchAgent):
    def __init__(self):
        super().__init__()
        self.name = "finance"
        self.description = "Handles markets, stocks, macro and financial analysis."
