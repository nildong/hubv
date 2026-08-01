"""Skill da fila `videos`: transforma uma história livre em filme animado narrado.

Pipeline (baseado em https://github.com/inematds/videos-agnes, adaptado para
rodar sem as dependências pessoais do projeto original — sem inemavox, sem
caminhos hardcoded, entrega pelo watcher deste bot em vez de um bot próprio):

1. Roteirização: o Claude Code CLI (mesmo padrão de `video_explicativo.py`,
   sem tools) lê a história em português e devolve um roteiro em JSON com
   âncoras de personagem (model sheet) e cenas (par de keyframes A/B), com
   todos os prompts de imagem/movimento já em INGLÊS.
2. Âncoras: 1ª âncora de cada personagem gerada em text2img; demais vistas
   DERIVADAS dela via img2img (mesmo indivíduo) na API Agnes AI.
3. Cenas: 2 imagens por cena (keyframe A abre / B fecha), até 2 referências.
4. Narração: cada cena vira um áudio via TTS da Groq (já usado em
   `video_explicativo.py`); a duração da fala define `num_frames` do clipe.
5. Clipes: interpolação de vídeo keyframe A→B via `agnes-video-v2.0`,
   respeitando o rate limit real da API (5 requisições/min).
6. Montagem: ffmpeg casa áudio/vídeo de cada cena (sem cortar a fala) e
   concatena tudo em `video.mp4`.

Todas as regras abaixo (prompt em inglês, máx. 2 refs, `size` em pixels
explícitos, retry em 503, "exactly one" positivo, etc.) vêm de ~70 chamadas
reais documentadas no README do projeto original — não são um palpite.

Achado em teste real (não documentado no projeto original): o filtro de
conteúdo da Agnes (HTTP 400 content_policy_violation) é probabilístico, não
determinístico — o MESMO prompt, palavra por palavra, em inglês, sem nada de
sensível, foi bloqueado e aceito em chamadas diferentes. Em teste, um prompt
benigno ("fox standing on a mossy log, sniffing the air") levou de 1 a 15+
tentativas idênticas para passar. Por isso `IMAGE_RETRIES` é alto (25) e o
backoff é curto (3s) — não é rate limit, é só tentar de novo até "acertar" a
classificação.
"""

import base64
import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Any

import requests

from agents.executor import AgentResult
from config import load_config

logger = logging.getLogger(__name__)

ROTEIRO_TIMEOUT_SECONDS = 120
FFMPEG_TIMEOUT_SECONDS = 300

AGNES_IMAGE_URL = "https://apihub.agnes-ai.com/v1/images/generations"
AGNES_VIDEO_URL = "https://apihub.agnes-ai.com/v1/videos"
AGNES_VIDEO_STATUS_URL = "https://apihub.agnes-ai.com/agnesapi"
AGNES_IMAGE_MODEL = "agnes-image-2.1-flash"
AGNES_VIDEO_MODEL = "agnes-video-v2.0"
AGNES_IMAGE_SIZE = "1312x736"
AGNES_FRAME_RATE = 24
AGNES_SEED = 12345
# A resposta de criação de vídeo da Agnes mente sobre a resolução (pede
# 1312x736, entrega 1280x704 na prática) — clipes de cenas diferentes podem
# sair com dimensões levemente diferentes. Normalizamos todos para este
# tamanho na montagem (16:9, múltiplo de 2) para o concat nunca falhar.
VIDEO_CANONICAL_WIDTH = 1280
VIDEO_CANONICAL_HEIGHT = 720

IMAGE_RETRIES = 25
VIDEO_RETRIES = 4
VIDEO_POLL_TIMEOUT_SECONDS = 900
VIDEO_POLL_INTERVAL_SECONDS = 15
VIDEO_MIN_GAP_SECONDS = 13  # rate limit real: 5 req/min no POST /v1/videos

STYLE = (
    "Pixar-style 3D animated feature film render, soft cinematic lighting, "
    "warm color palette, shallow depth of field, restrained natural saturation"
)
# Fórmula confirmada (PT e EN) para curar o bug de cauda/cabeça dupla em pose
# frontal simétrica: pedir "ONE SINGLE ... exactly one" de forma explícita e
# positiva funciona; negações ("no two tails") viram atrator do próprio bug.
SO_UM = (
    "Exactly one of each character, ONE SINGLE head, ONE SINGLE tail if the "
    "character has a tail, exactly one tail only, no duplicates, natural anatomy."
)

