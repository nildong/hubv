"""Entrypoint do watcher.

Uso: python -m delivery.run_watcher
"""

import asyncio
import logging

from telegram import Bot

from config import load_config
from db.connection import get_connection
from jobs.repository import JobRepository

from .watcher import Watcher

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)


def main() -> None:
    config = load_config()
    connection = get_connection(config.jobs_db_path)
    repository = JobRepository(connection)
    bot = Bot(token=config.telegram_bot_token)

    watcher = Watcher(bot=bot, repository=repository, poll_interval_ms=config.worker_poll_interval_ms)
    asyncio.run(watcher.run_forever())


if __name__ == "__main__":
    main()
