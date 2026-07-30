"""Conexão SQLite compartilhada pelo bot, workers e watcher.

O banco guarda apenas metadados de jobs (fila, skill, payload, status).
Nunca deve conter chaves de API, tokens ou credenciais.
"""

import sqlite3
import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

_lock = threading.Lock()
_connection: sqlite3.Connection | None = None


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """Retorna uma conexão SQLite única para o processo atual, com a migration aplicada."""
    global _connection
    with _lock:
        if _connection is None:
            path = Path(db_path)
            if not path.is_absolute():
                path = BASE_DIR / path
            path.parent.mkdir(parents=True, exist_ok=True)

            _connection = sqlite3.connect(
                path, check_same_thread=False, isolation_level=None
            )
            _connection.row_factory = sqlite3.Row
            _connection.execute("PRAGMA journal_mode=WAL")
            _connection.execute("PRAGMA foreign_keys=ON")
            _connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        return _connection
