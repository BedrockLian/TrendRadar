# PYTHON_GIL 崩溃陷阱

> Added: 2026-05-29
> Trigger: `archive_resend.py` 和 `hermes send` 在 cron 环境（PYTHON_GIL=0）下崩溃

## 症状

```
Fatal Python error: config_read_gil: Disabling the GIL is not supported by this build
Python runtime state: preinitialized
```

## 根因

cron 环境默认设置 `PYTHON_GIL=0`（free-threaded Python 3.14t 的标志），但 `archive_resend.py` 启动的子进程和 `hermes send` CLI 二进制在启动时尝试禁用 GIL 失败。这个 Python 构建不支持无 GIL 模式。

## 修复

### archive_resend.py

```bash
# ❌ 会崩溃：PYTHON_GIL=0 被继承
export PYTHON=/usr/local/bin/python3.14t PYTHONPATH=/home/asus/.hermes PYTHON_GIL=0
$PYTHON scripts/archive_resend.py --date YYYY-MM-DD --slot evening

# ✅ 正确：不设 PYTHON_GIL
export PYTHON=/usr/local/bin/python3.14t PYTHONPATH=/home/asus/.hermes
$PYTHON scripts/archive_resend.py --date YYYY-MM-DD --slot evening
```

### hermes send

```bash
# ❌ 会崩溃
hermes send --to wecom:bl < file.md

# ✅ 正确：PYTHON_GIL= 覆盖（设空字符串覆盖继承值）
cat file.md | PYTHON_GIL= hermes send --to wecom:bl
```

## 何时触达

- cron 推送失败后的手动补发
- 任何需要手动运行 `archive_resend.py` 的场景
- 在 cron 环境下直接调用 `hermes send`
