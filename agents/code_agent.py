"""Dedicated code and architecture agent."""

from agents.execution_agent import ExecutionAgent


class CodeAgent(ExecutionAgent):
    def __init__(self):
        super().__init__()
        self.name = "code"
        self.description = "Handles code, debugging, refactors and architecture tasks."
