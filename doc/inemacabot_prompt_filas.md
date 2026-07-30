# Prompt para implementar filas no `inemacabot`

## Missão

Você está trabalhando no projeto `inemacabot`.

Este projeto já possui um bot que recebe mensagens do usuário e responde utilizando inteligência artificial.

Sua missão é analisar o sistema atual e implementar um sistema de filas, workers, agentes temporários, skills e acompanhamento de resultados.

## Regras obrigatórias

- Não crie um projeto novo.
- Não substitua o bot atual.
- Não quebre o fluxo de respostas que já funciona.
- Não faça alterações grandes antes de entender a arquitetura existente.
- Reaproveite o máximo possível do código atual.
- Crie uma cópia de segurança ou uma branch antes das alterações.
- Primeiro analise, depois proponha e somente então implemente.

---

## Objetivo do sistema

O fluxo final deve funcionar assim:

```text
Usuário envia uma mensagem
→ inemacabot recebe
→ identifica o usuário
→ interpreta a intenção
→ decide se responde imediatamente ou cria uma tarefa
→ identifica a skill necessária
→ escolhe a fila
→ registra o job
→ informa ao usuário que o pedido entrou na fila
→ um worker captura o job
→ o worker inicia um agente temporário
→ o agente executa a skill
→ o resultado é salvo
→ um watcher identifica a conclusão
→ o inemacabot envia o resultado ao usuário
```

---

## Conceitos do sistema

### Bot

O `inemacabot` é a porta de entrada.

Ele deve:

- receber mensagens;
- identificar o usuário;
- interpretar o pedido;
- responder diretamente quando não for necessária execução;
- criar jobs quando o pedido exigir processamento;
- informar o status;
- entregar o resultado.

O bot não deve executar tarefas pesadas dentro do handler da mensagem.

### Fila

A fila guarda os pedidos que precisam ser processados.

Cada pedido armazenado é um `job`.

A fila controla:

- ordem;
- prioridade;
- status;
- tentativas;
- horário de criação;
- execução;
- resultado;
- falhas.

### Worker

O worker é um processo permanente.

Ele deve:

1. consultar sua fila;
2. encontrar o próximo job;
3. bloquear o job para impedir execução duplicada;
4. marcar como executando;
5. iniciar o agente;
6. acompanhar a execução;
7. salvar o resultado;
8. marcar como concluído ou com erro;
9. passar para o próximo job.

O worker não é a skill.

### Agente temporário

O agente é criado pelo worker para executar um job específico.

Ele recebe:

- a solicitação do usuário;
- os dados do job;
- a skill;
- o contexto permitido;
- a pasta de trabalho;
- as ferramentas disponíveis.

Quando termina, o agente é encerrado.

### Skill

A skill contém as instruções especializadas para realizar uma atividade.

Exemplos:

- criar um vídeo;
- gerar um roteiro;
- pesquisar um assunto;
- criar um book;
- analisar um documento;
- executar uma automação;
- produzir um relatório.

### Watcher

O watcher procura jobs concluídos ou com erro que ainda não foram entregues.

Ele envia o resultado ao usuário e registra que a entrega foi realizada.

---

## Etapa 1 — analisar o projeto atual

Antes de alterar qualquer arquivo, examine todo o projeto.

Identifique:

- linguagem utilizada;
- framework utilizado;
- arquivo de inicialização;
- integração com Telegram, WhatsApp, web ou outro canal;
- handlers de mensagens;
- fluxo atual da IA;
- modelo e provedor utilizado;
- banco de dados;
- sistema de autenticação;
- estrutura de configuração;
- arquivos `.env`;
- serviços existentes;
- sistema de logs;
- comandos disponíveis;
- testes existentes;
- como o sistema envia respostas ao usuário;
- se as respostas são síncronas ou assíncronas;
- se já existe algum conceito de tarefa, job, fila ou status;
- se já existe integração com Claude Code, Codex, OpenAI, scripts ou processos externos.

