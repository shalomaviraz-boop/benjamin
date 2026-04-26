from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from benjamin_brain import BenjaminBrain
from config import get_settings


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()


def get_brain(context: ContextTypes.DEFAULT_TYPE) -> BenjaminBrain:
    return context.application.bot_data["brain"]


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return

    brain = get_brain(context)
    await brain.ensure_user_profile(str(user.id), user.full_name)
    await message.reply_text(
        "אני בנג'מין.\n"
        "אני זוכר הקשר, לומד לאורך זמן, ומנסה לענות כמו עוזר אישי שחושב באמת.\n"
        "תדבר איתי רגיל."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if not message or not user or not message.text:
        return

    try:
        brain = get_brain(context)
        await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
        response = await brain.reply(
            user_id=str(user.id),
            display_name=user.full_name,
            message_text=message.text,
        )
        await message.reply_text(response)
    except Exception:
        logger.exception("Failed while handling user message")
        await message.reply_text("יש תקלה זמנית. נסה שוב בעוד רגע.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Telegram update failed", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("קרה משהו לא צפוי. נסה שוב בעוד רגע.")
        except Exception:
            logger.exception("Failed to send error recovery message")


def build_application() -> Application:
    settings.validate()
    application = Application.builder().token(settings.telegram_token).concurrent_updates(True).build()
    application.bot_data["brain"] = BenjaminBrain(settings)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    return application


def main() -> None:
    logger.info("Starting Benjamin with model=%s", settings.openai_model)
    application = build_application()
    application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
