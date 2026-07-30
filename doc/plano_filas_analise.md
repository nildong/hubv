# Plano — Sistema de Filas para o `ngmastercabot`

> Documento de análise e planejamento (Fase 1 do `doc/ngmastercabot_prompt_filas.md`).
> Nenhum código foi alterado. Este é apenas o relatório + plano de implementação.

---

## 1. Arquitetura atual

- **Linguagem/stack**: Python 3.12, `python-telegram-bot` (long polling), sem framework web.
- **Entrada da mensagem**: `bot.py` — handlers `handle_text` (texto) e `handle_voice` (voz/áudio), registrados em `Application` (long polling, `run_polling`).
- **Autenticação**: `_is_authorized()` em `bot.py:59` — single-user, gate por `TELEGRAM_ALLOWED_USER_ID`. Se não configurado, entra em "modo descoberta" (devolve o ID do usuário e não faz nada).
- **Transcrição de voz**: `transcription.py` (`Transcriber`), usa Groq Whisper. Chamada síncrona dentro do handler `handle_voice`.
- **Chamada da IA**: `ai_client.py` (`ClaudeClient.ask()`) — faz `subprocess.run(["claude", "-p", ...])`, síncrono, bloqueante, timeout de 120s (`CLAUDE_TIMEOUT_SECONDS`). Tools desabilitadas (`--tools ""`) — é só conversa, sem execução de ações externas.
- **Continuidade de conversa**: sessão por `user_id` do Telegram, guardada em memória (`ClaudeClient._sessions: dict[int, str]`), usando `--resume <session_id>` do próprio Claude Code CLI. Não sobrevive a restart do bot.
- **Montagem/envio da resposta**: `_reply_with_ai()` em `bot.py:111` chama `claude_client.ask()` e envia a resposta via `update.message.reply_text()`, dividindo em pedaços com `split_message()` (limite 4096 chars) quando necessário.
- **Banco de dados**: **não existe**. Toda a persistência é em memória (dict de sessões) ou nenhuma.
- **Configuração**: `config.py` — carrega `.env` via `python-dotenv`, falha rápido se faltar `TELEGRAM_BOT_TOKEN` ou `GROQ_API_KEY`. Também carrega `system_prompt.txt`.
- **Inicialização**: `python bot.py` → `main()` monta a `Application`, registra handlers e chama `run_polling()`. Há um exemplo de systemd unit em `deploy/telegram-assistente.service.example`.
- **Logs**: `logging` padrão do Python, config básica em `bot.py:21-25`, nível INFO, sem arquivo dedicado (stdout).
- **Testes**: nenhum teste automatizado no repositório.
- **Síncrono vs assíncrono**: os handlers são `async def` (exigido pela lib), mas dentro deles tudo é síncrono/bloqueante: `subprocess.run` do Claude CLI e a chamada Groq travam o event loop até responder (ou até estourar timeout). Não há paralelismo real de execução — dois usuários em sequência ficam na fila do event loop, não de um sistema de filas de fato.
- **Conceitos de job/fila/worker/status/skill/agent**: **inexistentes**. Nenhum termo do tipo `queue`, `job`, `worker`, `pending/running/completed/failed`, `skill`, `watcher`, `spawn`, `cron` aparece no código atual (confirmado por busca).
- **Integração com Claude Code**: já existe, e é exatamente o ponto que o executor de agente da Etapa 9 vai reaproveitar (`subprocess` chamando `claude -p ...`), mas hoje sem tools habilitadas e sem isolamento de diretório de trabalho por tarefa.

## 2. O que pode ser reaproveitado

