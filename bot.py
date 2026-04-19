"""Benjamin - GPT Orchestrator + Gemini Execution."""
import asyncio
import os

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
from memory.memory_store import seed_user_core_profile

# --- Proactive jobs ---
from datetime import time as dtime
from zoneinfo import ZoneInfo

from agents.registry import registry

handler = BenjaminMessageHandler()


# --- Proactive Daily Jobs ---

async def send_us_market_summary(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Legacy wrapper kept for compatibility."""
    await send_proactive_report(context)


async def send_ai_summary(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Legacy wrapper kept for compatibility."""
    await send_proactive_report(context)


async def send_proactive_report(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scheduled intelligence feed - 2 times a day."""
    chat_id = context.job.data.get("chat_id") if context.job and context.job.data else None
    if chat_id:
        seed_user_core_profile(str(chat_id))
    await registry.get("research").run_proactive_report(
        context,
        registry.get("quality"),
    )


async def check_breaking_events(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Checks for important global breaking events and pushes immediately."""
    chat_id = context.job.data.get("chat_id") if context.job and context.job.data else None
    if chat_id:
        seed_user_core_profile(str(chat_id))
    await registry.get("breaking").run_check(
        context,
        registry.get("quality"),
        registry.get("priority"),
        registry.get("memory"),
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("👋 היי! אני בנימין.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    print("BENJAMIN ENTRY ACTIVE")
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
    print(f"Runtime entry file: {__file__}")

    # --- Scheduler setup ---
    tz = ZoneInfo("Asia/Jerusalem")
    default_chat_id = os.getenv("PROACTIVE_CHAT_ID") or "1796609485"

    if default_chat_id:
        report_times = [
            dtime(hour=2, minute=0, tzinfo=tz),
            dtime(hour=17, minute=0, tzinfo=tz),
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

        print("📆 Proactive reports scheduled (02:00 / 17:00 Asia/Jerusalem)")
        print("⚡ Breaking events monitor scheduled (every 60 minutes, strict verification + cluster cooldown)")
    else:
        print("⚠️ PROACTIVE_CHAT_ID not set – proactive mode disabled.")

    app.add_handler(CommandHandler("start", start_command))
    text_handler = TelegramMessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    app.add_handler(text_handler)
    print("Registered update handlers: /start + TEXT(non-command) (single text handler)")

    print("🤖 Benjamin bot started (GPT=Brain, Gemini=Worker)")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