Procure especialmente por termos como:

```text
queue
job
worker
task
process
status
pending
running
completed
failed
skill
agent
spawn
exec
cron
watcher
```

### Entrega obrigatória da análise

Antes de implementar, apresente:

#### 1. Arquitetura atual

Explique de forma simples:

- onde a mensagem entra;
- onde a IA é chamada;
- onde a resposta é montada;
- onde a resposta é enviada;
- qual banco é usado;
- como o sistema é iniciado.

#### 2. O que pode ser reaproveitado

Liste os módulos existentes que podem ser mantidos.

#### 3. O que está faltando

Liste os componentes necessários para implementar as filas.

#### 4. Riscos

Informe quais partes podem quebrar caso sejam alteradas.

#### 5. Plano de implementação

Informe:

- arquivos que serão criados;
- arquivos que serão alterados;
- banco ou tabelas que serão criados;
- serviços que serão adicionados;
- testes que serão realizados.

Não faça uma reescrita completa do projeto.

---

## Etapa 2 — decidir entre resposta direta e job

Nem toda mensagem deve entrar em uma fila.

### Rota A — resposta direta

Use para:

- conversa simples;
- perguntas rápidas;
- esclarecimentos;
- ajuda;
- consulta que possa ser respondida imediatamente;
- perguntas sobre o próprio sistema.

```text
usuário
→ bot
→ IA
→ resposta
```

### Rota B — criação de job

Use para:

- tarefas demoradas;
- geração de arquivos;
- pesquisa aprofundada;
- criação de vídeos;
- geração de books;
- automações;
- processamento de áudio;
- processamento de documentos;
- tarefas que usam agentes ou ferramentas externas.

```text
usuário
→ bot
→ interpretação
→ fila
→ worker
→ agente
→ skill
→ resultado
→ entrega
```

A interpretação deve retornar uma estrutura previsível.

Exemplo:

```json
{
  "action": "enqueue",
  "queue": "videos",
  "skill": "video-explicativo",
  "payload": {
    "tema": "Como funcionam agentes de IA",
    "duracao": "60 segundos"
  }
}
```

Para resposta direta:

```json
{
  "action": "reply",
  "response": "Texto da resposta"
}
```

Para informação incompleta:

```json
{
  "action": "clarify",
  "question": "Qual deve ser a duração do vídeo?"
}
```

---

## Etapa 3 — filas iniciais

Crie inicialmente três filas:

```text
videos
textos
servicos
```

### Fila `videos`

Exemplos:

- vídeo explicativo;
- vídeo de curso;
- vídeo demonstrativo;
- reel;
- edição;
- avatar;
- trailer.

### Fila `textos`

Exemplos:

- roteiro;
- artigo;
- resumo;
- transcrição;
- dublagem;
- tradução;
- locução;
- legenda.

### Fila `servicos`

Exemplos:

- pesquisa;
- análise;
- criação de book;
- relatório;
- automação;
- processamento técnico;
- geração de documento.

As três filas devem poder funcionar simultaneamente.

Dentro de cada fila, inicialmente deve existir apenas um job em execução por vez.

```text
fila videos   → 1 job executando
fila textos   → 1 job executando
fila servicos → 1 job executando
```

Assim, o sistema pode executar até três jobs simultaneamente, desde que cada um esteja em uma fila diferente.

---

## Etapa 4 — modelo do job

Crie um modelo central de job.

```ts
type QueueName = "videos" | "textos" | "servicos";

type JobStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

interface Job {
  id: string;
  queue: QueueName;
  skill: string;
  payload: Record<string, unknown>;
  status: JobStatus;
  priority: number;
  attempts: number;
  maxAttempts: number;
  userId: string;
  chatId: string;
  sourceMessageId?: string;
  progress: number;
  result?: Record<string, unknown>;
  error?: string;
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
  lockedBy?: string;
  lockedAt?: string;
  deliveryStatus: "pending" | "delivered" | "failed";
  deliveredAt?: string;
  deliveryAttempts: number;
}
```

