"""Scheduled intelligence report generation."""

from telegram.ext import ContextTypes

from experts.gemini_client import generate_web


class ResearchAgent:
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

    async def run_proactive_report(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Scheduled intelligence feed - 2 times a day."""
        try:
            chat_id = context.job.data.get("chat_id")
            if not chat_id:
                return

            response = await self.generate_report()
            await context.bot.send_message(chat_id=chat_id, text=response)

        except Exception as e:
            print(f"Proactive report job error: {e}")
