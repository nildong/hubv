"""Watcher: entrega jobs concluídos/com erro ao usuário no Telegram.

Só considera jobs com `delivery_status='pending'`, e marca como entregue
somente após o envio ter sucesso — reiniciar o watcher não reenvia jobs
já marcados como `delivered`.
"""

import asyncio
import logging

from telegram import Bot
from telegram.error import TelegramError

from jobs.models import Job
from jobs.repository import JobRepository

from .result_formatter import format_message, result_file

logger = logging.getLogger(__name__)


class Watcher:
    def __init__(self, bot: Bot, repository: JobRepository, poll_interval_ms: int = 3000):
        self.bot = bot
        self.repository = repository
        self.poll_interval_seconds = poll_interval_ms / 1000

    async def run_forever(self) -> None:
        logger.info("watcher iniciado")
        while True:
            for job in self.repository.get_undelivered_jobs():
                await self._deliver(job)
            await asyncio.sleep(self.poll_interval_seconds)

    async def _deliver(self, job: Job) -> None:
        try:
            await self.bot.send_message(chat_id=int(job.chat_id), text=format_message(job))

            file_path = result_file(job)
            if file_path is not None:
                with file_path.open("rb") as file_obj:
                    await self.bot.send_document(chat_id=int(job.chat_id), document=file_obj)

            self.repository.mark_delivered(job.id)
            logger.info("job_id=%s status=%s delivery=delivered", job.id, job.status)
        except TelegramError as exc:
            self.repository.mark_delivery_failed(job.id, str(exc))
            logger.error("job_id=%s delivery=failed error=%s", job.id, exc)