- `config.py` — carregamento de `.env`, pode ser estendido com novas variáveis (`WORKER_POLL_INTERVAL_MS`, `JOB_LOCK_TIMEOUT_MINUTES`, etc.) sem quebrar o padrão existente.
- `ai_client.py` (`ClaudeClient`) — vira a base do primeiro `AgentExecutor` (execução via Claude Code CLI). O padrão de `subprocess.run` com args separados já segue a prática segura pedida na Etapa 9 (sem `shell=True`, sem concatenar string).
- `bot.py` — handlers de texto/voz continuam existindo como está para a Rota A (resposta direta). Só ganham um passo extra de roteamento antes de decidir "responder direto" vs "criar job".
- `transcription.py` — usado como está; a transcrição de voz é rápida o bastante para continuar síncrona no handler (a Etapa 3 já cita "processamento de áudio" como candidato a fila para casos mais pesados, mas a transcrição simples pode ficar fora do fluxo de filas).
- `split_message()` — reaproveitado tanto para resposta direta quanto para entrega de resultado de job pelo watcher.
- Padrão de logging existente — só precisa ganhar os campos extras (job_id, queue, skill, worker_id, attempt, duration) nos módulos novos.
- `deploy/telegram-assistente.service.example` — modelo para os novos `.service` de worker/watcher (Etapa 17).

## 3. O que está faltando

Tudo relativo a filas precisa ser criado do zero:

- Banco de dados (SQLite na primeira versão — hoje não existe nenhum).
- Modelo de `Job` e migration da tabela `jobs`.
- Repositório de jobs (`createJob`, `claimNextJob` atômico, `completeJob`, `failJob`, etc.).
- Registro de skills (`config/skills.json` + validação).
- Roteador de intenção (decidir `reply` / `clarify` / `enqueue`), com validação da resposta da IA (não confiar cegamente em JSON gerado pelo modelo).
- Workers (processo separado por fila: `videos`, `textos`, `servicos`), com polling, lock atômico, concorrência 1 por fila.
- Executor de agente (`AgentExecutor`) desacoplado do provedor, com implementação inicial via Claude Code CLI reaproveitando `ClaudeClient`, mas agora com tools habilitadas conforme a skill precisar, timeout, diretório isolado por job.
- Diretório isolado por job (`data/jobs/<job-id>/`).
- Watcher (processo separado, entrega idempotente do resultado ao usuário).
- Comandos novos no bot: `/status`, `/filas`, `/meusjobs`, `/job <id>`, `/cancelar <id>`, `/repetir <id>`, `/skills`.
- Recuperação de locks expirados na inicialização dos workers.
- Health check / heartbeat dos workers.
- Serviços systemd separados (bot, 3 workers, watcher).
- Suíte de testes (hoje inexistente — precisa nascer junto com o núcleo de filas).

## 4. Riscos

- **Concorrência sobre SQLite**: o bot (processo 1) e os workers (processos separados) vão acessar o mesmo arquivo SQLite simultaneamente. `claimNextJob` precisa ser implementado com transação `BEGIN IMMEDIATE` (ou `UPDATE ... WHERE status='pending' RETURNING`) para evitar dois workers pegando o mesmo job — se malfeito, gera corrida e duplicidade de execução.
- **Bloqueio do event loop do bot**: se o roteamento de intenção também chamar `claude -p` de forma síncrona (como hoje) para decidir `reply`/`enqueue`, o bot continua travando durante essa chamada. Precisa rodar em thread/executor (`run_in_executor`) para não regressão de responsividade.
- **Mudar `ai_client.py` sem cuidado quebra a Rota A**: `ClaudeClient.ask()` é usado hoje diretamente pelos handlers de texto/voz. Se for refatorado para virar `AgentExecutor` genérico, é preciso manter uma via de "resposta direta" equivalente à atual (mesma sessão por `user_id`, mesmo `--resume`), sem introduzir latência ou perda de contexto.
- **Habilitar tools no executor de agente** contraria a restrição do CLAUDE.md ("tools stay disabled unless o usuário pedir explicitamente para tornar isso um bot agôntico"). Este próprio pedido de filas + agentes temporários + skills é esse pedido explícito, mas a Rota A (conversa direta) deve continuar com `--tools ""` — só os jobs/skills executados pelos workers ganham tools.
- **`TELEGRAM_ALLOWED_USER_ID` / single-user**: qualquer novo comando (`/meusjobs`, `/cancelar`, etc.) precisa continuar passando por `_is_authorized()`. Fácil de esquecer ao adicionar handlers novos.
- **Processos zumbis**: se o worker spawnar `claude` (ou outro processo) e o timeout estourar, é preciso garantir `kill`/`terminate` do processo filho — hoje `subprocess.run` com timeout já mata o processo, mas isso precisa ser preservado no novo executor com diretório de trabalho customizado.
- **Migração de sessões em memória**: hoje `ClaudeClient._sessions` é um dict simples. Se o roteador também precisar de contexto (para decidir reply/enqueue), decidir se usa a mesma sessão Claude ou uma separada — misturar pode poluir o histórico de conversa do usuário com JSON de roteamento.
- **Crescimento de escopo**: o doc pede workers, skills, watcher, systemd, health check, retry, etc. — implementar tudo de uma vez viola a regra "não faça alterações grandes antes de entender a arquitetura" e "primeiro analise, depois proponha, depois implemente". A Etapa 21 do próprio doc já prevê isso com fases.

