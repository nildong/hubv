"""Skill da fila `servicos`: gera a estrutura de arquivos de um site/blog.

Executa o Claude Code CLI como um agente temporário (com ferramentas de
arquivo habilitadas, diferente da conversa direta em `ai_client.py`), preso
via `cwd` à pasta `files/` isolada do job — o único diretório em que ele tem
permissão de escrita automática. Ao final, os arquivos gerados são
compactados em `site.zip` para entrega pelo watcher.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Any

from agents.executor import AgentResult
from config import load_config

AGENT_TIMEOUT_SECONDS = 600


class SiteGenerationError(RuntimeError):
    pass


def _build_prompt(tema: str, tipo: str, instrucoes_extras: str) -> str:
    prompt = (
        f"Crie os arquivos de um(a) {tipo} sobre o tema: \"{tema}\".\n"
        "Gere os arquivos diretamente no diretório atual (ex.: index.html, "
        "estilos CSS, arquivos Markdown para posts, conforme o tipo pedido). "
        "Não peça confirmação, apenas crie os arquivos."
    )
    if instrucoes_extras:
        prompt += f"\n\nInstruções adicionais: {instrucoes_extras}"
    return prompt


def _run_agent(prompt: str, cwd: Path, model: str | None) -> None:
    cmd = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
        "--permission-mode",
        "acceptEdits",
    ]
    if model:
        cmd += ["--model", model]

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=AGENT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise SiteGenerationError("O agente demorou demais para gerar o site.") from exc

    if result.returncode != 0:
        raise SiteGenerationError(f"Falha ao gerar o site: {result.stderr.strip()[:500]}")


def run(payload: dict[str, Any], working_directory: Path) -> AgentResult:
    tema = payload.get("tema", "").strip()
    tipo = payload.get("tipo", "").strip()
    instrucoes_extras = payload.get("instrucoes_extras", "").strip()

    if not tema or not tipo:
        return AgentResult(success=False, error="Campos 'tema' e 'tipo' são obrigatórios.")

    files_dir = working_directory / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    config = load_config()
    prompt = _build_prompt(tema, tipo, instrucoes_extras)

    try:
        _run_agent(prompt, cwd=files_dir, model=config.claude_model)
    except SiteGenerationError as exc:
        return AgentResult(success=False, error=str(exc))

    generated = [p for p in files_dir.iterdir()]
    if not generated:
        return AgentResult(success=False, error="O agente não gerou nenhum arquivo.")

    zip_base = working_directory / "site"
    zip_path_str = shutil.make_archive(str(zip_base), "zip", root_dir=files_dir)
    zip_path = Path(zip_path_str)

    return AgentResult(
        success=True,
        result={"tema": tema, "tipo": tipo, "file": str(zip_path)},
    )
