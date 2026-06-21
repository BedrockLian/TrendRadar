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

# FIX 2026-06-10 (cron no_agent run): ensure `trendradar` package is importable
# regardless of where cron scheduler invokes this script from. Without this,
# `from trendradar.scripts.fragment_push import split_fragments` fails with
# `ModuleNotFoundError: No module named 'trendradar'` because sys.path only
# contains HERMES_HOME/scripts (where this file lives), not the trendradar
# package root.
#
# We use the env vars set by cron OR fall back to the Windows canonical path.
# The path resolvers below (defined further down) will re-resolve correctly
# once they execute; this block just sets up import-time sys.path.
import sys as _sys
for _p in (
    os.environ.get('TRENDRADAR_HOME'),
    os.environ.get('HERMES_HOME', '') + '\\trendradar' if os.environ.get('HERMES_HOME') else None,
    str(Path(os.environ.get('LOCALAPPDATA', 'C:/Users/ASUS/AppData/Local')) / 'hermes' / 'trendradar'),
    str(Path.home() / '.hermes' / 'trendradar'),  # Linux fallback
):
    if _p and Path(_p).exists() and _p not in _sys.path:
        _sys.path.insert(0, _p)
del _p

# FIX 2026-06-09 (Windows compatibility): resolve paths via Hermes' own API
# (hermes_constants.get_hermes_home) instead of hardcoding "~/.hermes" which
# only works on Linux. On Windows, Hermes lives at %LOCALAPPDATA%\hermes, so
# Path.home() / '.hermes' resolves to C:\Users\<user>\.hermes (non-existent).
def _resolve_hermes_home() -> Path:
    """Find Hermes root: env override → hermes_constants API → Linux fallback."""
    env = os.environ.get('HERMES_HOME')
    if env:
        return Path(env)
    try:
        # Lazy import: hermes-agent may not be on sys.path in standalone use.
        import sys as _sys
        candidates = [
            Path(os.environ.get('LOCALAPPDATA', '')) / 'hermes' / 'hermes-agent',
            Path.home() / '.hermes' / 'hermes-agent',
        ]
        for cand in candidates:
            if cand.exists():
                _sys.path.insert(0, str(cand))
                from hermes_constants import get_hermes_home  # type: ignore
                return Path(get_hermes_home())
    except Exception:
        pass
    # Last-resort fallback (Linux only — Windows will fail loudly later).
    return Path.home() / '.hermes'


def _resolve_trendradar_home() -> Path:
    env = os.environ.get('TRENDRADAR_HOME')
    if env:
        return Path(env)
    # Default: <HERMES_HOME>/trendradar (works on both Linux and Windows).
    return _resolve_hermes_home() / 'trendradar'


HERMES_HOME = _resolve_hermes_home()
TRENDRADAR_HOME = _resolve_trendradar_home()
MARKER_DIR = TRENDRADAR_HOME / 'data' / 'delivery_markers'

