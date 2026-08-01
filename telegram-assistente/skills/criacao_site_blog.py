"""Skill da fila `servicos`: gera a estrutura de arquivos de um site/blog.

Executa o Claude Code CLI como um agente temporário (com ferramentas de
arquivo habilitadas, diferente da conversa direta em `ai_client.py`), preso
via `cwd` à pasta `files/` isolada do job — o único diretório em que ele tem
permissão de escrita automática. Antes de chamar o agente, baixa fotos reais
da API da Pexels para `files/images/`, para que o site use imagens de verdade
em vez de placeholders ou URLs inventadas. Ao final, os arquivos gerados são
compactados em `site.zip` para entrega pelo watcher.
"""

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

import requests

from agents.executor import AgentResult
from config import load_config

logger = logging.getLogger(__name__)

AGENT_TIMEOUT_SECONDS = 600
PEXELS_TIMEOUT_SECONDS = 20
PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"
MAX_IMAGENS = 6

DESIGN_GUIDELINES = """
Diretrizes de design a seguir rigorosamente:
- Tipografia: importe 2 fontes do Google Fonts via <link> no <head> (uma para
  títulos, outra para corpo de texto — combine-as com bom contraste de peso,
  ex.: uma serifada de destaque + uma sans-serif neutra para leitura).
- Paleta de cores: defina uma paleta coesa (cor primária, secundária, neutros
  e fundo) como variáveis CSS (:root { --cor-primaria: ...; }); evite usar
  mais de 4-5 cores.
- Layout: use CSS Grid ou Flexbox para uma composição moderna, com espaçamento
  consistente (escala de spacing, ex.: 8px/16px/24px/48px), hierarquia visual
  clara entre seções e responsividade (media queries para mobile).
- Imagens: use exclusivamente os arquivos já baixados em `images/` (referencie
  como "images/nome-do-arquivo.jpg"). Não invente URLs externas de imagem e
  não use serviços de placeholder. Aplique object-fit: cover e bordas
  arredondadas onde fizer sentido.
- Acabamento: adicione microinterações simples em CSS (transições em hover de
  botões/links), sombras sutis e um favicon simples via emoji se pertinente.
""".strip()


class SiteGenerationError(RuntimeError):
    pass


def _buscar_imagens(tema: str, api_key: str, destino: Path) -> list[str]:
    destino.mkdir(parents=True, exist_ok=True)
    try:
        response = requests.get(
            PEXELS_SEARCH_URL,
            headers={"Authorization": api_key},
            params={"query": tema, "per_page": MAX_IMAGENS, "orientation": "landscape"},
            timeout=PEXELS_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        fotos = response.json().get("photos", [])
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Falha ao buscar imagens na Pexels: %s", exc)
        return []

    nomes: list[str] = []
    for i, foto in enumerate(fotos):
        url = foto.get("src", {}).get("large")
        if not url:
            continue
        nome = f"imagem-{i + 1}.jpg"
        try:
            img_response = requests.get(url, timeout=PEXELS_TIMEOUT_SECONDS)
            img_response.raise_for_status()
            (destino / nome).write_bytes(img_response.content)
            nomes.append(nome)
        except requests.RequestException as exc:
            logger.warning("Falha ao baixar imagem %s: %s", url, exc)

    return nomes


def _build_prompt(tema: str, tipo: str, instrucoes_extras: str, imagens: list[str]) -> str:
    prompt = (
        f"Crie os arquivos de um(a) {tipo} sobre o tema: \"{tema}\".\n"
        "Gere os arquivos diretamente no diretório atual (ex.: index.html, "
        "estilos CSS, arquivos Markdown para posts, conforme o tipo pedido). "
        "Não peça confirmação, apenas crie os arquivos.\n\n"
        f"{DESIGN_GUIDELINES}"
    )

    if imagens:
        lista = ", ".join(f'"images/{nome}"' for nome in imagens)
        prompt += (
            f"\n\nImagens reais já disponíveis em images/ (use-as, distribuindo "
            f"entre as seções apropriadas do site): {lista}."
        )
    else:
        prompt += (
            "\n\nNenhuma imagem real está disponível para este job — não use "
            "imagens (nem placeholders, nem URLs externas); construa o "
            "visual só com cores, tipografia e formas em CSS."
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

    imagens: list[str] = []
    if config.pexels_api_key:
        imagens = _buscar_imagens(tema, config.pexels_api_key, files_dir / "images")
    else:
        logger.warning("PEXELS_API_KEY não configurada — site será gerado sem imagens reais.")

    prompt = _build_prompt(tema, tipo, instrucoes_extras, imagens)

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
        result={"tema": tema, "tipo": tipo, "imagens": len(imagens), "file": str(zip_path)},
    )