Não salve no job:

- chave de API;
- token do bot;
- senha;
- conteúdo completo do `.env`;
- credenciais;
- cookies.

---

## Etapa 5 — banco da fila

Use o banco já existente no projeto.

Caso o projeto não possua banco adequado, use SQLite na primeira versão.

Não instale Redis, RabbitMQ ou Kafka neste primeiro momento.

Crie uma migration segura.

```sql
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    queue TEXT NOT NULL,
    skill TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    priority INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    user_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    source_message_id TEXT,
    progress INTEGER NOT NULL DEFAULT 0,
    result TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    locked_by TEXT,
    locked_at TEXT,
    delivery_status TEXT NOT NULL DEFAULT 'pending',
    delivered_at TEXT,
    delivery_attempts INTEGER NOT NULL DEFAULT 0,
    delivery_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_queue_status
ON jobs(queue, status, priority, created_at);

CREATE INDEX IF NOT EXISTS idx_jobs_user
ON jobs(user_id, created_at);

CREATE INDEX IF NOT EXISTS idx_jobs_delivery
ON jobs(delivery_status, completed_at);
```

Implemente um repositório com:

```text
createJob
getJob
getJobsByUser
claimNextJob
updateJobProgress
completeJob
failJob
cancelJob
retryJob
releaseExpiredLocks
getQueueStats
markDelivered
markDeliveryFailed
```

A operação `claimNextJob` deve ser atômica.

Dois workers nunca podem capturar o mesmo job.

---

## Etapa 6 — registro das skills

Crie um registro central.

Exemplo:

```text
config/skills.json
```

```json
{
  "video-explicativo": {
    "queue": "videos",
    "description": "Cria um vídeo explicativo",
    "enabled": true,
    "requiredFields": ["tema"]
  },
  "roteiro": {
    "queue": "textos",
    "description": "Cria um roteiro",
    "enabled": true,
    "requiredFields": ["tema"]
  },
  "pesquisa": {
    "queue": "servicos",
    "description": "Executa uma pesquisa aprofundada",
    "enabled": true,
    "requiredFields": ["tema"]
  }
}
```

O sistema não pode inventar uma skill inexistente.

Antes de criar o job:

1. valide se a skill existe;
2. valide se está habilitada;
3. valide a fila;
4. valide os campos obrigatórios;
5. valide as permissões do usuário.

Caso falte informação, pergunte ao usuário antes de criar o job.

---

## Etapa 7 — roteador

Crie um módulo central de roteamento.

```text
src/router/
├── intent-router.ts
├── queue-router.ts
├── skill-validator.ts
└── request-normalizer.ts
```

```ts
interface RouteDecision {
  action: "reply" | "clarify" | "enqueue";
  queue?: QueueName;
  skill?: string;
  payload?: Record<string, unknown>;
  response?: string;
  question?: string;
}
```

O código deve validar a resposta da IA.

Não confie diretamente em JSON produzido pelo modelo.

Caso a resposta da IA esteja inválida:

- registre o erro;
- tente corrigir uma vez;
- se continuar inválida, peça esclarecimento ao usuário;
- não crie job incompleto.

---

## Etapa 8 — workers

Crie três workers separados.

```text
src/workers/
├── worker-base.ts
├── video-worker.ts
├── text-worker.ts
├── service-worker.ts
└── worker-runner.ts
```

Cada worker deve receber uma fila específica.

```ts
new Worker({
  queue: "videos",
  concurrency: 1
});
```

O worker deve:

1. procurar job pendente;
2. capturar o job atomicamente;
3. marcar como `running`;
4. incrementar tentativas;
5. criar uma pasta exclusiva para o job;
6. iniciar o agente;
7. registrar progresso;
8. capturar o resultado;
9. marcar como `completed`;
10. em caso de erro, marcar como `failed` ou retornar para `pending`;
11. aguardar o próximo job.

