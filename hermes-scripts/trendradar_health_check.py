#!/usr/bin/env python3
"""TrendRadar 自动体检 + 自修复脚本

检查项：DB/脚本/配置/Cron/网关/API/数据时效/全链路/记忆/进程滞留
Cron 每日 15:00（c987a2883174）no_agent=true 静默运行。
健康→stdout 空→不推送；异常→Markdown→推送 WeCom。
"""
import json, sqlite3, subprocess, sys, os, re, time, logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
TR = Path(os.environ.get('TRENDRADAR_HOME', Path.home() / '.hermes' / 'trendradar'))
SCRIPTS = TR / 'scripts'
DATA = TR / 'data'
CACHE = TR / 'cache'

ISSUES = []
FIXES = []

# ── 已知 cron job IDs（从 hermes cron list 获取） ─────────────
CRON_JOBS = {
    '90a2866775df': '日报推送',       # 0 9,12,21 * * *
    '718b663e8c04': '性能优化器',      # 15 21 * * *
    'cab79825520e': '推送看门狗',      # 0 10,14,22 * * *
    '68db70cd8556': '每日维护',        # 0 3 * * *
    'c987a2883174': '自动体检',        # 0 15 * * *
    'c20e2c82deda': '周报推送',        # 30 9 * * 1
    '0b14c67429ba': '月度报告',        # 0 9 1 * *
}

# ── 核心配置键（settings.py 必须导出的常量） ──────────────────
SETTINGS_CONSTANTS = ['DOMAINS', 'DOMAIN_LABELS', 'MAX_PER_DOMAIN',
                      'BRIEFING_RATIO', 'DAILY_LIMIT', 'MIN_SCORE',
                      'TRENDRADAR_HOME']

def fail(component, severity, msg):
    ISSUES.append({'component': component, 'severity': severity, 'msg': msg})

# ═══════════════════════════════════════════════════════════════
# 检查函数
# ═══════════════════════════════════════════════════════════════

def check_db():
    """指纹库完整性"""
    db = DATA / 'fingerprints.db'
    if not db.exists():
        fail('fingerprints.db', 'CRITICAL', '数据库文件不存在')
        return
    if db.stat().st_size < 1000:
        fail('fingerprints.db', 'CRITICAL', f'数据库仅 {db.stat().st_size}B')
        return
    try:
        conn = sqlite3.connect(str(db))
        cur = conn.cursor()
        tables = [r[0] for r in cur.execute('SELECT name FROM sqlite_master WHERE type="table"').fetchall()]
        if 'fingerprints' not in tables:
            fail('fingerprints.db', 'CRITICAL', 'fingerprints 表不存在')
        else:
            cnt = cur.execute('SELECT COUNT(*) FROM fingerprints').fetchone()[0]
        if 'heat_tracker' not in tables:
            fail('heat_tracker', 'WARN', 'heat_tracker 表不存在')
        else:
            hc = cur.execute('SELECT COUNT(*) FROM heat_tracker').fetchone()[0]
        conn.close()
    except Exception as e:
        fail('fingerprints.db', 'CRITICAL', f'数据库异常: {e}')


def check_scripts():
    """所有脚本可执行"""
    required = ['push_prepare.py', 'batch_fetch.py', 'fetch_feeds.py', 'push_slot_detect.py',
                'record_fingerprints.py', 'track_events.py', 'heat_tracker.py', 'ai_translate.py',
                'render_markdown.py', 'fragment_push.py', 'render_deep_analysis.py',
                'curate_and_push.py', 'pipeline_orchestrator.py', 'common.py', 'exitcodes.py',
                'settings.py', 'storage.py', 'trace.py']
    for name in required:
        p = SCRIPTS / name
        if not p.exists():
            fail(f'scripts/{name}', 'WARN', '文件缺失')


def check_config():
    """关键配置存在 + 内容可用"""
    # YAML 配置文件
    for name in ['timeline.yaml', 'ai_interests.yaml', 'translate.yaml']:
        p = TR / 'config' / name
        if not p.exists():
            fail(f'config/{name}', 'WARN', '文件缺失')
        elif p.stat().st_size < 10:
            fail(f'config/{name}', 'WARN', '文件过小（疑为空）')

    # JSON 源
    sources = DATA / 'sources.json'
    if not sources.exists():
        fail('config/sources.json', 'WARN', '文件缺失')
    elif sources.stat().st_size < 50:
        fail('config/sources.json', 'WARN', 'sources.json 过小')

    # keywords.py — 必须存在且有内容（基于 frozenset/dict 结构，按最低文件大小判断）
    kw = TR / 'config' / 'keywords.py'
    if not kw.exists():
        fail('config/keywords.py', 'WARN', '文件缺失')
    elif kw.stat().st_size < 1000:
        fail('config/keywords.py', 'WARN', f'keywords.py 仅 {kw.stat().st_size}B，疑似过小')
    else:
        try:
            content = kw.read_text()
            if 'has_keyword_match_ci' not in content:
                fail('config/keywords.py', 'WARN', '缺少 has_keyword_match_ci 函数')
            # 检查至少有两个 frozenset/FROZEN/字典定义
            set_defs = [l for l in content.split('\n') if '= frozenset' in l or '= {' in l and 'GAME_KW' in l]
            if len(set_defs) < 2:
                fail('config/keywords.py', 'WARN', f'疑似关键词定义不足（仅 {len(set_defs)} 个集合）')
        except Exception as e:
            fail('config/keywords.py', 'WARN', f'读取失败: {e}')


