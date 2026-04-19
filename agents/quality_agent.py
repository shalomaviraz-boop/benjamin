"""Opt-in text polish helper.

Disabled by default so Benjamin does not auto-rewrite responses into chatbot voice.
"""

from experts.model_router import model_router
from utils.benjamin_identity import build_benjamin_internal_prompt


class QualityAgent:
    async def polish(self, text: str) -> str:
        return (text or "").strip() or text

    async def render_proactive_message(
        self,
        *,
        candidate: dict,
        memory_context: dict | None = None,
    ) -> str:
        headline = str(candidate.get("headline") or "").strip()
        summary = str(candidate.get("summary") or "").strip()
        why_relevant = str(candidate.get("why_relevant") or candidate.get("why_it_matters") or "").strip()
        category = str(candidate.get("category") or "").strip()
        opportunity = str(candidate.get("opportunity") or "").strip()

        prompt = build_benjamin_internal_prompt(
            "כתוב הודעת proactive קצרה ואישית למשתמש.\n"
            "חוקים:\n"
            "- 1 עד 3 משפטים קצרים.\n"
            "- תישמע כמו personal operator חד, לא כמו מגיש חדשות.\n"
            "- אם זה רלוונטי למשימת Super Agent או לעסקים/שוק/AI של המשתמש, תגיד למה בשורה אחת חדה.\n"
            "- בלי הקדמה טקסית, בלי כותרות, בלי bullets, בלי לינקים.\n"
            "- אם יש next move ברור, תן אותו בקצרה.\n"
            "- מותר לפתוח בשם Matan רק אם זה מרגיש טבעי.\n"
            "- אל תכתוב: 'להלן', 'לסיכום', 'נכון ל...', 'intelligence report'.\n\n"
            f"category: {category}\n"
            f"headline: {headline}\n"
            f"summary: {summary}\n"
            f"why_relevant: {why_relevant}\n"
            f"opportunity: {opportunity}\n"
        )

        try:
            output, _ = await model_router.generate(
                prompt=prompt,
                task_type="assistant",
                memory_context=memory_context,
                use_web=False,
            )
            return (output or "").strip()
        except Exception:
            fallback_parts = [part for part in [headline, why_relevant or summary, opportunity] if part]
            return " ".join(fallback_parts).strip()
