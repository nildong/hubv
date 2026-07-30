"""Skill placeholder da fila `videos`: gera um plano de vídeo a partir de um tema.

Ainda não produz vídeo de verdade (nenhuma integração de geração de vídeo
existe neste repositório) — só valida o fluxo de fila/worker/entrega da
fila `videos`. Trocar por uma integração real no futuro não muda o worker
nem o roteador, só o corpo de `run()`.
"""

import time
from pathlib import Path
from typing import Any

from agents.executor import AgentResult

WAIT_SECONDS = 5


def run(payload: dict[str, Any], working_directory: Path) -> AgentResult:
    tema = payload.get("tema", "")
    duracao = payload.get("duracao", "não especificada")

    time.sleep(WAIT_SECONDS)

    conteudo = (
        f"Plano de vídeo (placeholder) sobre: {tema}\n"
        f"Duração alvo: {duracao}\n\n"
        "Cena 1: abertura\n"
        "Cena 2: explicação principal\n"
        "Cena 3: encerramento\n"
    )

    files_dir = working_directory / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    result_path = files_dir / "plano_video.txt"
    result_path.write_text(conteudo, encoding="utf-8")

    return AgentResult(
        success=True,
        result={"tema": tema, "duracao": duracao, "file": str(result_path)},
    )
