# Relatório de análise e plano de implementação de filas

**Projeto:** `inemacabot`  
**Documento de origem:** `doc/inemacabot_prompt_filas.md`  
**Data da análise:** 29 de julho de 2026  
**Escopo desta entrega:** diagnóstico e planejamento. Nenhuma implementação foi
realizada.

## 1. Resumo executivo

O `inemacabot` é hoje um bot pessoal, assíncrono, escrito em Python e conectado
ao Telegram por long polling. Ele aceita somente um usuário autorizado, recebe
texto ou áudio, usa o Codex CLI para gerar a resposta e devolve o resultado no
mesmo chat. Não existe banco de dados, persistência de histórico, fila, job,
worker, watcher, registro de skills ou recuperação após reinício.

A evolução para filas deve ser incremental e preservar integralmente o caminho
atual de resposta direta. A recomendação é:

1. introduzir SQLite e o núcleo persistente de jobs sem mudar a resposta direta;
2. criar um roteador com saída validada;
3. validar o ciclo completo apenas com a fila `servicos` e uma skill
   determinística `teste-fila`;
4. separar worker e watcher em processos;
5. somente depois habilitar agentes temporários e as filas `videos` e `textos`.

Não é recomendável começar criando os três workers e um executor de agentes ao
mesmo tempo. Isso dificultaria distinguir falhas de roteamento, persistência,
execução e entrega.

## 2. Arquitetura atual

### 2.1 Tecnologias

| Área | Implementação atual |
|---|---|
| Linguagem | Python 3.11 ou superior |
| Telegram | `python-telegram-bot`, interface assíncrona |
| Inicialização | `python bot.py` |
| Transporte | long polling |
| IA | Codex CLI autenticado no usuário do sistema |
| Transcrição | API HTTP do Groq com `httpx` |
| Banco de dados | inexistente |
| Histórico | `deque` em memória |
| Autorização | um único `TELEGRAM_ALLOWED_USER_ID` |
| Configuração | variáveis de ambiente e `.env` |
| Logs | `logging` padrão para stdout/stderr |
| Testes | `unittest`, 13 testes atuais |

Dependências diretas atuais:

```text
python-telegram-bot
python-dotenv
httpx
```

O módulo `sqlite3` da biblioteca padrão é suficiente para a primeira versão da
fila, sem Redis, RabbitMQ ou Kafka.

### 2.2 Entrada e saída das mensagens

O ponto de entrada é `bot.py`.

```text
Telegram
  -> Application.run_polling()
  -> CommandHandler ou MessageHandler
  -> validação do usuário
  -> handler específico
```

Handlers existentes:

- `/start` -> `start_command`;
- `/ajuda` -> `help_command`;
- `/limpar` -> `clear_command`;
- texto -> `text_message`;
- voz ou áudio -> `audio_message`.

Usuários não autorizados são ignorados silenciosamente antes da chamada ao
Codex ou ao Groq.

### 2.3 Fluxo atual de texto

```text
text_message
  -> _generate_and_reply
  -> adquire conversation_lock
  -> history.snapshot()
  -> CodexClient.answer()
  -> codex exec em sessão efêmera
  -> history.add_exchange()
  -> split_message()
  -> reply_text()
```

`CodexClient.answer()`:

- cria um diretório temporário vazio;
- executa `codex exec`;
- usa sessão efêmera;
- ignora configuração e regras do usuário;
- trabalha em sandbox `read-only`;
- envia o prompt pela entrada padrão;
- lê somente a mensagem final de um arquivo temporário;
- aplica timeout;
- não permite ferramentas, comandos ou acesso a arquivos no prompt.

### 2.4 Fluxo atual de áudio

```text
audio_message
  -> valida tamanho e configuração
  -> baixa o arquivo do Telegram
  -> GroqTranscriptionClient.transcribe()
  -> _generate_and_reply(transcrição)
  -> mesmo fluxo de texto
```

### 2.5 Concorrência atual

Existe uma única `asyncio.Lock`, chamada `conversation_lock`, compartilhada por
toda a conversa. Ela garante a ordem entre histórico e respostas, mas também
serializa todas as chamadas ao Codex.

