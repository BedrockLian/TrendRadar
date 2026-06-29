#!/usr/bin/env python3
"""TrendRadar 健康体检脚本模板（v3.1，2026-06-29 更新）

变更：
- v3.1: check_gateway() 新增 Windows 支持（hermes gateway status）
- v3.1: CRON_JOB_NAMES 修正：'推送降级看门狗'→'推送看门狗'、'月度趋势报告'→'月度报告'、移除 slot_direct_push
- v3.0: 精简重建，纯 stdlib 实现，砍掉 trendradar.* import

设计原则：
- 不 import 任何 trendradar.* 包（避免 cron 环境 PYTHONPATH 缺失问题）
- 全部用 stdlib：sqlite3 / subprocess / curl / socket
- 7 个核心 check：db / scripts / cron / gateway / api / memory / data_freshness
- 偏好"一切从简"：只保留必要检查，静默健康

直接 `cp templates/trendradar_health_check.py ~/.hermes/scripts/trendradar_health_check.py` 即可使用。
Windows 上目标路径为 %LOCALAPPDATA%/hermes/scripts/trendradar_health_check.py。
"""
import json, subprocess, sys, os, time
from pathlib import Path
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
TR = Path(os.environ.get('TRENDRADAR_HOME', Path.home() / '.hermes' / 'trendradar'))
SCRIPTS = TR / 'scripts'
DATA = TR / 'data'

ISSUES = []
FIXES = []

# ── 已知 cron job 名称（模糊匹配，不依赖 job ID） ──────────
# 注意：名称必须与 hermes cron list 输出中 Name: 行的子串匹配
# 更新记录：2026-06-29 '推送降级看门狗'→'推送看门狗'、'月度趋势报告'→'月度报告'、移除 slot_direct_push
CRON_JOB_NAMES = [
    '日报推送', '推送看门狗', '每日维护',
    '自动体检', '周报推送', '月度报告',
]


def fail(component, severity, msg):
    ISSUES.append({'component': component, 'severity': severity, 'msg': msg})


# ═══════════════════════════════════════════════════════════════
# 核心检查（不 import trendradar.*）
# ═══════════════════════════════════════════════════════════════

def check_db():
    """指纹库完整性 + WAL"""
    db = DATA / 'fingerprints.db'
    if not db.exists():
        fail('fingerprints.db', 'CRITICAL', '数据库文件不存在')
        return
    size = db.stat().st_size
    if size < 1000:
        fail('fingerprints.db', 'CRITICAL', f'数据库仅 {size}B')
        return
    try:
        import sqlite3  # stdlib only
        conn = sqlite3.connect(str(db))
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        if 'fingerprints' not in tables:
            fail('fingerprints.db', 'CRITICAL', 'fingerprints 表不存在')
        else:
            cnt = conn.execute('SELECT COUNT(*) FROM fingerprints').fetchone()[0]
            if cnt == 0:
                fail('fingerprints.db', 'WARN', 'fingerprints 表为空（首次运行正常）')
        journal = conn.execute('PRAGMA journal_mode').fetchone()[0]
        if journal.upper() != 'WAL':
            fail('fingerprints.db', 'WARN', f'journal_mode={journal}（建议 WAL）')
        conn.close()
    except Exception as e:
        fail('fingerprints.db', 'WARN', f'数据库检查失败: {e}')


def check_scripts():
    """核心脚本存在性（不含已删除的 batch_fetch.py）"""
    required = [
        'push_prepare.py', 'fetch_feeds.py', 'push_slot_detect.py',
        'record_fingerprints.py', 'track_events.py', 'heat_tracker.py',
        'ai_translate.py', 'render_markdown.py', 'fragment_push.py',
        'render_deep_analysis.py', 'curate_and_push.py',
        'pipeline_orchestrator.py', 'common.py', 'settings.py', 'storage.py',
        'sanity_check.py', 'blind_spot_audit.py', 'aggregate_monthly.py',
    ]
    for name in required:
        if not (SCRIPTS / name).exists():
            fail(f'trendradar/scripts/{name}', 'WARN', '文件缺失')