## 5. Plano de implementação (por fases, incremental)

### Fase 2 — núcleo da fila (sem workers ainda)

**Criar:**
- `telegram-assistente/db/schema.sql` — migration com a tabela `jobs` (SQL da Etapa 5 do doc).
- `telegram-assistente/db/connection.py` — helper de conexão SQLite (`sqlite3`, `check_same_thread=False` ou pool simples), aplica migration no startup se a tabela não existir.
- `telegram-assistente/jobs/models.py` — dataclass `Job` / `JobStatus` / `QueueName` (equivalente Python da interface TS do doc).
- `telegram-assistente/jobs/repository.py` — `JobRepository` com `create_job`, `get_job`, `get_jobs_by_user`, `claim_next_job` (atômico via `UPDATE ... WHERE status='pending' RETURNING *` ou transação `BEGIN IMMEDIATE`), `update_job_progress`, `complete_job`, `fail_job`, `cancel_job`, `retry_job`, `release_expired_locks`, `get_queue_stats`, `mark_delivered`, `mark_delivery_failed`.
- `telegram-assistente/config/skills.json` — registro inicial com 1 skill de teste (`teste-fila`, fila `servicos`).
- `telegram-assistente/router/skill_registry.py` — carrega e valida `skills.json`.
- `telegram-assistente/router/intent_router.py` — chama a IA para decidir `reply`/`clarify`/`enqueue`, valida o JSON de saída (schema check), fallback para `reply` de erro se inválido após 1 tentativa de correção.

**Alterar:**
- `config.py` — novas variáveis: `JOBS_DB_PATH`, `SKILLS_CONFIG_PATH` (com defaults sensatos, mesmo padrão de `SYSTEM_PROMPT_FILE`).
- `bot.py` — `_reply_with_ai` passa a chamar o roteador primeiro; se `action=reply`, comportamento igual ao atual; se `action=enqueue`, cria o job via `JobRepository.create_job` e responde com a mensagem de "entrou na fila" (Etapa 12); se `action=clarify`, pergunta ao usuário sem criar job.
- `.env.example` — documentar as novas variáveis.

**Não alterar:** `ai_client.py`, `transcription.py` — seguem intocados nesta fase (worker/executor ainda não existe).

**Banco/tabelas:** tabela `jobs` conforme SQL do doc (Etapa 5), em SQLite local (`data/jobs.db` ou similar, fora do git via `.gitignore`).

**Testes desta fase:**
1. resposta direta sem fila (regressão da Rota A).
2. criação correta de job (payload, campos obrigatórios).
3. skill inexistente → erro tratado, sem job criado.
4. campos obrigatórios ausentes → `clarify`, sem job.
5. captura atômica de `claim_next_job` (dois "workers" simulados em teste não pegam o mesmo job).
6. seleção por prioridade e por data de criação (empate).

### Fase 3 — primeiro worker (fila `servicos`) + skill de teste