# FIX 2026-06-09 (Windows): PYTHON default no longer hardcodes Linux path.
# Prefer venv python.exe alongside this script's parents, else sys.executable.
_SCRIPT_PY_CANDIDATES = [
    HERMES_HOME / 'hermes-agent' / 'venv' / 'Scripts' / 'python.exe',  # Windows
    HERMES_HOME / 'hermes-agent' / 'venv' / 'bin' / 'python',           # Linux
    Path(sys.executable),                                                # fallback
]
PYTHON = os.environ.get('PYTHON') or str(
    next((p for p in _SCRIPT_PY_CANDIDATES if p.exists()), Path(sys.executable))
)


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
    """通过 hermes send 投递内容到 WeCom，自动分片避免截断。

    WeCom markdown 消息限制约 4096 字节。当前 archive 简报经常 8-10KB，
    直接发送会被截断。修法：按 `### ` 节标题拆分，每片 ≤ 3200 字节，
    逐片发送（审计 2026-06-21 修复）。

    如果内容很干净（≤3200B），单次发送走快速路径。
    """
    content = Path(file_path).read_text(encoding='utf-8')
    WECOM_CHUNK_LIMIT = 3200  # 安全余量，实际限制~4096

    # 快速路径：内容足够短
    if len(content.encode('utf-8')) <= WECOM_CHUNK_LIMIT:
        return _send_raw(file_path, subject)

    # 按 `### ` 节拆分（保留标题标记）
    import re
    sections = re.split(r'(?=^### )', content, flags=re.MULTILINE)
    if len(sections) <= 1:
        # 没有节标题，按段落拆分
        sections = re.split(r'(?=^\*\*|^---)', content, flags=re.MULTILINE)

    chunks = []
    current = []
    current_size = 0

    for section in sections:
        section_size = len(section.encode('utf-8'))
        # 单节超过限制 → 按行拆
        if section_size > WECOM_CHUNK_LIMIT:
            if current:
                chunks.append(''.join(current))
                current = []
                current_size = 0
            lines = section.splitlines(keepends=True)
            sub = []
            sub_size = 0
            for line in lines:
                line_sz = len(line.encode('utf-8'))
                if sub_size + line_sz > WECOM_CHUNK_LIMIT and sub:
                    chunks.append(''.join(sub))
                    sub = []
                    sub_size = 0
                sub.append(line)
                sub_size += line_sz
            if sub:
                chunks.append(''.join(sub))
        elif current_size + section_size > WECOM_CHUNK_LIMIT and current:
            chunks.append(''.join(current))
            current = [section]
            current_size = section_size
        else:
            current.append(section)
            current_size += section_size

    if current:
        chunks.append(''.join(current))

    # 逐片发送
    success = True
    for i, chunk in enumerate(chunks):
        import tempfile, os as _os
        fd, tmp = tempfile.mkstemp(suffix='.md', prefix=f'fragment_{i}_')
        _os.close(fd)
        tmp_path = Path(tmp)
        try:
            tmp_path.write_text(chunk, encoding='utf-8')
            ok = _send_raw(tmp_path, subject=f'{subject} ({i+1}/{len(chunks)})' if subject else f'({i+1}/{len(chunks)})')
            if not ok:
                success = False
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    return success


def _send_raw(file_path: Path, subject: str | None = None) -> bool:
    """单次 hermes send 调用（内部使用）。"""
    cmd = ['hermes', 'send', '--to', 'wecom:bl', '--file', str(file_path)]
    if subject:
        cmd.extend(['--subject', subject])
    for gil in ('1', '0'):
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                env={**os.environ, 'PYTHON_GIL': gil}
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass
    return False


# ── 原有检查 ──────────────────────────────────────────


