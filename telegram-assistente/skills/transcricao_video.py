"""Skill da fila `textos`: transcreve o áudio de uma URL de vídeo/áudio.

Baixa apenas a trilha de áudio da URL informada (via `yt-dlp`, executado com
argumentos separados — nunca concatenados em uma string de shell) dentro da
pasta isolada do job, transcreve com a API da Groq (Whisper) e grava o
resultado em `files/transcricao.txt`.
"""

import subprocess
from pathlib import Path
from typing import Any

from agents.executor import AgentResult
from config import load_config
from transcription import Transcriber, TranscriptionError

DOWNLOAD_TIMEOUT_SECONDS = 300


class DownloadError(RuntimeError):
    pass


def _download_audio(url: str, files_dir: Path) -> Path:
    output_template = str(files_dir / "audio.%(ext)s")
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-x",
        "--audio-format",
        "mp3",
        "-o",
        output_template,
        url,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise DownloadError(
            "yt-dlp não está instalado no ambiente (adicione ao requirements.txt / PATH)."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise DownloadError("Download do áudio demorou demais.") from exc

    if result.returncode != 0:
        raise DownloadError(f"Falha ao baixar áudio da URL: {result.stderr.strip()[:500]}")

    audio_path = files_dir / "audio.mp3"
    if not audio_path.is_file():
        raise DownloadError("Download concluído, mas o arquivo de áudio não foi encontrado.")
    return audio_path


def run(payload: dict[str, Any], working_directory: Path) -> AgentResult:
    url = payload.get("url", "").strip()
    if not url:
        return AgentResult(success=False, error="Campo 'url' vazio.")

    files_dir = working_directory / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    try:
        audio_path = _download_audio(url, files_dir)
    except DownloadError as exc:
        return AgentResult(success=False, error=str(exc))

    config = load_config()
    transcriber = Transcriber(
        api_key=config.groq_api_key,
        model=config.groq_transcribe_model,
        language=config.groq_language,
    )

    try:
        texto = transcriber.transcribe(audio_path)
    except TranscriptionError as exc:
        return AgentResult(success=False, error=str(exc))

    result_path = files_dir / "transcricao.txt"
    result_path.write_text(texto, encoding="utf-8")

    return AgentResult(
        success=True,
        result={"url": url, "texto": texto, "file": str(result_path)},
    )
