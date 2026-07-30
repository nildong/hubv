# Plano de implementação — Bot Telegram + Claude (assinatura) + Groq (transcrição)

Baseado em `prompt_bot_telegram.md`, com três adaptações definidas pelo usuário:

- As chaves (Telegram, APIs) serão fornecidas na hora da implementação.
- A IA usada será o **Claude via assinatura** (Claude Pro/Max), não a API paga por token.
- A **Groq** será usada para transcrição de áudio (mensagens de voz).

## Mudança de arquitetura em relação ao doc original

O doc original assume uma API compatível com OpenAI (`AI_API_KEY` + `AI_BASE_URL` + `AI_MODEL`, chamada via HTTP). Como a IA será o Claude da assinatura, a integração muda:

- Em vez de chamar uma API HTTP com `AI_API_KEY`, o bot invoca o **Claude Code CLI em modo headless** (`claude -p "..."`) ou o **Claude Agent SDK** (que por baixo usa esse mesmo CLI).
- Isso usa a sessão autenticada por `claude login` (login OAuth da conta com assinatura Pro/Max), sem precisar de API key nem billing por token.
- **Implicação de deploy:** a VPS precisa ter o `claude` CLI instalado e autenticado manualmente uma vez (`claude login` é interativo). Isso substitui a etapa "configurar `.env`" com API key por uma etapa extra de login na máquina.
- **Ressalva:** limites de uso da assinatura (semanais) se aplicam — uso muito frequente pode esbarrar no limite do plano. Como é uso pessoal (um único usuário autorizado), tende a ser tranquilo.

## Fluxo atualizado

```text
Eu envio texto ou áudio no Telegram
        ↓
Bot verifica se sou o usuário autorizado
        ↓
Se for áudio → baixa o arquivo → envia para Groq (Whisper) → recebe texto transcrito
        ↓
Texto (digitado ou transcrito) vai para o Claude via CLI/Agent SDK (sessão da assinatura)
        ↓
Claude responde
        ↓
Bot envia a resposta no Telegram (dividida se ultrapassar 4096 caracteres)
```

## Estrutura de arquivos proposta

```text
telegram-assistente/
├── bot.py              # handlers do Telegram: texto, voz, /start, /limpar, /ajuda
├── ai_client.py         # integração com Claude (subprocess/Agent SDK), sessão por usuário
├── transcription.py     # integração com Groq Whisper (download do áudio + conversão + transcrição)
├── config.py             # carrega variáveis de ambiente
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Variáveis de ambiente (revisadas)

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_USER_ID=
GROQ_API_KEY=
GROQ_TRANSCRIBE_MODEL=whisper-large-v3
CLAUDE_MODEL=              # opcional, ex: claude-sonnet-5
```

Removidos `AI_API_KEY` / `AI_BASE_URL` (não fazem sentido no modo assinatura). Na hora da implementação só é necessário informar o token do Telegram, o ID autorizado e a key da Groq — o Claude não precisa de key, só de login prévio na máquina.

## Pontos técnicos do plano

1. **Histórico de conversa**: usar o mecanismo nativo de sessão do Claude Code (`--resume <session_id>` por usuário) em vez de montar manualmente um array de mensagens — mais simples e já suportado pelo CLI. `/limpar` encerra a sessão atual e inicia uma nova.
2. **Áudio do Telegram**: mensagens de voz chegam em `.ogg/opus`. A API da Groq aceita ogg diretamente; se der problema, usar `ffmpeg` como conversão de fallback (dependência extra no sistema).
3. **Segurança**: checagem do `TELEGRAM_ALLOWED_USER_ID` em todo handler (texto, voz, comandos) — cobrindo também o handler de voz.
4. **Mensagens longas**: split em blocos de até 4096 caracteres antes de enviar.
5. **Logging**: erros básicos no terminal (falha na transcrição, falha ao chamar o Claude, timeout, etc.), sem parar o bot.
6. **Prompt de sistema**: mantém o texto do doc original, configurável (arquivo ou variável), passado como system prompt para o Claude a cada chamada/sessão.

## Passos de implementação (ordem sugerida)

1. Instalar e autenticar o Claude Code CLI na máquina/VPS (`claude login`, conta com assinatura).
2. Criar o bot no BotFather → obter `TELEGRAM_BOT_TOKEN`.
3. Descobrir o `TELEGRAM_ALLOWED_USER_ID`.
4. Criar conta/API key na Groq.
5. Montar a estrutura de arquivos.
6. Implementar `config.py` (leitura do `.env`).
7. Implementar `ai_client.py` (chamada ao Claude via CLI/Agent SDK + gestão de sessão por usuário).
8. Implementar `transcription.py` (download do áudio do Telegram + chamada à Groq).
9. Implementar `bot.py` (handlers de texto, voz, `/start`, `/limpar`, `/ajuda`, checagem de autorização, split de mensagens longas, logging).
10. Criar `requirements.txt` e `.env.example`.
11. Escrever `README.md` (BotFather, descobrir ID, configurar `.env`, `claude login`, instalar dependências, rodar localmente, manter rodando na VPS via systemd, testar integração).
12. Testar localmente: texto, áudio, `/limpar`, e mensagem de um usuário não autorizado (deve ser ignorada).
13. Deploy na VPS: instalar Python + ffmpeg + Claude CLI, autenticar, configurar serviço systemd, subir o bot.
