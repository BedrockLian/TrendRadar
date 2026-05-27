# Atomic File Writes (并发安全)

## 问题

多 cron job 并发写入同一 JSON 文件时，`read_text` → modify → `write_text` 之间存在竞争窗口（TOCTOU）。
若两个进程同时读、各自修改、先后写入，后写者覆盖前写者的数据。

## 模式：临时文件 + os.replace

```python
import json, os, tempfile

def atomic_write_json(path: Path, data):
    """原子写入 JSON — 先写临时文件，再 os.replace（原子 rename）"""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.tmp_')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)  # 原子操作 — 不会出现半写文件
    except Exception:
        os.unlink(tmp)
        raise
```

## 适用场景

- `push_log.json` — 每次推送追加一条记录，多 cron 可能同时写入
- `sources.json` — 多进程可能同时更新
- 任何被多个 cron job 并发读写的 JSON 文件

## 已应用

- `settings.atomic_write_json()` — 通用原子写入（`push_prepare.py` 使用）
- `pipeline_orchestrator._write_push_log()` — 已改为临时文件 + os.replace 模式（v2.8.0+）
