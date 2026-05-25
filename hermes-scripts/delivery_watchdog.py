#!/usr/bin/env python3
"""TrendRadar 推送降级看门狗 — 检查错误指标 + push_log 持续性故障。

检查项:
1. WeCom IPC socket 连通性
2. 所有 cron job 的 last_delivery_error
3. cron job 是否停止运行（已启用但从未执行）
4. push_log.json — 最近 3 次推送是否有持续性错误
5. sanity_check.py 可用性（拦截器就位检查）
"""

import json
import os
import socket
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

CST = timezone(timedelta(hours=8))
HERMES_HOME = os.path.expanduser("~/.hermes")
TRENDRADAR_HOME = Path(os.environ.get(
    'TRENDRADAR_HOME',
    Path.home() / '.hermes' / 'trendradar'
))


def check_socket():
    """检查 WeCom gateway IPC socket 是否存在且可连接"""
    socket_paths = [
        "/tmp/hermes_gateway.sock",
        "/tmp/hermes_wecom.sock",
    ]
    for path in socket_paths:
        if os.path.exists(path):
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(3)
                s.connect(path)
                s.close()
                return True
            except (socket.error, FileNotFoundError):
                continue
    return False


def get_cron_jobs():
    """从 hermes cron list 获取 job 状态"""
    try:
        result = subprocess.run(
            ["hermes", "cron", "list", "--json"],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "HERMES_HOME": HERMES_HOME}
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        pass
    try:
        result = subprocess.run(
            ["hermes", "cron", "list"],
            capture_output=True, text=True, timeout=15
        )
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def check_push_log() -> list[str]:
    """检查 push_log.json 最近 3 次推送是否有持续性错误。

    如果最近 3 次全部 error → 管线可能已卡死。
    如果非空 errors 数组 → 部分失败，需注意。
    """
    log_path = TRENDRADAR_HOME / 'data' / 'push_log.json'
    if not log_path.exists():
        return []

    alerts = []
    try:
        log = json.loads(log_path.read_text())
        if not isinstance(log, list) or len(log) < 1:
            return []

        recent = log[-3:]  # 最近 3 次
        error_entries = [e for e in recent if e.get('status') == 'error']
        partial_entries = [e for e in recent if e.get('error_count', 0) > 0]

        if len(error_entries) == len(recent) and len(recent) >= 2:
            alerts.append(
                f"🚨 push_log: 最近 {len(recent)} 次推送全部失败 "
                f"({', '.join(e.get('push_id','?') for e in error_entries)})"
            )
        elif len(error_entries) >= 1:
            alerts.append(
                f"⚠️ push_log: {len(error_entries)}/{len(recent)} 次推送失败"
            )
        elif partial_entries:
            alerts.append(
                f"ℹ️ push_log: {len(partial_entries)}/{len(recent)} 次推送有部分错误"
            )
    except Exception:
        pass

    return alerts


def check_sanity() -> str | None:
    """检查 sanity_check.py 是否可用（拦截器就位检查）。"""
    script = TRENDRADAR_HOME / 'scripts' / 'sanity_check.py'
    if not script.exists():
        return "⚠️ sanity_check.py 不存在 — 发布前拦截器未就位"

    try:
        result = subprocess.run(
            ['/usr/local/bin/python3.14t', str(script), '--json', '--no-check-links'],
            input='test', capture_output=True, text=True, timeout=10,
            env={**os.environ, 'PYTHONPATH': str(TRENDRADAR_HOME.parent), 'PYTHON_GIL': '0'}
        )
        if result.returncode not in (0, 3):
            return f"⚠️ sanity_check.py 异常退出 (exit={result.returncode})"
    except Exception as e:
        return f"⚠️ sanity_check.py 不可用: {e}"

    return None


def main():
    now = datetime.now(CST)
    alerts = []

    # 1. Socket 检查
    if not check_socket():
        alerts.append("🚨 WeCom IPC socket 不可达 — gateway 可能已停止")

    # 2. Cron job 错误检查
    jobs = get_cron_jobs()
    if isinstance(jobs, list):
        for job in jobs:
            jid = job.get("job_id", "?")
            name = job.get("name", "?")
            err = job.get("last_delivery_error")
            last_run = job.get("last_run_at")
            enabled = job.get("enabled", True)

            if not enabled:
                continue

            if err:
                alerts.append(f"🟡 [{jid}] {name}\n   投递错误: {err}")

            if enabled and last_run is None:
                status = job.get("state", "")
                if status != "pending":
                    alerts.append(f"🟡 [{jid}] {name}\n   已启用但从未运行 (state={status})")

    # 3. push_log 持续性故障检查
    alerts.extend(check_push_log())

    # 4. sanity_check 拦截器就位检查
    sanity_issue = check_sanity()
    if sanity_issue:
        alerts.append(sanity_issue)

    # 5. 输出
    if alerts:
        print(f"TrendRadar 推送看门狗巡检 ({now.strftime('%Y-%m-%d %H:%M:%S')})")
        print()
        for a in alerts:
            print(a)
    # 静默退出 — 无事件不推送


if __name__ == "__main__":
    main()
