"""Helpers de formatação de mensagem compartilhados entre bot, workers e watcher."""

TELEGRAM_MAX_LENGTH = 4096


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
