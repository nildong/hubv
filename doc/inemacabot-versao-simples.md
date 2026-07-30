# INEMACABOT — Versão Simples

Crie um projeto simples chamado `inemacabot`.

O sistema será um bot do Telegram feito em Node.js com TypeScript.

## Objetivo

Receber uma mensagem do usuário e decidir entre três opções:

1. responder diretamente;
2. pedir uma informação que está faltando;
3. chamar uma skill cadastrada.

Não crie banco de dados, Redis, filas, painel, Docker ou estrutura complexa nesta primeira versão.

## Estrutura

```text
inemacabot/
├── src/
│   ├── index.ts
│   ├── bot.ts
│   ├── dispatcher.ts
│   ├── llm.ts
│   ├── skills.ts
│   └── executor.ts
├── config/
│   └── skills.json
├── .env.example
├── package.json
├── tsconfig.json
└── README.md
```

## Funcionamento

Fluxo:

1. O usuário envia uma mensagem no Telegram.
2. O bot recebe a mensagem.
3. A LLM interpreta o pedido.
4. A LLM decide entre responder, perguntar ou chamar uma skill.
5. O sistema entrega o resultado ao usuário.

A LLM deve retornar somente este JSON:

```json
{
  "action": "respond | ask | skill",
  "response": "mensagem para o usuário",
  "skill": "nome da skill ou null",
  "input": {}
}
```

## Exemplo 1 — Responder

Usuário:

> O que é um agente de IA?

Resposta da LLM:

```json
{
  "action": "respond",
  "response": "Um agente de IA é um sistema que recebe um objetivo e executa ações para alcançá-lo.",
  "skill": null,
  "input": {}
}
```

## Exemplo 2 — Pedir informação

Usuário:

> Crie um vídeo.

Resposta:

```json
{
  "action": "ask",
  "response": "Qual é o assunto do vídeo?",
  "skill": "video-explicativo",
  "input": {}
}
```

## Exemplo 3 — Chamar uma skill

Usuário:

> Crie um vídeo sobre agentes de IA.

Resposta:

```json
{
  "action": "skill",
  "response": "Vou iniciar a criação do vídeo.",
  "skill": "video-explicativo",
  "input": {
    "assunto": "agentes de IA"
  }
}
```

## Skills

Crie o arquivo `config/skills.json`:

```json
{
  "skills": [
    {
      "name": "video-explicativo",
      "description": "Cria um vídeo explicativo.",
      "required_fields": ["assunto"]
    },
    {
      "name": "criar-texto",
      "description": "Cria textos e roteiros.",
      "required_fields": ["assunto"]
    },
    {
      "name": "executar-automacao",
      "description": "Executa uma automação.",
      "required_fields": ["nome"]
    }
  ]
}
```

## Função de cada arquivo

### `index.ts`

Inicia o projeto.

### `bot.ts`

Conecta ao Telegram e recebe mensagens.

### `llm.ts`

Envia a mensagem para a IA e recebe a decisão em JSON.

### `dispatcher.ts`

Analisa a decisão e escolhe o caminho.

### `skills.ts`

Carrega as skills e verifica os campos obrigatórios.

### `executor.ts`

Executa uma simulação da skill.

Na primeira versão, não execute serviços reais.

Apenas retorne algo como:

> Skill video-explicativo executada com sucesso.

## Regras

- Use TypeScript.
- Use a biblioteca grammY ou Telegraf.
- Use variáveis de ambiente para o token do Telegram e a chave da IA.
- Trate erros.
- Não use banco de dados.
- Não use Redis.
- Não use filas.
- Não use Docker.
- Não crie painel.
- Não crie sistema de usuários.
- Não crie permissões avançadas.
- Não execute comandos no computador.
- Não adicione recursos que não foram pedidos.

## Arquivo `.env.example`

```env
TELEGRAM_BOT_TOKEN=
OPENAI_API_KEY=
OPENAI_MODEL=
```

## Entrega

Crie todos os arquivos.

Inclua no `README.md`:

1. como instalar;
2. como configurar;
3. como iniciar;
4. como testar.

Antes de começar, mostre um plano com no máximo 5 etapas.

Depois crie o projeto completo e teste o fluxo básico.

## Arquitetura inicial

```text
Telegram
   ↓
INEMACABOT
   ↓
Entende a mensagem
   ↓
Responde, pergunta ou chama skill
   ↓
Entrega o resultado
```

O foco da primeira versão é apenas provar que o fluxo funciona.

Banco de dados, filas, workers reais e acompanhamento de tarefas podem ser adicionados depois.
