"""Modelo de dados do job da fila."""

from dataclasses import dataclass, field
from typing import Any, Literal

QueueName = Literal["videos", "textos", "servicos"]

JobStatus = Literal["pending", "running", "completed", "failed", "cancelled"]

DeliveryStatus = Literal["pending", "delivered", "failed"]

QUEUE_NAMES: tuple[QueueName, ...] = ("videos", "textos", "servicos")


@dataclass
class Job:
    id: str
    queue: QueueName
    skill: str
    payload: dict[str, Any]
    user_id: str
    chat_id: str
    status: JobStatus = "pending"
    priority: int = 0
    attempts: int = 0
    max_attempts: int = 3
    source_message_id: str | None = None
    progress: int = 0
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    locked_by: str | None = None
    locked_at: str | None = None
    delivery_status: DeliveryStatus = "pending"
    delivered_at: str | None = None
    delivery_attempts: int = 0
    delivery_error: str | None = None