Essa trava protege apenas o processo atual. Ela:

- não funciona entre processos;
- não persiste após reinício;
- não pode proteger jobs capturados por workers separados;
- não deve ser reutilizada como mecanismo de fila.

### 2.6 Persistência atual

Não há banco ou arquivos persistentes de estado.

- O histórico desaparece ao reiniciar o bot.
- Não existem IDs de tarefa ou estados de execução.
- Não há como recuperar trabalho interrompido.
- Não há controle persistente de tentativas ou de entrega.

### 2.7 Envio de respostas

As respostas são síncronas do ponto de vista do usuário: o handler fica
aguardando o Codex terminar. Durante a espera, o Telegram recebe apenas a ação
`typing`.

Quando a resposta chega, `split_message()` divide o texto em blocos de no
máximo 4.000 caracteres e o bot envia cada bloco com `reply_text()`.

## 3. Componentes que podem ser reaproveitados

| Componente | Reaproveitamento proposto |
|---|---|
| `bot.py` | manter bootstrap, autorização, handlers atuais e resposta direta; adicionar integração mínima com roteador e repositório |
| `auth.py` | manter a validação inicial e reutilizar a regra de propriedade nos comandos de jobs |
| `config.py` | ampliar `Settings` com banco, polling, locks, retenção e diretórios |
| `codex_client.py` | preservar `answer()` para resposta direta e extrair uma primitiva segura de execução para roteamento |
| `transcription_client.py` | manter a transcrição atual; decidir por roteamento somente após obter o texto |
| `history.py` | manter para conversas diretas; não usar como armazenamento de jobs |
| `message_utils.py` | reutilizar na formatação de status e entrega de resultados textuais |
| `BotServices` | continuar como composição de dependências, adicionando roteador e repositório |
| `is_authorized()` | aplicar antes de qualquer criação, consulta, cancelamento ou repetição de job |
| logging atual | manter como base e adicionar contexto estruturado de job |
| `unittest` | continuar como framework de testes |
| configuração por `.env` | manter, adicionando somente valores não secretos ao `.env.example` |
| exemplo `systemd` | evoluir para serviços separados |

O caminho de resposta direta deve continuar chamando `CodexClient.answer()` e
`split_message()` como hoje, para reduzir o risco de regressão.

## 4. Componentes ausentes

São necessários:

- modelo Python de `Job`;
- enumerações de fila, status e entrega;
- migration e conexão SQLite;
- repositório de jobs com transações;
- captura atômica do próximo job;
- registro central e validado de skills;
- roteador de intenção com saída previsível;
- validação independente da saída produzida pelo modelo;
- três workers, inicialmente habilitando apenas `servicos`;
- abstração de executor;
- executor determinístico para o primeiro teste;
- executor Codex separado do cliente de conversa;
- pasta isolada por job;
- retry com `available_at`;
- locks com expiração;
- cancelamento cooperativo;
- watcher de resultados;
- registro persistente de entregas;
- heartbeat dos workers;
- comandos de consulta e controle;
- scripts ou módulos de inicialização dos processos;
- serviços `systemd`;
- política de retenção de jobs, logs e arquivos;
- testes de integração e concorrência.

## 5. Decisões de arquitetura recomendadas

### 5.1 Organização de módulos

O projeto atual usa módulos simples na raiz. Não é necessário reescrevê-lo como
um novo pacote. Os componentes novos podem ser agrupados em pacotes pequenos:

```text
inemacabot/
├── bot.py
├── config.py
├── codex_client.py
├── auth.py
├── history.py
├── message_utils.py
├── transcription_client.py
├── routing/
│   ├── __init__.py
│   ├── models.py
│   ├── intent_router.py
│   └── validator.py
├── queueing/
│   ├── __init__.py
│   ├── models.py
│   ├── database.py
│   ├── migrations.py
│   └── job_repository.py
├── skills/
│   ├── registry.json
│   ├── registry.py
│   └── executors/
│       └── test_queue.py
├── agents/
│   ├── __init__.py
│   ├── base.py
│   ├── factory.py
│   └── codex_executor.py
├── workers/
│   ├── __init__.py
│   ├── worker.py
│   └── runner.py
├── delivery/
│   ├── __init__.py
│   ├── formatter.py
│   ├── service.py
│   └── watcher.py
├── data/
│   └── .gitkeep
└── tests/
```

