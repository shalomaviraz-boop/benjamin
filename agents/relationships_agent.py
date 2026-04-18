"""Dedicated relationships agent."""

from agents.execution_agent import ExecutionAgent


class RelationshipsAgent(ExecutionAgent):
    def __init__(self):
        super().__init__()
        self.name = "relationships"
        self.description = "Handles relationship dynamics, dating, communication and social analysis."
