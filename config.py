from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    openai_api_key: str
    openai_model: str
    openai_analysis_model: str
    openai_timeout_seconds: float
    database_path: Path
    bot_name: str
    default_user_name: str
    default_user_language: str
    recent_conversation_limit: int
    relevant_memory_limit: int
    max_memories_to_scan: int
    primary_user_id: str
    single_user_mode: bool

    def validate(self) -> None:
        missing = []
        if not self.telegram_token:
            missing.append("TELEGRAM_TOKEN")
        if not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    single_user_mode_value = os.getenv("BENJAMIN_SINGLE_USER_MODE", "true").strip().casefold()
    return Settings(
        telegram_token=os.getenv("TELEGRAM_TOKEN", "").strip(),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.5").strip(),
        openai_analysis_model=os.getenv("OPENAI_ANALYSIS_MODEL", "").strip() or os.getenv("OPENAI_MODEL", "gpt-5.5").strip(),
        openai_timeout_seconds=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "60")),
        database_path=Path(os.getenv("DATABASE_PATH", BASE_DIR / "benjamin_memory.db")).expanduser(),
        bot_name=os.getenv("BOT_NAME", "Benjamin").strip(),
        default_user_name=os.getenv("DEFAULT_USER_NAME", "מתן").strip(),
        default_user_language=os.getenv("DEFAULT_USER_LANGUAGE", "he").strip(),
        recent_conversation_limit=int(os.getenv("RECENT_CONVERSATION_LIMIT", "10")),
        relevant_memory_limit=int(os.getenv("RELEVANT_MEMORY_LIMIT", "8")),
        max_memories_to_scan=int(os.getenv("MAX_MEMORIES_TO_SCAN", "250")),
        primary_user_id=os.getenv("PRIMARY_USER_ID", "Matan primary user").strip(),
        single_user_mode=single_user_mode_value in {"1", "true", "yes", "on"},
    )
