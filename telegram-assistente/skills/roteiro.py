"""Skill placeholder da fila `textos`: gera um roteiro simples a partir de um tema.

Ainda não chama nenhum provedor de IA para gerar o conteúdo real — serve para
validar o fluxo de fila/worker/entrega da fila `textos` de ponta a ponta.
Quando a geração de verdade for implementada, só o corpo de `run()` muda.
"""

import time
from pathlib import Path
from typing import Any

from agents.executor import AgentResult

WAIT_SECONDS = 5


def run(payload: dict[str, Any], working_directory: Path) -> AgentResult:
    tema = payload.get("tema", "")

    time.sleep(WAIT_SECONDS)

    conteudo = (
        f"Roteiro (placeholder) sobre: {tema}\n\n"
        "1. Introdução ao tema\n"
        "2. Desenvolvimento\n"
        "3. Conclusão\n"
    )

    files_dir = working_directory / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    result_path = files_dir / "roteiro.txt"
    result_path.write_text(conteudo, encoding="utf-8")

    return AgentResult(success=True, result={"tema": tema, "file": str(result_path)})
