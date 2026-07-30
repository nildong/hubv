# ngmastercabot (telegram-assistente)

Bot pessoal para Telegram: recebe texto ou áudio, encaminha para o Claude
(usando sua **assinatura** Claude Pro/Max, sem API key) e responde no chat.
Áudios são transcritos primeiro pela **Groq** (Whisper).

Além da conversa direta, o bot tem um sistema de filas: pedidos demorados
(gerar um roteiro, um vídeo, etc.) viram um `job`, processado em segundo
plano por um worker, com o resultado entregue de volta no chat quando fica
pronto.

## Como funciona

```text
Você envia texto ou áudio no Telegram
        ↓
Bot verifica se você é o usuário autorizado
        ↓
Se for áudio → Groq transcreve para texto
        ↓
Roteador de intenção classifica: reply / clarify / enqueue
        ↓                              ↓
Conversa simples?             Tarefa demorada com skill conhecida?
        ↓                              ↓
Vai para o Claude Code CLI     Cria um job na fila (videos/textos/servicos)
(sessão da sua assinatura)     e responde "adicionado à fila"
        ↓                              ↓
Claude responde                Um worker da fila pega o job, executa a
        ↓                      skill e salva o resultado
Bot envia a resposta                    ↓
no Telegram                    O watcher detecta o job concluído e
                                entrega o resultado no mesmo chat
```

## Pré-requisitos

