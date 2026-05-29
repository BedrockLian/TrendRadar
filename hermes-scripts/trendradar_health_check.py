#!/usr/bin/env python3
"""TrendRadar 自动体检 + 自修复脚本 v2.1

检查项：DB/脚本/配置/Cron/网关/API/数据时效/全链路/盲点/记忆/进程滞留/拦截器
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

# ── 已知 cron job 名称（用于动态匹配，不依赖 job ID） ──────────
CRON_JOB_NAMES = [
    '日报推送', '性能优化器', '推送降级看门狗', '每日维护',
    '自动体检', '周报推送', '月度趋势报告',
]

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
    """指纹库完整性 — 统一通过 Storage 检查"""
    db = DATA / 'fingerprints.db'
    if not db.exists():
        fail('fingerprints.db', 'CRITICAL', '数据库文件不存在')
        return
    if db.stat().st_size < 1000:
        fail('fingerprints.db', 'CRITICAL', f'数据库仅 {db.stat().st_size}B')
        return
    try:
        # 通过 Storage 统一接入
        sys.path.insert(0, str(TR.parent))
        from trendradar.scripts.storage import Storage
        store = Storage(DATA)
        conn = store.db('fingerprints.db')
        tables = [r[0] for r in conn.execute('SELECT name FROM sqlite_master WHERE type="table"').fetchall()]
        if 'fingerprints' not in tables:
            fail('fingerprints.db', 'CRITICAL', 'fingerprints 表不存在')
        else:
            cnt = conn.execute('SELECT COUNT(*) FROM fingerprints').fetchone()[0]
        if 'heat_tracker' not in tables:
            fail('heat_tracker', 'WARN', 'heat_tracker 表不存在')
        else:
            hc = conn.execute('SELECT COUNT(*) FROM heat_tracker').fetchone()[0]
        # WAL 模式检查
        journal = conn.execute('PRAGMA journal_mode').fetchone()[0]
        if journal.upper() != 'WAL':
            fail('fingerprints.db', 'WARN', f'journal_mode={journal}（建议 WAL）')
        store.close_db('fingerprints.db')
    except Exception as e:
        fail('fingerprints.db', 'CRITICAL', f'数据库异常: {e}')


def check_scripts():
    """所有脚本可执行 — 含 v2.8.0 新增脚本"""
    required = [
        'push_prepare.py', 'batch_fetch.py', 'fetch_feeds.py', 'push_slot_detect.py',
        'record_fingerprints.py', 'track_events.py', 'heat_tracker.py', 'ai_translate.py',
        'render_markdown.py', 'fragment_push.py', 'render_deep_analysis.py',
        'curate_and_push.py', 'pipeline_orchestrator.py', 'common.py', 'exitcodes.py',
        'settings.py', 'storage.py', 'trace.py',
        # v2.8.0 新增
        'sanity_check.py', 'blind_spot_audit.py', 'aggregate_monthly.py',
    ]
    for name in required:
        p = SCRIPTS / name
        if not p.exists():
            fail(f'scripts/{name}', 'WARN', '文件缺失')


def check_config():
    """关键配置存在 + 内容可用"""
    # YAML 配置文件
    for name in ['timeline.yaml', 'ai_interests.yaml']:
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

    # 新增数据文件
    for name, label in [
        ('source_health.json', 'source_health'),
        ('push_log.json', 'push_log'),
    ]:
        p = DATA / name
        if not p.exists():
            fail(f'data/{name}', 'INFO', f'{label} 尚未创建（首次运行正常）')

    # keywords.py
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
        expected = {'top_headlines', 'foreign_china', 'tech', 'economy', 'gaming'}
        if set(DOMAINS) != expected:
            fail('settings.py', 'WARN', f'DOMAINS 不完整: {DOMAINS}')
        if set(BRIEFING_RATIO.keys()) != {'morning', 'noon', 'evening'}:
            fail('settings.py', 'WARN', f'BRIEFING_RATIO 缺少时段: {list(BRIEFING_RATIO.keys())}')
    except Exception as e:
        fail('settings.py', 'WARN', f'导入/验证失败: {e}')


def check_cron():
    """cron 调度器 — 所有关键 job 注册（按名称匹配，不依赖 job ID）"""
    try:
        r = subprocess.run(['hermes', 'cron', 'list'], capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            # Parse table output: lines with "Name:      xxx"
            import re
            job_names = set()
            for line in r.stdout.split('\n'):
                m = re.match(r'\s+Name:\s+(.+)', line)
                if m:
                    job_names.add(m.group(1).strip())
            if not job_names:
                # Fallback: search for known names in full output
                for name in CRON_JOB_NAMES:
                    if name not in r.stdout:
                        fail('cron', 'WARN', f'job "{name}" 未注册')
            else:
                for name in CRON_JOB_NAMES:
                    if not any(name in jn for jn in job_names):
                        # Try fuzzy: name "日报推送" should match "TrendRadar 日报推送（早/午/晚）"
                        fuzzy_found = False
                        for jn in job_names:
                            for token in name.split():
                                if token in jn:
                                    fuzzy_found = True
                                    break
                            if fuzzy_found:
                                break
                        if not fuzzy_found:
                            fail('cron', 'WARN', f'job "{name}" 未注册')
    except Exception as e:
        fail('cron', 'WARN', f'查询失败: {e}')


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
        elif status == 'inactive' or status == 'dead':
            fail('gateway', 'WARN', 'hermes-gateway.service 未运行 (inactive)')
        elif status == 'failed':
            fail('gateway', 'WARN', 'hermes-gateway.service 已崩溃 (failed)')
        else:
            # Fallback: try gateway status command
            r2 = subprocess.run(
                ['hermes', 'gateway', 'status'],
                capture_output=True, text=True, timeout=10,
            )
            if 'is running' not in r2.stdout and 'active' not in r2.stdout:
                fail('gateway', 'WARN', 'hermes gateway 进程可能未运行')
    except FileNotFoundError:
        # No systemd (Docker etc.) — fallback to socket check
        sock_paths = [
            '/tmp/hermes-wecom-card.sock',
            '/tmp/hermes_wecom.sock',
            '/tmp/hermes_gateway.sock',
        ]
        if not any(Path(p).exists() for p in sock_paths):
            fail('gateway', 'WARN', f'IPC socket 不存在（检查了 {len(sock_paths)} 个路径）')
    except Exception as e:
        fail('gateway', 'WARN', f'检查失败: {e}')


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
    """快速外网连通性测试 — 用 DeepSeek API（经 NO_PROXY 直连可达）代替被代理阻断的 httpbin"""
    for url, label in [
        ('https://api.deepseek.com/v1/models', '外网 API 可达（DeepSeek）'),
    ]:
        try:
            # DeepSeek 直连（绕过代理），在 cron 环境也有效
            env = os.environ.copy()
            env.pop('HTTP_PROXY', None)
            env.pop('HTTPS_PROXY', None)
            env.pop('http_proxy', None)
            env.pop('https_proxy', None)
            r = subprocess.run(
                ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}',
                 '--connect-timeout', '5', url],
                capture_output=True, text=True, timeout=10, env=env
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
        for line in r.stdout.split('\n'):
            if 'cron_' not in line and 'trendradar' not in line.lower():
                continue
            parts = line.split()
            if len(parts) < 11:
                continue
            if 'python' in line.lower() or 'python3' in line.lower():
                for jid in CRON_JOB_NAMES:
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
    """push_log.json 体积监控"""
    log_file = DATA / 'push_log.json'
    if not log_file.exists():
        return
    size = log_file.stat().st_size
    if size > 1_000_000:
        fail('push_log', 'WARN', f'push_log.json 已 {size/1024/1024:.1f}MB，建议清理或轮转')
    elif size > 100_000:
        fail('push_log', 'WARN', f'push_log.json 已 {size/1024:.0f}KB，接近 1MB 阈值')


def check_sanity_interceptor():
    """发布前拦截器就位检查"""
    script = SCRIPTS / 'sanity_check.py'
    if not script.exists():
        fail('sanity_check', 'WARN', 'sanity_check.py 缺失 — 发布前拦截器未就位')
        return

    try:
        env = os.environ.copy()
        env['PYTHONPATH'] = str(TR.parent)
        env.setdefault('PYTHON_GIL', '0')
        pipeline_python = os.environ.get('PYTHON', '/usr/local/bin/python3.14t')
        r = subprocess.run(
            [pipeline_python, str(script), '--json', '--no-check-links'],
            input='test content', capture_output=True, text=True, timeout=10, env=env
        )
        if r.returncode not in (0, 3):
            fail('sanity_check', 'WARN', f'sanity_check.py 异常退出 (exit={r.returncode})')
    except Exception as e:
        fail('sanity_check', 'WARN', f'sanity_check.py 不可用: {e}')


def check_pipeline():
    """全链路探测"""
    pipeline_python = os.environ.get('PYTHON', '/usr/local/bin/python3.14t')
    if not os.access(pipeline_python, os.X_OK):
        pipeline_python = sys.executable

    # 1) 时段探测
    try:
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

    # 2) RSS 源连通性（跳过 localhost 源 — 本地 RSSHub 通常不运行）
    if (DATA / 'sources.json').exists():
        try:
            import socket
            sources = json.loads((DATA / 'sources.json').read_text())
            feeds = sources.get('data_sources', [])
            if isinstance(feeds, dict):
                feeds = list(feeds.values())
            if not isinstance(feeds, list):
                feeds = []
            if feeds:
                rss_feeds = [f for f in feeds if isinstance(f, dict) and f.get('feed_url')
                             and f.get('enabled', True)
                             and 'localhost' not in f.get('feed_url', '')]
                # 取前 3 个非 localhost 的源（确定性，不随机）
                sample = rss_feeds[:3]
                failed_urls = []
                for f in sample:
                    url = f.get('feed_url', '')
                    if not url:
                        continue
                    try:
                        host = url.split('/')[2] if '://' in url else url.split('/')[0]
                        s = socket.create_connection((host, 443), timeout=5)
                        s.close()
                    except Exception:
                        failed_urls.append(url[:60])
                if failed_urls:
                    if len(failed_urls) == len(sample):
                        fail('pipeline', 'WARN', f'所有抽样 RSS 源不可达: {failed_urls[0]} 等 {len(failed_urls)} 个')
                    else:
                        # 部分失败只记录，不报 WARN（单个源不稳定是常态）
                        logging.debug(f'RSS 抽样 {len(failed_urls)}/{len(sample)} 不可达: {failed_urls}')
                        for url in failed_urls:
                            print(f'[HEALTH] ⚠️ RSS 源偶发不可达: {url}', file=sys.stderr)
        except Exception:
            pass

    # 3) 核心脚本导入检查
    import_check = [
        'push_prepare', 'batch_fetch', 'fetch_feeds', 'heat_tracker',
        'record_fingerprints', 'ai_translate', 'common', 'exitcodes',
        'fragment_push', 'curate_and_push',
        'blind_spot_audit', 'aggregate_monthly', 'storage',
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

    # 4) 流水线步骤完整性
    pipeline_steps = [
        'push_slot_detect.py', 'push_prepare.py', 'batch_fetch.py',
        'track_events.py', 'record_fingerprints.py', 'fetch_feeds.py',
        'ai_translate.py', 'render_markdown.py', 'fragment_push.py',
        'render_deep_analysis.py', 'pipeline_orchestrator.py',
        'curate_and_push.py', 'common.py', 'exitcodes.py',
        'storage.py', 'trace.py',
        'sanity_check.py', 'blind_spot_audit.py', 'aggregate_monthly.py',
    ]
    for ps in pipeline_steps:
        if not (SCRIPTS / ps).exists():
            fail('pipeline', 'WARN', f'流水线脚本 {ps} 缺失')

    # 5) 系统资源
    _check_system_resources()


def check_blind_spot():
    """板块覆盖率盲点检测"""
    pipeline_python = os.environ.get('PYTHON', '/usr/local/bin/python3.14t')
    if not os.access(pipeline_python, os.X_OK):
        pipeline_python = sys.executable

    audit_script = SCRIPTS / 'blind_spot_audit.py'
    if not audit_script.exists():
        fail('blind_spot', 'WARN', 'blind_spot_audit.py 脚本缺失')
        return

    try:
        env = os.environ.copy()
        env['PYTHONPATH'] = str(TR.parent)
        env.setdefault('PYTHON_GIL', '0')
        r = subprocess.run(
            [pipeline_python, str(audit_script), '--days', '3', '--json',
             '--coverage-threshold', '10'],
            capture_output=True, text=True, timeout=30, env=env,
        )
        if r.returncode != 0:
            fail('blind_spot', 'WARN', f'盲点审计执行失败: {r.stderr[:100]}')
            return

        result = json.loads(r.stdout)
        low_domains = result.get('low_coverage_domains', [])

        if low_domains:
            for d in low_domains:
                pct = result['coverage'].get(d, {}).get('percentage', '?')
                fail('blind_spot', 'WARN',
                     f'板块 {d} 近 3 天覆盖率仅 {pct}%（低于 10% 阈值）'
                     f' — 该领域 RSS 源可能大面积失效')
    except json.JSONDecodeError:
        fail('blind_spot', 'WARN', f'盲点审计输出非 JSON: {r.stdout[:100]}')
    except subprocess.TimeoutExpired:
        fail('blind_spot', 'WARN', '盲点审计执行超时')
    except Exception as e:
        fail('blind_spot', 'WARN', f'盲点审计异常: {e}')


def _check_system_resources():
    """系统资源占用"""
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
    """自动重建指纹表"""
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
    check_sanity_interceptor()
    check_blind_spot()
    check_pipeline()


def run_repairs():
    auto_repair_missing_table()
    auto_repair_empty_db()


def generate_report():
    now = datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')
    lines = [f'# Hermes 趋势雷达 · 自动体检报告', f'', f'**时间:** {now}', '']

    if not ISSUES and not FIXES:
        return ''

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
    run_repairs()
    run_checks()
    print(generate_report())
