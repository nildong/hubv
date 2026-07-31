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

python bot.py                        # the bot itself (long-polling) — always required
python -m workers.run_service_worker # worker for the "servicos" queue
python -m workers.run_video_worker   # worker for the "videos" queue
python -m workers.run_text_worker    # worker for the "textos" queue
python -m delivery.run_watcher       # delivers finished job results back to the user
```

The bot works standalone (direct conversation) even with no worker/watcher running — job-based requests just sit `pending` until a worker picks them up. There is no linter or build step in this repo; ad-hoc functional checks live in the doc under `doc/plano_filas_analise.md`, there's no pytest suite yet.

## Architecture

### Direct conversation (Rota A — unchanged from before the queue system)

- **`bot.py`** — Telegram handlers (`python-telegram-bot`, long polling). Every handler first calls `_is_authorized()`, which gates all activity on a single `TELEGRAM_ALLOWED_USER_ID`; if unset, the bot replies with the sender's ID instead of acting ("discovery mode") and does nothing else. Long replies are split on `TELEGRAM_MAX_LENGTH` (4096) at newline/space boundaries via `messaging.split_message()`.
- **`ai_client.py`** — `ClaudeClient.ask()` shells out to `claude -p <message> --output-format json --tools "" --system-prompt <prompt>`, parses the JSON result, and raises `ClaudeError` on failure/timeout (`CLAUDE_TIMEOUT_SECONDS = 120`). Tools are explicitly disabled (`--tools ""`) — this is a conversation-only assistant, not an agent that can act. Conversation continuity is per-Telegram-`user_id`, implemented by caching the Claude session id in `self._sessions` and passing `--resume <session_id>` on subsequent calls. This map is in-memory only — restarting the bot loses all sessions. `/limpar` clears a user's cached session id.
- **`transcription.py`** — thin wrapper around the Groq SDK for voice-to-text.
- **`config.py`** — loads and validates `.env` via `python-dotenv`; fails fast (raises) if `TELEGRAM_BOT_TOKEN` or `GROQ_API_KEY` is missing. Also loads `system_prompt.txt` (path configurable via `SYSTEM_PROMPT_FILE`).
- **`system_prompt.txt`** — editable system prompt; change assistant tone/rules here without touching code.

### Queue system (Rota B — jobs/workers/skills/watcher)

Every incoming message is first classified by `router/intent_router.py` (`IntentRouter.route()`, a standalone Claude CLI call, no session resume) into `reply` / `clarify` / `enqueue`. `reply` falls through to the direct conversation path above unchanged; `clarify` asks the user a follow-up question; `enqueue` creates a job.

- **`db/schema.sql`, `db/connection.py`** — single SQLite file (`JOBS_DB_PATH`, default `data/jobs.db`), WAL mode, migration applied idempotently on connect. Tables: `jobs`, `worker_heartbeats`.
- **`jobs/models.py`** — `Job` dataclass; queues are `videos` / `textos` / `servicos`; statuses `pending` → `running` → `completed`/`failed`/`cancelled`.
- **`jobs/repository.py`** — `JobRepository`. `claim_next_job()` is the only operation that must be atomic (two workers must never grab the same job): it uses a `BEGIN IMMEDIATE` transaction, additionally serialized by an in-process `threading.Lock` because a single `sqlite3.Connection` corrupts its transaction state if used from multiple threads concurrently (found and fixed via a real concurrency test — see the lock's docstring). Cross-process concurrency (the actual worker deployment) is safe via SQLite's own file locking.
- **`jobs/heartbeat_repository.py`** — `worker_heartbeats` upserts; workers beat on every idle poll and on job start so `/status` can show which queues are actually being served.
- **`router/skill_registry.py`** — loads `config/skills.json`, validates a skill exists/is enabled/has its required payload fields before a job is ever created. The router must never invent a skill.
- **`router/intent_router.py`** — builds the classification prompt from the skill registry, validates the model's JSON output against the expected schema, retries once on invalid output, then falls back to `clarify` rather than creating an incomplete job.
- **`agents/executor.py`** — `AgentExecutor` protocol + `SkillDispatchExecutor`, which maps a skill name to a plain Python function (`skills/registry.py` → `SKILL_FUNCTIONS`). This is the seam for swapping in a real Claude-CLI-based executor (with tools enabled) later without touching `workers/base.py`.
- **`skills/*.py`** — one module per skill. `teste_fila.py`, `roteiro.py`, `video_explicativo.py` are placeholders (`time.sleep()` + write a file to `files/`) that prove the pipeline works end-to-end. `transcricao_video.py` (queue `textos`) is real: downloads audio from a URL via `yt-dlp` (spawned with a list of args, never a shell string) into the job's `files/`, then transcribes it with the existing Groq `Transcriber`. `criacao_site_blog.py` (queue `servicos`) is also real: spawns the `claude` CLI with `--permission-mode acceptEdits` (tools enabled, unlike `ai_client.py`'s conversation path) with `cwd` pinned to the job's `files/` dir so its write access is scoped to that job, then zips the result into `site.zip` for the watcher to deliver.
- **`workers/base.py`** — `Worker`: on start, releases locks held longer than `JOB_LOCK_TIMEOUT_MINUTES` (crash recovery), then polls its single queue, claims one job at a time (concurrency 1 per queue), creates `data/jobs/<job_id>/{input.json,output.json,files/}`, runs the skill via the executor, marks `completed`/retries/`failed`, beats its heartbeat throughout.
- **`workers/runner.py`, `workers/run_{service,video,text}_worker.py`** — one process per queue; all three can run in parallel (verified: 3 queues finish in the time of the slowest single job, not the sum).
- **`delivery/watcher.py`, `delivery/run_watcher.py`, `delivery/result_formatter.py`** — separate process; polls jobs with `status in (completed, failed) and delivery_status='pending'`, sends the formatted result (and the result file, if any) via `telegram.Bot`, marks `delivered` only on send success — restarting the watcher never re-delivers an already-delivered job.
- **`messaging.py`** — `split_message()`, shared by `bot.py` and the watcher.

### Full flow reference

See `doc/ngmastercabot_prompt_filas.md` (the original spec this system was built from) and `doc/plano_filas_analise.md` (architecture analysis + phased implementation plan actually followed: Fase 2 = job core + router, Fase 3 = first worker + watcher, Fase 4 = all three queues in parallel, Fase 5 = systemd + heartbeat, this section).

## Key constraints to preserve

- The bot must remain single-user: don't remove or weaken the `_is_authorized` check — including on every new job-related command (`/meusjobs`, `/job`, `/cancelar`, `/filas`, `/status`, `/skills`).
- Tools stay disabled (`--tools ""`) in `ai_client.py` — the direct-conversation path (Rota A) must keep behaving exactly as before the queue system was added. Only skill execution inside workers is allowed to use tools/agents; the router's own classification call also runs with `--tools ""` (it just classifies, it doesn't act).
- The `claude` CLI must be logged in (`claude login`) on whatever machine runs the bot/workers/router; there's no API-key fallback path in this codebase.
- The bot must keep responding even if no worker or the watcher is down (`ACCEPT_JOBS_WHEN_WORKER_OFFLINE`, default `true`) — job creation never blocks on worker availability, it only appends an informational warning to the "added to queue" reply when heartbeats are stale.
- `claim_next_job()`'s locking is load-bearing — don't refactor away the `BEGIN IMMEDIATE` + `threading.Lock` combo without re-running a real multi-thread/multi-process concurrency check first.
- Never write API keys/tokens/credentials into the `jobs` table (`payload`, `result`, `error` columns) — those are logged and shown back to the user via `/job <id>`.
