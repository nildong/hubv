"""Repositório de jobs sobre SQLite.

`claim_next_job` é a única operação que precisa ser atômica: dois workers da
mesma fila nunca podem capturar o mesmo job. Isso é garantido com uma
transação `BEGIN IMMEDIATE`, que adquire o lock de escrita do SQLite antes de
ler o próximo job pendente.

A implantação prevista roda cada worker em seu próprio processo (um
`Connection` por processo), então a concorrência real de captura acontece
via lock de arquivo do SQLite. Ainda assim, o objeto `sqlite3.Connection`
guarda o estado da transação em si mesmo, não por thread: se a mesma
`Connection` for usada por múltiplas threads (ex.: testes ou um único
processo rodando vários workers), duas transações podem se entrelaçar e
corromper esse estado. O lock abaixo serializa `claim_next_job` dentro do
processo para eliminar esse risco, sem enfraquecer a atomicidade entre
processos (que já é garantida pelo SQLite).
"""

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jobs.models import Job, QueueName


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        queue=row["queue"],
        skill=row["skill"],
        payload=json.loads(row["payload"]),
        user_id=row["user_id"],
        chat_id=row["chat_id"],
        status=row["status"],
        priority=row["priority"],
        attempts=row["attempts"],
        max_attempts=row["max_attempts"],
        source_message_id=row["source_message_id"],
        progress=row["progress"],
        result=json.loads(row["result"]) if row["result"] else None,
        error=row["error"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        locked_by=row["locked_by"],
        locked_at=row["locked_at"],
        delivery_status=row["delivery_status"],
        delivered_at=row["delivered_at"],
        delivery_attempts=row["delivery_attempts"],
        delivery_error=row["delivery_error"],
    )


class JobRepository:
    def __init__(self, connection: sqlite3.Connection):
        self._conn = connection
        self._claim_lock = threading.Lock()

    def create_job(
        self,
        queue: QueueName,
        skill: str,
        payload: dict[str, Any],
        user_id: str,
        chat_id: str,
        priority: int = 0,
        max_attempts: int = 3,
        source_message_id: str | None = None,
    ) -> Job:
        job = Job(
            id=f"job_{uuid.uuid4().hex[:20]}",
            queue=queue,
            skill=skill,
            payload=payload,
            user_id=user_id,
            chat_id=chat_id,
            priority=priority,
            max_attempts=max_attempts,
            source_message_id=source_message_id,
            created_at=_now(),
        )
        self._conn.execute(
            """
            INSERT INTO jobs (
                id, queue, skill, payload, status, priority, attempts,
                max_attempts, user_id, chat_id, source_message_id,
                progress, created_at, delivery_status, delivery_attempts
            ) VALUES (?, ?, ?, ?, 'pending', ?, 0, ?, ?, ?, ?, 0, ?, 'pending', 0)
            """,
            (
                job.id,
                job.queue,
                job.skill,
                json.dumps(job.payload, ensure_ascii=False),
                job.priority,
                job.max_attempts,
                job.user_id,
                job.chat_id,
                job.source_message_id,
                job.created_at,
            ),
        )
        return job

    def get_job(self, job_id: str) -> Job | None:
        row = self._conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _row_to_job(row) if row else None

    def get_jobs_by_user(self, user_id: str, limit: int = 20) -> list[Job]:
        rows = self._conn.execute(
            "SELECT * FROM jobs WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [_row_to_job(row) for row in rows]

    def claim_next_job(self, queue: QueueName, worker_id: str) -> Job | None:
        """Captura atomicamente o próximo job pendente da fila, se houver."""
        with self._claim_lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    """
                    SELECT * FROM jobs
                    WHERE queue = ? AND status = 'pending'
                    ORDER BY priority DESC, created_at ASC
                    LIMIT 1
                    """,
                    (queue,),
                ).fetchone()
                if row is None:
                    self._conn.execute("COMMIT")
                    return None

                now = _now()
                self._conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'running',
                        attempts = attempts + 1,
                        started_at = ?,
                        locked_by = ?,
                        locked_at = ?
                    WHERE id = ?
                    """,
                    (now, worker_id, now, row["id"]),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

        return self.get_job(row["id"])

    def update_job_progress(self, job_id: str, progress: int) -> None:
        self._conn.execute(
            "UPDATE jobs SET progress = ? WHERE id = ?", (progress, job_id)
        )

    def complete_job(self, job_id: str, result: dict[str, Any]) -> None:
        self._conn.execute(
            """
            UPDATE jobs
            SET status = 'completed', progress = 100, result = ?, completed_at = ?,
                locked_by = NULL, locked_at = NULL
            WHERE id = ?
            """,
            (json.dumps(result, ensure_ascii=False), _now(), job_id),
        )

    def fail_job(self, job_id: str, error: str, retry: bool) -> None:
        job = self.get_job(job_id)
        if job is None:
            return

        if retry and job.attempts < job.max_attempts:
            self._conn.execute(
                """
                UPDATE jobs
                SET status = 'pending', error = ?, locked_by = NULL, locked_at = NULL
                WHERE id = ?
                """,
                (error, job_id),
            )
        else:
            self._conn.execute(
                """
                UPDATE jobs
                SET status = 'failed', error = ?, completed_at = ?,
                    locked_by = NULL, locked_at = NULL
                WHERE id = ?
                """,
                (error, _now(), job_id),
            )

    def cancel_job(self, job_id: str, user_id: str) -> bool:
        cursor = self._conn.execute(
            """
            UPDATE jobs SET status = 'cancelled', completed_at = ?
            WHERE id = ? AND user_id = ? AND status IN ('pending', 'running')
            """,
            (_now(), job_id, user_id),
        )
        return cursor.rowcount > 0

    def retry_job(self, job_id: str, user_id: str) -> bool:
        cursor = self._conn.execute(
            """
            UPDATE jobs
            SET status = 'pending', attempts = 0, error = NULL,
                locked_by = NULL, locked_at = NULL,
                delivery_status = 'pending', delivered_at = NULL
            WHERE id = ? AND user_id = ? AND status IN ('failed', 'cancelled')
            """,
            (job_id, user_id),
        )
        return cursor.rowcount > 0

    def release_expired_locks(self, timeout_minutes: int) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)).isoformat()
        cursor = self._conn.execute(
            """
            UPDATE jobs
            SET status = 'pending', locked_by = NULL, locked_at = NULL
            WHERE status = 'running' AND locked_at < ?
            """,
            (cutoff,),
        )
        return cursor.rowcount

    def get_queue_stats(self, queue: QueueName) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT status, COUNT(*) as n FROM jobs WHERE queue = ? GROUP BY status",
            (queue,),
        ).fetchall()
        return {row["status"]: row["n"] for row in rows}

    def get_undelivered_jobs(self) -> list[Job]:
        rows = self._conn.execute(
            """
            SELECT * FROM jobs
            WHERE status IN ('completed', 'failed') AND delivery_status = 'pending'
            ORDER BY completed_at ASC
            """
        ).fetchall()
        return [_row_to_job(row) for row in rows]

    def mark_delivered(self, job_id: str) -> None:
        self._conn.execute(
            """
            UPDATE jobs SET delivery_status = 'delivered', delivered_at = ?
            WHERE id = ?
            """,
            (_now(), job_id),
        )

    def mark_delivery_failed(self, job_id: str, error: str) -> None:
        self._conn.execute(
            """
            UPDATE jobs
            SET delivery_attempts = delivery_attempts + 1, delivery_error = ?
            WHERE id = ?
            """,
            (error, job_id),
        )
