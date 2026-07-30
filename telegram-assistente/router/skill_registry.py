"""Carrega e valida o registro de skills (config/skills.json).

O sistema não pode inventar uma skill inexistente: toda skill usada em um
job precisa estar cadastrada aqui, habilitada, e com os campos obrigatórios
presentes no payload.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from jobs.models import QUEUE_NAMES, QueueName


class SkillValidationError(ValueError):
    pass


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    queue: QueueName
    description: str
    enabled: bool
    required_fields: list[str]


class SkillRegistry:
    def __init__(self, skills_path: str | Path):
        path = Path(skills_path)
        raw = json.loads(path.read_text(encoding="utf-8"))

        skills: dict[str, SkillDefinition] = {}
        for name, definition in raw.items():
            queue = definition["queue"]
            if queue not in QUEUE_NAMES:
                raise SkillValidationError(
                    f"Skill '{name}' aponta para fila desconhecida: '{queue}'"
                )
            skills[name] = SkillDefinition(
                name=name,
                queue=queue,
                description=definition.get("description", ""),
                enabled=bool(definition.get("enabled", False)),
                required_fields=list(definition.get("requiredFields", [])),
            )
        self._skills = skills

    def get(self, name: str) -> SkillDefinition | None:
        return self._skills.get(name)

    def list_enabled(self) -> list[SkillDefinition]:
        return [s for s in self._skills.values() if s.enabled]

    def validate_payload(self, name: str, payload: dict) -> None:
        """Levanta SkillValidationError se a skill não existir, estiver desabilitada
        ou faltar algum campo obrigatório no payload."""
        skill = self.get(name)
        if skill is None:
            raise SkillValidationError(f"Skill '{name}' não existe.")
        if not skill.enabled:
            raise SkillValidationError(f"Skill '{name}' está desabilitada.")

        missing = [field for field in skill.required_fields if field not in payload]
        if missing:
            raise SkillValidationError(
                f"Campos obrigatórios ausentes para a skill '{name}': {', '.join(missing)}"
            )
