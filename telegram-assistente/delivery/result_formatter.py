"""Formata o resultado de um job para entrega no Telegram."""

from pathlib import Path

from jobs.models import Job


def format_message(job: Job) -> str:
    if job.status == "completed":
        return (
            "Seu pedido foi concluído.\n\n"
            f"Job: {job.id}\n"
            "Resultado: disponível"
        )

    return (
        "Não foi possível concluir seu pedido.\n\n"
        f"Job: {job.id}\n"
        f"Tentativas: {job.attempts}\n"
        f"Motivo: {job.error or 'erro durante a execução'}"
    )


def result_file(job: Job) -> Path | None:
    if job.status != "completed" or not job.result:
        return None
    file_path = job.result.get("file")
    if not file_path:
        return None
    path = Path(file_path)
    return path if path.is_file() else None
