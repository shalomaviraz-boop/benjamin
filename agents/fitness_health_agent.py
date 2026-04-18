"""Dedicated fitness, nutrition and health agent."""

from agents.execution_agent import ExecutionAgent


class FitnessHealthAgent(ExecutionAgent):
    def __init__(self):
        super().__init__()
        self.name = "fitness_health"
        self.description = "Handles training, nutrition, body composition and health routines."