def check_socket():
    """检查 WeCom gateway IPC socket 是否存在且可连接

    FIX 2026-06-09 (Windows): Hermes Desktop / Windows builds use a different
    IPC location (named pipe or TCP localhost). Unix-domain sockets under
    /tmp/ are Linux-only. We probe both layouts and also accept the gateway
    as 'up' when its HTTP API responds on localhost.
    """
    socket_paths = [
        # Linux Unix-domain sockets
        "/tmp/hermes_gateway.sock",
        "/tmp/hermes_wecom.sock",
        "/tmp/hermes-wecom-card.sock",  # also checked by health_check
    ]
    # Windows: Hermes uses named pipes or TCP. Probe via gateway HTTP health.
    # We try a few likely ports (gateway default + common alternates) using a
    # short timeout — if any responds we treat the gateway as reachable.
    import urllib.request
    for port in (8765, 8000, 8888, 7777):
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/health", timeout=2
            ) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
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
    """从 hermes cron list 获取 job 状态

    FIX 2026-06-09 (Windows): env values must be str, not Path. Wrap explicitly
    to avoid TypeError on Windows CreateProcess.
    """
    for gil in ['1', '0']:
        try:
            # Build env with explicit str() coercion (HERMES_HOME is a Path).
            _env = {k: (str(v) if not isinstance(v, str) else v)
                    for k, v in os.environ.items()}
            _env["HERMES_HOME"] = str(HERMES_HOME)
            _env["PYTHON_GIL"] = gil
            result = subprocess.run(
                ["hermes", "cron", "list", "--json"],
                capture_output=True, text=True, timeout=15,
                env=_env
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
    """检查 sanity_check.py 是否可用（拦截器就位检查）。

    FIX 2026-06-09: probe both the outer sync copy and the inner git-truth
    copy. With scripts_sync.sh in place they should be identical, but if a
    sync was missed, the inner copy is the canonical source and should count.
    """
    candidates = [
        TRENDRADAR_HOME / 'scripts' / 'sanity_check.py',         # outer (synced)
        TRENDRADAR_HOME / 'trendradar' / 'scripts' / 'sanity_check.py',  # inner (git truth)
    ]
    script = next((p for p in candidates if p.exists()), None)
    if not script:
        return "⚠️ sanity_check.py 不存在 — 发布前拦截器未就位"

    try:
        # FIX 2026-06-09: sanity_check doesn't have a --probe mode, so we
        # invoke it with a trivial empty file + --no-check-links. exit 0/3
        # both indicate "the script ran successfully" (3 = warnings only).
        import tempfile as _tf
        with _tf.NamedTemporaryFile(
            mode='w', suffix='.md', delete=False, encoding='utf-8'
        ) as _tfh:
            _tfh.write('')
            _probe_file = _tfh.name
        try:
            result = subprocess.run(
                [PYTHON, str(script), '--no-check-links', '--file', _probe_file],
                capture_output=True, timeout=15,
                env={**os.environ, 'PYTHONPATH': str(TRENDRADAR_HOME), 'PYTHON_GIL': '0'}
            )
        finally:
            try:
                os.unlink(_probe_file)
            except OSError:
                pass
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
    """从 archive 文件读取内容，分片后逐片通过 hermes send 投递。返回成功/失败。"""
    try:
        content = archive_path.read_text(encoding='utf-8').strip()
        if not content:
            alerts.append(f"  ⚠️ {slot_name} 存档内容为空")
            return False
        from trendradar.scripts.fragment_push import split_fragments
        fragments = split_fragments(content)
        if not fragments:
            alerts.append(f"  ⚠️ {slot_name} 分片后无内容")
            return False
        import subprocess, tempfile
        success = True
        for i, frag in enumerate(fragments):
            fd, tmp_path = tempfile.mkstemp(suffix='.md', prefix=f'{archive_path.stem}_frag{i}_')
            os.close(fd)
            tmp = Path(tmp_path)
            try:
                tmp.write_text(frag)
                for gil in ['1', '0']:
                    result = subprocess.run(
                        ['hermes', 'send', '--to', 'wecom:bl', '--file', str(tmp)],
                        capture_output=True, text=True, timeout=30,
                        env={**os.environ, 'PYTHON_GIL': gil}
                    )
                    if result.returncode == 0:
                        break
                if result.returncode == 0:
                    alerts.append(f"  ✅ {slot_name} 分片{i+1}/{len(fragments)} 已投递")
                else:
                    alerts.append(f"  ❌ {slot_name} 分片{i+1}/{len(fragments)} 投递失败")
                    success = False
            finally:
                try:
                    tmp.unlink()
                except OSError:
                    pass
        return success
    except Exception as e:
        alerts.append(f"  ⚠️ {slot_name} 补发异常: {e}")
        return False


def _write_marker(today: str, push_id: str) -> None:
    """写入投递确认水印。

    FIX 2026-06-09 (marker naming consistency): was writing '{today}_{push_id}.marker'
    which is the FAILED-attempt naming, not the delivered-attempt naming.
    is_delivered(run_id) and mark_delivered(run_id) both expect the
    'delivered_{...}.marker' prefix. Without this fix, auto_redeliver_slot
    would re-deliver forever after every successful send.
    """
    _ensure_marker_dir()
    # Use the same key shape as mark_delivered: derived from today + push_id
    # so that get_run_id_from_push() lookups and 'delivered_<run_id>' align.
    run_id = f'{today.replace("-", "")}_{push_id}'
    marker_path = MARKER_DIR / f'delivered_{run_id}.marker'
    marker_path.write_text(
        json.dumps({
            'push_id': push_id,
            'date': today,
            'run_id': run_id,
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
    VALID_PUSH_IDS = {'morning', 'noon', 'evening'}
    if push_id not in VALID_PUSH_IDS:
        alerts.append(f"⚠️ 无效 push_id: {push_id}，跳过补发")
        return
    
    latest = get_latest_push_for_slot(push_id)
    
    if not latest:
        # push_log 不存在或没有该 slot 记录 → 退一步检查 archive
        today = datetime.now(CST).strftime('%Y-%m-%d')
        archive_path = TRENDRADAR_HOME / 'archive' / today / f'{push_id}.md'
        if archive_path.exists():
            # 检查水印 — 避免重复补发（FIX 2026-06-09: 用 delivered_ 前缀
            # 跟 _write_marker 保持一致，否则每次都重发）
            run_id = f'{today.replace("-", "")}_{push_id}'
            marker_path = MARKER_DIR / f'delivered_{run_id}.marker'
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
    fd, tmp_path = tempfile.mkstemp(suffix='.md', prefix=f'{push_id}_briefing_')
    os.close(fd)
    briefing_path = Path(tmp_path)
    try:
        result = subprocess.run(
            [PYTHON, str(TRENDRADAR_HOME / 'scripts' / 'render_markdown.py'),
             '--push-id', push_id],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, 'PYTHONPATH': str(TRENDRADAR_HOME), 'PYTHON_GIL': '0'}
        )
        if result.returncode == 0 and result.stdout.strip():
            briefing_path.write_text(result.stdout)
            subprocess.run(
                [PYTHON, str(TRENDRADAR_HOME / 'scripts' / 'sanity_check.py'),
                 '--push-id', push_id],
                capture_output=True, timeout=15,
                env={**os.environ, 'PYTHONPATH': str(TRENDRADAR_HOME), 'PYTHON_GIL': '0'}
            )
            if send_to_wecom(briefing_path):
                alerts.append(f"  ✅ {slot_name}已补发至 WeCom")
                mark_delivered(run_id)
            else:
                alerts.append(f"  ❌ {slot_name}补发失败 (hermes send exit != 0)")
        else:
            alerts.append(f"  ⚠️ {slot_name}重新渲染失败 (exit={result.returncode})")
    except Exception as e:
        alerts.append(f"  ⚠️ {slot_name}补发异常: {e}")
    finally:
        try:
            briefing_path.unlink(missing_ok=True)
        except OSError:
            pass


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
                fd, tmp_path = tempfile.mkstemp(suffix='.md', prefix='risk_analysis_formatted_')
                os.close(fd)
                formatted = Path(tmp_path)
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
                finally:
                    try:
                        formatted.unlink(missing_ok=True)
                    except OSError:
                        pass


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

    # 1. Socket 检查（FIX 2026-06-10: 改为 DEBUG-only，cron 主链路用 hermes send
    # 直连 gateway HTTP API，不依赖 Unix socket。socket 检查在 Windows 上永远
    # 不可达（gateway 用 HTTP / WebSocket，不暴露 /tmp socket），不应触发警报。
    # 这里只静默探测，记入隐式健康状态供将来扩展。
    _socket_ok = check_socket()
    # 不再 append alert — 仅日志

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

    # 5. 新增：auto-delivery 空投检测 + 自动补发（所有时段）
    auto_redeliver_morning(alerts)
    auto_redeliver_noon(alerts)
    auto_redeliver_evening(alerts)

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
