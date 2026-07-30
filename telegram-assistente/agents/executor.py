"""Abstração de execução de agente/skill.

O worker não sabe COMO uma skill é executada — só chama `AgentExecutor.execute()`.
Isso permite trocar a implementação no futuro (função Python local, chamada ao
Claude Code CLI, script externo, etc.) sem alterar o worker.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol


@dataclass
class AgentResult:
    success: bool
    result: dict[str, Any] | None = None
    error: str | None = None


class AgentExecutor(Protocol):
    def execute(
        self,
        *,
        job_id: str,
        skill: str,
        payload: dict[str, Any],
        working_directory: Path,
    ) -> AgentResult: ...


SkillFunction = Callable[[dict[str, Any], Path], AgentResult]


class SkillDispatchExecutor:
    """Executor que despacha cada skill para uma função Python registrada.

    Usado para skills locais/simples (como a `teste-fila`). Skills que
    precisarem de um agente de verdade (ex.: Claude Code CLI com tools)
    podem registrar aqui uma função que faça esse spawn internamente.
    """

    def __init__(self, skill_functions: dict[str, SkillFunction]):
        self._skill_functions = skill_functions

    def execute(
        self,
        *,
        job_id: str,
        skill: str,
        payload: dict[str, Any],
        working_directory: Path,
    ) -> AgentResult:
        function = self._skill_functions.get(skill)
        if function is None:
            return AgentResult(success=False, error=f"Skill '{skill}' sem executor registrado.")

        try:
            return function(payload, working_directory)
        except Exception as exc:  # noqa: BLE001 - isolamento de falha de skill
            return AgentResult(success=False, error=str(exc))
