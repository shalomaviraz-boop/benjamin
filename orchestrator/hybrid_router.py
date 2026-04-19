from orchestrator.rule_router import RuleRouter
from orchestrator.llm_router import LLMRouter


class HybridRouter:
    def __init__(self, gpt_orchestrator):
        self.rule_router = RuleRouter()
        self.llm_router = LLMRouter(gpt_orchestrator)
        self.gpt = gpt_orchestrator

    async def decide(self, message: str, memory_context: dict | None = None) -> dict:
        rule_result = self.rule_router.route(message)
        if rule_result:
            return rule_result

        return await self.llm_router.decide(message, memory_context=memory_context)

    async def analyze_governor(self, message: str, personal_model: dict | None = None) -> dict:
        return await self.gpt.analyze_governor(message, personal_model=personal_model or {})

    async def extract_profile_update(self, message: str) -> dict:
        return await self.gpt.extract_profile_update(message)
