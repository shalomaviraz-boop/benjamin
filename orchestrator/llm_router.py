class LLMRouter:
    def __init__(self, gpt_orchestrator):
        self.gpt = gpt_orchestrator

    async def decide(self, message: str, memory_context: dict | None = None) -> dict:
        plan = await self.gpt.decide(message, memory_context=memory_context)
        if isinstance(plan, dict):
            plan.setdefault("routing_source", "llm")
        return plan

    async def analyze_governor(self, message: str, personal_model: dict | None = None) -> dict:
        return await self.gpt.analyze_governor(message, personal_model=personal_model)

    async def extract_profile_update(self, message: str) -> dict:
        return await self.gpt.extract_profile_update(message)
