"""Entrypoint do worker da fila `videos`.

Uso: python -m workers.run_video_worker
"""

from workers.runner import run_worker

if __name__ == "__main__":
    run_worker("videos")