Os três workers podem usar o mesmo código em `workers/runner.py`, recebendo
`--queue videos`, `--queue textos` ou `--queue servicos`. Isso evita três
implementações divergentes.

### 5.2 Resposta direta, esclarecimento ou job

O roteador deve produzir somente uma destas decisões:

```python
RouteAction = Literal["reply", "clarify", "enqueue"]
QueueName = Literal["videos", "textos", "servicos"]
```

Campos:

```text
action
response
question
queue
skill
payload
```

Validações obrigatórias:

- `reply` exige `response` não vazia e não aceita campos de job;
- `clarify` exige `question` não vazia;
- `enqueue` exige fila, skill e payload;
- a fila precisa estar na lista permitida;
- a skill deve existir, estar habilitada e pertencer à fila indicada;
- todos os campos obrigatórios da skill devem estar presentes;
- campos desconhecidos devem ser rejeitados ou normalizados explicitamente;
- tamanho e profundidade do payload devem ser limitados;
- uma decisão inválida pode ser reparada apenas uma vez;
- persistindo a falha, o sistema deve pedir esclarecimento, sem criar o job.

Para preservar o comportamento atual, a primeira entrega pode usar regras
determinísticas para comandos e um modo de roteamento desabilitado por padrão.
Quando habilitado, o roteador pode reutilizar o Codex CLI, mas sua saída deve ser
tratada como dado não confiável.

Há um custo importante: fazer uma chamada para classificar e outra para
responder dobra latência e consumo. A implementação deve preferir uma única
decisão estruturada que já contenha a resposta quando `action=reply`, ou aplicar
regras determinísticas antes de chamar o modelo.

### 5.3 Banco SQLite

Arquivo recomendado:

```text
data/inemacabot.sqlite3
```

Configuração inicial:

- journal mode `WAL`;
- `foreign_keys=ON`;
- `busy_timeout` configurado;
- transações curtas;
- uma conexão por operação ou por processo, nunca uma conexão global
  compartilhada entre processos;
- timestamps em UTC no formato ISO 8601;
- payload e resultado em JSON validado;
- migrations versionadas e idempotentes.

### 5.4 Modelo de dados

#### Tabela `schema_migrations`

```text
version       INTEGER PRIMARY KEY
applied_at    TEXT NOT NULL
```

#### Tabela `jobs`

Campos mínimos do prompt, com duas extensões necessárias:

```text
id                    TEXT PRIMARY KEY
queue                 TEXT NOT NULL
skill                 TEXT NOT NULL
payload               TEXT NOT NULL
status                TEXT NOT NULL
priority              INTEGER NOT NULL DEFAULT 0
attempts              INTEGER NOT NULL DEFAULT 0
max_attempts          INTEGER NOT NULL DEFAULT 3
user_id               TEXT NOT NULL
chat_id               TEXT NOT NULL
source_message_id     TEXT
progress              INTEGER NOT NULL DEFAULT 0
result                TEXT
error                 TEXT
created_at            TEXT NOT NULL
available_at          TEXT NOT NULL
started_at            TEXT
completed_at          TEXT
cancel_requested_at   TEXT
locked_by             TEXT
locked_at             TEXT
delivery_status       TEXT NOT NULL DEFAULT 'pending'
delivered_at          TEXT
delivery_attempts     INTEGER NOT NULL DEFAULT 0
delivery_error        TEXT
```

Restrições recomendadas:

- `queue IN ('videos', 'textos', 'servicos')`;
- `status IN ('pending', 'running', 'completed', 'failed', 'cancelled')`;
- `delivery_status IN ('pending', 'delivering', 'delivered', 'failed')`;
- `progress BETWEEN 0 AND 100`;
- `attempts >= 0`;
- `max_attempts > 0`;
- `priority` limitado a valores autorizados.

Índices:

```text
(queue, status, available_at, priority DESC, created_at ASC)
(user_id, created_at DESC)
(delivery_status, completed_at)
(locked_at)
```

