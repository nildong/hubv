"""Mapa skill -> função Python que a executa (usado pelo SkillDispatchExecutor)."""

from skills import (
    criacao_site_blog,
    roteiro,
    teste_fila,
    transcricao_video,
    video_explicativo,
)

SKILL_FUNCTIONS = {
    "teste-fila": teste_fila.run,
    "roteiro": roteiro.run,
    "video-explicativo": video_explicativo.run,
    "transcricao-video": transcricao_video.run,
    "criacao-site-blog": criacao_site_blog.run,
}
