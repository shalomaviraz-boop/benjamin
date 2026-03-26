"""Central registry for Benjamin internal agents."""

from agents.breaking_agent import BreakingAgent
from agents.base_agent import BaseAgent
from agents.execution_agent import ExecutionAgent
from agents.memory_agent import MemoryAgent
from agents.planning_agent import PlanningAgent
from agents.priority_agent import PriorityAgent
from agents.quality_agent import QualityAgent
from agents.research_agent import ResearchAgent
from agents.verification_agent import VerificationAgent


class AgentRegistry:
    def __init__(self):
        self._agents = {}

    def register(self, name: str, agent, *, overwrite: bool = True) -> None:
        if not overwrite and name in self._agents:
            return
        self._agents[name] = agent

    def get(self, name: str):
        return self._agents.get(name)

    def list_agents(self) -> list[str]:
        return sorted(self._agents.keys())

    def has(self, name: str) -> bool:
        return name in self._agents


class PlaceholderAgent(BaseAgent):
    async def run(self, task: dict, context: dict) -> dict:
        return {
            "status": "not_implemented",
            "agent": self.name,
            "task": task,
        }


def build_default_registry() -> AgentRegistry:
    registry = AgentRegistry()

    # Existing proactive intelligence agents (reused, no duplicate logic).
    registry.register("research", ResearchAgent())
    registry.register("breaking", BreakingAgent())
    registry.register("quality", QualityAgent())
    registry.register("priority", PriorityAgent())
    registry.register("memory", MemoryAgent())

    # Multi-agent foundation (v1).
    registry.register("planning", PlanningAgent(), overwrite=False)
    registry.register("execution", ExecutionAgent(), overwrite=False)
    registry.register("verification", VerificationAgent(), overwrite=False)
    return registry


registry = build_default_registry()