def check_settings_constants():
    """验证 settings.py 导出关键常量"""
    try:
        sys.path.insert(0, str(TR.parent))
        from trendradar.scripts.settings import (
            DOMAINS, DOMAIN_LABELS, MAX_PER_DOMAIN,
            BRIEFING_RATIO, DAILY_LIMIT, MIN_SCORE, TRENDRADAR_HOME
        )
        # 验证 DOMAINS 完整性
        expected = {'top_headlines', 'foreign_china', 'tech', 'economy', 'gaming'}
        if set(DOMAINS) != expected:
            fail('settings.py', 'WARN', f'DOMAINS 不完整: {DOMAINS}')
        # 验证 BRIEFING_RATIO
        if set(BRIEFING_RATIO.keys()) != {'morning', 'noon', 'evening'}:
            fail('settings.py', 'WARN', f'BRIEFING_RATIO 缺少时段: {list(BRIEFING_RATIO.keys())}')
    except Exception as e:
        fail('settings.py', 'WARN', f'导入/验证失败: {e}')


def check_cron():
    """cron 调度器 — 所有关键 job 注册"""
    try:
        r = subprocess.run(['hermes', 'cron', 'list'], capture_output=True, text=True, timeout=15)
        for jid, label in CRON_JOBS.items():
            if jid not in r.stdout:
                fail('cron', 'WARN', f'job {label} ({jid[:8]}…) 未注册')
    except Exception as e:
        fail('cron', 'WARN', f'查询失败: {e}')


def check_gateway():
    """WeCom gateway 连接"""
    sock = Path('/tmp/hermes-wecom-card.sock')
    if not sock.exists():
        fail('gateway', 'WARN', 'IPC socket /tmp/hermes-wecom-card.sock 不存在')
    try:
        r = subprocess.run(['ps', 'aux'], capture_output=True, text=True, timeout=5)
        # 检查 hermes gateway 进程 — 更多信号位
        gateway_lines = [l for l in r.stdout.split('\n') if 'hermes gateway' in l.lower()]
        if gateway_lines:
            # 检查是否包含 wecom
            wecom_lines = [l for l in r.stdout.split('\n') if 'wecom' in l.lower()]
            if not wecom_lines:
                fail('gateway', 'WARN', 'hermes 运行但无 wecom 相关进程')
        else:
            fail('gateway', 'WARN', 'hermes gateway 进程可能未运行')
    except Exception:
        logging.debug("Gateway check failed, skipping")


def check_data_freshness():
    """检查最新数据文件时效"""
    now = time.time()
    curated_files = sorted(DATA.glob('curated_*.json'), key=lambda f: f.stat().st_mtime, reverse=True)
    if curated_files:
        age_hours = (now - curated_files[0].stat().st_mtime) / 3600
        if age_hours > 15:
            fail('data', 'WARN', f'最新 curated 数据已 {age_hours:.1f}h 未更新')
    else:
        fail('data', 'WARN', '无 curated 数据文件')


def check_api():
    """快速 API 连通性测试"""
    for url, label in [
        ('https://api.deepseek.com/v1/models', 'DeepSeek API'),
        ('https://httpbin.org/get', '外网出口'),
    ]:
        try:
            r = subprocess.run(
                ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}',
                 '--connect-timeout', '5', url],
                capture_output=True, text=True, timeout=10
            )
            code = r.stdout.strip()
            if code not in ('200', '401', '403'):
                fail('api', 'WARN', f'{label} 不可达 (HTTP {code})')
        except subprocess.TimeoutExpired:
            fail('api', 'WARN', f'{label} 超时')
        except Exception as e:
            fail('api', 'WARN', f'{label} 检查失败: {e}')


