"""Benjamin - Telegram assistant (reactive only)."""
import asyncio, os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, MessageHandler as TelegramMessageHandler, filters, ContextTypes
from handlers.message_handler import BenjaminMessageHandler

handler = BenjaminMessageHandler()

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
        await update.message.reply_text("מצטער, הייתה תקלה זמנית. נסה שוב.")

def main() -> None:
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_TOKEN not set in .env")

    async def _cleanup() -> None:
        bot = Bot(token=token)
        await bot.delete_webhook(drop_pending_updates=True)
        await asyncio.sleep(2)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_cleanup())

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(TelegramMessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Benjamin started in reactive mode (no proactive alerts)")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
