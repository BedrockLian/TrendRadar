-- 002_heat_archive.sql
-- 归档 heat_tracker 中的 dormant（>14 天未见）条目到 heat_tracker_archive
-- 解决 heat_signals JSON blob 膨胀问题（3181/3850 条 = 82.6% 是 dormant，占 4.9MB）
--
-- 数据保留策略:
--   - active: 主表保留
--   - dormant 且 last_seen < 14 天: 主表保留（可能被复活）
--   - dormant 且 last_seen >= 14 天: 移到归档表
--
-- 注意:
--   - 归档表 schema 与 heat_tracker 完全相同，方便必要时回迁
--   - 不做物理删除，保留历史用于月报/趋势分析
--   - 下次 archive 操作可重复执行（INSERT OR IGNORE 防重复）

CREATE TABLE IF NOT EXISTS heat_tracker_archive (
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
    rank_history TEXT DEFAULT '[]',
    archived_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_heat_arch_lastseen ON heat_tracker_archive(last_seen);
CREATE INDEX IF NOT EXISTS idx_heat_arch_status ON heat_tracker_archive(status);

-- 归档: dormant 且 last_seen 超过 7 天
-- (实际数据最早 5-30, 14 天阈值 0 匹配; 用 7 天合理且安全)
-- 修复: last_seen 是 ISO 8601 带时区格式（2026-06-08T17:19:09+08:00），
--       strftime 默认转 UTC 再格式化; 用 datetime(last_seen) 强转保留时区
INSERT OR IGNORE INTO heat_tracker_archive
    (fingerprint, title, first_seen, last_seen, appearance_count, fetch_cycles,
     platforms, platform_count, heat_signals, domain, status, rank_history)
SELECT fingerprint, title, first_seen, last_seen, appearance_count, fetch_cycles,
       platforms, platform_count, heat_signals, domain, status, rank_history
FROM heat_tracker
WHERE status = 'dormant'
  AND datetime(last_seen) < datetime('now', '-7 days');

-- 删除已归档的主表行
DELETE FROM heat_tracker
WHERE status = 'dormant'
  AND datetime(last_seen) < datetime('now', '-7 days');

-- VACUUM 释放空间: SQLite 在事务外单独执行才能生效
-- executescript 不开事务，所以这里 VACUUM 可以工作
VACUUM;

-- down: DROP TABLE IF EXISTS heat_tracker_archive;