def check_stale_processes():
    """检查卡死的 python 进程"""
    try:
        r = subprocess.run(['ps', 'aux'], capture_output=True, text=True, timeout=5)
        now_ts = time.time()
        for line in r.stdout.split('\n'):
            if 'cron_' not in line and 'trendradar' not in line.lower():
                continue
            # 尝试提取进程启动时间
            parts = line.split()
            if len(parts) < 11:
                continue
            # 简易检测：匹配已知 cron job ID 或 trendradar 脚本
            if 'python' in line.lower() or 'python3' in line.lower():
                for jid in CRON_JOBS:
                    if jid[:8] in line or jid[:6] in line:
                        fail('process', 'WARN', f'疑似滞留进程: {line[:120]}')
                        break
    except (subprocess.SubprocessError, FileNotFoundError):
        pass


def check_memory_size():
    """监控记忆文件和用户画像膨胀"""
    mem_file = Path.home() / '.hermes' / 'memories' / 'MEMORY.md'
    user_file = Path.home() / '.hermes' / 'memories' / 'USER.md'

    for label, path in [('MEMORY.md', mem_file), ('USER.md', user_file)]:
        if not path.exists():
            fail('memory', 'WARN', f'{label} 文件缺失')
            continue
        size = len(path.read_text(encoding='utf-8'))
        limit = 2200 if label == 'MEMORY.md' else 1375
        pct = int(size / limit * 100)
        if pct >= 90:
            fail('memory', 'WARN', f'{label} 已膨胀至 {pct}% ({size}/{limit})，建议压缩')
        elif pct >= 75:
            fail('memory', 'WARN', f'{label} 使用率 {pct}% ({size}/{limit})，接近阈值')


def check_push_log_backpressure():
    """push_log.json 体积监控（不存在或过大告警）"""
    log_file = DATA / 'push_log.json'
    if not log_file.exists():
        return  # 首次运行时可能不存在，不告警
    size = log_file.stat().st_size
    if size > 1_000_000:
        fail('push_log', 'WARN', f'push_log.json 已 {size/1024/1024:.1f}MB，建议清理或轮转')
    elif size > 100_000:
        fail('push_log', 'WARN', f'push_log.json 已 {size/1024:.0f}KB，接近 1MB 阈值')


def check_pipeline():
    """全链路探测 — 每个环节测试是否可执行"""
    # 1) 时段探测（用管线 Python，带 PYTHONPATH）
    try:
        pipeline_python = os.environ.get('PYTHON', '/usr/local/bin/python3.14t')
        if not os.access(pipeline_python, os.X_OK):
            pipeline_python = sys.executable
        penv = os.environ.copy()
        penv['PYTHONPATH'] = str(TR.parent)
        penv.setdefault('PYTHON_GIL', '0')
        r = subprocess.run(
            [pipeline_python, str(SCRIPTS / 'push_slot_detect.py')],
            capture_output=True, text=True, timeout=30, env=penv
        )
        if r.returncode != 0:
            fail('pipeline', 'WARN', f'push_slot_detect 执行失败 (exit={r.returncode})')
        elif r.stdout.strip() not in ('NO_SLOT',) and 'PUSH_ID=' not in r.stdout:
            fail('pipeline', 'WARN', f'push_slot_detect 输出异常: {r.stdout.strip()[:60]}')
    except subprocess.TimeoutExpired:
        fail('pipeline', 'WARN', 'push_slot_detect 超时 (>30s)')
    except Exception as e:
        fail('pipeline', 'WARN', f'push_slot_detect 异常: {e}')

    # 2) RSS 源连通性 — 抽检 3 个
    if (DATA / 'sources.json').exists():
        try:
            import random, socket
            sources = json.loads((DATA / 'sources.json').read_text())
            feeds = []
            for v in sources.values():
                if isinstance(v, list):
                    feeds.extend(v)
                elif isinstance(v, dict):
                    for sub in v.values():
                        if isinstance(sub, list):
                            feeds.extend(sub)
            sample = random.sample(feeds, min(3, len(feeds)))
            for f in sample:
                url = f.get('feed', '') or f.get('url', '')
                if not url: continue
                try:
                    host = url.split('/')[2] if '://' in url else url.split('/')[0]
                    s = socket.create_connection((host, 443), timeout=5)
                    s.close()
                except Exception:
                    fail('pipeline', 'WARN', f'RSS 源不可达: {url[:60]}')
                    break
        except Exception:
            pass  # sources.json parse error caught by check_config

    # 3) 核心脚本导入检查（全限定包路径，用管线 Python 解释器）
    pipeline_python = os.environ.get('PYTHON', '/usr/local/bin/python3.14t')
    if not os.access(pipeline_python, os.X_OK):
        pipeline_python = sys.executable  # fallback
    import_check = [
        'push_prepare', 'batch_fetch', 'fetch_feeds', 'heat_tracker',
        'record_fingerprints', 'ai_translate', 'common', 'exitcodes',
        'fragment_push', 'curate_and_push',
    ]
    for mod_name in import_check:
        try:
            env = os.environ.copy()
            env['PYTHONPATH'] = str(TR.parent)
            env.setdefault('PYTHON_GIL', '0')
            r = subprocess.run(
                [pipeline_python, '-c', f'import trendradar.scripts.{mod_name}'],
                capture_output=True, text=True, timeout=15, env=env
            )
            if r.returncode != 0:
                fail('pipeline', 'WARN', f'{mod_name}.py 导入失败: {r.stderr[:80]}')
        except subprocess.TimeoutExpired:
            fail('pipeline', 'WARN', f'{mod_name}.py 导入超时')
        except Exception as e:
            fail('pipeline', 'WARN', f'{mod_name}.py 导入异常: {e}')

    # 4) 流水线步骤完整性 — 验证 cron prompt 引用的脚本都存在
    pipeline_steps = ['push_slot_detect.py', 'push_prepare.py', 'batch_fetch.py',
                      'track_events.py', 'record_fingerprints.py', 'fetch_feeds.py',
                      'ai_translate.py', 'render_markdown.py', 'fragment_push.py',
                      'render_deep_analysis.py', 'pipeline_orchestrator.py',
                      'curate_and_push.py', 'common.py', 'exitcodes.py',
                      'storage.py', 'trace.py']
    for ps in pipeline_steps:
        if not (SCRIPTS / ps).exists():
            fail('pipeline', 'WARN', f'流水线脚本 {ps} 缺失')

    # 5) 系统资源 — 仅记录，不告警
    _check_system_resources()


