class LLMRouter:
    def __init__(self, gpt_orchestrator):
        self.gpt = gpt_orchestrator

    async def decide(self, message: str, memory_context: dict | None = None) -> dict:
        plan = await self.gpt.decide(message, memory_context=memory_context)
        if isinstance(plan, dict):
            plan.setdefault("routing_source", "llm")
        return plan