MAX_CENAS = 4


class VideoHistoriaError(RuntimeError):
    pass


def _gerar_roteiro(historia: str, model: str | None) -> dict[str, Any]:
    prompt = (
        "Transforme esta história em um roteiro de filme animado curto. "
        f"História (em português): \"{historia}\"\n\n"
        f"Divida em 2 a {MAX_CENAS} cenas. Responda APENAS com um JSON válido, "
        "sem texto antes ou depois, no formato:\n"
        "{\n"
        '  "titulo": "...",\n'
        '  "personagens": [{"id": "anc-nome", "descricao_en": "..."}],\n'
        '  "cenas": [{\n'
        '    "narracao_pt": "...",\n'
        '    "prompt_a_en": "...",\n'
        '    "prompt_b_en": "...",\n'
        '    "movimento_en": "...",\n'
        '    "refs": ["anc-nome"]\n'
        "  }]\n"
        "}\n\n"
        "Regras obrigatórias para os campos em inglês (prompt_a_en, prompt_b_en, "
        "movimento_en, descricao_en): escreva SEMPRE em inglês (a API de imagem "
        "bloqueia conteúdo legítimo em português). 'descricao_en' é a descrição "
        "fixa e literal do personagem (repita-a como referência de identidade). "
        "'prompt_a_en' é o início da cena, 'prompt_b_en' o fim; 'movimento_en' "
        "descreve o que acontece entre A e B. 'refs' lista os ids de personagens "
        "(de 'personagens') que aparecem na cena (no máximo 2). 'narracao_pt' é "
        "o texto que será narrado em voz alta, em português, fiel ao texto "
        "original da história."
    )
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--tools", ""]
    if model:
        cmd += ["--model", model]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=ROTEIRO_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired as exc:
        raise VideoHistoriaError("Roteirização demorou demais.") from exc

    if result.returncode != 0:
        raise VideoHistoriaError(f"Falha ao gerar roteiro: {result.stderr.strip()[:500]}")

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
        raise VideoHistoriaError("Roteiro retornado não é um JSON válido.") from exc

    personagens = data.get("personagens")
    cenas = data.get("cenas")
    if not isinstance(personagens, list) or not personagens:
        raise VideoHistoriaError("Roteiro sem personagens.")
    if not isinstance(cenas, list) or not cenas:
        raise VideoHistoriaError("Roteiro sem cenas.")
    return data


def _data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def _gerar_imagem_agnes(dest: Path, prompt: str, api_key: str, refs: list[Path] | None = None) -> bool:
    """text2img (refs=None) ou img2img (<=2 refs)."""
    if refs and len(refs) > 2:
        refs = refs[:2]
    # MESMO (texto pedindo "same face/hair/eye color...") dispara o filtro de
    # conteúdo (400 content_policy_violation) quando combinado com uma imagem
    # de referência — confirmado empiricamente. A própria referência já ancora
    # a identidade, então usamos só SO_UM + STYLE em ambos os casos.
    texto = f"{prompt} {SO_UM} {STYLE}"
    body: dict[str, Any] = {
        "model": AGNES_IMAGE_MODEL,
        "prompt": texto,
        "size": AGNES_IMAGE_SIZE,
        "extra_body": {"response_format": "url"},
    }
    if refs:
        body["extra_body"]["image"] = [_data_uri(r) for r in refs]

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    for tentativa in range(1, IMAGE_RETRIES + 1):
        try:
            resp = requests.post(AGNES_IMAGE_URL, json=body, headers=headers, timeout=180)
            resp.raise_for_status()
            url = resp.json()["data"][0]["url"]
            img = requests.get(url, timeout=180)
            img.raise_for_status()
            dest.write_bytes(img.content)
            return True
        except requests.RequestException as exc:
            logger.warning("Falha ao gerar imagem (tentativa %d/%d): %s", tentativa, IMAGE_RETRIES, exc)
            # Confirmado empiricamente: o filtro de conteúdo (400) às vezes bloqueia
            # um prompt em inglês legítimo de forma inconsistente — o mesmo prompt
            # idêntico às vezes passa, às vezes não. Retry curto sem mexer no
            # prompt já resolveu em teste real; sem backoff longo, pois não é
            # rate limit.
            time.sleep(3)
    return False


