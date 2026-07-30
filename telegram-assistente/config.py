"""Carrega e valida a configuração do bot a partir de variáveis de ambiente."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


def _get_int_or_none(value: str | None) -> int | None:
    if value is None or value.strip() == "":
        return None
    return int(value)


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    telegram_allowed_user_id: int | None
    groq_api_key: str
    groq_transcribe_model: str
    groq_language: str | None
    claude_model: str | None
    system_prompt: str


def load_config() -> Config:
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN não configurado no .env")

    groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not groq_api_key:
        raise RuntimeError("GROQ_API_KEY não configurado no .env")

    system_prompt_file = os.getenv("SYSTEM_PROMPT_FILE", "system_prompt.txt").strip()
    system_prompt_path = Path(system_prompt_file)
    if not system_prompt_path.is_absolute():
        system_prompt_path = BASE_DIR / system_prompt_path
    system_prompt = system_prompt_path.read_text(encoding="utf-8").strip()

    return Config(
        telegram_bot_token=telegram_bot_token,
        telegram_allowed_user_id=_get_int_or_none(os.getenv("TELEGRAM_ALLOWED_USER_ID")),
        groq_api_key=groq_api_key,
        groq_transcribe_model=os.getenv("GROQ_TRANSCRIBE_MODEL", "whisper-large-v3").strip(),
        groq_language=(os.getenv("GROQ_LANGUAGE", "").strip() or None),
        claude_model=(os.getenv("CLAUDE_MODEL", "").strip() or None),
        system_prompt=system_prompt,
    )
