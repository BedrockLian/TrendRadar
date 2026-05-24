-- 001_initial.sql
-- TrendRadar 初始数据库 Schema
-- 包含: fingerprints 表 + heat_tracker 表 + 索引

CREATE TABLE IF NOT EXISTS fingerprints (
    fingerprint TEXT PRIMARY KEY,
    title TEXT,
    summary TEXT,
    source_platform TEXT,
    url TEXT,
    push_id TEXT,
    push_time TEXT,
    event_keywords TEXT,
    created_at TEXT,
    run_id TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS heat_tracker (
    fingerprint TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    first_seen TIMESTAMP NOT NULL,
    last_seen TIMESTAMP NOT NULL,
    appearance_count INTEGER DEFAULT 1,
    fetch_cycles INTEGER DEFAULT 1,
    platforms TEXT DEFAULT '[]',
    platform_count INTEGER DEFAULT 1,
    heat_signals TEXT DEFAULT '[]',
    domain TEXT DEFAULT '',
    status TEXT DEFAULT 'active',
    rank_history TEXT DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_fp_push_time ON fingerprints(push_time);
CREATE INDEX IF NOT EXISTS idx_fp_url ON fingerprints(url);
CREATE INDEX IF NOT EXISTS idx_heat_status ON heat_tracker(status);
CREATE INDEX IF NOT EXISTS idx_heat_last_seen ON heat_tracker(last_seen);
CREATE INDEX IF NOT EXISTS idx_heat_platform_count ON heat_tracker(platform_count);
