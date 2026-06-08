#!/usr/bin/env python3
"""TrendRadar 自动体检 + 自修复脚本 v3.0 (2026-06-02 精简重建)

设计原则（按 2026-06-02 偏好"一切从简"）：
- 只保留 4 个核心 check：DB / scripts / cron / process
- 砍掉所有 auto_repair、blind_spot_audit、sanity_interceptor、push_slot_detect 子进程调用
- 不再 import 任何 trendradar.* 包（避免 cron 环境 PYTHONPATH 缺失问题）
- 4 个最关键警告由 cron 15:00 驱动，无异常时静默

Cron 每日 15:00 (c987a2883174) no_agent=true 静默运行。
健康→stdout 空→不推送；异常→Markdown→推送 WeCom。
"""
import json, subprocess, sys, os, time, logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
TR = Path(os.environ.get('TRENDRADAR_HOME', Path.home() / '.hermes' / 'trendradar'))
SCRIPTS = TR / 'scripts'
DATA = TR / 'data'

ISSUES = []
FIXES = []

# ── 已知 cron job 名称（用于动态匹配，不依赖 job ID） ──────────
CRON_JOB_NAMES = [
    '日报推送', '推送降级看门狗', '每日维护',
    '自动体检', '周报推送', '月度趋势报告', 'slot_direct_push',
]

def fail(component, severity, msg):
    ISSUES.append({'component': component, 'severity': severity, 'msg': msg})


# ═══════════════════════════════════════════════════════════════
# 核心检查
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
    # 直接用 sqlite3 stdlib 查表（避免 import trendradar.*）
    try:
        import sqlite3
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
        # WAL 模式检查
        journal = conn.execute('PRAGMA journal_mode').fetchone()[0]
        if journal.upper() != 'WAL':
            fail('fingerprints.db', 'WARN', f'journal_mode={journal}（建议 WAL）')
        conn.close()
    except Exception as e:
        fail('fingerprints.db', 'WARN', f'数据库检查失败: {e}')


def check_scripts():
    """核心脚本存在性 — 只列 pipeline_orchestrator 直接 import 的关键文件

    之前列了 17 个，新版 30+ 脚本会持续膨胀；只校验管线核心 import 链。
    """
    required = [
        'pipeline_orchestrator.py',  # 一键管线入口
        'push_prepare.py',           # 编排 fetch+curate
        'fetch_feeds.py',            # RSS 抓取
        'curate_and_push.py',        # 5 域精选
        'ai_translate.py',           # AI 翻译
        'render_markdown.py',        # 渲染
        'render_deep_analysis.py',   # 深度分析渲染
        'fragment_push.py',          # 分片
        'sanity_check.py',           # 拦截器
        'record_fingerprints.py',    # 指纹记录
        'track_events.py',           # 事件追踪
        'heat_tracker.py',           # 热度追踪
        'push_slot_detect.py',       # 时段检测
        'common.py',                 # 公共工具
        'settings.py',               # 统一配置
        'storage.py',                # 存储抽象
    ]
    for name in required:
        p = SCRIPTS / name
        if not p.exists():
            fail(f'trendradar/scripts/{name}', 'WARN', '文件缺失')