#### Tabela `workers`

```text
worker_id        TEXT PRIMARY KEY
queue            TEXT NOT NULL
status           TEXT NOT NULL
last_seen_at     TEXT NOT NULL
current_job_id   TEXT
started_at       TEXT NOT NULL
```

#### Tabela `deliveries`

É recomendável separar tentativas de entrega do job para auditoria:

```text
id               TEXT PRIMARY KEY
job_id           TEXT NOT NULL
attempt          INTEGER NOT NULL
status           TEXT NOT NULL
started_at       TEXT NOT NULL
completed_at     TEXT
telegram_message_id TEXT
error            TEXT
```

Uma restrição única em `(job_id, attempt)` evita a repetição interna da mesma
tentativa.

### 5.5 Captura atômica

`claim_next_job()` deve:

1. abrir uma transação `BEGIN IMMEDIATE`;
2. selecionar o job elegível da fila:
   `pending`, `available_at <= agora`, maior prioridade e mais antigo;
3. atualizar esse mesmo job para `running`, definir lock, início e incrementar
   `attempts`;
4. confirmar a transação;
5. devolver o job atualizado.

O `UPDATE` deve também exigir `status='pending'`. Se nenhuma linha for alterada,
o worker perdeu a disputa e deve tentar novamente. A correção precisa ser
testada com conexões SQLite independentes, não apenas com mocks.

### 5.6 Skills

O registro inicial deve conter somente skills realmente executáveis:

```json
{
  "teste-fila": {
    "queue": "servicos",
    "description": "Valida o ciclo da fila gravando o texto recebido",
    "enabled": false,
    "requiredFields": ["texto"],
    "executor": "test"
  }
}
```

Ela deve começar desabilitada fora de ambiente de teste ou homologação.

O registro precisa ser validado na inicialização:

- nomes únicos;
- fila válida;
- executor conhecido;
- lista válida de campos obrigatórios;
- configuração sem segredos;
- nenhuma skill inventada pelo modelo.

### 5.7 Workers

Cada processo de worker:

1. registra heartbeat;
2. recupera locks expirados da própria fila;
3. captura um job atomicamente;
4. cria `data/jobs/<job-id>/`;
5. grava entrada normalizada, sem segredos;
6. seleciona o executor pelo registro da skill;
7. atualiza progresso;
8. conclui, agenda retry ou falha definitivamente;
9. limpa o heartbeat do job atual;
10. volta ao polling.

Concorrência inicial:

```text
videos   -> 1 processo, 1 job
textos   -> 1 processo, 1 job
servicos -> 1 processo, 1 job
```

O banco deve impor a posse por lock; a configuração operacional de um processo
por fila não é proteção suficiente.

### 5.8 Executor e agentes temporários

Definir uma interface Python independente de provedor:

```python
class AgentExecutor(Protocol):
    async def execute(self, request: AgentRequest) -> AgentResult: ...
    async def cancel(self, job_id: str) -> None: ...
```

O cliente atual de conversa não pode ser convertido diretamente em executor de
jobs, porque ele:

- usa um diretório temporário que é apagado;
- trabalha em sandbox somente leitura;
- proíbe ferramentas e acesso a arquivos;
- produz apenas texto final.

O futuro `CodexAgentExecutor` deve ser separado e receber:

- diretório exclusivo do job;
- instrução da skill;
- payload validado;
- timeout específico;
- limite de stdout/stderr;
- ambiente reduzido e explicitamente permitido;
- sandbox compatível com a skill;
- cancelamento e encerramento do processo.

Processos devem ser iniciados com argumentos separados e `shell=False`. Texto
do usuário nunca pode ser concatenado a um comando.

Para a primeira validação, `teste-fila` deve usar um executor Python
determinístico que aguarda 10 segundos e grava `resultado.txt`. Isso testa a
infraestrutura sem atribuir erros aleatórios a um modelo.

### 5.9 Isolamento de arquivos

Estrutura:

```text
data/jobs/<job-id>/
├── input.json
├── output.json
├── stdout.log
├── stderr.log
└── files/
```

Regras:

