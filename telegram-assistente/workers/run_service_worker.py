"""Entrypoint do worker da fila `servicos`.

Uso: python -m workers.run_service_worker
"""

from workers.runner import run_worker

if __name__ == "__main__":
    run_worker("servicos")