def check_cron():
    """cron 调度器 — 所有关键 job 注册（按名称模糊匹配）+ last run 错误检测

    不仅检查 job 是否注册，还解析 Last run 行检测 error/critical 失败。
    """
    try:
        r = subprocess.run(['hermes', 'cron', 'list'],
                          capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            fail('cron', 'WARN', f'hermes cron list 失败 (exit={r.returncode})')
            return
        # 解析 Name: 行 + Last run: 行（按 job block 分组）
        import re
        job_names = set()
        last_runs = {}  # name → "ok" | "error: ..." | missing
        current_name = None
        for line in r.stdout.split('\n'):
            m = re.match(r'\s+Name:\s+(.+)', line)
            if m:
                current_name = m.group(1).strip()
                job_names.add(current_name)
                last_runs.setdefault(current_name, None)
                continue
            m = re.match(r'\s+Last run:\s+(.+)', line)
            if m and current_name:
                txt = m.group(1).strip()
                if 'error' in txt.lower() or 'fail' in txt.lower():
                    last_runs[current_name] = txt
                else:
                    last_runs[current_name] = 'ok'
        # 模糊匹配 job 存在性
        for name in CRON_JOB_NAMES:
            found = any(name in jn for jn in job_names)
            if not found:
                fuzzy = False
                for jn in job_names:
                    for token in name.split():
                        if token in jn:
                            fuzzy = True
                            break
                    if fuzzy:
                        break
                if not fuzzy:
                    fail('cron', 'WARN', f'job "{name}" 未注册')
        # last run 错误检测
        for name, status in last_runs.items():
            if status and status != 'ok' and status is not None:
                # 截短到一行
                short = status[:120].replace('\n', ' ')
                fail('cron', 'WARN', f'job "{name}" 上次运行失败: {short}')
    except Exception as e:
        fail('cron', 'WARN', f'cron 检查异常: {e}')


def check_gateway():
    """WeCom gateway 连接 — 通过 systemd 状态检测"""
    try:
        r = subprocess.run(
            ['systemctl', '--user', 'is-active', 'hermes-gateway.service'],
            capture_output=True, text=True, timeout=5,
        )
        status = r.stdout.strip()
        if status == 'active':
            return  # ✅ 正常
        elif status in ('inactive', 'dead'):
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
    """外网连通性 — DeepSeek API（NO_PROXY 直连可达）

    注意：DeepSeek 失败时 trendradar 渲染仍可能走本地 Ollama 兜底，
    所以 DeepSeek 不可达只 WARN，不 CRITICAL。
    """
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


def check_ollama():
    """本地 Ollama 健康 — 晚间 flash 深度分析依赖

    Ollama 挂了 deep analysis 会降级到 DeepSeek，但应告警以便排查。
    """
    # 1. systemd 状态
    try:
        r = subprocess.run(
            ['systemctl', '--user', 'is-active', 'ollama.service'],
            capture_output=True, text=True, timeout=5,
        )
        status = r.stdout.strip()
        if status != 'active':
            fail('ollama', 'WARN', f'ollama.service 未运行 ({status})')
            return
    except FileNotFoundError:
        # 无 systemd — 跳过 systemctl 检查
        pass
    except Exception as e:
        fail('ollama', 'WARN', f'ollama systemd 检查异常: {e}')
        return
    # 2. HTTP 探活（systemd active 也要确认端口真的在听）
    try:
        r = subprocess.run(
            ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}',
             '--connect-timeout', '3', 'http://127.0.0.1:11434/api/tags'],
            capture_output=True, text=True, timeout=5,
        )
        code = r.stdout.strip()
        if code != '200':
            fail('ollama', 'WARN', f'Ollama /api/tags 返回 HTTP {code}')
    except subprocess.TimeoutExpired:
        fail('ollama', 'WARN', 'Ollama /api/tags 超时（服务卡住？）')
    except Exception as e:
        fail('ollama', 'WARN', f'Ollama 探活失败: {e}')


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
            fail('memory', 'WARN', f'{label} 已膨胀至 {pct}% ({size}/{limit})，建议压缩')
        elif pct >= 75:
            fail('memory', 'WARN', f'{label} 使用率 {pct}% ({size}/{limit})，接近阈值')


def check_data_freshness():
    """最新 curated 数据时效 — 动态阈值避免日报间歇期误报

    阈值取"到下次日报 cron 触发时间的小时数" + 30min buffer：
    早报 09:00 后，最迟 12:00 午报应已出（间隔 3h）；
    午报 12:00 后，最迟 15:00 体检时晚 21:00 报还没出（间隔 9h）；
    晚报 21:00 后到次日 09:00 是 12h；
    体检 cron 跑在 15:00 — 距最近一次已跑日报是 3h（12:00 午报）。

    简单做法：阈值 6h，cron 正常时 15:00 体检距 12:00 午报 3h（不报）；
    cron 出错时 check_cron 的 last run 检测会报（互不重叠）。
    """
    now = time.time()
    files = sorted(DATA.glob('curated_*.json'),
                   key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        fail('data', 'WARN', '无 curated 数据文件')
        return
    age_h = (now - files[0].stat().st_mtime) / 3600
    # 体检 cron 在 15:00 跑；距最近日报（12:00 午报）3h；
    # 阈值取 6h 既能盖过间歇期，又能检出 cron 真的卡住
    if age_h > 6:
        fail('data', 'WARN', f'最新 curated 数据已 {age_h:.1f}h 未更新（阈值 6h）')


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════

def main():
    # 执行所有检查
    check_db()
    check_scripts()
    check_cron()
    check_gateway()
    check_api()
    check_ollama()
    check_memory_size()
    check_data_freshness()

    # 过滤：INFO 不算异常，WARN/CRITICAL 触发推送
    severe = [i for i in ISSUES if i['severity'] in ('WARN', 'CRITICAL')]

    if not severe and not FIXES:
        return 0  # 静默健康

    # 输出 Markdown 报告（c987a2883174 推送 WeCom）
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