```env
WORKER_POLL_INTERVAL_MS=3000
```

---

## Etapa 9 — executor do agente

Crie uma abstração de execução.

```ts
interface AgentExecutor {
  execute(input: {
    jobId: string;
    skill: string;
    payload: Record<string, unknown>;
    workingDirectory: string;
  }): Promise<{
    success: boolean;
    result?: Record<string, unknown>;
    error?: string;
  }>;
}
```

O executor deve poder ser trocado futuramente.

Implemente inicialmente com a tecnologia já usada pelo projeto.

Pode ser:

- chamada direta a uma API;
- Claude Code;
- Codex;
- script Python;
- script Node;
- processo externo;
- outro agente já existente.

Não fixe o sistema inteiro em um único provedor.

```text
src/agents/
├── agent-executor.ts
├── api-agent-executor.ts
├── process-agent-executor.ts
└── agent-factory.ts
```

### Segurança na execução

Ao iniciar processo externo:

- use `spawn`;
- use argumentos separados;
- nunca concatene diretamente o texto do usuário em um comando de shell;
- defina timeout;
- limite tamanho de stdout e stderr;
- registre código de saída;
- permita cancelamento;
- use diretório isolado;
- não exponha variáveis sensíveis;
- elimine o processo em caso de timeout.

Não faça:

```ts
exec(`comando ${textoDoUsuario}`);
```

Faça algo semelhante:

```ts
spawn("comando", ["--input", textoDoUsuario], {
  cwd: workingDirectory,
  shell: false
});
```

---

## Etapa 10 — pasta isolada por job

```text
data/jobs/<job-id>/
├── input.json
├── output.json
├── stdout.log
├── stderr.log
└── files/
```

O agente só deve trabalhar dentro dessa pasta, salvo quando uma skill exigir outro caminho autorizado.

---

## Etapa 11 — watcher

```text
src/delivery/
├── watcher.ts
├── result-formatter.ts
├── delivery-service.ts
└── delivery-repository.ts
```

O watcher deve procurar:

```text
completed + delivery_status=pending
failed + delivery_status=pending
```

Fluxo:

```text
job termina
→ watcher encontra
→ identifica usuário e canal
→ formata o resultado
→ envia
→ marca como entregue
```

A entrega deve ser idempotente.

Reiniciar o bot ou o watcher não pode entregar o mesmo resultado duas vezes.

---

## Etapa 12 — respostas ao usuário

Ao entrar na fila:

```text
Seu pedido foi adicionado à fila.

Job: job_01...
Fila: vídeos
Skill: video-explicativo
Status: aguardando
Posição aproximada: 2
```

Ao iniciar:

```text
Seu pedido começou a ser processado.

Job: job_01...
Progresso: 10%
```

Ao concluir:

```text
Seu pedido foi concluído.

Job: job_01...
Resultado: disponível
```

Ao falhar:

```text
Não foi possível concluir seu pedido.

Job: job_01...
Tentativas: 3
Motivo: erro durante a execução
```

---

## Etapa 13 — comandos do bot

Adicione ou adapte:

```text
/status
/filas
/meusjobs
/job <id>
/cancelar <id>
/repetir <id>
/skills
/ajuda
```

O usuário somente pode visualizar e manipular os próprios jobs.

---

## Etapa 14 — prioridade

Sugestão:

```text
0  = normal
10 = alta
20 = urgente
```

A seleção deve seguir:

```text
maior prioridade primeiro
→ em caso de empate, job mais antigo primeiro
```

---

## Etapa 15 — retry

Cada job deve possuir:

```text
attempts
maxAttempts
```

Fluxo:

```text
erro
→ attempts < maxAttempts
→ volta para pending
→ aguarda nova execução
```

Atrasos sugeridos:

```text
1ª falha → aguardar 30 segundos
2ª falha → aguardar 2 minutos
3ª falha → falha definitiva
```

