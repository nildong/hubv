"""Entrypoint do worker da fila `textos`.

Uso: python -m workers.run_text_worker
"""

from workers.runner import run_worker

if __name__ == "__main__":
    run_worker("textos")
