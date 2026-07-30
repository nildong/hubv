# Instrução para criar um bot simples no Telegram

Crie um sistema simples de bot para Telegram.

## Objetivo

O bot deve receber as mensagens que eu enviar pelo Telegram, encaminhar o texto para uma inteligência artificial e devolver a resposta diretamente no Telegram.

O bot não precisa executar automações, chamar outros agentes, controlar filas ou possuir várias funções.

Ele deve apenas:

1. receber minha mensagem;
2. entender o que eu pedi;
3. gerar uma resposta usando uma API de inteligência artificial;
4. enviar a resposta de volta para mim no Telegram.

## Funcionamento esperado

O fluxo deve ser:

```text
Eu envio uma mensagem no Telegram
        ↓
O bot recebe a mensagem
        ↓
O bot envia a mensagem para a API da IA
        ↓
A IA gera uma resposta
        ↓
O bot responde no Telegram
```

## Requisitos

- Usar a API oficial do Telegram Bot.
- Usar Python.
- Criar um projeto simples e organizado.
- Utilizar variáveis de ambiente para guardar as chaves.
- Nunca colocar tokens ou chaves diretamente no código.
- Permitir definir qual modelo de IA será utilizado.
- Responder somente ao meu usuário do Telegram.
- Ignorar mensagens enviadas por pessoas não autorizadas.
- Registrar erros básicos no terminal.
- Dividir respostas muito grandes, caso ultrapassem o limite do Telegram.
- Manter um pequeno histórico da conversa para que a IA entenda o contexto.
- Criar uma instrução de sistema configurável para definir o comportamento do assistente.

## Variáveis de ambiente

Criar um arquivo `.env.example` com:

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_USER_ID=
AI_API_KEY=
AI_BASE_URL=
AI_MODEL=
```

O sistema deve funcionar com APIs compatíveis com o formato da OpenAI.

## Comportamento do bot

A instrução principal da IA deve ser:

```text
Você é meu assistente pessoal dentro do Telegram.

Responda diretamente ao que eu pedir.

Seja claro, prático e objetivo.

Não invente informações.

Quando não souber alguma coisa, informe claramente.

Não execute tarefas externas.

Não chame outros agentes.

Não crie fluxos complexos.

Sua única função é conversar comigo, entender minhas solicitações e responder no próprio Telegram.
```

## Comandos básicos

Adicionar somente estes comandos:

### `/start`

Mostra:

```text
Olá! Sou seu assistente pessoal. Envie uma mensagem e eu responderei.
```

### `/limpar`

Apaga o histórico da conversa.

### `/ajuda`

Mostra uma explicação curta sobre como usar o bot.

## Segurança

O bot deve verificar o ID do usuário antes de responder.

Exemplo de regra:

```python
if user_id != TELEGRAM_ALLOWED_USER_ID:
    não responder
```

Não permitir que usuários desconhecidos utilizem a API de inteligência artificial.

## Estrutura sugerida

```text
telegram-assistente/
├── bot.py
├── ai_client.py
├── config.py
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Entrega esperada

Crie todos os arquivos necessários.

Inclua no `README.md`:

1. como criar um bot usando o BotFather;
2. como descobrir meu ID do Telegram;
3. como configurar o arquivo `.env`;
4. como instalar as dependências;
5. como iniciar o bot;
6. como manter o bot funcionando em uma VPS;
7. como testar se a integração está funcionando.

Utilize código simples, bem comentado e fácil de modificar.

Ao terminar, revise o projeto, corrija possíveis erros e apresente os comandos exatos para executar o sistema.
