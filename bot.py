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

# --- Proactive job imports ---
from datetime import time as dtime
from zoneinfo import ZoneInfo

handler = BenjaminMessageHandler()


# --- Proactive Daily Jobs ---

async def send_us_market_summary(context: ContextTypes.DEFAULT_TYPE) -> None:
    """01:00 Israel time – US markets + major economic events."""
    try:
        chat_id = context.job.data.get("chat_id")
        if not chat_id:
            return

        prompt = (
            "תן סיכום תמציתי של האירועים הכלכליים המרכזיים שקרו היום בארה\"ב "
            "כולל שינויי אחוזים במדדים: S&P 500, Nasdaq, Dow Jones. "
            "תשובה קצרה וברורה בעברית."
        )

        response = await handler.handle(prompt, str(chat_id))
        await context.bot.send_message(chat_id=chat_id, text=response)

    except Exception as e:
        print(f"US summary job error: {e}")


async def send_ai_summary(context: ContextTypes.DEFAULT_TYPE) -> None:
    """01:10 Israel time – AI news summary."""
    try:
        chat_id = context.job.data.get("chat_id")
        if not chat_id:
            return

        prompt = (
            "תן סיכום תמציתי של האירועים המרכזיים שקרו היום בתחום הבינה המלאכותית "
            "בעולם. תשובה קצרה וברורה בעברית."
        )

        response = await handler.handle(prompt, str(chat_id))
        await context.bot.send_message(chat_id=chat_id, text=response)

    except Exception as e:
        print(f"AI summary job error: {e}")


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

    # IMPORTANT:
    # Replace this with your own Telegram user ID if needed
    default_chat_id = os.getenv("PROACTIVE_CHAT_ID") or "1796609485"

    if default_chat_id:
        app.job_queue.run_daily(
            send_us_market_summary,
            time=dtime(hour=1, minute=0, tzinfo=tz),
            data={"chat_id": default_chat_id},
            name="us_market_summary",
        )

        app.job_queue.run_daily(
            send_ai_summary,
            time=dtime(hour=1, minute=10, tzinfo=tz),
            data={"chat_id": default_chat_id},
            name="ai_summary",
        )

        print("📆 Proactive jobs scheduled (01:00 + 01:10 Asia/Jerusalem)")
    else:
        print("⚠️ PROACTIVE_CHAT_ID not set – proactive mode disabled.")

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(TelegramMessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Benjamin bot started (GPT=Brain, Gemini=Worker)")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
