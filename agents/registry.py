"""Central registry for Benjamin internal agents."""

from agents.agent_capabilities import DEFAULT_AGENT_CAPABILITIES
from agents.assistant_agent import AssistantAgent
from agents.breaking_agent import BreakingAgent
from agents.business_strategy_agent import BusinessStrategyAgent
from agents.base_agent import BaseAgent
from agents.code_agent import CodeAgent
from agents.execution_agent import ExecutionAgent
from agents.finance_agent import FinanceAgent
from agents.fitness_health_agent import FitnessHealthAgent
from agents.memory_agent import MemoryAgent
from agents.planning_agent import PlanningAgent
from agents.priority_agent import PriorityAgent
from agents.relationships_agent import RelationshipsAgent
from agents.quality_agent import QualityAgent
from agents.research_agent import ResearchAgent
from agents.verification_agent import VerificationAgent


class AgentRegistry:
    def __init__(self):
        self._agents = {}
        self._capabilities = {}

    def register(self, name: str, agent, *, overwrite: bool = True) -> None:
        if not overwrite and name in self._agents:
            return
        self._agents[name] = agent
        self._capabilities[name] = getattr(agent, "capabilities", DEFAULT_AGENT_CAPABILITIES.get(name, {}))

    def get(self, name: str):
        return self._agents.get(name)

    def get_capabilities(self, name: str) -> dict:
        return dict(self._capabilities.get(name) or {})

    def list_agents(self) -> list[str]:
        return sorted(self._agents.keys())

    def list_capabilities(self) -> dict:
        return {name: dict(meta) for name, meta in sorted(self._capabilities.items())}

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
    registry.register("research", ResearchAgent())
    registry.register("memory", MemoryAgent())
    registry.register("planning", PlanningAgent(), overwrite=False)
    registry.register("execution", ExecutionAgent(), overwrite=False)
    registry.register("verification", VerificationAgent(), overwrite=False)
    registry.register("code", CodeAgent())
    registry.register("finance", FinanceAgent())
    registry.register("assistant", AssistantAgent())
    registry.register("fitness_health", FitnessHealthAgent())
    registry.register("relationships", RelationshipsAgent())
    registry.register("business_strategy", BusinessStrategyAgent())
    registry.register("breaking", BreakingAgent())
    registry.register("quality", QualityAgent())
    registry.register("priority", PriorityAgent())
    return registry


registry = build_default_registry()
