"""Integração com o Claude usando a assinatura (Claude Code CLI), sem API key.

O comando `claude` precisa estar instalado e autenticado na máquina
(rodar `claude login` uma vez antes de subir o bot). Cada usuário do
Telegram tem sua própria sessão de conversa, mantida via `--resume`
do próprio Claude Code (não precisamos guardar o histórico manualmente).
"""

import json
import logging
import subprocess

logger = logging.getLogger(__name__)

CLAUDE_TIMEOUT_SECONDS = 120


class ClaudeError(RuntimeError):
    pass


class ClaudeClient:
    def __init__(self, system_prompt: str, model: str | None = None):
        self.system_prompt = system_prompt
        self.model = model
        self._sessions: dict[int, str] = {}

    def ask(self, user_id: int, message: str) -> str:
        cmd = [
            "claude",
            "-p",
            message,
            "--output-format",
            "json",
            "--tools",
            "",
            "--system-prompt",
            self.system_prompt,
        ]
        if self.model:
            cmd += ["--model", self.model]

        session_id = self._sessions.get(user_id)
        if session_id:
            cmd += ["--resume", session_id]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=CLAUDE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise ClaudeError("O Claude demorou demais para responder.") from exc

        if result.returncode != 0:
            logger.error("claude cli retornou erro: %s", result.stderr.strip())
            raise ClaudeError("Falha ao chamar o Claude (veja o log do servidor).")

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            logger.error("saída inesperada do claude cli: %s", result.stdout[:500])
            raise ClaudeError("Resposta inesperada do Claude.") from exc

        if data.get("is_error"):
            raise ClaudeError(data.get("result") or "Erro desconhecido do Claude.")

        self._sessions[user_id] = data["session_id"]
        return data["result"]

    def clear(self, user_id: int) -> None:
        self._sessions.pop(user_id, None)
