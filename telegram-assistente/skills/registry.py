"""Mapa skill -> função Python que a executa (usado pelo SkillDispatchExecutor)."""

from skills import roteiro, teste_fila, video_explicativo

SKILL_FUNCTIONS = {
    "teste-fila": teste_fila.run,
    "roteiro": roteiro.run,
    "video-explicativo": video_explicativo.run,
}