- o ID deve ser gerado pelo sistema, nunca aceito como caminho;
- resolver o caminho e confirmar que permanece abaixo de `data/jobs`;
- aplicar limites de tamanho e quantidade de arquivos;
- não copiar `.env`, tokens ou credenciais;
- adicionar `data/*.sqlite3`, `data/jobs/*` e logs ao `.gitignore`;
- definir retenção e limpeza somente depois da entrega.

### 5.10 Retry e recuperação

Falhas transitórias:

```text
1ª falha -> pending, available_at = agora + 30 segundos
2ª falha -> pending, available_at = agora + 2 minutos
3ª falha -> failed
```

Falhas de validação, skill inexistente e permissão não devem ser repetidas.

Na inicialização, o worker libera jobs `running` com lock expirado. Um job
recuperado só volta a `pending` se ainda possuir tentativas; caso contrário,
vai para `failed`.

Não é confiável verificar apenas se um PID existe, pois PIDs podem ser
reutilizados. O lock deve combinar `worker_id`, heartbeat e horário.

### 5.11 Cancelamento

- `pending`: pode ser alterado imediatamente para `cancelled`;
- `running`: recebe `cancel_requested_at` e o executor é avisado;
- `completed`, `failed` ou `cancelled`: operação idempotente, sem nova mudança;
- o usuário só pode cancelar o próprio job;
- cancelar não deve apagar arquivos ou histórico imediatamente.

### 5.12 Watcher e entrega

O watcher deve usar um lease de entrega:

```text
pending -> delivering -> delivered
                     \-> failed ou pending para retry
```

Ele consulta jobs finais ainda não entregues, formata o resultado, envia ao
`chat_id` persistido e registra o `message_id` devolvido pelo Telegram.

Limitação importante: o Telegram e o SQLite não participam da mesma transação.
Se o processo cair depois do envio e antes de marcar `delivered`, existe uma
pequena janela de possível duplicidade. Portanto, “exactly once” não pode ser
garantido tecnicamente. O objetivo realista é entrega idempotente dentro do
sistema e “at least once” com deduplicação e reconciliação operacional.

### 5.13 Comandos

Adicionar gradualmente:

| Comando | Comportamento |
|---|---|
| `/status` | resumo do bot, workers e filas |
| `/filas` | quantidade por fila e estado |
| `/meusjobs` | últimos jobs do usuário |
| `/job <id>` | detalhes de um job próprio |
| `/cancelar <id>` | cancela ou solicita cancelamento |
| `/repetir <id>` | cria um novo job a partir de um job próprio permitido |
| `/skills` | lista somente skills habilitadas |
| `/ajuda` | inclui os novos comandos |

Mesmo sendo hoje um bot de usuário único, todas as consultas devem filtrar por
`user_id`. Isso evita uma falha futura quando houver mais usuários.

## 6. Arquivos planejados

### 6.1 Arquivos a criar

```text
routing/__init__.py
routing/models.py
routing/intent_router.py
routing/validator.py
queueing/__init__.py
queueing/models.py
queueing/database.py
queueing/migrations.py
queueing/job_repository.py
skills/registry.json
skills/registry.py
skills/executors/test_queue.py
agents/__init__.py
agents/base.py
agents/factory.py
agents/codex_executor.py
workers/__init__.py
workers/worker.py
workers/runner.py
delivery/__init__.py
delivery/formatter.py
delivery/service.py
delivery/watcher.py
tests/test_routing.py
tests/test_skill_registry.py
tests/test_job_repository.py
tests/test_worker.py
tests/test_delivery.py
tests/test_job_commands.py
tests/test_queue_integration.py
deploy/inemacabot-video-worker.service
deploy/inemacabot-text-worker.service
deploy/inemacabot-service-worker.service
deploy/inemacabot-watcher.service
```

### 6.2 Arquivos a alterar