def check_cron():
    """cron 调度器 — 关键 job 注册（按名称模糊匹配）"""
    try:
        r = subprocess.run(['hermes', 'cron', 'list'],
                          capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            fail('cron', 'WARN', f'hermes cron list 失败 (exit={r.returncode})')
            return
        import re
        job_names = set()
        for line in r.stdout.split('\n'):
            m = re.match(r'\s+Name:\s+(.+)', line)
            if m:
                job_names.add(m.group(1).strip())
        for name in CRON_JOB_NAMES:
            if any(name in jn for jn in job_names):
                continue
            # 退化：分 token 匹配
            fuzzy = any(
                any(token in jn for token in name.split())
                for jn in job_names
            )
            if not fuzzy:
                fail('cron', 'WARN', f'job "{name}" 未注册')
    except Exception as e:
        fail('cron', 'WARN', f'cron 检查异常: {e}')


def check_gateway():
    """WeCom gateway 连接 — systemd (Linux) / hermes CLI (Windows)"""
    # Windows: 用 hermes gateway status 检查
    if sys.platform == 'win32':
        try:
            r = subprocess.run(
                [sys.executable, '-m', 'hermes_cli.main', 'gateway', 'status'],
                capture_output=True, text=True, timeout=10,
            )
            if 'Gateway process running' in r.stdout or 'PID:' in r.stdout:
                return  # ✅ 正常
            fail('gateway', 'WARN', 'hermes-gateway 未运行')
        except Exception as e:
            fail('gateway', 'WARN', f'gateway 检查异常: {e}')
        return
    # Linux: systemd 状态检测
    try:
        r = subprocess.run(
            ['systemctl', '--user', 'is-active', 'hermes-gateway.service'],
            capture_output=True, text=True, timeout=5,
        )
        status = r.stdout.strip()
        if status == 'active':
            return
        if status in ('inactive', 'dead'):
            fail('gateway', 'WARN', 'hermes-gateway.service 未运行 (inactive)')
        elif status == 'failed':
            fail('gateway', 'WARN', 'hermes-gateway.service 已崩溃 (failed)')
        else:
            fail('gateway', 'WARN', f'hermes-gateway 状态未知: {status}')
    except FileNotFoundError:
        # 无 systemd — 检查 IPC socket
        for p in ['/tmp/hermes-wecom-card.sock', '/tmp/hermes_wecom.sock',
                  '/tmp/hermes_gateway.sock']:
            if Path(p).exists():
                return
        fail('gateway', 'WARN', 'hermes-gateway 未运行（无 systemd 且无 IPC socket）')
    except Exception as e:
        fail('gateway', 'WARN', f'gateway 检查异常: {e}')


def check_api():
    """外网连通性 — DeepSeek API（NO_PROXY 直连可达）"""
    try:
        env = os.environ.copy()
        for k in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
            env.pop(k, None)
        r = subprocess.run(
            ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}',
             '--connect-timeout', '5', 'https://api.deepseek.com/v1/models'],
            capture_output=True, text=True, timeout=10, env=env
        )
        code = r.stdout.strip()
        if code not in ('200', '401', '403'):
            fail('api', 'WARN', f'DeepSeek API 不可达 (HTTP {code})')
    except subprocess.TimeoutExpired:
        fail('api', 'WARN', 'DeepSeek API 超时')
    except Exception as e:
        fail('api', 'WARN', f'API 检查失败: {e}')


def check_memory_size():
    """记忆文件膨胀监控"""
    for label, rel_path, limit in [
        ('MEMORY.md', '.hermes/memories/MEMORY.md', 2200),
        ('USER.md', '.hermes/memories/USER.md', 1375),
    ]:
        p = Path.home() / rel_path
        if not p.exists():
            continue
        size = len(p.read_text(encoding='utf-8'))
        pct = int(size / limit * 100)
        if pct >= 90:
            fail('memory', 'WARN', f'{label} 已膨胀至 {pct}% ({size}/{limit})')
        elif pct >= 75:
            fail('memory', 'WARN', f'{label} 使用率 {pct}% ({size}/{limit})')


def check_data_freshness():
    """最新 curated 数据时效"""
    now = time.time()
    files = sorted(DATA.glob('curated_*.json'),
                   key=lambda f: f.stat().st_mtime, reverse=True)
    if files:
        age_h = (now - files[0].stat().st_mtime) / 3600
        if age_h > 15:
            fail('data', 'WARN', f'最新 curated 数据已 {age_h:.1f}h 未更新')
    else:
        fail('data', 'WARN', '无 curated 数据文件')


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════

def main():
    check_db()
    check_scripts()
    check_cron()
    check_gateway()
    check_api()
    check_memory_size()
    check_data_freshness()

    severe = [i for i in ISSUES if i['severity'] in ('WARN', 'CRITICAL')]

    if not severe and not FIXES:
        return 0  # 静默健康

    now = datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')
    out = [f'# Hermes 趋势雷达 · 自动体检报告\n\n**时间:** {now}\n']
    if FIXES:
        out.append('### 🔧 自动修复')
        for f in FIXES:
            out.append(f'- ✅ {f}')
        out.append('')
    if severe:
        out.append('### ⚠️ 警告')
        for i in severe:
            out.append(f"- **{i['component']}**: {i['msg']}")
        out.append('')
    if severe:
        critical = sum(1 for i in severe if i['severity'] == 'CRITICAL')
        warn = sum(1 for i in severe if i['severity'] == 'WARN')
        if critical:
            status = f'🔴 **状态: 异常** — {critical} 个 CRITICAL 项需立即处理'
        else:
            status = f'🟡 **状态: 亚健康** — {warn} 个警告项需关注'
        out.append(status + '\n')
    out.append('📡 趋势雷达自动体检 · 下次运行时自动重检')
    print('\n'.join(out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
