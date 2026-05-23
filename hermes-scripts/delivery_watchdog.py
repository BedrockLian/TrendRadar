#!/usr/bin/env python3
"""TrendRadar 推送降级看门狗 — 只检查错误指标，不按时间窗口判死。

检查项:
1. WeCom IPC socket 连通性
2. 所有 cron job 的 last_delivery_error（最近一次投递错误）
3. cron job 是否停止运行（last_run 为 None 且状态不是 pending）

不检查: "最近X小时内无活动" — 因为各 job 调度间隔不同（日报12h空档、优化器23h空档），
固定时间窗口会产生假阳性。
"""

import json
import os
import socket
import subprocess
import sys
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
HERMES_HOME = os.path.expanduser("~/.hermes")

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
    # fallback: try parsing the CLI output
    try:
        result = subprocess.run(
            ["hermes", "cron", "list"],
            capture_output=True, text=True, timeout=15
        )
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

def main():
    now = datetime.now(CST)
    alerts = []

    # 1. Socket 检查
    if not check_socket():
        alerts.append(f"🚨 WeCom IPC socket 不可达 — gateway 可能已停止")

    # 2. 从 cron list 检查
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

            # 只检查错误
            if err:
                alerts.append(f"🟡 [{jid}] {name}\n   投递错误: {err}")

            # 检查从未运行过的 job（已启用但从未执行过）
            if enabled and last_run is None:
                status = job.get("state", "")
                if status != "pending":
                    alerts.append(f"🟡 [{jid}] {name}\n   已启用但从未运行 (state={status})")

    elif isinstance(jobs, str):
        # CLI text output fallback — just report basic info
        alerts.append(f"📋 看门狗运行于 {now.strftime('%Y-%m-%d %H:%M')}")

    # 3. 输出
    if alerts:
        print(f"TrendRadar 推送看门狗巡检 ({now.strftime('%Y-%m-%d %H:%M:%S')})")
        print()
        for a in alerts:
            print(a)
        sys.exit(0)
    else:
        # 静默退出 — 无事件不推送
        sys.exit(0)

if __name__ == "__main__":
    main()
