"""Scheduled intelligence report generation."""

from telegram.ext import ContextTypes

from agents.agent_context import read_shared_context
from agents.agent_contract import build_agent_result
from agents.base_agent import BaseAgent
from experts.gemini_client import generate_web


NEWS_KEYWORDS = [
    "חדשות", "עדכונים", "אחרונות", "אחרונים", "מה חדש", "מה קורה", "היום",
    "latest", "news", "current", "recent", "today", "update", "updates",
]


def _is_news_query(message: str) -> bool:
    msg = (message or "").lower()
    return any(keyword in msg for keyword in NEWS_KEYWORDS)


def _build_research_prompt(message: str) -> str:
    if _is_news_query(message):
        return (
            "ענה בעברית, קצר, חד ומדויק. מדובר בבקשת חדשות/עדכונים ולכן חובה להחזיר מידע עדכני בלבד מהווב.\n"
            "חוקים מחייבים:\n"
            "- תביא רק 3 עד 5 עדכונים הכי חשובים ורלוונטיים\n"
            "- לכל עדכון חובה לציין תאריך מפורש\n"
            "- אל תביא מידע ישן או רקע היסטורי אם לא התבקש\n"
            "- אם אין ודאות או שהמידע לא עדכני מספיק, תגיד זאת במפורש\n"
            "- בלי הקדמה כללית ובלי חפירות\n"
            "- התחל ישר מהעדכונים\n"
            "- בסוף תן שורת סיכום אחת: למה זה חשוב\n\n"
            f"בקשת המשתמש: {message}"
        )

    return (
        "ענה בעברית בצורה קצרה, חדה ומבוססת מקורות עדכניים.\n"
        "חוקים:\n"
        "- אם השאלה נוגעת למידע עדכני, חובה להסתמך על ווב עדכני\n"
        "- אם חסר מידע ודאי תגיד זאת\n"
        "- בלי הקדמות מיותרות\n\n"
        f"בקשת המשתמש: {message}"
    )


class ResearchAgent(BaseAgent):
    def __init__(self):
        super().__init__("research", "Researches current information and web-grounded answers.")

    async def generate_report(self) -> str:
        prompt = (
            "כתוב דוח אינטליגנציה יומי בעברית, חד, מקצועי וקריא.\n"
            "הדוח מיועד למתן. בלי שאלות בכלל.\n"
            "\n"
            "פורמט חובה ומדויק:\n"
            "כותרת קצרה עם תאריך ושעה\n"
            "\n"
            "🌍 Global\n"
            "- 3 עד 5 התפתחויות גלובליות חשובות ביותר\n"
            "- בולטים קצרים וחדים בלבד\n"
            "\n"
            "🇮🇱 Israel\n"
            "- 3 עד 5 התפתחויות ישראליות חשובות ביותר\n"
            "- בולטים קצרים וחדים בלבד\n"
            "\n"
            "Takeaway:\n"
            "- שורת סיכום קצרה אחת בלבד\n"
            "\n"
            "חוקים:\n"
            "- בלי שאלות למשתמש\n"
            "- בלי ניתוח פסיכולוגי\n"
            "- בלי חפירות\n"
            "- בלי להמציא עובדות\n"
            "- בלי הקדמות מיותרות\n"
            "- מקסימום 220 מילים לכל הדוח\n"
            "- אם אין מספיק אירועים מהותיים, כתוב רק את המשמעותיים באמת\n"
        )
        return await generate_web(prompt)

    async def run(self, task: dict, context: dict) -> dict:
        shared = read_shared_context(task, context)
        message = (shared.user_message or task.get("message") or "").strip()
        if not message:
            result = build_agent_result(
                agent=self.name,
                status="failed",
                notes="missing research message",
                should_fallback=True,
                agent_context=shared.to_dict(),
            )
            shared.research_output = result
            shared.add_log(self.name, "missing research message")
            result["agent_context"] = shared.to_dict()
            return result

        prompt = _build_research_prompt(message)
        try:
            output = await generate_web(prompt, memory_context=shared.memory_context or (context or {}).get("memory_context"))
            result = build_agent_result(
                agent=self.name,
                output=output,
                notes="news research completed" if _is_news_query(message) else "web research completed",
                agent_context=shared.to_dict(),
            )
            shared.research_output = result
            shared.add_log(self.name, "research success")
            result["agent_context"] = shared.to_dict()
            return result
        except Exception as e:
            result = build_agent_result(
                agent=self.name,
                status="failed",
                notes=f"research error: {e}",
                should_fallback=True,
                agent_context=shared.to_dict(),
            )
            shared.research_output = result
            shared.add_log(self.name, f"research failed: {e}")
            result["agent_context"] = shared.to_dict()
            return result

    async def run_proactive_report(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            chat_id = context.job.data.get("chat_id")
            if not chat_id:
                return
            response = await self.generate_report()
            await context.bot.send_message(chat_id=chat_id, text=response)
        except Exception as e:
            print(f"Proactive report job error: {e}")
