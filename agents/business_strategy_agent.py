"""Dedicated business strategy agent."""

from agents.execution_agent import ExecutionAgent


class BusinessStrategyAgent(ExecutionAgent):
    def __init__(self):
        super().__init__()
        self.name = "business_strategy"
        self.description = "Handles business strategy, positioning, offers, GTM and monetization."