def _ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _frames_para(segundos: float) -> int:
    """Regra 8n+1, teto 441 (18.4s @24fps)."""
    n = round((segundos * AGNES_FRAME_RATE - 1) / 8)
    return max(9, min(441, int(n * 8 + 1)))


def _gerar_video_agnes(
    dest: Path, kf_a: Path, kf_b: Path, prompt: str, frames: int, api_key: str
) -> bool:
    body = {
        "model": AGNES_VIDEO_MODEL,
        "prompt": (
            f"Smooth cinematic transition between the keyframes: {prompt}. "
            "Natural motion, consistent characters and style, cinematic camera."
        ),
        "num_frames": frames,
        "frame_rate": AGNES_FRAME_RATE,
        "seed": AGNES_SEED,
        "width": 1312,
        "height": 736,
        "extra_body": {"image": [_data_uri(kf_a), _data_uri(kf_b)], "mode": "keyframes"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    video_id = None
    for tentativa in range(1, VIDEO_RETRIES + 1):
        try:
            resp = requests.post(AGNES_VIDEO_URL, json=body, headers=headers, timeout=300)
            if resp.status_code == 429:
                time.sleep(70)
                continue
            resp.raise_for_status()
            data = resp.json()
            video_id = data.get("video_id") or data.get("task_id") or data.get("id")
            break
        except requests.RequestException as exc:
            logger.warning("Falha ao criar vídeo (tentativa %d/%d): %s", tentativa, VIDEO_RETRIES, exc)
            time.sleep(6 * tentativa)

    if not video_id:
        return False

    inicio = time.time()
    while time.time() - inicio < VIDEO_POLL_TIMEOUT_SECONDS:
        time.sleep(VIDEO_POLL_INTERVAL_SECONDS)
        try:
            resp = requests.get(
                AGNES_VIDEO_STATUS_URL,
                params={"video_id": video_id},
                headers=headers,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException:
            continue

        status = data.get("status")
        if status == "completed":
            url = data.get("url") or (data.get("data") or [{}])[0].get("url") or data.get("video_url")
            if not url:
                return False
            video_resp = requests.get(url, timeout=300)
            video_resp.raise_for_status()
            dest.write_bytes(video_resp.content)
            return True
        if status == "failed":
            logger.warning("Geração de vídeo falhou: %s", json.dumps(data)[:200])
            return False
    return False


def _sintetizar_narracao(texto: str, destino: Path) -> float:
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
    except Exception as exc:
        logger.exception("Falha ao sintetizar narração na Groq")
        raise VideoHistoriaError("Não consegui gerar a narração em áudio.") from exc
    return _ffprobe_duration(destino)


def _run_ffmpeg(cmd: list[str]) -> bool:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0


def _montar_cena(video: Path, audio: Path, saida: Path) -> bool:
    dv = _ffprobe_duration(video)
    da = _ffprobe_duration(audio)
    alvo = max(dv, da + 0.4)
    return _run_ffmpeg([
        "ffmpeg", "-loglevel", "error", "-y",
        "-i", str(video), "-i", str(audio),
        "-filter_complex",
        f"[0:v]scale={VIDEO_CANONICAL_WIDTH}:{VIDEO_CANONICAL_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={VIDEO_CANONICAL_WIDTH}:{VIDEO_CANONICAL_HEIGHT}:(ow-iw)/2:(oh-ih)/2,"
        f"tpad=stop_mode=clone:stop_duration={max(0, alvo - dv):.2f},"
        f"trim=0:{alvo:.2f},setpts=PTS-STARTPTS[v];"
        f"[1:a]apad=pad_dur={max(0, alvo - da):.2f},atrim=0:{alvo:.2f},asetpts=PTS-STARTPTS[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac",
        str(saida),
    ])


def _concatenar(clipes: list[Path], lista_path: Path, saida: Path) -> bool:
    lista_path.write_text("\n".join(f"file '{c.name}'" for c in clipes), encoding="utf-8")
    return _run_ffmpeg([
        "ffmpeg", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(lista_path),
        "-c:v", "libx264", "-crf", "27", "-preset", "slow", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        str(saida),
    ])


def run(payload: dict[str, Any], working_directory: Path) -> AgentResult:
    historia = payload.get("historia", "").strip()
    if not historia:
        return AgentResult(success=False, error="Campo 'historia' é obrigatório.")

    config = load_config()
    if not config.agnes_api_key:
        return AgentResult(
            success=False,
            error="AGNES_API_KEY não configurada — não é possível gerar imagens/vídeo.",
        )

    files_dir = working_directory / "files"
    cenas_dir = working_directory / "cenas"
    files_dir.mkdir(parents=True, exist_ok=True)
    cenas_dir.mkdir(parents=True, exist_ok=True)

    try:
        roteiro = _gerar_roteiro(historia, config.claude_model)
    except VideoHistoriaError as exc:
        return AgentResult(success=False, error=str(exc))

    api_key = config.agnes_api_key

    # 1) âncoras: a 1ª de cada personagem em text2img, demais (se houver) derivadas por img2img.
    anc_paths: dict[str, Path] = {}
    for personagem in roteiro["personagens"]:
        pid = personagem.get("id", "").strip()
        desc = personagem.get("descricao_en", "").strip()
        if not pid or not desc:
            continue
        png = cenas_dir / f"{pid}.png"
        if not _gerar_imagem_agnes(png, f"Character reference of {desc}, three-quarter view, full body.", api_key):
            return AgentResult(success=False, error=f"Falha ao gerar a âncora do personagem '{pid}'.")
        anc_paths[pid] = png

    # 2) cenas: 2 imagens por cena (keyframe A/B), até 2 referências de personagem.
    clipes: list[Path] = []
    ultima_criacao_video = 0.0
    for i, cena in enumerate(roteiro["cenas"], start=1):
        refs = [anc_paths[r] for r in cena.get("refs", []) if r in anc_paths][:2]

        png_a = cenas_dir / f"cena-{i:02d}-a.png"
        png_b = cenas_dir / f"cena-{i:02d}-b.png"
        if not _gerar_imagem_agnes(png_a, cena["prompt_a_en"], api_key, refs or None):
            return AgentResult(success=False, error=f"Falha ao gerar o keyframe A da cena {i}.")
        if not _gerar_imagem_agnes(png_b, cena["prompt_b_en"], api_key, refs or None):
            return AgentResult(success=False, error=f"Falha ao gerar o keyframe B da cena {i}.")

        # 3) narração define a duração do clipe.
        wav = cenas_dir / f"cena-{i:02d}.wav"
        try:
            duracao = _sintetizar_narracao(cena["narracao_pt"], wav)
        except VideoHistoriaError as exc:
            return AgentResult(success=False, error=str(exc))

        # 4) clipe de vídeo, respeitando o rate limit real (5 req/min).
        espera = VIDEO_MIN_GAP_SECONDS - (time.time() - ultima_criacao_video)
        if espera > 0:
            time.sleep(espera)
        mp4 = cenas_dir / f"clipe-{i:02d}.mp4"
        frames = _frames_para(duracao or 3.4)
        ok = _gerar_video_agnes(mp4, png_a, png_b, cena.get("movimento_en", ""), frames, api_key)
        ultima_criacao_video = time.time()
        if not ok:
            return AgentResult(success=False, error=f"Falha ao gerar o clipe de vídeo da cena {i}.")

        # 5) casa áudio/vídeo sem cortar a fala.
        clipe_final = cenas_dir / f"final-{i:02d}.mp4"
        if not _montar_cena(mp4, wav, clipe_final):
            return AgentResult(success=False, error=f"Falha ao montar a cena {i} (ffmpeg).")
        clipes.append(clipe_final)

    if not clipes:
        return AgentResult(success=False, error="Nenhuma cena foi montada com sucesso.")

    lista_path = cenas_dir / "lista.txt"
    video_final = files_dir / "video.mp4"
    if not _concatenar(clipes, lista_path, video_final):
        return AgentResult(success=False, error="Falha ao concatenar as cenas (ffmpeg).")

    return AgentResult(
        success=True,
        result={
            "titulo": roteiro.get("titulo", ""),
            "cenas": len(clipes),
            "file": str(video_final),
        },
    )