- Python 3.11+
- [Claude Code](https://docs.claude.com/claude-code) instalado e logado com sua conta de assinatura
- Conta na [Groq](https://console.groq.com) com uma API key

## 1. Criar o bot no BotFather

1. Abra o Telegram e procure por `@BotFather`.
2. Envie `/newbot` e siga as instruções (nome e username do bot).
3. O BotFather vai te dar um token no formato `123456:ABC-DEF...`. Esse é o `TELEGRAM_BOT_TOKEN`.

## 2. Descobrir seu ID do Telegram

Duas formas:

- Fale com `@userinfobot` no Telegram — ele responde com seu ID.
- Ou: rode o bot sem definir `TELEGRAM_ALLOWED_USER_ID` no `.env`. Ao enviar
  qualquer mensagem para o bot, ele responde com o seu ID e não faz mais
  nada (modo "descoberta"). Copie o ID, coloque no `.env` e reinicie o bot.

## 3. Autenticar o Claude na máquina (assinatura)

Na máquina onde o bot vai rodar (seu PC ou a VPS):

```bash
claude login
```

Faça login com a conta que tem a assinatura Pro/Max. Isso cria uma sessão
local que o bot vai reutilizar — não é necessário nenhuma `ANTHROPIC_API_KEY`.

> Importante: essa autenticação é por máquina/usuário do sistema operacional.
> Se trocar de servidor, rode `claude login` novamente lá.

## 4. Configurar o `.env`

Copie o exemplo e preencha:

```bash
cp .env.example .env
```

```env
TELEGRAM_BOT_TOKEN=            # token do BotFather
TELEGRAM_ALLOWED_USER_ID=      # seu ID do Telegram (passo 2)
GROQ_API_KEY=                  # key da Groq
GROQ_TRANSCRIBE_MODEL=whisper-large-v3
GROQ_LANGUAGE=pt               # deixe em branco para detecção automática
CLAUDE_MODEL=                  # opcional, ex: sonnet, opus, ou nome completo do modelo
SYSTEM_PROMPT_FILE=system_prompt.txt

# Sistema de filas
JOBS_DB_PATH=data/jobs.db
SKILLS_CONFIG_PATH=config/skills.json
WORKER_POLL_INTERVAL_MS=3000
JOB_LOCK_TIMEOUT_MINUTES=30
HEARTBEAT_STALE_MINUTES=2
ACCEPT_JOBS_WHEN_WORKER_OFFLINE=true
```

O comportamento do assistente é definido em `system_prompt.txt` — edite esse
arquivo para mudar o tom/regras sem tocar no código.

**Nunca** commite o arquivo `.env` (ele já está no `.gitignore`).

## 5. Instalar as dependências

```bash
cd telegram-assistente
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 6. Iniciar o bot

```bash
source .venv/bin/activate
python bot.py
```

Se tudo estiver certo, o terminal mostra `Bot iniciado. Aguardando mensagens...`.

O bot sozinho já responde conversa direta. Para pedidos que viram job
(fila), rode também pelo menos um worker e o watcher (passo 8 abaixo) —
sem eles, jobs ficam parados em `pending` até um worker aparecer.

## 7. Testar a integração

1. Envie `/start` no Telegram — deve responder a mensagem de boas-vindas.
2. Envie uma mensagem de texto qualquer — deve vir uma resposta do Claude.
3. Envie um áudio/mensagem de voz — o bot responde com a transcrição (🎙️) e
   depois com a resposta do Claude sobre esse conteúdo.
4. Envie `/limpar` — o histórico da conversa é reiniciado.
5. Envie `/ajuda` — mostra a lista de comandos.
6. Peça para outra pessoa (ou outra conta) mandar mensagem para o bot — ele
   deve ignorar (ou, se `TELEGRAM_ALLOWED_USER_ID` ainda não estiver
   configurado, responder só com o ID de quem mandou).
7. Com pelo menos o worker de `servicos` e o watcher rodando (passo 8), peça
   algo como "crie um teste na fila com o texto ola mundo" — o bot deve
   responder "Seu pedido foi adicionado à fila", e ~10s depois o watcher
   entrega o resultado (mensagem + arquivo `resultado.txt`).
8. Envie `/filas`, `/status`, `/meusjobs`, `/skills` — devem responder com o
   estado atual das filas, dos workers e dos seus jobs.

## 8. Rodar os workers e o watcher

Cada peça é um processo independente — pode rodar tudo na mesma máquina.
O bot continua respondendo normalmente mesmo se algum desses estiver parado
(os jobs só ficam esperando na fila).

```bash
source .venv/bin/activate
python -m workers.run_service_worker   # fila "servicos"
python -m workers.run_video_worker     # fila "videos"
python -m workers.run_text_worker      # fila "textos"
python -m delivery.run_watcher         # entrega os resultados no Telegram
```

## 9. Manter tudo rodando em uma VPS

Use `systemd` para manter cada processo ativo e reiniciar sozinho se cair.

1. Copie o projeto para a VPS (ex: `/opt/telegram-assistente`).
2. Rode `claude login` na VPS (passo 3 acima).
3. Crie o venv e instale as dependências (passo 5) dentro da VPS.
4. Copie cada arquivo de `deploy/*.service.example` para
   `/etc/systemd/system/<nome>.service` (sem `.example`) e ajuste `User`,
   `WorkingDirectory` e `ExecStart` para os caminhos reais:
   - `telegram-assistente.service.example` — o bot
   - `ngmastercabot-service-worker.service.example` — worker da fila `servicos`
   - `ngmastercabot-video-worker.service.example` — worker da fila `videos`
   - `ngmastercabot-text-worker.service.example` — worker da fila `textos`
   - `ngmastercabot-watcher.service.example` — o watcher
5. Ative os serviços:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-assistente
sudo systemctl enable --now ngmastercabot-service-worker
sudo systemctl enable --now ngmastercabot-video-worker
sudo systemctl enable --now ngmastercabot-text-worker
sudo systemctl enable --now ngmastercabot-watcher
```

6. Ver logs em tempo real:

```bash
sudo journalctl -u telegram-assistente -f
sudo journalctl -u ngmastercabot-service-worker -f
```

## Estrutura do projeto

```text
telegram-assistente/
├── bot.py                      # handlers do Telegram (texto, voz, comandos, roteamento)
├── ai_client.py                 # integração com o Claude via CLI (assinatura) — conversa direta
├── transcription.py             # integração com a Groq (transcrição de áudio)
├── config.py                    # carrega e valida variáveis de ambiente
├── messaging.py                 # split_message() compartilhado entre bot e watcher
├── system_prompt.txt            # instrução de sistema do assistente (editável)
├── db/
│   ├── schema.sql                 # migration (tabelas jobs, worker_heartbeats)
│   └── connection.py               # conexão SQLite (WAL) compartilhada
├── jobs/
│   ├── models.py                    # dataclass Job
│   ├── repository.py                 # JobRepository (create/claim/complete/fail/...)
│   └── heartbeat_repository.py        # heartbeat de workers
├── router/
│   ├── skill_registry.py               # valida skills contra config/skills.json
│   └── intent_router.py                 # classifica reply / clarify / enqueue
├── agents/executor.py                    # AgentExecutor + SkillDispatchExecutor
├── skills/
│   ├── registry.py                         # mapa skill -> função Python
│   ├── teste_fila.py                        # skill de teste (fila servicos)
│   ├── roteiro.py                            # skill placeholder (fila textos)
│   └── video_explicativo.py                   # skill placeholder (fila videos)
├── workers/
│   ├── base.py                                 # Worker genérico (uma fila por processo)
│   ├── runner.py                                # bootstrap comum aos entrypoints
│   ├── run_service_worker.py                     # entrypoint fila servicos
│   ├── run_video_worker.py                        # entrypoint fila videos
│   └── run_text_worker.py                          # entrypoint fila textos
├── delivery/
│   ├── watcher.py                                    # entrega idempotente ao Telegram
│   ├── result_formatter.py                            # formata mensagem/arquivo do job
│   └── run_watcher.py                                  # entrypoint do watcher
├── config/skills.json                                   # registro de skills habilitadas
├── data/                                                 # jobs.db + pastas isoladas por job (gitignored)
├── requirements.txt
├── .env.example
├── .env                                                   # suas chaves reais (não versionar)
├── .gitignore
├── deploy/*.service.example                               # bot + 3 workers + watcher
└── README.md
```

## Limitações conhecidas

- O bot depende do CLI `claude` estar instalado e autenticado na máquina —
  se a sessão expirar, rode `claude login` de novo.
- O uso está sujeito aos limites da sua assinatura Claude (Pro/Max), não é
  cobrado por token como a API paga.
- Histórico de conversa é mantido pela própria sessão do Claude Code
  (`--resume`) e fica em memória do processo do bot; reiniciar o bot ou
  usar `/limpar` começa uma conversa nova.
