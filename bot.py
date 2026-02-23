"""Benjamin - Personal Assistant Bot. Main entry point."""
import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))  # Before imports that need env

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler as TelegramMessageHandler,
    filters,
    ContextTypes,
)

from handlers.message_handler import BenjaminMessageHandler

handler = BenjaminMessageHandler()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    await update.message.reply_text("👋 היי! אני בנימין, העוזר האישי שלך.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages."""
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
    """Run the bot."""
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_TOKEN not set. Copy .env.example to .env and add your token.")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(TelegramMessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Benjamin bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