| Arquivo | Alteração planejada |
|---|---|
| `bot.py` | compor novos serviços, rotear texto, criar jobs e registrar comandos |
| `config.py` | incluir configurações de banco, workers, locks, retry e diretórios |
| `codex_client.py` | extrair execução reutilizável sem alterar o contrato de resposta direta |
| `.env.example` | documentar variáveis novas sem valores secretos |
| `.gitignore` | ignorar banco, jobs, logs e artefatos |
| `requirements.txt` | alterar somente se validação escolhida exigir dependência |
| `README.md` | documentar arquitetura, execução, comandos, backup e recuperação |
| `AGENTS.md` | atualizar regras após aprovação da nova arquitetura |
| testes existentes | preservar e adaptar somente quando o contrato realmente mudar |

`auth.py`, `history.py`, `message_utils.py` e `transcription_client.py` não
precisam ser reescritos.

## 7. Variáveis de ambiente planejadas

```env
QUEUE_DATABASE_PATH=data/inemacabot.sqlite3
QUEUE_ROUTING_ENABLED=false
QUEUE_ACCEPT_WHEN_WORKER_OFFLINE=true
WORKER_POLL_INTERVAL_MS=3000
WORKER_HEARTBEAT_INTERVAL_SECONDS=10
JOB_LOCK_TIMEOUT_MINUTES=30
JOB_DEFAULT_MAX_ATTEMPTS=3
JOB_WORK_ROOT=data/jobs
JOB_EXECUTION_TIMEOUT_SECONDS=1800
JOB_MAX_OUTPUT_MB=50
DELIVERY_POLL_INTERVAL_MS=3000
DELIVERY_MAX_ATTEMPTS=5
JOB_RETENTION_DAYS=30
```

Valores devem ser validados como positivos e caminhos devem ser resolvidos com
segurança. Nenhuma dessas variáveis deve conter segredo.

## 8. Plano incremental

### Fase 0 — proteção e linha de base

Objetivo: criar um ponto seguro antes de implementar.

1. garantir árvore de trabalho compreendida;
2. criar branch `agent/filas-fase-2`;
3. registrar o resultado dos 13 testes atuais;
4. fazer backup do banco quando ele passar a existir;
5. não misturar a futura migração para API OpenAI descrita em
   `doc/plano_implementacao.md` com o trabalho de filas.

Critério de saída: comportamento atual documentado e testes verdes.

### Fase 1 — persistência e domínio

Objetivo: criar o núcleo sem conectar ao bot.

1. criar modelos e enumerações;
2. criar migration SQLite;
3. implementar repositório;
4. implementar criação, consulta, prioridade, claim, conclusão e falha;
5. implementar `available_at`, retry e locks;
6. testar concorrência com bancos temporários.

Critério de saída: dois consumidores concorrentes nunca recebem o mesmo job.

### Fase 2 — skills e roteamento

Objetivo: produzir decisões válidas sem executar tarefas.

1. criar registro e validação de skills;
2. definir `RouteDecision`;
3. implementar regras determinísticas;
4. integrar saída estruturada do Codex;
5. aplicar tentativa única de reparo;
6. manter `QUEUE_ROUTING_ENABLED=false` por padrão;
7. testar `reply`, `clarify` e `enqueue`.

Critério de saída: nenhuma decisão inválida cria job.

### Fase 3 — integração mínima no bot

Objetivo: criar jobs sem bloquear o handler.

1. autorizar o usuário antes do roteamento;
2. manter a rota direta existente;
3. persistir o job em uma transação curta;
4. responder imediatamente com ID, fila e status;
5. adicionar `/job`, `/meusjobs`, `/filas` e `/skills`;
6. manter áudio: transcrever primeiro, rotear depois;
7. confirmar que worker offline não derruba o bot.

Critério de saída: o bot continua respondendo diretamente e também consegue
registrar jobs pendentes.

### Fase 4 — primeiro worker e skill de teste

Objetivo: validar a fila `servicos`.

1. criar worker genérico limitado à fila recebida;
2. criar heartbeat;
3. criar diretório isolado;
4. implementar executor determinístico `teste-fila`;
5. aguardar 10 segundos e gerar `resultado.txt`;
6. implementar progresso, conclusão e falha;
7. testar reinício e lock expirado.

Critério de saída: job sobrevive ao reinício e gera resultado exatamente uma
vez no armazenamento.

### Fase 5 — watcher e entrega

Objetivo: fechar o ciclo com Telegram.

