"""Text polish for outbound proactive messages."""

from experts.gemini_client import generate_web


class QualityAgent:
    async def polish(self, text: str) -> str:
        prompt = (
            "שכתב את ההודעה הבאה לעברית מקצועית, חדה וקצרה, בלי להוסיף עובדות חדשות.\n"
            "שמור על כל העובדות כפי שהן, רק נקה ניסוח אם צריך.\n\n"
            f"{text}"
        )
        polished = await generate_web(prompt)
        return (polished or text).strip() or text
