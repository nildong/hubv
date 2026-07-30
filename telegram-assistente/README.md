# Telegram Assistente

Bot pessoal para Telegram: recebe texto ou áudio, encaminha para o Claude
(usando sua **assinatura** Claude Pro/Max, sem API key) e responde no chat.
Áudios são transcritos primeiro pela **Groq** (Whisper).

## Como funciona

```text
Você envia texto ou áudio no Telegram
        ↓
Bot verifica se você é o usuário autorizado
        ↓
Se for áudio → Groq transcreve para texto
        ↓
Texto vai para o Claude Code CLI (sessão da sua assinatura)
        ↓
Claude responde
        ↓
Bot envia a resposta no Telegram (dividida se for muito longa)
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

## 8. Manter rodando em uma VPS

Use `systemd` para manter o bot ativo e reiniciar sozinho se cair.

1. Copie o projeto para a VPS (ex: `/opt/telegram-assistente`).
2. Rode `claude login` na VPS (passo 3 acima).
3. Crie o venv e instale as dependências (passo 5) dentro da VPS.
4. Copie `deploy/telegram-assistente.service.example` para
   `/etc/systemd/system/telegram-assistente.service` e ajuste `User`,
   `WorkingDirectory` e `ExecStart` para os caminhos reais.
5. Ative o serviço:

```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-assistente
sudo systemctl start telegram-assistente
sudo systemctl status telegram-assistente
```

6. Ver logs em tempo real:

```bash
sudo journalctl -u telegram-assistente -f
```

## Estrutura do projeto

```text
telegram-assistente/
├── bot.py                # handlers do Telegram (texto, voz, comandos)
├── ai_client.py            # integração com o Claude via CLI (assinatura)
├── transcription.py         # integração com a Groq (transcrição de áudio)
├── config.py                 # carrega e valida variáveis de ambiente
├── system_prompt.txt          # instrução de sistema do assistente (editável)
├── requirements.txt
├── .env.example
├── .env                        # suas chaves reais (não versionar)
├── .gitignore
├── deploy/telegram-assistente.service.example
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