1. criar lease de entrega;
2. formatar resultado e erro;
3. enviar texto ou arquivo com limites;
4. persistir tentativas e `telegram_message_id`;
5. implementar retry de entrega;
6. testar falha antes e depois do envio.

Critério de saída: o usuário recebe o resultado e o sistema registra a entrega.

### Fase 6 — agentes temporários

Objetivo: executar skills reais de forma isolada.

1. definir contrato de executor;
2. criar factory por skill;
3. implementar executor Codex separado;
4. filtrar ambiente;
5. aplicar sandbox, timeout e limites;
6. implementar cancelamento cooperativo;
7. habilitar uma única skill real em homologação.

Critério de saída: uma skill real não acessa caminhos ou credenciais fora do
permitido.

### Fase 7 — filas adicionais

Objetivo: habilitar `videos` e `textos`.

1. registrar apenas skills existentes;
2. iniciar um worker por fila;
3. comprovar serialização dentro de cada fila;
4. comprovar execução paralela entre as três;
5. testar limites de disco e duração específicos por tipo.

Critério de saída: até três jobs podem executar em paralelo, nunca dois na mesma
fila.

### Fase 8 — operação e endurecimento

Objetivo: preparar operação contínua.

1. criar serviços `systemd`;
2. definir dependências e reinício;
3. documentar migration, backup e restore;
4. implementar retenção;
5. adicionar logs com contexto;
6. criar health check via comando ou tabela, sem servidor web inicialmente;
7. revisar permissões do diretório `data`;
8. executar testes de falha e recuperação;
9. liberar o roteamento por feature flag.

Critério de saída: bot, workers e watcher podem reiniciar independentemente.

## 9. Estratégia de testes

### 9.1 Testes unitários

- validação de todas as configurações;
- serialização e validação do job;
- transições de estado permitidas e proibidas;
- registro de skills;
- skill inexistente ou desabilitada;
- campos obrigatórios ausentes;
- decisões `reply`, `clarify` e `enqueue`;
- saída inválida do modelo;
- formatação de mensagens e resultados;
- cálculo de retry;
- autorização e propriedade do job.

### 9.2 Testes de repositório SQLite

- migration idempotente;
- criação e leitura;
- prioridade maior primeiro;
- desempate pelo job mais antigo;
- `available_at`;
- claim atômico com duas conexões;
- somente um job `running` por fila;
- conclusão, falha, cancelamento e repetição;
- expiração e recuperação de lock;
- heartbeat;
- filtro por usuário;
- transações revertidas em erro.

### 9.3 Testes de worker

- job concluído;
- erro transitório com retry;
- erro definitivo;
- timeout;
- cancelamento pendente e em execução;
- diretório isolado;
- stdout/stderr limitados;
- reinício do worker;
- worker offline sem afetar o bot;
- três filas em paralelo;
- ausência de paralelismo dentro da mesma fila.

### 9.4 Testes de entrega

- resultado textual curto e longo;
- envio de arquivo;
- job com erro;
- falha do Telegram;
- retry de entrega;
- lease expirado;
- nenhuma entrega para usuário/chat diferente;
- registro do `telegram_message_id`;
- simulação da janela de falha após envio.

### 9.5 Regressão

- 13 testes atuais continuam passando;
- `/start`, `/ajuda` e `/limpar` mantêm comportamento;
- texto simples continua recebendo resposta;
- áudio continua sendo transcrito quando configurado;
- usuário não autorizado não chama Codex, Groq, roteador ou repositório;
- respostas longas continuam divididas corretamente.

## 10. Logs, segurança e privacidade

Cada evento de worker deve incluir, quando aplicável:

```text
timestamp
job_id
queue
skill
worker_id
status
attempt
duration_ms
```

Não registrar:

- token do Telegram;
- chave do Groq;
- credenciais do Codex;
- conteúdo do `.env`;
- cookies;
- payload integral quando contiver dados pessoais;
- stdout/stderr sem filtragem e limite.

Outras medidas:

