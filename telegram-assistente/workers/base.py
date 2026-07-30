"""Worker genérico: consome uma única fila, um job por vez.

Fluxo por iteração: captura atômica do próximo job pendente -> pasta isolada
-> executa a skill via AgentExecutor -> salva resultado -> completed/failed.
Não sabe nada sobre Telegram; a entrega é responsabilidade do watcher.
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from agents.executor import AgentExecutor
from jobs.heartbeat_repository import HeartbeatRepository
from jobs.models import Job, QueueName
from jobs.repository import JobRepository

logger = logging.getLogger(__name__)


class Worker:
    def __init__(
        self,
        queue: QueueName,
        worker_id: str,
        repository: JobRepository,
        executor: AgentExecutor,
        jobs_dir: Path,
        poll_interval_ms: int = 3000,
        lock_timeout_minutes: int = 30,
        heartbeat_repository: HeartbeatRepository | None = None,
    ):
        self.queue = queue
        self.worker_id = worker_id
        self.repository = repository
        self.executor = executor
        self.jobs_dir = jobs_dir
        self.poll_interval_seconds = poll_interval_ms / 1000
        self.lock_timeout_minutes = lock_timeout_minutes
        self.heartbeat_repository = heartbeat_repository
        self.started_at = datetime.now(timezone.utc).isoformat()

    def _beat(self, status: str, current_job_id: str | None = None) -> None:
        if self.heartbeat_repository is None:
            return
        self.heartbeat_repository.upsert(
            worker_id=self.worker_id,
            queue=self.queue,
            status=status,
            current_job_id=current_job_id,
            started_at=self.started_at,
        )

    def recover_stale_locks(self) -> None:
        released = self.repository.release_expired_locks(self.lock_timeout_minutes)
        if released:
            logger.warning(
                "worker=%s queue=%s recuperou %d job(s) com lock expirado",
                self.worker_id,
                self.queue,
                released,
            )

    def run_forever(self) -> None:
        self.recover_stale_locks()
        self._beat("idle")
        logger.info("worker=%s queue=%s iniciado", self.worker_id, self.queue)
        while True:
            job = self.repository.claim_next_job(self.queue, self.worker_id)
            if job is None:
                self._beat("idle")
                time.sleep(self.poll_interval_seconds)
                continue
            self._run_job(job)

    def _run_job(self, job: Job) -> None:
        self._beat("running", current_job_id=job.id)
        started = time.monotonic()
        working_dir = self.jobs_dir / job.id
        (working_dir / "files").mkdir(parents=True, exist_ok=True)
        (working_dir / "input.json").write_text(
            json.dumps(job.payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        logger.info(
            "job_id=%s queue=%s skill=%s worker_id=%s status=running attempt=%d",
            job.id,
            job.queue,
            job.skill,
            self.worker_id,
            job.attempts,
        )

        result = self.executor.execute(
            job_id=job.id,
            skill=job.skill,
            payload=job.payload,
            working_directory=working_dir,
        )

        duration = time.monotonic() - started

        if result.success:
            (working_dir / "output.json").write_text(
                json.dumps(result.result or {}, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            self.repository.complete_job(job.id, result.result or {})
            logger.info(
                "job_id=%s queue=%s skill=%s worker_id=%s status=completed attempt=%d duration=%.2fs",
                job.id,
                job.queue,
                job.skill,
                self.worker_id,
                job.attempts,
                duration,
            )
        else:
            retry = job.attempts < job.max_attempts
            self.repository.fail_job(job.id, result.error or "erro desconhecido", retry=retry)
            logger.error(
                "job_id=%s queue=%s skill=%s worker_id=%s status=%s attempt=%d duration=%.2fs error=%s",
                job.id,
                job.queue,
                job.skill,
                self.worker_id,
                "pending(retry)" if retry else "failed",
                job.attempts,
                duration,
                result.error,
            )
