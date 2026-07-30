"""Roteador de intenção: decide se uma mensagem é respondida direto (Rota A)
ou vira um job na fila (Rota B).

Chama o Claude Code CLI de forma independente da conversa principal (sem
`--resume`), pedindo uma resposta em JSON estrito. A saída nunca é confiada
cegamente: é validada contra o schema esperado, com uma tentativa de
correção antes de cair em `clarify`.
"""

import json
import logging
import subprocess
from dataclasses import dataclass
from typing import Any, Literal

from router.skill_registry import SkillRegistry, SkillValidationError

logger = logging.getLogger(__name__)

ROUTER_TIMEOUT_SECONDS = 30

RouteAction = Literal["reply", "clarify", "enqueue"]

_VALID_ACTIONS = {"reply", "clarify", "enqueue"}


class RouteValidationError(ValueError):
    pass


@dataclass
class RouteDecision:
    action: RouteAction
    queue: str | None = None
    skill: str | None = None
    payload: dict[str, Any] | None = None
    response: str | None = None
    question: str | None = None


def _build_system_prompt(registry: SkillRegistry) -> str:
    skills_desc = "\n".join(
        f'- "{s.name}" (fila: {s.queue}): {s.description}. '
        f"Campos obrigatórios: {s.required_fields or 'nenhum'}."
        for s in registry.list_enabled()
    )
    if not skills_desc:
        skills_desc = "(nenhuma skill disponível no momento)"

    return f"""Você é o roteador de intenção de um bot do Telegram.

Sua única tarefa é classificar a mensagem do usuário e devolver **apenas**
um JSON válido, sem texto antes ou depois, em uma destas três formas:

1. Resposta direta (conversa simples, pergunta rápida, esclarecimento):
{{"action": "reply", "response": "texto da resposta"}}

2. Pedido de esclarecimento (falta informação para criar a tarefa):
{{"action": "clarify", "question": "pergunta para o usuário"}}

3. Criação de tarefa (tarefa demorada que usa uma das skills abaixo):
{{"action": "enqueue", "queue": "nome_da_fila", "skill": "nome_da_skill", "payload": {{...}}}}

Skills disponíveis:
{skills_desc}

Regras:
- Só use "enqueue" com uma skill da lista acima, preenchendo todos os campos obrigatórios no payload.
- Se faltar informação obrigatória para a skill, use "clarify" em vez de "enqueue".
- Se a mensagem for conversa comum, pergunta rápida ou não corresponder a nenhuma skill, use "reply".
- Responda SEMPRE com um único objeto JSON válido, nada mais.
"""


def _parse_decision(raw_text: str) -> RouteDecision:
    try:
        data = json.loads(raw_text.strip())
    except json.JSONDecodeError as exc:
        raise RouteValidationError(f"JSON inválido: {exc}") from exc

    if not isinstance(data, dict):
        raise RouteValidationError("Resposta não é um objeto JSON.")

    action = data.get("action")
    if action not in _VALID_ACTIONS:
        raise RouteValidationError(f"action inválida: {action!r}")

    if action == "reply":
        response = data.get("response")
        if not isinstance(response, str) or not response.strip():
            raise RouteValidationError("action=reply exige 'response' não vazio.")
        return RouteDecision(action="reply", response=response)

    if action == "clarify":
        question = data.get("question")
        if not isinstance(question, str) or not question.strip():
            raise RouteValidationError("action=clarify exige 'question' não vazia.")
        return RouteDecision(action="clarify", question=question)

    queue = data.get("queue")
    skill = data.get("skill")
    payload = data.get("payload")
    if not isinstance(queue, str) or not queue:
        raise RouteValidationError("action=enqueue exige 'queue'.")
    if not isinstance(skill, str) or not skill:
        raise RouteValidationError("action=enqueue exige 'skill'.")
    if not isinstance(payload, dict):
        raise RouteValidationError("action=enqueue exige 'payload' como objeto.")
    return RouteDecision(action="enqueue", queue=queue, skill=skill, payload=payload)


class IntentRouter:
    def __init__(self, skill_registry: SkillRegistry, model: str | None = None):
        self._registry = skill_registry
        self._model = model

    def _call_claude(self, system_prompt: str, message: str) -> str:
        cmd = [
            "claude",
            "-p",
            message,
            "--output-format",
            "json",
            "--tools",
            "",
            "--system-prompt",
            system_prompt,
        ]
        if self._model:
            cmd += ["--model", self._model]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=ROUTER_TIMEOUT_SECONDS
        )
        if result.returncode != 0:
            raise RouteValidationError(f"claude cli falhou: {result.stderr.strip()}")

        data = json.loads(result.stdout)
        if data.get("is_error"):
            raise RouteValidationError(data.get("result") or "erro desconhecido do roteador")
        return data["result"]

    def route(self, message: str) -> RouteDecision:
        system_prompt = _build_system_prompt(self._registry)

        try:
            raw = self._call_claude(system_prompt, message)
            decision = _parse_decision(raw)
        except (RouteValidationError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            logger.warning("Roteamento inválido na 1ª tentativa: %s", exc)
            try:
                correction_prompt = (
                    system_prompt
                    + "\n\nATENÇÃO: sua resposta anterior não era um JSON válido "
                    "no formato pedido. Responda de novo, só com o JSON."
                )
                raw = self._call_claude(correction_prompt, message)
                decision = _parse_decision(raw)
            except (RouteValidationError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc2:
                logger.error("Roteamento inválido após correção: %s", exc2)
                return RouteDecision(
                    action="clarify",
                    question=(
                        "Não consegui entender exatamente o que você precisa. "
                        "Pode reformular seu pedido com mais detalhes?"
                    ),
                )

        if decision.action == "enqueue":
            try:
                self._registry.validate_payload(decision.skill, decision.payload)
            except SkillValidationError as exc:
                logger.warning("Job rejeitado pela validação de skill: %s", exc)
                return RouteDecision(
                    action="clarify",
                    question=f"{exc} Pode complementar o pedido?",
                )

        return decision