**Criar:**
- `telegram-assistente/agents/executor.py` — interface `AgentExecutor` + `ClaudeCliExecutor` (reaproveita a lógica de `ClaudeClient.ask`, mas roda num diretório de trabalho isolado e com tools habilitadas conforme a skill).
- `telegram-assistente/workers/base.py` — loop genérico: poll → claim → running → executa via `AgentExecutor` → salva resultado → completed/failed → repete.
- `telegram-assistente/workers/service_worker.py` — instancia o worker para a fila `servicos`, concorrência 1.
- `telegram-assistente/workers/run_service_worker.py` — entrypoint (`python -m workers.run_service_worker`).
- `telegram-assistente/skills/teste_fila.py` (ou pasta de skills) — a skill "teste-fila": recebe texto, aguarda 10s, escreve `resultado.txt` em `data/jobs/<job-id>/files/`, conclui.
- `telegram-assistente/delivery/watcher.py` — processo separado: procura `completed`/`failed` com `delivery_status=pending`, formata e envia via Telegram Bot API (usando o mesmo token, sem precisar do `Application` do bot principal — pode usar `telegram.Bot` diretamente), marca `delivered`.
- `telegram-assistente/delivery/run_watcher.py` — entrypoint do watcher.

**Alterar:**
- `config.py` — `WORKER_POLL_INTERVAL_MS`, `JOB_LOCK_TIMEOUT_MINUTES`.
- `bot.py` — adicionar comandos `/status`, `/meusjobs`, `/job <id>`, `/cancelar <id>` (leitura/gestão de jobs do próprio usuário via `JobRepository`).

**Testes desta fase:**
7. execução completa da skill `teste-fila` fim a fim (job criado → worker pega → arquivo gerado → watcher entrega).
8. dois workers do mesmo tipo não pegam o mesmo job (concorrência real, não simulada).
9. apenas um job ativo por vez na fila `servicos`.
10. entrega única (idempotência do watcher, mesmo reiniciando o processo).
11. retry após falha (job volta para `pending`, respeita `max_attempts`).
12. cancelamento de job pendente.
13. recuperação após reinício (job `running` órfão volta a `pending`/`failed`).
14. bot continua respondendo normalmente com o worker/watcher desligados (`ACCEPT_JOBS_WHEN_WORKER_OFFLINE`).

### Fase 4 — filas `videos` e `textos`

- Repetir o padrão da Fase 3: `workers/video_worker.py`, `workers/text_worker.py`, entrypoints próprios, skills reais cadastradas em `skills.json` (roteiro, video-explicativo, etc. — ou placeholders até existir a integração real de geração).
- Confirmar que as três filas rodam em paralelo sem interferência (teste dedicado).

### Fase 5 — operação

- `deploy/*.service.example` para cada worker e o watcher (seguindo o modelo do bot atual).
- Heartbeat (`worker_id`, `queue`, `status`, `last_seen_at`, `current_job_id`, `started_at`) — tabela extra `worker_heartbeats` ou reaproveitar `jobs` com uma tabela separada simples.
- Logging estruturado com os campos da Etapa 19 nos módulos de worker/watcher/router.
- `/skills` e `/ajuda` atualizados no bot.
- Documentação: atualizar `CLAUDE.md` e `README.md` com a nova arquitetura (bot + workers + watcher como serviços separados).

## Observações finais

- A Rota A (conversa direta, sem fila) do doc já é essencialmente o que o bot faz hoje — a mudança real é inserir o roteador de intenção antes da chamada direta ao `ClaudeClient`.
- O ponto de maior atenção arquitetural é manter `ai_client.py` funcionando como está para conversa direta enquanto nasce um `AgentExecutor` separado para os jobs — são dois casos de uso com necessidades diferentes de tools/timeout/isolamento, mesmo reaproveitando a mesma chamada de CLI por baixo.
- Nenhum código foi criado ou alterado nesta etapa, conforme solicitado — este documento cobre a Fase 1 (diagnóstico) e propõe o plano das Fases 2–5.
