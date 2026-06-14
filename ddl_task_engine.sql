-- SciPDF 异步任务引擎 — 3 个新表 DDL
-- 在 PostgreSQL 上执行：psql -h <host> -U <user> -d article_analysis_v3 -f ddl_task_engine.sql

-- ── 任务主表 ──
CREATE TABLE IF NOT EXISTS task_jobs (
    id SERIAL PRIMARY KEY,
    public_id VARCHAR(36) UNIQUE NOT NULL,
    task_type VARCHAR(100) NOT NULL,
    queue_name VARCHAR(100) DEFAULT '' NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    priority INTEGER DEFAULT 0 NOT NULL,

    total_items INTEGER DEFAULT 0 NOT NULL,
    completed_items INTEGER DEFAULT 0 NOT NULL,
    failed_items INTEGER DEFAULT 0 NOT NULL,

    payload JSON DEFAULT '{}' NOT NULL,
    result JSON DEFAULT '{}' NOT NULL,
    error_code VARCHAR(100) DEFAULT '' NOT NULL,
    error_message TEXT DEFAULT '' NOT NULL,

    scheduled_at TIMESTAMP WITH TIME ZONE,
    started_at TIMESTAMP WITH TIME ZONE,
    finished_at TIMESTAMP WITH TIME ZONE,

    created_by VARCHAR(36) DEFAULT '' NOT NULL,
    project_public_id VARCHAR(36) DEFAULT '' NOT NULL,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_jobs_public_id ON task_jobs(public_id);
CREATE INDEX IF NOT EXISTS idx_task_jobs_status ON task_jobs(status);
CREATE INDEX IF NOT EXISTS idx_task_jobs_task_type ON task_jobs(task_type);
CREATE INDEX IF NOT EXISTS idx_task_jobs_project_public_id ON task_jobs(project_public_id);

-- ── 任务子项表 ──
CREATE TABLE IF NOT EXISTS task_items (
    id SERIAL PRIMARY KEY,
    public_id VARCHAR(36) UNIQUE NOT NULL,
    job_id INTEGER NOT NULL REFERENCES task_jobs(id) ON DELETE CASCADE,

    task_type VARCHAR(100) NOT NULL,
    item_type VARCHAR(100) DEFAULT '' NOT NULL,
    item_key VARCHAR(255) DEFAULT '' NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    priority INTEGER DEFAULT 0 NOT NULL,

    payload JSON DEFAULT '{}' NOT NULL,
    result JSON DEFAULT '{}' NOT NULL,
    error_code VARCHAR(100) DEFAULT '' NOT NULL,
    error_message TEXT DEFAULT '' NOT NULL,

    attempt_count INTEGER DEFAULT 0 NOT NULL,
    max_attempts INTEGER DEFAULT 3 NOT NULL,
    worker_id VARCHAR(100) DEFAULT '' NOT NULL,

    heartbeat_at TIMESTAMP WITH TIME ZONE,
    scheduled_at TIMESTAMP WITH TIME ZONE,
    started_at TIMESTAMP WITH TIME ZONE,
    finished_at TIMESTAMP WITH TIME ZONE,
    stream_id VARCHAR(100) DEFAULT '' NOT NULL,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_items_public_id ON task_items(public_id);
CREATE INDEX IF NOT EXISTS idx_task_items_job_id ON task_items(job_id);
CREATE INDEX IF NOT EXISTS idx_task_items_status ON task_items(status);

-- ── 死信表 ──
CREATE TABLE IF NOT EXISTS task_dead_letters (
    id SERIAL PRIMARY KEY,
    task_type VARCHAR(100) NOT NULL,
    item_type VARCHAR(100) DEFAULT '' NOT NULL,
    item_key VARCHAR(255) DEFAULT '' NOT NULL,

    payload JSON DEFAULT '{}' NOT NULL,
    error_code VARCHAR(100) DEFAULT '' NOT NULL,
    error_message TEXT DEFAULT '' NOT NULL,

    attempt_count INTEGER DEFAULT 0 NOT NULL,
    max_attempts INTEGER DEFAULT 3 NOT NULL,
    original_item_public_id VARCHAR(36) DEFAULT '' NOT NULL,
    worker_id VARCHAR(100) DEFAULT '' NOT NULL,
    stream_id VARCHAR(100) DEFAULT '' NOT NULL,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_dead_letters_task_type ON task_dead_letters(task_type);
CREATE INDEX IF NOT EXISTS idx_task_dead_letters_created_at ON task_dead_letters(created_at);
