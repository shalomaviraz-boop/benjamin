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


# --- Breaking Alerts Verification ---

def _normalize_cluster_key(category: str, cluster: str, headline: str) -> str:
    cat = (category or "").strip().lower()
    cl = re.sub(r"\s+", "", (cluster or "").strip().lower())[:80]
    hl = re.sub(r"\s+", "", (headline or "").strip().lower())[:80]
    return f"{cat}:{cl or hl}"


async def _verify_breaking_candidate(raw_candidate: str) -> dict:
    """Second-pass verification gate for breaking alerts."""
    prompt = (
        "אתה שכבת אימות להתראות חדשות. קיבלת טיוטת JSON של אירוע אפשרי.\n"
        "המטרה שלך: להחזיר JSON מאומת בלבד, ולפסול כל דבר לא ודאי, כפול או ספקולטיבי.\n"
        "\n"
        "האירוע לבדיקה:\n"
        f"{raw_candidate}\n"
        "\n"
        "החזר JSON בלבד בפורמט הזה:\n"
        "{\n"
        "  \"should_send\": true/false,\n"
        "  \"category\": \"markets\" | \"ai\" | \"\",\n"
        "  \"headline\": \"כותרת קצרה בעברית\",\n"
        "  \"summary\": \"2-3 שורות בעברית, חד וברור\",\n"
        "  \"why_it_matters\": \"שורה אחת בעברית\",\n"
        "  \"severity\": \"high\" | \"critical\" | \"\",\n"
        "  \"confidence\": 0-100,\n"
        "  \"source_count\": 0-10,\n"
        "  \"event_cluster\": \"תגית קצרה ויציבה לאירוע\",\n"
        "  \"dedupe_key\": \"מזהה קצר ויציב לאירוע\"\n"
        "}\n"
        "\n"
        "כללים קשיחים:\n"
        "- אל תמציא עובדות או חברות או מספרים.\n"
        "- אם אין ודאות גבוהה: should_send=false.\n"
        "- אם נראה שזה אותו אירוע שכבר יכול להישלח שוב בניסוח אחר, החזר event_cluster יציב.\n"
        "- שלח התראה רק אם confidence>=85 וגם source_count>=2.\n"
        "- בלי טקסט מחוץ ל-JSON.\n"
    )
    raw = await generate_web(prompt)
    return _extract_json_object(raw)


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
            "אתר אם קרה ממש עכשיו אירוע חריג ומשמעותי באמת שמצדיק התראה מיידית.\n"
            "התמקד רק ב-2 תחומים:\n"
            "1. שוקי ארה״ב / מקרו / מדדים / תשואות / נפט / אירוע שוק חריג\n"
            "2. AI - הכרזה גדולה, השקה משמעותית, מימון גדול, רגולציה חשובה, מהלך של OpenAI/Google/Anthropic/Meta/Nvidia\n"
            "\n"
            "החזר JSON בלבד בפורמט הזה:\n"
            "{\n"
            "  \"should_send\": true/false,\n"
            "  \"category\": \"markets\" | \"ai\" | \"\",\n"
            "  \"headline\": \"כותרת קצרה בעברית\",\n"
            "  \"summary\": \"2-3 שורות בעברית, חד וברור\",\n"
            "  \"why_it_matters\": \"שורה אחת בעברית\",\n"
            "  \"severity\": \"high\" | \"critical\" | \"\",\n"
            "  \"event_cluster\": \"תגית קצרה ויציבה לאירוע\",\n"
            "  \"dedupe_key\": \"מזהה קצר ויציב לאירוע\"\n"
            "}\n"
            "\n"
            "כללים:\n"
            "- בלי שאלות.\n"
            "- בלי טקסט מחוץ ל-JSON.\n"
            "- אם אין אירוע חשוב באמת: should_send=false.\n"
            "- אל תמציא אירועים. אם לא בטוח: should_send=false.\n"
            "- החזר רק אירוע אחד לכל ריצה: החשוב ביותר כרגע.\n"
        )

        raw_candidate = await generate_web(prompt)
        candidate = _extract_json_object(raw_candidate)
        if not candidate or not bool(candidate.get("should_send")):
            return

        verified = await _verify_breaking_candidate(raw_candidate)
        if not verified or not bool(verified.get("should_send")):
            return

        confidence = int(verified.get("confidence") or 0)
        source_count = int(verified.get("source_count") or 0)
        severity = (verified.get("severity") or "").strip().lower()
        if confidence < 85 or source_count < 2:
            return
        if severity not in {"high", "critical"}:
            return

        category = (verified.get("category") or "").strip()
        headline = (verified.get("headline") or "").strip()
        summary = (verified.get("summary") or "").strip()
        why_it_matters = (verified.get("why_it_matters") or "").strip()
        event_cluster = (verified.get("event_cluster") or "").strip()

        dedupe_key = (
            (verified.get("dedupe_key") or "").strip()
            or _normalize_cluster_key(category, event_cluster, headline)
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
        print(
            f"Breaking alert sent: {category} | {headline} | confidence={confidence} | sources={source_count}"
        )

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
            interval=3600,
            first=120,
            data={"chat_id": default_chat_id},
            name="breaking_events_monitor",
        )

        print("📆 Proactive reports scheduled (09:00 / 15:30 / 23:50 Asia/Jerusalem)")
        print("⚡ Breaking events monitor scheduled (every 60 minutes, with verification gate)")
    else:
        print("⚠️ PROACTIVE_CHAT_ID not set – proactive mode disabled.")

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(TelegramMessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Benjamin bot started (GPT=Brain, Gemini=Worker)")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

registry = AgentRegistry()
registry.register("research", ResearchAgent())
registry.register("breaking", BreakingAgent())
registry.register("quality", QualityAgent())


registry = AgentRegistry()
registry.register("research", ResearchAgent())
registry.register("breaking", BreakingAgent())
registry.register("quality", QualityAgent())
