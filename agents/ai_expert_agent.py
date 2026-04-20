from agents.base_agent import BaseAgent
from agents.agent_contract import build_agent_result
from experts.gemini_client import generate_web


class AIExpertAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="ai_expert")

    async def run(self, message: str, context: dict | None = None):
        context = context or {}
        text = (message or "").lower()

        is_news = any(
            x in text for x in [
                "חדשות", "עדכון", "עדכונים", "מה חדש", "latest", "news",
                "openai", "anthropic", "claude", "gemini", "gpt",
                "meta", "llama", "xai", "grok", "mistral"
            ]
        )

        if is_news:
            prompt = (
                "You are a world-class AI expert with 40 years of experience in artificial intelligence and machine learning. "
                "Answer in Hebrew. This is an AI news/update request, so return only current and relevant information. "
                "Give 3 to 5 key updates. For each one include: explicit date, what was released, what it does, and why it matters. "
                "Be sharp, practical, and non-generic. No old background and no fluff.\n\n"
                f"User request: {message}"
            )
            output = await generate_web(prompt, web_mode="news")
        else:
            prompt = (
                "You are a world-class AI expert with 40 years of experience in artificial intelligence and machine learning. "
                "You deeply understand language models, AI systems, tools, agents, prompting, model capabilities, tradeoffs, "
                "integrations, and real-world use cases. "
                "Answer in Hebrew. Be sharp, practical, clear, and non-generic. "
                "If relevant, compare models/tools and give a clear recommendation.\n\n"
                f"User request: {message}"
            )
            output = await generate_web(prompt, web_mode="research")

        return build_agent_result(
            agent=self.name,
            output=output,
            notes="ai expert completed",
            agent_context=context,
        )