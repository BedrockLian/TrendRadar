#!/usr/bin/env python3
"""TrendRadar 推送降级看门狗 — 检查错误指标 + push_log 持续性故障 + 未送达补发。

检查项:
1. WeCom IPC socket 连通性
2. 所有 cron job 的 last_delivery_error
3. cron job 是否停止运行（已启用但从未执行）
4. push_log.json — 最近 3 次推送是否有持续性错误
5. sanity_check.py 可用性（拦截器就位检查）
6. auto-delivery 空投检测 — cron 产出后若内容未送达 WeCom，自动补发
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
MARKER_DIR = TRENDRADAR_HOME / 'data' / 'delivery_markers'
PYTHON = os.environ.get('PYTHON', '/usr/local/bin/python3.14t')


def _ensure_marker_dir():
    MARKER_DIR.mkdir(parents=True, exist_ok=True)


def _delivery_marker_path(run_id: str) -> Path:
    return MARKER_DIR / f'delivered_{run_id}.marker'


def mark_delivered(run_id: str):
    """标记某个 run_id 的内容已成功投递到 WeCom"""
    _ensure_marker_dir()
    _delivery_marker_path(run_id).write_text(
        datetime.now(CST).isoformat()
    )


def is_delivered(run_id: str) -> bool:
    """检查某个 run_id 是否已标记为投递成功"""
    return _delivery_marker_path(run_id).exists()


def send_to_wecom(file_path: str | Path, subject: str | None = None) -> bool:
    """通过 hermes send 投递内容到 WeCom。返回 True 表示成功。"""
    cmd = ['hermes', 'send', '--to', 'wecom:bl', '--file', str(file_path)]
    if subject:
        cmd.extend(['--subject', subject])
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            env={**os.environ, 'PYTHON_GIL': '1'}
        )
        if result.returncode == 0:
            return True
        # fallback: 部分系统 hermes 命令需要 GIL=0
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            env={**os.environ, 'PYTHON_GIL': '0'}
        )
        return result.returncode == 0
    except Exception:
        return False


# ── 原有检查 ──────────────────────────────────────────


def check_socket():
    """检查 WeCom gateway IPC socket 是否存在且可连接"""
    socket_paths = [
        "/tmp/hermes_gateway.sock",
        "/tmp/hermes_wecom.sock",
        "/tmp/hermes-wecom-card.sock",  # also checked by health_check
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
    for gil in ['1', '0']:
        try:
            result = subprocess.run(
                ["hermes", "cron", "list", "--json"],
                capture_output=True, text=True, timeout=15,
                env={**os.environ, "HERMES_HOME": HERMES_HOME, "PYTHON_GIL": gil}
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
            continue
    return None


def check_push_log() -> list[str]:
    """检查 push_log.json 最近 3 次推送是否有持续性错误。"""
    log_path = TRENDRADAR_HOME / 'data' / 'push_log.json'
    if not log_path.exists():
        return []

    alerts = []
    try:
        log = json.loads(log_path.read_text())
        if not isinstance(log, list) or len(log) < 1:
            return []

        recent = log[-3:]
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
            [PYTHON, str(script), '--json', '--no-check-links'],
            input='test', capture_output=True, text=True, timeout=10,
            env={**os.environ, 'PYTHONPATH': str(TRENDRADAR_HOME.parent), 'PYTHON_GIL': '0'}
        )
        if result.returncode not in (0, 3):
            return f"⚠️ sanity_check.py 异常退出 (exit={result.returncode})"
    except Exception as e:
        return f"⚠️ sanity_check.py 不可用: {e}"

    return None


# ── 新增：auto-delivery 空投检测 ────────────────────


def get_latest_evening_push() -> dict | None:
    """从 push_log.json 获取最新一次晚间推送记录。"""
    log_path = TRENDRADAR_HOME / 'data' / 'push_log.json'
    if not log_path.exists():
        return None
    try:
        log = json.loads(log_path.read_text())
        if not isinstance(log, list):
            return None
        # 从后往前找第一条 push_id=evening
        for entry in reversed(log):
            if entry.get('push_id') == 'evening':
                return entry
    except Exception:
        pass
    return None


def get_run_id_from_push(entry: dict) -> str | None:
    """从 push_log 条目提取 run_id。
    
    Matches format from common.py gen_run_id(): YYYYMMDD_slot_8hex
    Falls back to timestamp-based construction if run_id not in entry.
    """
    # Prefer explicit run_id if available
    run_id = entry.get('run_id', '')
    if run_id:
        return run_id
    # Fallback: construct from timestamp + push_id
    ts = entry.get('timestamp', '')
    push_id = entry.get('push_id', '')
    date_part = ts[:10].replace('-', '') if ts else ''
    if date_part and push_id:
        return f"{date_part}_{push_id}"
    return None


def get_latest_push_for_slot(slot: str) -> dict | None:
    """从 push_log.json 获取最近一次指定 slot 的推送记录。"""
    log_path = TRENDRADAR_HOME / 'data' / 'push_log.json'
    if not log_path.exists():
        return None
    try:
        log = json.loads(log_path.read_text())
        if not isinstance(log, list):
            return None
        for entry in reversed(log):
            if entry.get('push_id') == slot:
                return entry
    except Exception:
        pass
    return None


def _send_from_archive(archive_path: Path, alerts: list[str], slot_name: str) -> bool:
    """从 archive 文件读取内容并通过 hermes send 投递。返回成功/失败。"""
    try:
        content = archive_path.read_text(encoding='utf-8').strip()
        if not content:
            alerts.append(f"  ⚠️ {slot_name} 存档内容为空")
            return False
        import subprocess, tempfile
        tmp = Path(tempfile.gettempdir()) / f'{archive_path.stem}_redeliver.md'
        tmp.write_text(content)
        result = subprocess.run(
            ['hermes', 'send', '--to', 'wecom:bl', '--file', str(tmp)],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, 'PYTHON_GIL': '1'}
        )
        if result.returncode == 0:
            alerts.append(f"  ✅ {slot_name} 已补发至 WeCom")
            return True
        # fallback GIL
        result = subprocess.run(
            ['hermes', 'send', '--to', 'wecom:bl', '--file', str(tmp)],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, 'PYTHON_GIL': '0'}
        )
        if result.returncode == 0:
            alerts.append(f"  ✅ {slot_name} 已补发至 WeCom")
            return True
        alerts.append(f"  ❌ {slot_name} 补发失败 (hermes send exit={result.returncode})")
        return False
    except Exception as e:
        alerts.append(f"  ⚠️ {slot_name} 补发异常: {e}")
        return False


def _write_marker(today: str, push_id: str) -> None:
    """写入投递确认水印。"""
    _ensure_marker_dir()
    marker_path = MARKER_DIR / f'{today}_{push_id}.marker'
    marker_path.write_text(
        json.dumps({
            'push_id': push_id,
            'date': today,
            'delivered': True,
            'delivered_at': datetime.now(CST).isoformat(),
            'verified_by': 'delivery_watchdog',
        })
    )


def auto_redeliver_slot(alerts: list[str], push_id: str, slot_name: str, max_age_hours: int = 6) -> None:
    """检查某个 slot 的推送是否投递成功，未投递则自动补发。
    
    Args:
        push_id: 'morning' | 'noon' | 'evening'
        slot_name: 中文名称 for logging
        max_age_hours: 超过此时限的推送不补发
    """
    latest = get_latest_push_for_slot(push_id)
    
    if not latest:
        # push_log 不存在或没有该 slot 记录 → 退一步检查 archive
        today = datetime.now(CST).strftime('%Y-%m-%d')
        archive_path = TRENDRADAR_HOME / 'archive' / today / f'{push_id}.md'
        if archive_path.exists():
            # 检查水印 — 避免重复补发
            marker_path = MARKER_DIR / f'{today}_{push_id}.marker'
            if marker_path.exists():
                return  # 已标记投递
            alerts.append(f"🔄 {slot_name} ({today}) push_log 无记录但存档存在 → 从 archive 补发...")
            if _send_from_archive(archive_path, alerts, slot_name):
                _write_marker(today, push_id)
        return

    run_id = get_run_id_from_push(latest)
    if not run_id:
        return

    if is_delivered(run_id):
        return

    status = latest.get('status', '')
    ts = latest.get('timestamp', '')[:19]

    if status != 'ok':
        alerts.append(f"ℹ️ 最近{slot_name} ({ts}) 状态={status}，跳过补发")
        mark_delivered(run_id)
        return

    try:
        push_time = datetime.fromisoformat(ts)
        age_hours = (datetime.now(CST) - push_time).total_seconds() / 3600
        if age_hours > max_age_hours:
            alerts.append(f"ℹ️ 最近{slot_name} ({ts}) 已超过 {max_age_hours} 小时，不补发")
            mark_delivered(run_id)
            return
    except Exception:
        pass

    alerts.append(f"🔄 检测到{slot_name} ({ts}) 未投递到 WeCom，启动补发...")

    import tempfile
    briefing_path = Path(tempfile.gettempdir()) / f'{push_id}_briefing_{run_id}.md'
    try:
        result = subprocess.run(
            [PYTHON, str(TRENDRADAR_HOME / 'scripts' / 'render_markdown.py'),
             '--push-id', push_id],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, 'PYTHONPATH': str(TRENDRADAR_HOME.parent), 'PYTHON_GIL': '0'}
        )
        if result.returncode == 0 and result.stdout.strip():
            briefing_path.write_text(result.stdout)
            subprocess.run(
                [PYTHON, str(TRENDRADAR_HOME / 'scripts' / 'sanity_check.py'),
                 '--push-id', push_id],
                capture_output=True, timeout=15,
                env={**os.environ, 'PYTHONPATH': str(TRENDRADAR_HOME.parent), 'PYTHON_GIL': '0'}
            )
            if send_to_wecom(briefing_path):
                alerts.append(f"  ✅ {slot_name}已补发至 WeCom")
            else:
                alerts.append(f"  ❌ {slot_name}补发失败 (hermes send exit != 0)")
        else:
            alerts.append(f"  ⚠️ {slot_name}重新渲染失败 (exit={result.returncode})")
    except Exception as e:
        alerts.append(f"  ⚠️ {slot_name}补发异常: {e}")

    mark_delivered(run_id)


def auto_redeliver_evening(alerts: list[str]) -> None:
    """检查晚间晚报是否投递成功，未投递则自动补发（含深度分析）。"""
    auto_redeliver_slot(alerts, 'evening', '晚间推送', max_age_hours=6)

    # 晚间额外补发深度分析
    latest = get_latest_push_for_slot('evening')
    if latest:
        run_id = get_run_id_from_push(latest)
        if run_id and is_delivered(run_id):
            report_path = TRENDRADAR_HOME / 'reports'
            risk_file = None
            for f in sorted(report_path.glob('risk_analysis_*_evening.md'), reverse=True):
                risk_file = f
                break
            if risk_file and risk_file.stat().st_mtime > (datetime.now() - timedelta(hours=6)).timestamp():
                import tempfile
                formatted = Path(tempfile.gettempdir()) / f'risk_analysis_formatted_{run_id}.md'
                try:
                    result = subprocess.run(
                        ['cat', str(risk_file)],
                        capture_output=True, text=True, timeout=10
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        formatted.write_text(result.stdout)
                        if send_to_wecom(formatted, subject="🔬 风险与警示"):
                            alerts.append(f"  ✅ 深度分析已补发至 WeCom")
                except Exception as e:
                    alerts.append(f"  ⚠️ 深度分析补发异常: {e}")


def auto_redeliver_morning(alerts: list[str]) -> None:
    """检查早报是否投递成功，未投递则自动补发。"""
    auto_redeliver_slot(alerts, 'morning', '早报', max_age_hours=4)


def auto_redeliver_noon(alerts: list[str]) -> None:
    """检查午报是否投递成功，未投递则自动补发。"""
    auto_redeliver_slot(alerts, 'noon', '午间速递', max_age_hours=4)


# ── 主流程 ──────────────────────────────────────────


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

    # 5. 新增：auto-delivery 空投检测 + 自动补发（所有时段）\n    auto_redeliver_morning(alerts)\n    auto_redeliver_noon(alerts)\n    auto_redeliver_evening(alerts)

    # 6. 输出
    if alerts:
        # 过滤掉纯信息性日志（仅在有警报时输出标题）
        has_real_alert = any(
            a.startswith(('🚨', '🟡', '⚠️', '❌', '🔄')) for a in alerts
        )
        if has_real_alert:
            print(f"TrendRadar 推送看门狗巡检 ({now.strftime('%Y-%m-%d %H:%M:%S')})")
            print()
            for a in alerts:
                print(a)
    # 静默退出 — 无事件不推送


if __name__ == "__main__":
    main()
