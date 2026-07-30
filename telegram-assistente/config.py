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
    jobs_db_path: str
    skills_config_path: str
    worker_poll_interval_ms: int
    job_lock_timeout_minutes: int
    heartbeat_stale_minutes: int
    accept_jobs_when_worker_offline: bool


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
        jobs_db_path=os.getenv("JOBS_DB_PATH", "data/jobs.db").strip(),
        skills_config_path=os.getenv("SKILLS_CONFIG_PATH", "config/skills.json").strip(),
        worker_poll_interval_ms=int(os.getenv("WORKER_POLL_INTERVAL_MS", "3000")),
        job_lock_timeout_minutes=int(os.getenv("JOB_LOCK_TIMEOUT_MINUTES", "30")),
        heartbeat_stale_minutes=int(os.getenv("HEARTBEAT_STALE_MINUTES", "2")),
        accept_jobs_when_worker_offline=os.getenv(
            "ACCEPT_JOBS_WHEN_WORKER_OFFLINE", "true"
        ).strip().lower()
        not in ("false", "0", "no"),
    )
