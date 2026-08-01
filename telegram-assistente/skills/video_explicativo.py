"""Skill da fila `videos`: gera um vídeo explicativo real a partir de um tema.

Pipeline local (sem serviço externo de geração de vídeo):
1. Roteirização: o Claude Code CLI (mesmo padrão de `criacao_site_blog.py`,
   mas sem tools) devolve um roteiro em JSON com uma lista de cenas.
2. Narração: cada cena vira um áudio via TTS da Groq.
3. Slide: cada cena vira uma imagem estática (PIL) com o texto da cena,
   dimensionada conforme o formato pedido (horizontal 16:9 ou vertical 9:16).
4. Montagem: `ffmpeg` gera um clipe por cena (imagem + áudio) e concatena
   tudo em `video.mp4`.
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from agents.executor import AgentResult
from config import load_config

logger = logging.getLogger(__name__)

ROTEIRO_TIMEOUT_SECONDS = 120
FFMPEG_TIMEOUT_SECONDS = 300

RESOLUCOES = {
    "horizontal": (1920, 1080),
    "vertical": (1080, 1920),
}

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_PATH_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

BG_COLOR = (17, 24, 39)
TITLE_COLOR = (250, 250, 250)
TEXT_COLOR = (209, 213, 219)


class VideoGenerationError(RuntimeError):
    pass


def _normalizar_formato(valor: str) -> str:
    valor = (valor or "").strip().lower()
    return valor if valor in RESOLUCOES else "horizontal"


def _gerar_roteiro(tema: str, duracao: str, model: str | None) -> list[dict[str, str]]:
    prompt = (
        f'Crie um roteiro de vídeo explicativo curto sobre o tema: "{tema}". '
        f"Duração alvo: {duracao}.\n"
        "Divida em 3 a 5 cenas. Responda APENAS com um JSON válido no formato "
        '{"cenas": [{"titulo": "...", "narracao": "..."}]}, sem texto antes '
        "ou depois. 'narracao' deve ser o texto que será narrado em voz alta "
        "(frases curtas, tom natural, em português)."
    )
    cmd = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
        "--tools",
        "",
    ]
    if model:
        cmd += ["--model", model]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=ROTEIRO_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired as exc:
        raise VideoGenerationError("Roteirização demorou demais.") from exc

    if result.returncode != 0:
        raise VideoGenerationError(f"Falha ao gerar roteiro: {result.stderr.strip()[:500]}")

    try:
        outer = json.loads(result.stdout)
        raw = outer["result"] if isinstance(outer, dict) and "result" in outer else result.stdout
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[len("json"):]
        data = json.loads(raw.strip())
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise VideoGenerationError("Roteiro retornado não é um JSON válido.") from exc

    cenas = data.get("cenas") if isinstance(data, dict) else None
    if not isinstance(cenas, list) or not cenas:
        raise VideoGenerationError("Roteiro sem cenas.")

    normalizado = []
    for cena in cenas:
        titulo = str(cena.get("titulo", "")).strip()
        narracao = str(cena.get("narracao", "")).strip()
        if narracao:
            normalizado.append({"titulo": titulo, "narracao": narracao})

    if not normalizado:
        raise VideoGenerationError("Roteiro sem narração utilizável.")
    return normalizado


def _sintetizar_narracao(texto: str, destino: Path) -> None:
    config = load_config()
    from groq import Groq

    client = Groq(api_key=config.groq_api_key)
    try:
        response = client.audio.speech.create(
            model=config.groq_tts_model,
            voice=config.groq_tts_voice,
            input=texto,
            response_format="wav",
        )
        response.write_to_file(destino)
    except Exception as exc:  # erro de rede/API da Groq
        logger.exception("Falha ao sintetizar narração na Groq")
        raise VideoGenerationError("Não consegui gerar a narração em áudio.") from exc


def _quebrar_linhas(draw: ImageDraw.ImageDraw, texto: str, font: ImageFont.FreeTypeFont, largura_max: int) -> list[str]:
    palavras = texto.split()
    linhas: list[str] = []
    atual = ""
    for palavra in palavras:
        candidata = f"{atual} {palavra}".strip()
        if draw.textlength(candidata, font=font) <= largura_max:
            atual = candidata
        else:
            if atual:
                linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas


def _gerar_slide(titulo: str, texto: str, largura: int, altura: int, destino: Path) -> None:
    img = Image.new("RGB", (largura, altura), BG_COLOR)
    draw = ImageDraw.Draw(img)
    margem = int(largura * 0.08)
    largura_util = largura - 2 * margem

    titulo_tam = max(36, largura // 22)
    texto_tam = max(28, largura // 32)
    font_titulo = ImageFont.truetype(FONT_PATH, titulo_tam)
    font_texto = ImageFont.truetype(FONT_PATH_REGULAR, texto_tam)

    y = altura * 0.30
    if titulo:
        for linha in _quebrar_linhas(draw, titulo, font_titulo, largura_util):
            draw.text((margem, y), linha, font=font_titulo, fill=TITLE_COLOR)
            y += titulo_tam * 1.3
        y += titulo_tam

    for linha in _quebrar_linhas(draw, texto, font_texto, largura_util):
        draw.text((margem, y), linha, font=font_texto, fill=TEXT_COLOR)
        y += texto_tam * 1.4

    img.save(destino)


def _run_ffmpeg(cmd: list[str]) -> None:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired as exc:
        raise VideoGenerationError("ffmpeg demorou demais.") from exc
    if result.returncode != 0:
        raise VideoGenerationError(f"ffmpeg falhou: {result.stderr.strip()[-500:]}")


def _montar_cena(imagem: Path, audio: Path, saida: Path, largura: int, altura: int) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(imagem),
        "-i",
        str(audio),
        "-c:v",
        "libx264",
        "-tune",
        "stillimage",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-pix_fmt",
        "yuv420p",
        "-vf",
        f"scale={largura}:{altura}",
        "-shortest",
        str(saida),
    ]
    _run_ffmpeg(cmd)


def _concatenar_cenas(clipes: list[Path], lista_path: Path, saida: Path) -> None:
    lista_path.write_text(
        "\n".join(f"file '{clipe.name}'" for clipe in clipes), encoding="utf-8"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(lista_path),
        "-c",
        "copy",
        str(saida),
    ]
    _run_ffmpeg(cmd)


def run(payload: dict[str, Any], working_directory: Path) -> AgentResult:
    tema = payload.get("tema", "").strip()
    duracao = payload.get("duracao", "cerca de 1 minuto").strip() or "cerca de 1 minuto"
    formato = _normalizar_formato(payload.get("formato", "horizontal"))

    if not tema:
        return AgentResult(success=False, error="Campo 'tema' é obrigatório.")

    largura, altura = RESOLUCOES[formato]

    files_dir = working_directory / "files"
    cenas_dir = working_directory / "cenas"
    files_dir.mkdir(parents=True, exist_ok=True)
    cenas_dir.mkdir(parents=True, exist_ok=True)

    config = load_config()

    try:
        cenas = _gerar_roteiro(tema, duracao, config.claude_model)

        clipes: list[Path] = []
        for i, cena in enumerate(cenas):
            audio_path = cenas_dir / f"cena_{i:02d}.wav"
            imagem_path = cenas_dir / f"cena_{i:02d}.png"
            clipe_path = cenas_dir / f"cena_{i:02d}.mp4"

            _sintetizar_narracao(cena["narracao"], audio_path)
            _gerar_slide(cena["titulo"], cena["narracao"], largura, altura, imagem_path)
            _montar_cena(imagem_path, audio_path, clipe_path, largura, altura)
            clipes.append(clipe_path)

        lista_path = cenas_dir / "lista.txt"
        video_final = files_dir / "video.mp4"
        _concatenar_cenas(clipes, lista_path, video_final)
    except VideoGenerationError as exc:
        return AgentResult(success=False, error=str(exc))

    return AgentResult(
        success=True,
        result={
            "tema": tema,
            "formato": formato,
            "resolucao": f"{largura}x{altura}",
            "cenas": len(cenas),
            "file": str(video_final),
        },
    )
