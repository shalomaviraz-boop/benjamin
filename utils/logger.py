"""Logging configuration for Benjamin."""
import logging
import os

# Ensure logs directory exists
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "benjamin.log")),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("benjamin")


def log_pipeline(pipeline: str, message: str, result: bool) -> None:
    """Log pipeline execution."""
    msg_preview = message[:50] + "..." if len(message) > 50 else message
    logger.info(f"Pipeline: {pipeline} | Message: {msg_preview} | Success: {bool(result)}")
