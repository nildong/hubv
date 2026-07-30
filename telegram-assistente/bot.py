"""Bot Telegram que encaminha mensagens (texto e voz) para o Claude e responde."""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ai_client import ClaudeClient, ClaudeError
from config import load_config
from db.connection import get_connection
from jobs.heartbeat_repository import HeartbeatRepository
from jobs.repository import JobRepository
from messaging import split_message
from router.intent_router import IntentRouter, RouteDecision
from router.skill_registry import SkillRegistry
from transcription import Transcriber, TranscriptionError

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("bot")

QUEUE_LABELS = {"videos": "vídeos", "textos": "textos", "servicos": "serviços"}
STATUS_LABELS = {
    "pending": "aguardando",
    "running": "em execução",
    "completed": "concluído",
    "failed": "falhou",
    "cancelled": "cancelado",
}

config = load_config()
claude_client = ClaudeClient(system_prompt=config.system_prompt, model=config.claude_model)
transcriber = Transcriber(
    api_key=config.groq_api_key,
    model=config.groq_transcribe_model,
    language=config.groq_language,
)

db_connection = get_connection(config.jobs_db_path)
job_repository = JobRepository(db_connection)
heartbeat_repository = HeartbeatRepository(db_connection)
skill_registry = SkillRegistry(config.skills_config_path)
intent_router = IntentRouter(skill_registry, model=config.claude_model)


async def _is_authorized(update: Update) -> bool:
    user = update.effective_user
    if user is None or update.message is None:
        return False

    if config.telegram_allowed_user_id is None:
        logger.warning(
            "TELEGRAM_ALLOWED_USER_ID não configurado. Mensagem de %s (id=%s).",
            user.username or user.full_name,
            user.id,
        )
        await update.message.reply_text(
            "Bot ainda não configurado.\n"
            f"Seu ID do Telegram é: {user.id}\n"
            "Coloque esse valor em TELEGRAM_ALLOWED_USER_ID no .env e reinicie o bot."
        )
        return False

    if user.id != config.telegram_allowed_user_id:
        logger.warning("Mensagem ignorada de usuário não autorizado (id=%s).", user.id)
        return False

    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_authorized(update):
        return
    await update.message.reply_text(
        "Olá! Sou seu assistente pessoal. Envie uma mensagem e eu responderei."
    )


async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_authorized(update):
        return
    await update.message.reply_text(
        "Envie um texto ou um áudio e eu responderei usando o Claude.\n\n"
        "Comandos disponíveis:\n"
        "/start - mensagem inicial\n"
        "/limpar - apaga o histórico da conversa\n"
        "/meusjobs - lista seus últimos pedidos\n"
        "/job <id> - detalhes de um pedido\n"
        "/cancelar <id> - cancela um pedido pendente\n"
        "/filas - status das filas\n"
        "/status - status dos workers (heartbeat)\n"
        "/skills - skills disponíveis\n"
        "/ajuda - mostra esta mensagem"
    )


async def limpar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_authorized(update):
        return
    claude_client.clear(update.effective_user.id)
    await update.message.reply_text("Histórico apagado.")


def _format_job_line(job) -> str:
    return f"{job.id} [{QUEUE_LABELS.get(job.queue, job.queue)}/{job.skill}] {STATUS_LABELS.get(job.status, job.status)}"


async def meusjobs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_authorized(update):
        return
    jobs = job_repository.get_jobs_by_user(str(update.effective_user.id))
    if not jobs:
        await update.message.reply_text("Você ainda não tem pedidos.")
        return
    lines = [_format_job_line(job) for job in jobs]
    await update.message.reply_text("\n".join(lines))


async def job_detalhe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_authorized(update):
        return
    if not context.args:
        await update.message.reply_text("Uso: /job <id>")
        return
    job = job_repository.get_job(context.args[0])
    if job is None or job.user_id != str(update.effective_user.id):
        await update.message.reply_text("Job não encontrado.")
        return
    text = (
        f"Job: {job.id}\n"
        f"Fila: {QUEUE_LABELS.get(job.queue, job.queue)}\n"
        f"Skill: {job.skill}\n"
        f"Status: {STATUS_LABELS.get(job.status, job.status)}\n"
        f"Progresso: {job.progress}%\n"
        f"Tentativas: {job.attempts}/{job.max_attempts}\n"
    )
    if job.error:
        text += f"Erro: {job.error}\n"
    await update.message.reply_text(text)


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_authorized(update):
        return
    if not context.args:
        await update.message.reply_text("Uso: /cancelar <id>")
        return
    ok = job_repository.cancel_job(context.args[0], str(update.effective_user.id))
    if ok:
        await update.message.reply_text("Job cancelado.")
    else:
        await update.message.reply_text("Não foi possível cancelar (job inexistente ou já finalizado).")


async def filas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_authorized(update):
        return
    lines = []
    for queue, label in QUEUE_LABELS.items():
        stats = job_repository.get_queue_stats(queue)
        resumo = ", ".join(f"{STATUS_LABELS.get(s, s)}: {n}" for s, n in stats.items()) or "vazia"
        lines.append(f"{label}: {resumo}")
    await update.message.reply_text("\n".join(lines))


