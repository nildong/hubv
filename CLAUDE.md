# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

This repo has a single application, `telegram-assistente/`, plus a `doc/` folder with planning notes (`plano_bot_telegram.md`, `prompt_bot_telegram.md`, `inemacabot-versao-simples.md`) that describe the original design intent — check these when a change touches scope/behavior decisions.

## What this is

A personal Telegram bot that relays text/voice messages to the **Claude Code CLI** (the user's Pro/Max subscription, invoked as a subprocess — no `ANTHROPIC_API_KEY` involved) and replies in the chat. Voice messages are transcribed first via the **Groq** Whisper API.

## Commands

```bash
cd telegram-assistente
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # then fill in TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_ID, GROQ_API_KEY

claude login            # once per machine — authenticates the CLI the bot shells out to

python bot.py            # run the bot (long-polling)
```

There is no test suite, linter, or build step in this repo.

## Architecture

- **`bot.py`** — Telegram handlers (`python-telegram-bot`, long polling). Every handler first calls `_is_authorized()`, which gates all activity on a single `TELEGRAM_ALLOWED_USER_ID`; if unset, the bot replies with the sender's ID instead of acting ("discovery mode") and does nothing else. Long replies are split on `TELEGRAM_MAX_LENGTH` (4096) at newline/space boundaries via `split_message()`.
- **`ai_client.py`** — `ClaudeClient.ask()` shells out to `claude -p <message> --output-format json --tools "" --system-prompt <prompt>`, parses the JSON result, and raises `ClaudeError` on failure/timeout (`CLAUDE_TIMEOUT_SECONDS = 120`). Tools are explicitly disabled (`--tools ""`) — this is a conversation-only assistant, not an agent that can act. Conversation continuity is per-Telegram-`user_id`, implemented by caching the Claude session id in `self._sessions` and passing `--resume <session_id>` on subsequent calls. This map is in-memory only — restarting the bot loses all sessions. `/limpar` clears a user's cached session id.
- **`transcription.py`** — thin wrapper around the Groq SDK for voice-to-text.
- **`config.py`** — loads and validates `.env` via `python-dotenv`; fails fast (raises) if `TELEGRAM_BOT_TOKEN` or `GROQ_API_KEY` is missing. Also loads `system_prompt.txt` (path configurable via `SYSTEM_PROMPT_FILE`) as the system prompt passed to Claude on every call.
- **`system_prompt.txt`** — editable system prompt; change assistant tone/rules here without touching code.

## Key constraints to preserve

- The bot must remain single-user: don't remove or weaken the `_is_authorized` check.
- Tools stay disabled (`--tools ""`) in `ai_client.py` unless the user explicitly asks to turn this into an agentic bot — the whole design (see `doc/`) is intentionally "conversation only, no external actions, no sub-agents."
- The `claude` CLI must be logged in (`claude login`) on whatever machine runs the bot; there's no API-key fallback path in this codebase.
