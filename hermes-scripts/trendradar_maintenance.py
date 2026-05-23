#!/usr/bin/env python3
"""TrendRadar 每日维护：数据备份 + 缓存清理

安排：每天 03:00 运行（推送空闲时段）
- 备份 fingerprints.db / 配置 / preferences 到 ~/backups/trendradar/
- 清理 cache/ 和旧 curated/raw 文件（>7 天）
- 保留 30 天备份
"""
import shutil
import os
import sys
import time
import glob
from datetime import datetime

TRENDDIR = os.path.expanduser("~/.hermes/trendradar")
BACKUPDIR = os.path.expanduser("~/backups/trendradar")
RETENTION_FILE_DAYS = 7
RETENTION_BACKUP_DAYS = 30


def backup():
    today = datetime.now().strftime("%Y%m%d")
    dest = os.path.join(BACKUPDIR, today)
    os.makedirs(dest, exist_ok=True)

    items = [
        ("data/fingerprints.db", "fingerprints.db"),
        ("data/preferences.json", "preferences.json"),
        ("data/push_log.json", "push_log.json"),
        ("data/sources.json", "sources.json"),
    ]
    errors = []
    for src_rel, name in items:
        src = os.path.join(TRENDDIR, src_rel)
        if os.path.exists(src):
            try:
                shutil.copy2(src, os.path.join(dest, name))
            except OSError as e:
                errors.append(f"{name}: {e}")

    # 配置目录
    cfg_src = os.path.join(TRENDDIR, "config")
    if os.path.exists(cfg_src):
        cfg_dst = os.path.join(dest, "config")
        try:
            shutil.copytree(cfg_src, cfg_dst, dirs_exist_ok=True)
        except OSError as e:
            errors.append(f"config: {e}")

    # 过期备份清理
    cutoff = time.time() - RETENTION_BACKUP_DAYS * 86400
    for d in glob.glob(os.path.join(BACKUPDIR, "*")):
        if os.path.isdir(d) and os.path.getmtime(d) < cutoff:
            try:
                shutil.rmtree(d)
            except OSError:
                pass

    if errors:
        print(f"[BACKUP ERROR] {'; '.join(errors)}")
        sys.exit(1)


def cleanup():
    cutoff = time.time() - RETENTION_FILE_DAYS * 86400
    patterns = [
        "cache/*.json",
        "data/raw_*.json",
        "data/curated_*_????????.json",
    ]
    errors = []
    for pat in patterns:
        for f in glob.glob(os.path.join(TRENDDIR, pat)):
            try:
                if os.path.getmtime(f) < cutoff:
                    os.remove(f)
            except OSError as e:
                errors.append(f"{os.path.basename(f)}: {e}")

    if errors:
        print(f"[CLEANUP ERROR] {'; '.join(errors)}")
        sys.exit(1)


def runtests() -> bool:
    """运行 pytest 烟雾测试，返回是否全部通过。"""
    import subprocess
    result = subprocess.run(
        ["python3", "-m", "pytest", "tests/", "-q", "--tb=line", "-m", "not slow"],
        cwd=TRENDDIR,
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        print(f"[TESTS FAILED] {result.stdout[-200:]}", file=sys.stderr)
        return False
    return True


if __name__ == "__main__":
    backup()
    cleanup()
    if not runtests():
        print("[WARNING] 烟雾测试未通过，但备份和清理已完成", file=sys.stderr)
