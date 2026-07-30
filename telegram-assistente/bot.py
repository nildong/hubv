"""Bot Telegram que encaminha mensagens (texto e voz) para o Claude e responde."""

import logging
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
from transcription import Transcriber, TranscriptionError

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("bot")

TELEGRAM_MAX_LENGTH = 4096

config = load_config()
claude_client = ClaudeClient(system_prompt=config.system_prompt, model=config.claude_model)
transcriber = Transcriber(
    api_key=config.groq_api_key,
    model=config.groq_transcribe_model,
    language=config.groq_language,
)


def split_message(text: str, limit: int = TELEGRAM_MAX_LENGTH) -> list[str]:
    """Divide uma mensagem longa em pedaços que cabem no limite do Telegram."""
    if len(text) <= limit:
        return [text]

    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        cut = remaining.rfind("\n", 0, limit)
        if cut == -1:
            cut = remaining.rfind(" ", 0, limit)
        if cut == -1:
            cut = limit
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip()
    return chunks


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
        "/ajuda - mostra esta mensagem"
    )


async def limpar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_authorized(update):
        return
    claude_client.clear(update.effective_user.id)
    await update.message.reply_text("Histórico apagado.")


async def _reply_with_ai(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, text: str
) -> None:
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )
    try:
        answer = claude_client.ask(user_id, text)
    except ClaudeError as exc:
        logger.error("Erro do Claude: %s", exc)
        await update.message.reply_text(f"Erro ao falar com o Claude: {exc}")
        return

    for chunk in split_message(answer):
        await update.message.reply_text(chunk)


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
    application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_error_handler(on_error)

    logger.info("Bot iniciado. Aguardando mensagens...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
