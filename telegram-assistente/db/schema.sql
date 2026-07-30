CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    queue TEXT NOT NULL,
    skill TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    priority INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    user_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    source_message_id TEXT,
    progress INTEGER NOT NULL DEFAULT 0,
    result TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    locked_by TEXT,
    locked_at TEXT,
    delivery_status TEXT NOT NULL DEFAULT 'pending',
    delivered_at TEXT,
    delivery_attempts INTEGER NOT NULL DEFAULT 0,
    delivery_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_queue_status
ON jobs(queue, status, priority, created_at);

CREATE INDEX IF NOT EXISTS idx_jobs_user
ON jobs(user_id, created_at);

CREATE INDEX IF NOT EXISTS idx_jobs_delivery
ON jobs(delivery_status, completed_at);

CREATE TABLE IF NOT EXISTS worker_heartbeats (
    worker_id TEXT PRIMARY KEY,
    queue TEXT NOT NULL,
    status TEXT NOT NULL,
    current_job_id TEXT,
    started_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_heartbeats_queue
ON worker_heartbeats(queue, last_seen_at);
