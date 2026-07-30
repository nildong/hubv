"""Heartbeat de workers: permite ao bot/operador saber se cada fila está sendo
atendida (Etapa 18 do plano de filas), sem acoplar o bot ao ciclo de vida dos
workers — o bot continua funcionando normalmente mesmo sem nenhum heartbeat
recente (ver `ACCEPT_JOBS_WHEN_WORKER_OFFLINE`)."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class WorkerHeartbeat:
    worker_id: str
    queue: str
    status: str
    current_job_id: str | None
    started_at: str
    last_seen_at: str


class HeartbeatRepository:
    def __init__(self, connection: sqlite3.Connection):
        self._conn = connection

    def upsert(
        self,
        worker_id: str,
        queue: str,
        status: str,
        current_job_id: str | None,
        started_at: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO worker_heartbeats (worker_id, queue, status, current_job_id, started_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(worker_id) DO UPDATE SET
                status = excluded.status,
                current_job_id = excluded.current_job_id,
                last_seen_at = excluded.last_seen_at
            """,
            (worker_id, queue, status, current_job_id, started_at, _now()),
        )

    def list_all(self) -> list[WorkerHeartbeat]:
        rows = self._conn.execute(
            "SELECT * FROM worker_heartbeats ORDER BY queue, worker_id"
        ).fetchall()
        return [
            WorkerHeartbeat(
                worker_id=row["worker_id"],
                queue=row["queue"],
                status=row["status"],
                current_job_id=row["current_job_id"],
                started_at=row["started_at"],
                last_seen_at=row["last_seen_at"],
            )
            for row in rows
        ]
