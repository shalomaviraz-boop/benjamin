from agents.base_agent import BaseAgent
from agents.agent_contract import build_agent_result
from experts.gemini_client import generate_web
from experts.model_router import WEB_UNAVAILABLE_MESSAGE, _looks_like_stale_cutoff


class AIExpertAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="ai_expert")

    async def run(self, message: str, context: dict | None = None):
        context = context or {}
        # Support both the newer dict-style task payload and a raw string.
        plan = {}
        user_message = ""
        if isinstance(message, dict):
            plan = message.get("plan") or {}
            user_message = (message.get("message") or "").strip()
        else:
            user_message = (message or "").strip()

        text = user_message.lower()

        is_news = any(
            x in text for x in [
                "חדשות", "עדכון", "עדכונים", "מה חדש", "latest", "news",
                "openai", "anthropic", "claude", "gemini", "gpt",
                "meta", "llama", "xai", "grok", "mistral",
                "release", "launch", "breaking",
            ]
        )

        grounded_web = bool(plan.get("grounded_web")) or is_news

        if is_news:
            prompt = (
                "אתה בנימין — עוזר אישי פרימיום עם רקע עמוק ב-AI. ענה בעברית, קצר, חד, אישי, לא רובוטי.\n"
                "זו בקשת עדכונים/חדשות בתחום ה-AI → חובה להשתמש בחיפוש חי בגוגל ולא להסתמך על ידע פנימי ישן.\n"
                "פורמט:\n"
                "- 3 עד 5 עדכונים מהותיים ועדכניים\n"
                "- לכל עדכון: תאריך מפורש, מה שוחרר/קרה, מה זה עושה, למה זה חשוב\n"
                "- בלי 'נכון ל...' ובלי אזכור של תאריך cutoff\n"
                "- אם אין מידע ודאי עדכני — תגיד זאת במפורש\n\n"
                f"בקשת המשתמש: {user_message}"
            )
            try:
                output = await generate_web(prompt, web_mode="news")
            except Exception as e:
                if grounded_web:
                    return build_agent_result(
                        agent=self.name,
                        output=WEB_UNAVAILABLE_MESSAGE,
                        notes=f"web unavailable on grounded_web ai query: {e}",
                        should_fallback=False,
                        agent_context=context,
                    )
                output = ""
        else:
            prompt = (
                "אתה בנימין עם רקע מומחה ב-AI. ענה בעברית, קצר, חד, אישי, מעשי.\n"
                "אם רלוונטי, השוואה וחיווי חד להמלצה.\n\n"
                f"בקשת המשתמש: {user_message}"
            )
            try:
                output = await generate_web(prompt, web_mode="research")
            except Exception as e:
                output = f"לא הצלחתי להשלים את שליפת המידע: {e}"

        text_out = (output or "").strip()
        if grounded_web and (not text_out or _looks_like_stale_cutoff(text_out)):
            return build_agent_result(
                agent=self.name,
                output=WEB_UNAVAILABLE_MESSAGE,
                notes="ai expert: web grounding returned stale/empty on news query",
                should_fallback=False,
                agent_context=context,
            )

        return build_agent_result(
            agent=self.name,
            output=text_out,
            notes="ai expert completed",
            agent_context=context,
        )