def _queue_has_fresh_heartbeat(queue: str) -> bool:
    cutoff_seconds = config.heartbeat_stale_minutes * 60
    now = datetime.now(timezone.utc)
    for hb in heartbeat_repository.list_all():
        if hb.queue != queue:
            continue
        last_seen = datetime.fromisoformat(hb.last_seen_at)
        if (now - last_seen).total_seconds() <= cutoff_seconds:
            return True
    return False


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_authorized(update):
        return
    heartbeats = heartbeat_repository.list_all()
    if not heartbeats:
        await update.message.reply_text(
            "Nenhum worker reportou heartbeat ainda (podem estar desligados)."
        )
        return
    lines = []
    for hb in heartbeats:
        online = "online" if _queue_has_fresh_heartbeat(hb.queue) else "offline (heartbeat antigo)"
        job_info = f" job atual: {hb.current_job_id}" if hb.current_job_id else ""
        lines.append(f"{hb.worker_id} [{hb.queue}] {online} - {hb.status}{job_info}")
    await update.message.reply_text("\n".join(lines))


async def skills_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_authorized(update):
        return
    enabled = skill_registry.list_enabled()
    if not enabled:
        await update.message.reply_text("Nenhuma skill habilitada no momento.")
        return
    lines = [f"{s.name} ({QUEUE_LABELS.get(s.queue, s.queue)}): {s.description}" for s in enabled]
    await update.message.reply_text("\n".join(lines))


async def _reply_direct(update: Update, user_id: int, text: str) -> None:
    try:
        answer = await asyncio.to_thread(claude_client.ask, user_id, text)
    except ClaudeError as exc:
        logger.error("Erro do Claude: %s", exc)
        await update.message.reply_text(f"Erro ao falar com o Claude: {exc}")
        return

    for chunk in split_message(answer):
        await update.message.reply_text(chunk)


async def _enqueue_job(update: Update, user_id: int, chat_id: int, decision: RouteDecision) -> None:
    worker_online = _queue_has_fresh_heartbeat(decision.queue)
    if not worker_online and not config.accept_jobs_when_worker_offline:
        await update.message.reply_text(
            f"O worker da fila '{QUEUE_LABELS.get(decision.queue, decision.queue)}' "
            "está offline no momento e o sistema está configurado para não aceitar "
            "pedidos nessa condição. Tente novamente mais tarde."
        )
        return

    job = job_repository.create_job(
        queue=decision.queue,
        skill=decision.skill,
        payload=decision.payload,
        user_id=str(user_id),
        chat_id=str(chat_id),
        source_message_id=str(update.message.message_id),
    )
    stats = job_repository.get_queue_stats(decision.queue)
    position = stats.get("pending", 0)

    aviso = "" if worker_online else "\n\n(aviso: nenhum worker dessa fila reportou atividade recentemente)"
    await update.message.reply_text(
        "Seu pedido foi adicionado à fila.\n\n"
        f"Job: {job.id}\n"
        f"Fila: {QUEUE_LABELS.get(decision.queue, decision.queue)}\n"
        f"Skill: {decision.skill}\n"
        "Status: aguardando\n"
        f"Posição aproximada: {position}"
        f"{aviso}"
    )


async def _reply_with_ai(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, text: str
) -> None:
    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    try:
        decision = await asyncio.to_thread(intent_router.route, text)
    except Exception:
        logger.exception("Falha inesperada no roteador de intenção; caindo para resposta direta.")
        await _reply_direct(update, user_id, text)
        return

    if decision.action == "clarify":
        await update.message.reply_text(decision.question)
        return

    if decision.action == "enqueue":
        await _enqueue_job(update, user_id, chat_id, decision)
        return

    await _reply_direct(update, user_id, text)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_authorized(update):
        return
    user = update.effective_user
    await _reply_with_ai(update, context, user.id, update.message.text)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_authorized(update):
        return
    user = update.effective_user
    message = update.message
    voice_or_audio = message.voice or message.audio

    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)

    with TemporaryDirectory() as tmp_dir:
        suffix = ".ogg"
        if message.audio and message.audio.file_name:
            suffix = Path(message.audio.file_name).suffix or ".mp3"
        local_path = Path(tmp_dir) / f"audio{suffix}"

        tg_file = await voice_or_audio.get_file()
        await tg_file.download_to_drive(local_path)

        try:
            text = transcriber.transcribe(local_path)
        except TranscriptionError as exc:
            logger.error("Erro na transcrição: %s", exc)
            await message.reply_text(str(exc))
            return

    await message.reply_text(f"🎙️ {text}")
    await _reply_with_ai(update, context, user.id, text)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Erro não tratado: %s", context.error, exc_info=context.error)


def main() -> None:
    application = Application.builder().token(config.telegram_bot_token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ajuda", ajuda))
    application.add_handler(CommandHandler("limpar", limpar))
    application.add_handler(CommandHandler("meusjobs", meusjobs))
    application.add_handler(CommandHandler("job", job_detalhe))
    application.add_handler(CommandHandler("cancelar", cancelar))
    application.add_handler(CommandHandler("filas", filas))
    application.add_handler(CommandHandler("status", status_cmd))
    application.add_handler(CommandHandler("skills", skills_cmd))
    application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_error_handler(on_error)

    logger.info("Bot iniciado. Aguardando mensagens...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
