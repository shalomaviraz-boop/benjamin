"""Benjamin - GPT Orchestrator + Gemini Execution."""
import asyncio
import os
import json
import hashlib
import sqlite3
import re
from pathlib import Path
from experts.gemini_client import generate_web

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))  # Before other imports

from telegram import Bot, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler as TelegramMessageHandler,
    filters,
    ContextTypes,
)

from handlers.message_handler import BenjaminMessageHandler

# --- Proactive job imports ---
from datetime import time as dtime
from zoneinfo import ZoneInfo

handler = BenjaminMessageHandler()

# --- Proactive state ---
_STATE_DB_PATH = Path(__file__).resolve().parent / "proactive_state.db"


def _state_conn():
    conn = sqlite3.connect(_STATE_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sent_alerts (
            dedupe_key TEXT PRIMARY KEY,
            category TEXT,
            sent_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    return conn


def _normalize_dedupe_key(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _alert_already_sent(dedupe_key: str) -> bool:
    key = _normalize_dedupe_key(dedupe_key)
    if not key:
        return False
    conn = _state_conn()
    try:
        row = conn.execute(
            "SELECT dedupe_key FROM sent_alerts WHERE dedupe_key = ?",
            (key,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _mark_alert_sent(dedupe_key: str, category: str) -> None:
    key = _normalize_dedupe_key(dedupe_key)
    if not key:
        return
    conn = _state_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO sent_alerts (dedupe_key, category) VALUES (?, ?)",
            (key, category),
        )
        conn.commit()
    finally:
        conn.close()


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
        data = json.loads(raw[start:end + 1])
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# --- Proactive Daily Jobs ---

async def send_us_market_summary(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Legacy wrapper kept for compatibility."""
    await send_proactive_report(context)


async def send_ai_summary(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Legacy wrapper kept for compatibility."""
    await send_proactive_report(context)


async def send_proactive_report(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scheduled intelligence feed - 3 times a day."""
    try:
        chat_id = context.job.data.get("chat_id")
        if not chat_id:
            return

        prompt = (
            "כתוב דוח אינטליגנציה יומי בעברית, חד, מקצועי וקריא.\n"
            "הדוח מיועד למתן. אפשר לפתוח ב'מתן,' אבל בלי שאלות בכלל.\n"
            "\n"
            "פורמט חובה ומדויק:\n"
            "כותרת קצרה עם תאריך ושעה\n"
            "שורת פתיחה אחת: תמונת מצב כללית\n"
            "\n"
            "🇺🇸 שוק ארה״ב\n"
            "- S&P 500: אחוז שינוי + רמה\n"
            "- Nasdaq: אחוז שינוי\n"
            "- Dow Jones: אחוז שינוי\n"
            "- עד 3 אירועים מרכזיים בלבד\n"
            "- שורה אחת: המשמעות כרגע\n"
            "\n"
            "🤖 AI\n"
            "- 3-4 אירועים מרכזיים בלבד\n"
            "- שורה אחת: למה זה חשוב עכשיו\n"
            "\n"
            "סיים בשורת takeaway אחת בלבד שמתחילה ב-'Takeaway:'\n"
            "\n"
            "חוקים:\n"
            "- בלי שאלות למשתמש\n"
            "- בלי ניתוח פסיכולוגי\n"
            "- בלי חפירות\n"
            "- בלי להמציא עובדות\n"
            "- בלי הקדמות מיותרות\n"
            "- מקסימום 200 מילים לכל הדוח\n"
            "- אם אין אירוע מהותי בקטגוריה מסוימת, כתוב בקצרה שהיום היה שקט יחסית\n"
        )

        response = await generate_web(prompt)
        await context.bot.send_message(chat_id=chat_id, text=response)

    except Exception as e:
        print(f"Proactive report job error: {e}")


async def check_breaking_events(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Checks for important breaking US markets / AI events and pushes immediately."""
    try:
        chat_id = context.job.data.get("chat_id")
        if not chat_id:
            return

        prompt = (
            "בדוק אם קרה ממש עכשיו אירוע מהותי באמת שמצדיק התראה מיידית למשתמש.\n"
            "התמקד רק ב-2 תחומים:\n"
            "1. שוקי ארה״ב / מקרו / מדדים / תשואות / נפט / אירוע שוק חריג\n"
            "2. AI - הכרזה גדולה, השקה משמעותית, מימון גדול, רגולציה חשובה, מהלך של OpenAI/Google/Anthropic/Meta/Nvidia\n"
            "\n"
            "שלח התראה רק אם מדובר באירוע חריג ומשמעותי באמת, לא רעש יומי.\n"
            "\n"
            "החזר JSON בלבד בפורמט הזה:\n"
            "{\n"
            "  \"should_send\": true/false,\n"
            "  \"category\": \"markets\" | \"ai\" | \"\",\n"
            "  \"headline\": \"כותרת קצרה בעברית\",\n"
            "  \"summary\": \"2-3 שורות בעברית, חד וברור\",\n"
            "  \"why_it_matters\": \"שורה אחת בעברית\",\n"
            "  \"severity\": \"high\" | \"critical\" | \"\",\n"
            "  \"dedupe_key\": \"מזהה קצר ויציב לאירוע\"\n"
            "}\n"
            "\n"
            "חוקים:\n"
            "- בלי שאלות\n"
            "- בלי טקסט מחוץ ל-JSON\n"
            "- אם אין אירוע חשוב באמת: should_send=false\n"
            "- אל תמציא אירועים. אם לא בטוח: should_send=false\n"
        )

        raw = await generate_web(prompt)
        data = _extract_json_object(raw)
        if not data:
            return

        should_send = bool(data.get("should_send"))
        if not should_send:
            return

        # Only truly important events should be sent
        severity = (data.get("severity") or "").strip().lower()
        if severity not in {"high", "critical"}:
            return

        category = (data.get("category") or "").strip()
        headline = (data.get("headline") or "").strip()
        summary = (data.get("summary") or "").strip()
        why_it_matters = (data.get("why_it_matters") or "").strip()
        severity = severity
        dedupe_key = (
            (data.get("dedupe_key") or "").strip()
            or re.sub(r"\s+", "", headline.lower())[:80]
            or re.sub(r"\s+", "", summary.lower())[:80]
        )

        if not headline or not summary or not dedupe_key:
            return
        if _alert_already_sent(dedupe_key):
            return

        if severity == "critical":
            prefix = "🚨🚨 שוק" if category == "markets" else "🚨🚨 AI" if category == "ai" else "🚨🚨 עדכון"
        else:
            prefix = "🚨 שוק" if category == "markets" else "🚨 AI" if category == "ai" else "🚨 עדכון"

        text = f"{prefix} | {headline}\n\n{summary}"
        if why_it_matters:
            text += f"\n\n🎯 למה זה חשוב:\n{why_it_matters}"

        await context.bot.send_message(chat_id=chat_id, text=text)
        _mark_alert_sent(dedupe_key, category)
        print(f"Breaking alert sent: {category} | {headline}")

    except Exception as e:
        print(f"Breaking events job error: {e}")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("👋 היי! אני בנימין.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    message = update.message.text
    user_id = str(update.effective_user.id) if update.effective_user else "unknown"
    try:
        response = await handler.handle(message, user_id)
        await update.message.reply_text(response)
    except Exception as e:
        print(f"Error: {e}")
        await update.message.reply_text("מצטער, נתקלתי בבעיה. נסה שוב?")



def main() -> None:
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_TOKEN not set in .env")
    if not os.getenv("GEMINI_API_KEY"):
        raise ValueError("GEMINI_API_KEY not set in .env")
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY not set in .env (required for GPT orchestrator)")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise ValueError("ANTHROPIC_API_KEY not set in .env (required for Claude worker)")

    async def _cleanup() -> None:
        bot = Bot(token=token)
        await bot.delete_webhook(drop_pending_updates=True)
        print("⏳ ממתין 10 שניות...")
        await asyncio.sleep(10)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_cleanup())

    app = Application.builder().token(token).build()

    # --- Scheduler setup ---
    tz = ZoneInfo("Asia/Jerusalem")
    default_chat_id = os.getenv("PROACTIVE_CHAT_ID") or "1796609485"

    if default_chat_id:
        report_times = [
            dtime(hour=9, minute=0, tzinfo=tz),
            dtime(hour=15, minute=30, tzinfo=tz),
            dtime(hour=23, minute=50, tzinfo=tz),
        ]

        for idx, report_time in enumerate(report_times, start=1):
            app.job_queue.run_daily(
                send_proactive_report,
                time=report_time,
                data={"chat_id": default_chat_id},
                name=f"proactive_report_{idx}",
            )

        app.job_queue.run_repeating(
            check_breaking_events,
            interval=1800,
            first=120,
            data={"chat_id": default_chat_id},
            name="breaking_events_monitor",
        )

        print("📆 Proactive reports scheduled (09:00 / 15:30 / 23:50 Asia/Jerusalem)")
        print("⚡ Breaking events monitor scheduled (every 30 minutes)")
    else:
        print("⚠️ PROACTIVE_CHAT_ID not set – proactive mode disabled.")

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(TelegramMessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Benjamin bot started (GPT=Brain, Gemini=Worker)")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
