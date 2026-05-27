# 缓存清理规程

按优先级顺序执行，每步完成后检查磁盘释放量。

## 步骤

### 1. TrendRadar 旧缓存

```bash
cd ~/.hermes/trendradar/cache
# 前日 raw_YYYYMMDD.json、batch_*.json 可安全删除
# raw_blogs.json（88B）保留日常使用
rm -f raw_$(date -d yesterday +%Y%m%d).json batch_*.json
```

### 2. __pycache__（排除 venv）

```bash
find ~/.hermes -path "*/venv/*" -prune -o -name __pycache__ -type d -exec rm -rf {} +
```

### 3. pip cache

```bash
pip cache purge
# 通常释放 10-14MB
```

### 4. apt cache

```bash
sudo apt-get clean
sudo apt-get autoremove --purge -y
```

### 5. 缩略图

```bash
rm -rf ~/.cache/thumbnails/*
```

### 6. 日志

```bash
# 旧 agent.log.1 压缩后删原文
gzip ~/.hermes/logs/agent.log.1
rm -f ~/.hermes/logs/agent.log.1

# 删除旧诊断日志（每日产生 44K+24K）
rm -f ~/.hermes/logs/gateway-shutdown-diag.log
rm -f ~/.hermes/logs/gateway-exit-diag.log
```

### 7. 临时会话文件

```bash
rm -f ~/.hermes/sessions/*.jsonl
# 这些是旧格式非结构化会话记录，state.db 已覆盖
```

### 8. SQLite VACUUM

```bash
sqlite3 ~/.hermes/state.db "VACUUM;"
sqlite3 ~/.hermes/trendradar/data/fingerprints.db "VACUUM;"
# state.db 通常释放 2-10MB
```

## 适用范围

- 清理前确认 `hermes gateway` 和 `cron` 未在写入关键数据
- **自动维护**: `trendradar_maintenance.py` 每日 03:00 自动执行 `cleanup()` 函数，清理 >7 天的 cache/*.json、cache/*.json.zst、data/curated_*_YYYYMMDD.json、data/curated_*_YYYYMMDD.json.zst、data/raw_*.json（排除 test_* 文件）
- 本手册步骤为**额外手动触发**的激进清理（含日志/缩略图/pip cache/VACUUM），用于磁盘紧张时回收更多空间
- 完整流程每次可回收 20-40MB