- validar autorização antes de persistir;
- filtrar consultas por `user_id`;
- não aceitar caminhos vindos do modelo;
- usar UUID/ULID gerado internamente;
- aplicar permissões restritas ao diretório `data`;
- não usar `shell=True`;
- não liberar prioridade urgente ao usuário sem regra explícita;
- limitar payload, resultado, arquivos, tempo e tentativas;
- não dar ao executor o ambiente completo do processo do bot.

## 11. Riscos e mitigação

| Risco | Impacto | Mitigação |
|---|---|---|
| alterar `_generate_and_reply` e quebrar respostas atuais | alto | manter rota direta intacta e proteger filas por feature flag |
| roteador do modelo inventar skill ou payload | alto | validar contra registro e nunca persistir decisão inválida |
| dois workers capturarem o mesmo job | crítico | transação SQLite e teste real com duas conexões |
| travar SQLite com transações longas | alto | nunca executar agente dentro de transação |
| Codex de conversa receber permissões de agente | crítico | clientes e prompts separados |
| executor acessar segredos ou outros diretórios | crítico | ambiente permitido, sandbox e diretório isolado |
| resultado enviado ao chat errado | crítico | persistir `user_id` e `chat_id`, conferir propriedade |
| duplicidade após queda durante envio | médio | lease, registro de mensagem e reconciliação; documentar limite externo |
| job preso em `running` | alto | heartbeat, expiração e recuperação |
| retry repetir efeito externo não idempotente | alto | skills com chave de idempotência e classificação de erros |
| disco crescer sem limite | alto | cotas e retenção |
| trava global bloquear novas mensagens | médio | não manter `conversation_lock` durante criação ou execução de job |
| misturar plano de filas com migração de provedor | alto | trabalhos e branches separados |
| comandos mostrarem jobs alheios no futuro | crítico | filtrar sempre por proprietário |
| aceitar jobs sem worker disponível | médio | feature flag e indicação de saúde/posição |

## 12. Pontos que exigem decisão antes da implementação

1. O roteamento usará o Codex CLI atual ou outro provedor estruturado?
2. O bot continuará restrito a um único usuário na primeira versão?
3. Quais skills reais estarão disponíveis depois de `teste-fila`?
4. Jobs serão aceitos quando o worker correspondente estiver offline?
5. Qual limite de tempo, disco e tamanho por fila?
6. Por quantos dias banco, logs e arquivos serão mantidos?
7. O cancelamento de jobs externos é obrigatório para todas as skills?
8. Resultados grandes serão enviados pelo Telegram, por link ou armazenados?
9. Quais dados pessoais podem ser mantidos no payload?
10. A prioridade alta/urgente será automática ou administrativa?

Recomendações iniciais:

- manter usuário único;
- usar o Codex atual somente para roteamento experimental e resposta direta;
- aceitar jobs offline, mas informar indisponibilidade do worker;
- retenção inicial de 30 dias;
- prioridade normal para todos os jobs;
- `teste-fila` como única skill habilitada em homologação;
- nenhuma skill real em produção antes dos testes de isolamento.

## 13. Critérios de aceite globais

A implementação futura estará concluída quando:

- conversa simples continuar respondendo imediatamente;
- tarefa válida gerar job e confirmação sem bloquear o bot;
- decisão inválida nunca criar job;
- job sobreviver ao reinício;
- dois workers nunca capturarem o mesmo job;
- houver no máximo um job ativo por fila;
- as três filas puderem trabalhar simultaneamente;
- retry respeitar tentativas e atrasos;
- cancelamento respeitar estado e propriedade;
- agente trabalhar somente no diretório autorizado;
- watcher entregar ao usuário/chat corretos;
- falhas de bot, worker e watcher forem recuperáveis separadamente;
- segredos não aparecerem em banco, jobs, arquivos ou logs;
- testes atuais e novos estiverem verdes;
- instalação, operação, backup e recuperação estiverem documentados.

## 14. Resultado desta etapa

Esta etapa produziu apenas análise e planejamento.

Não foram criados:

- banco;
- tabelas;
- migrations executáveis;
- workers;
- watcher;
- roteador;
- skills;
- agentes;
- comandos do bot;
- serviços;
- dependências.

A implementação deve começar somente após aprovação das decisões da seção 12 e
em uma branch própria.
