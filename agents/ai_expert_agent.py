"""Dedicated AI specialist agent."""

from agents.research_agent import ResearchAgent


class AIExpertAgent(ResearchAgent):
    def __init__(self):
        super().__init__()
        self.name = "ai_expert"
        self.description = "Handles AI models, agent systems, launches, tools, and practical comparisons."
