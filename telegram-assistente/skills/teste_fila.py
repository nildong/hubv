"""Skill de teste: valida o fluxo completo de fila ponta a ponta.

Recebe um texto, aguarda alguns segundos (simulando trabalho), escreve o
texto em `files/resultado.txt` dentro da pasta isolada do job e conclui.
"""

import time
from pathlib import Path
from typing import Any

from agents.executor import AgentResult

WAIT_SECONDS = 10


def run(payload: dict[str, Any], working_directory: Path) -> AgentResult:
    texto = payload.get("texto", "")

    time.sleep(WAIT_SECONDS)

    files_dir = working_directory / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    result_path = files_dir / "resultado.txt"
    result_path.write_text(texto, encoding="utf-8")

    return AgentResult(
        success=True,
        result={"texto": texto, "file": str(result_path)},
    )
