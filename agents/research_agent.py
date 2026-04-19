"""Scheduled intelligence report generation."""

import json

from telegram.ext import ContextTypes

from agents.agent_context import read_shared_context
from agents.agent_contract import build_agent_result
from agents.base_agent import BaseAgent
from experts.model_router import model_router
from memory.memory_store import load_memory_context_snapshot


NEWS_KEYWORDS = [
    "חדשות", "עדכונים", "אחרונות", "אחרונים", "מה חדש", "מה קורה", "היום",
    "latest", "news", "current", "recent", "today", "update", "updates",
]


def _is_news_query(message: str) -> bool:
    msg = (message or "").lower()
    return any(keyword in msg for keyword in NEWS_KEYWORDS)


def _build_research_prompt(message: str, agent_name: str = "research", description: str = "") -> str:
    role_line = f"אתה הסוכן {agent_name} של בנימין. {description}".strip()
    if _is_news_query(message):
        return (
            f"{role_line}\n"
            "ענה בעברית, קצר, חד ומדויק. מדובר בבקשת חדשות/עדכונים ולכן חובה להחזיר מידע עדכני בלבד מהווב.\n"
            "חוקים מחייבים:\n"
            "- תביא רק 3 עד 5 עדכונים הכי חשובים ורלוונטיים\n"
            "- לכל עדכון חובה לציין תאריך מפורש\n"
            "- אל תביא מידע ישן או רקע היסטורי אם לא התבקש\n"
            "- אם אין ודאות או שהמידע לא עדכני מספיק, תגיד זאת במפורש\n"
            "- בלי הקדמה כללית, בלי סיכום טקסי, ובלי חפירות\n"
            "- התחל ישר מהעדכונים\n"
            "- בלי לינקים גולמיים ובלי dump של מקורות\n"
            "- אל תכתוב: 'נכון ל...', 'לסיכום...', 'להלן הצעה...'\n"
            "- סיים בשורה קצרה אחת של למה זה חשוב, בלי כותרת מיוחדת\n\n"
            f"בקשת המשתמש: {message}"
        )

    return (
        f"{role_line}\n"
        "ענה בעברית בצורה קצרה, חדה, פרקטית ומבוססת מידע עדכני כשצריך.\n"
        "חוקים:\n"
        "- אם השאלה נוגעת למידע עדכני, חובה להסתמך על ווב עדכני\n"
        "- אם חסר מידע ודאי תגיד זאת\n"
        "- בלי הקדמות מיותרות ובלי dump של מקורות\n"
        "- אל תכתוב: 'נכון ל...', 'לסיכום...', 'להלן הצעה...'\n\n"
        f"בקשת המשתמש: {message}"
    )


def _extract_json_object(text: str) -> dict:
    raw = (text or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        data = json.loads(raw[start : end + 1])
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


class ResearchAgent(BaseAgent):
    def __init__(self):
        super().__init__("research", "Researches current information and web-grounded answers.")

    async def generate_proactive_candidate(self, memory_context: dict | None = None) -> dict:
        prompt = (
            "בדוק אם יש כרגע עדכון אחד בלבד ששווה לשלוח proactively למשתמש.\n"
            "Allowed triggers בלבד:\n"
            "1. Important AI breakthrough\n"
            "2. Important release from OpenAI / Anthropic / Google / Meta / xAI\n"
            "3. Strong business opportunity relevant to the user\n"
            "4. Strategic insight relevant to the current Super Agent project\n"
            "5. Important market / macro move relevant to the user's interests\n"
            "6. Personal reminder tied to stated goals\n"
            "\n"
            "חוקים:\n"
            "- אל תשלח generic world news, filler, robotic summaries, או low-signal headlines.\n"
            "- אם אין משהו חזק באמת: should_send=false.\n"
            "- חשיבה אישית: המשתמש בונה עכשיו Super Agent / premium personal AI assistant.\n"
            "- חפש leverage, bottlenecks, pricing changes, reliability changes, launches, and strategic opportunities.\n"
            "- החזר JSON בלבד:\n"
            "{\n"
            '  "should_send": true/false,\n'
            '  "category": "ai" | "business" | "project" | "markets" | "personal" | "",\n'
            '  "headline": "כותרת קצרה",\n'
            '  "summary": "1-2 שורות חדות",\n'
            '  "why_relevant": "למה זה חשוב אישית למשתמש",\n'
            '  "opportunity": "מה אפשר לעשות עם זה, או ריק"\n'
            "}\n"
        )
        raw, _ = await model_router.generate(
            prompt=prompt,
            task_type=self.name,
            memory_context=memory_context,
            use_web=True,
            web_mode="news",
        )
        return _extract_json_object(raw)

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

        prompt = _build_research_prompt(message, self.name, self.description)
        try:
            web_mode = "news" if _is_news_query(message) or self.name == "ai_expert" else "market" if self.name == "finance" else "research"
            output, provider = await model_router.generate(
                prompt=prompt,
                task_type=self.name,
                memory_context=shared.memory_context or (context or {}).get("memory_context"),
                use_web=True,
                require_verification=bool((shared.task or {}).get("require_verification")),
                web_mode=web_mode,
            )
            result = build_agent_result(
                agent=self.name,
                output=output,
                notes=f"provider={provider}, mode={web_mode}",
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

    async def run_proactive_report(self, context: ContextTypes.DEFAULT_TYPE, quality=None) -> None:
        try:
            chat_id = context.job.data.get("chat_id")
            if not chat_id:
                return
            memory_context = load_memory_context_snapshot(
                str(chat_id),
                "super agent ai business markets proactive update",
            )
            candidate = await self.generate_proactive_candidate(memory_context)
            if not candidate or not bool(candidate.get("should_send")):
                return

            if quality is not None:
                response = await quality.render_proactive_message(
                    candidate=candidate,
                    memory_context=memory_context,
                )
            else:
                response = str(candidate.get("headline") or "").strip()

            if not response.strip():
                return
            await context.bot.send_message(chat_id=chat_id, text=response)
        except Exception as e:
            print(f"Proactive report job error: {e}")
