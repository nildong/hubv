"""Bootstrap comum aos entrypoints de worker (um por fila)."""

import logging
import socket
import uuid
from pathlib import Path

from agents.executor import SkillDispatchExecutor
from config import load_config
from db.connection import get_connection
from jobs.heartbeat_repository import HeartbeatRepository
from jobs.models import QueueName
from jobs.repository import JobRepository
from skills.registry import SKILL_FUNCTIONS
from workers.base import Worker

BASE_DIR = Path(__file__).resolve().parent.parent


def run_worker(queue: QueueName) -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )

    config = load_config()
    connection = get_connection(config.jobs_db_path)
    repository = JobRepository(connection)
    heartbeat_repository = HeartbeatRepository(connection)
    executor = SkillDispatchExecutor(SKILL_FUNCTIONS)

    worker_id = f"{queue}-{socket.gethostname()}-{uuid.uuid4().hex[:6]}"
    worker = Worker(
        queue=queue,
        worker_id=worker_id,
        repository=repository,
        executor=executor,
        jobs_dir=BASE_DIR / "data" / "jobs",
        poll_interval_ms=config.worker_poll_interval_ms,
        lock_timeout_minutes=config.job_lock_timeout_minutes,
        heartbeat_repository=heartbeat_repository,
    )
    worker.run_forever()