def _check_system_resources():
    """系统资源占用 — 仅 info"""
    try:
        r = subprocess.run(['df', '-h', str(TR)], capture_output=True, text=True, timeout=5)
        for line in r.stdout.split('\n')[1:]:
            if not line.strip(): continue
            parts = line.split()
            if len(parts) >= 5 and parts[4].rstrip('%').isdigit():
                pct = int(parts[4].rstrip('%'))
                if pct >= 90:
                    fail('disk', 'WARN', f'磁盘 {parts[5]} 使用率 {pct}%')
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# 自动修复
# ═══════════════════════════════════════════════════════════════

def auto_repair_missing_table():
    """自动重建指纹表 — 通过迁移引擎确保 schema 为最新版"""
    db = DATA / 'fingerprints.db'
    if not db.exists(): return
    try:
        sys.path.insert(0, str(TR.parent))
        from trendradar.migrations.runner import repair_missing_tables, migrate
        if repair_missing_tables(db):
            FIXES.append('已修复缺失的数据库表')
        ver = migrate(db)
        if ver > 0 and not any('数据库迁移' in f for f in FIXES):
            FIXES.append(f'数据库 schema 版本 v{ver}')
    except Exception as e:
        fail('repair', 'WARN', f'数据库迁移失败: {e}')


def auto_repair_empty_db():
    """处理 0 字节 DB 文件"""
    for p in [TR / 'fingerprints.db', DATA / 'fingerprints.db']:
        if p.exists() and p.stat().st_size == 0:
            p.unlink()
            FIXES.append(f'已删除空壳文件 {p.name}')


# ═══════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════

def run_checks():
    check_db()
    check_scripts()
    check_config()
    check_settings_constants()
    check_cron()
    check_gateway()
    check_data_freshness()
    check_api()
    check_stale_processes()
    check_memory_size()
    check_push_log_backpressure()
    check_pipeline()


def run_repairs():
    auto_repair_missing_table()
    auto_repair_empty_db()


def generate_report():
    now = datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')
    lines = [f'# Hermes 趋势雷达 · 自动体检报告', f'', f'**时间:** {now}', '']

    if not ISSUES and not FIXES:
        return ''  # 安静模式：健康时无输出

    if FIXES:
        lines.append('### 🔧 自动修复')
        for f in FIXES:
            lines.append(f'- ✅ {f}')
        lines.append('')

    if ISSUES:
        for sev in ['CRITICAL', 'WARN']:
            items = [i for i in ISSUES if i['severity'] == sev]
            if not items: continue
            icon = '🔴' if sev == 'CRITICAL' else '⚠️'
            label = '严重问题' if sev == 'CRITICAL' else '警告'
            lines.append(f'### {icon} {label}')
            for i in items:
                lines.append(f'- **{i["component"]}**: {i["msg"]}')
            lines.append('')

    if any(i['severity'] == 'CRITICAL' for i in ISSUES):
        lines.append('🔴 **状态: 异常** — 需要人工介入')
    elif ISSUES:
        lines.append('🟡 **状态: 亚健康** — 警告项需关注')
    else:
        lines.append('🟢 **状态: 健康**')

    lines.append('')
    lines.append('📡 趋势雷达自动体检 · 下次运行时自动重检')

    return '\n'.join(lines)


if __name__ == '__main__':
    run_checks()
    run_repairs()
    print(generate_report())
