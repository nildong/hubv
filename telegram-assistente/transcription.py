"""Transcrição de áudio usando a API da Groq (Whisper)."""

import logging
from pathlib import Path

from groq import Groq

logger = logging.getLogger(__name__)


class TranscriptionError(RuntimeError):
    pass


class Transcriber:
    def __init__(self, api_key: str, model: str, language: str | None = None):
        self._client = Groq(api_key=api_key)
        self._model = model
        self._language = language

    def transcribe(self, audio_path: Path) -> str:
        try:
            with open(audio_path, "rb") as audio_file:
                kwargs = {
                    "file": (audio_path.name, audio_file.read()),
                    "model": self._model,
                }
                if self._language:
                    kwargs["language"] = self._language
                transcription = self._client.audio.transcriptions.create(**kwargs)
        except Exception as exc:  # erro de rede/API da Groq
            logger.exception("Falha ao transcrever áudio na Groq")
            raise TranscriptionError("Não consegui transcrever o áudio.") from exc

        text = (transcription.text or "").strip()
        if not text:
            raise TranscriptionError("A transcrição veio vazia.")
        return text
