"""Scheduled intelligence report generation."""

from telegram.ext import ContextTypes

from agents.agent_context import read_shared_context
from agents.agent_contract import build_agent_result
from agents.base_agent import BaseAgent
from experts.gemini_client import generate_web
from experts.model_router import WEB_UNAVAILABLE_MESSAGE, _looks_like_stale_cutoff


NEWS_KEYWORDS = [
    "חדשות", "עדכונים", "אחרונות", "אחרונים", "מה חדש", "מה קורה", "היום",
    "עדכון אחרון", "הכרזות אחרונות", "פריצות דרך",
    "latest", "news", "current", "recent", "today", "update", "updates",
    "breaking", "release", "releases", "launch",
]


def _is_news_query(message: str) -> bool:
    msg = (message or "").lower()
    return any(keyword in msg for keyword in NEWS_KEYWORDS)


def _build_research_prompt(message: str) -> str:
    if _is_news_query(message):
        return (
            "אתה בנימין, עוזר אישי פרימיום. תענה בעברית, קצר, חד, ברור, בקול אישי וטבעי — "
            "לא בסגנון דוח רובוטי ולא בסגנון 'אינטליגנס'.\n"
            "זו בקשת חדשות/עדכונים → חובה להשתמש בחיפוש גוגל בזמן אמת ולהחזיר אך ורק מידע עדכני.\n"
            "חוקים מחייבים:\n"
            "- 3 עד 5 עדכונים הכי חשובים ועדכניים\n"
            "- לכל עדכון חובה תאריך מפורש (יום/חודש/שנה)\n"
            "- בלי רקע היסטורי ובלי מידע ישן\n"
            "- בלי 'נכון לעדכון האחרון שלי' ובלי אזכור של תאריך cutoff\n"
            "- בלי להקדים עם 'להלן', 'לסיכום', 'נכון ל'\n"
            "- אם לא קיבלת מידע ודאי עדכני ממקורות חיים — תגיד זאת בפירוש, אל תמציא\n"
            "- שורת סיכום אחת בסוף: למה זה חשוב עכשיו\n\n"
            f"בקשת המשתמש: {message}"
        )

    return (
        "אתה בנימין. ענה בעברית, קצר, חד, מבוסס מקורות עדכניים.\n"
        "חוקים:\n"
        "- אם השאלה נוגעת למידע עדכני, חובה להסתמך על ווב עדכני\n"
        "- אם חסר מידע ודאי תגיד זאת במפורש\n"
        "- בלי הקדמות מיותרות ובלי חפירות\n\n"
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
        plan = shared.task or task.get("plan") or {}
        grounded_web = bool(plan.get("grounded_web")) or _is_news_query(message)

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
            output = await generate_web(
                prompt,
                memory_context=shared.memory_context or (context or {}).get("memory_context"),
                web_mode="news" if _is_news_query(message) else "research",
            )
        except Exception as e:
            shared.add_log(self.name, f"research web call failed: {e}")
            # On a realtime/grounded query we refuse to fall back to a
            # non-web provider — a stale answer is worse than a clear
            # "live retrieval unavailable" message.
            if grounded_web:
                result = build_agent_result(
                    agent=self.name,
                    output=WEB_UNAVAILABLE_MESSAGE,
                    notes=f"web unavailable on grounded_web query: {e}",
                    should_fallback=False,
                    agent_context=shared.to_dict(),
                )
                shared.research_output = result
                shared.final_output = WEB_UNAVAILABLE_MESSAGE
                result["agent_context"] = shared.to_dict()
                return result
            result = build_agent_result(
                agent=self.name,
                status="failed",
                notes=f"research error: {e}",
                should_fallback=True,
                agent_context=shared.to_dict(),
            )
            shared.research_output = result
            result["agent_context"] = shared.to_dict()
            return result

        text = (output or "").strip()
        # If we asked for realtime and the model served a stale-cutoff answer,
        # refuse it and return the clear unavailability message.
        if grounded_web and (not text or _looks_like_stale_cutoff(text)):
            shared.add_log(self.name, "grounded_web: model returned stale/empty; refusing")
            result = build_agent_result(
                agent=self.name,
                output=WEB_UNAVAILABLE_MESSAGE,
                notes="web grounding returned stale or empty content",
                should_fallback=False,
                agent_context=shared.to_dict(),
            )
            shared.research_output = result
            shared.final_output = WEB_UNAVAILABLE_MESSAGE
            result["agent_context"] = shared.to_dict()
            return result

        result = build_agent_result(
            agent=self.name,
            output=text,
            notes="news research completed" if _is_news_query(message) else "web research completed",
            agent_context=shared.to_dict(),
        )
        shared.research_output = result
        shared.add_log(self.name, "research success")
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
