"""Dedicated personal assistant agent."""

from agents.execution_agent import ExecutionAgent


class AssistantAgent(ExecutionAgent):
    def __init__(self):
        super().__init__()
        self.name = "assistant"
        self.description = "Handles personal organization, reminders and task execution."