Adicione `available_at` se necessário.

---

## Etapa 16 — recuperação após reinício

Na inicialização de cada worker:

1. procure jobs `running`;
2. verifique se o processo ainda existe;
3. verifique o tempo do lock;
4. libere locks expirados;
5. recoloque o job como `pending` ou marque como `failed`;
6. incremente a tentativa;
7. registre a recuperação.

```env
JOB_LOCK_TIMEOUT_MINUTES=30
```

---

## Etapa 17 — serviços separados

```text
inemacabot.service
inemacabot-video-worker.service
inemacabot-text-worker.service
inemacabot-service-worker.service
inemacabot-watcher.service
```

O bot deve continuar respondendo mesmo que um worker esteja fora do ar.

```env
ACCEPT_JOBS_WHEN_WORKER_OFFLINE=true
```

---

## Etapa 18 — health check

Crie heartbeat com:

```text
worker_id
queue
status
last_seen_at
current_job_id
started_at
```

---

## Etapa 19 — logs

Cada log deve conter:

```text
timestamp
job_id
queue
skill
worker_id
status
attempt
duration
```

Não registre tokens, senhas, chaves, cookies ou conteúdo do `.env`.

---

## Etapa 20 — testes

Crie testes para:

1. resposta direta sem fila;
2. criação correta de job;
3. roteamento para vídeos;
4. roteamento para textos;
5. roteamento para serviços;
6. skill inexistente;
7. campos obrigatórios ausentes;
8. seleção por prioridade;
9. seleção por data;
10. captura atômica;
11. dois workers não pegarem o mesmo job;
12. apenas um job ativo por fila;
13. três filas funcionando em paralelo;
14. conclusão;
15. falha;
16. retry;
17. cancelamento;
18. recuperação após reinício;
19. entrega única;
20. isolamento entre usuários;
21. worker offline;
22. bot funcionando com worker offline.

---

## Etapa 21 — implementação em fases

### Fase 1 — diagnóstico

Apenas analise o projeto.

Entregue:

- arquitetura atual;
- fluxo atual;
- banco atual;
- arquivos importantes;
- componentes reutilizáveis;
- riscos;
- plano.

### Fase 2 — núcleo da fila

Implemente:

- modelo de job;
- migration;
- repository;
- registro de skills;
- roteador;
- criação de job.

### Fase 3 — primeiro worker

Implemente somente um worker inicialmente:

```text
servicos
```

Use uma skill simples para validar todo o fluxo.

### Fase 4 — outras filas

Depois que o primeiro fluxo estiver funcionando, implemente:

```text
videos
textos
```

### Fase 5 — operação

Implemente:

- systemd ou Docker;
- health check;
- logs;
- retry;
- cancelamento;
- recuperação;
- documentação;
- testes finais.

---

## Primeiro teste prático

Crie temporariamente uma skill:

```text
teste-fila
```

Ela deve:

1. receber um texto;
2. aguardar 10 segundos;
3. criar um arquivo `resultado.txt`;
4. escrever o texto recebido;
5. concluir o job;
6. enviar o arquivo ou conteúdo ao usuário.

Esse teste deve comprovar:

- criação do job;
- persistência;
- execução;
- worker separado;
- acompanhamento;
- conclusão;
- entrega;
- ausência de duplicidade.

---

## Resultado final esperado

O `inemacabot` continuará respondendo perguntas normais imediatamente.

Quando receber uma tarefa, ele deverá:

1. interpretar;
2. escolher a skill;
3. escolher a fila;
4. criar o job;
5. responder imediatamente que o job foi criado;
6. liberar o bot para outras mensagens;
7. deixar o worker executar;
8. acompanhar o resultado;
9. entregar ao mesmo usuário;
10. registrar todo o histórico.

Não apenas descreva a solução.

Implemente de forma incremental, teste cada etapa e documente tudo.
