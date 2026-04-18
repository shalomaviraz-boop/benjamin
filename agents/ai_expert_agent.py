from agents.base_agent import BaseAgent
from agents.agent_contract import build_agent_result
from experts.gemini_client import generate_web


class AIExpertAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="ai_expert",
            system_prompt=(
                "You are a world-class AI expert with 40 years of experience in artificial intelligence and machine learning. "
                "You deeply understand language models, AI systems, tools, agents, prompting, model capabilities, tradeoffs, "
                "integrations, and real-world use cases. "
                "You explain clearly, sharply, practically, and without generic fluff. "
                "You also track major AI updates from OpenAI, Anthropic, Google, Meta, xAI, Mistral and others."
            ),
        )

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
                "ענה בעברית. מדובר בבקשת חדשות AI ולכן תביא רק מידע עדכני ורלוונטי. "
                "תן 3 עד 5 עדכונים הכי חשובים. "
                "לכל סעיף ציין תאריך, מה יצא, מה זה עושה, ולמה זה חשוב. "
                "בלי מידע ישן ובלי חפירות.\n\n"
                f"בקשת המשתמש: {message}"
            )
            output = await generate_web(prompt, web_mode="news")
        else:
            prompt = (
                "ענה בעברית כמומחה AI בכיר. "
                "תהיה קצר, חד, פרקטי ולא גנרי. "
                "אם צריך השוואה בין מודלים/כלים תן המלצה ברורה.\n\n"
                f"בקשת המשתמש: {message}"
            )
            output = await generate_web(prompt, web_mode="research")

        return build_agent_result(
            agent=self.name,
            output=output,
            notes="ai expert completed",
            agent_context=context,
        )