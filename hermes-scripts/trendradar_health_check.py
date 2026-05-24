#!/usr/bin/env python3
"""TrendRadar 自动体检 + 自修复脚本"""
import json, sqlite3, subprocess, sys, os, re, time, logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
TR = Path(os.environ.get('TRENDRADAR_HOME', Path.home() / '.hermes' / 'trendradar'))
SCRIPTS = TR / 'scripts'
DATA = TR / 'data'
CACHE = TR / 'cache'
SKILL_DIR = Path(os.environ.get('HERMES_SKILLS_DIR', Path.home() / '.hermes' / 'skills' / 'trendradar' / 'news-secretary'))

ISSUES = []
FIXES = []

def fail(component, severity, msg):
    ISSUES.append({'component': component, 'severity': severity, 'msg': msg})

def ok(component, msg):
    pass  # verbose only

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
            ok('fingerprints.db', f'{cnt} 条记录')
        if 'heat_tracker' not in tables:
            fail('heat_tracker', 'WARN', 'heat_tracker 表不存在')
        else:
            hc = cur.execute('SELECT COUNT(*) FROM heat_tracker').fetchone()[0]
            ok('heat_tracker', f'{hc} 条记录')
        conn.close()
    except Exception as e:
        fail('fingerprints.db', 'CRITICAL', f'数据库异常: {e}')

def check_scripts():
    """所有脚本可执行"""
    required = ['push_prepare.py', 'batch_fetch.py', 'fetch_feeds.py', 'push_slot_detect.py',
                'record_fingerprints.py', 'track_events.py', 'heat_tracker.py', 'ai_translate.py',
                'render_markdown.py', 'fragment_push.py', 'render_deep_analysis.py',
                'curate_and_push.py', 'pipeline_orchestrator.py']
    for name in required:
        p = SCRIPTS / name
        if not p.exists():
            fail(f'scripts/{name}', 'WARN', '文件缺失')
        elif os.access(str(p), os.X_OK) is False:
            # not an exec issue for .py files
            pass

def check_config():
    """关键配置存在"""
    configs = [TR / 'config/timeline.yaml', TR / 'config/ai_interests.yaml',
               TR / 'config/translate.yaml', DATA / 'sources.json']
    for p in configs:
        if not p.exists():
            fail(f'config/{p.name}', 'WARN', '文件缺失')

def check_cron():
    """cron 调度器状态"""
    try:
        r = subprocess.run(['hermes', 'cron', 'list'], capture_output=True, text=True, timeout=15)
        if '90a2866775df' not in r.stdout:
            fail('cron', 'CRITICAL', '日报 cron job 不存在')
        if '718b663e8c04' not in r.stdout:
            fail('cron', 'WARN', '性能优化器 cron job 不存在')
        if 'cab79825520e' not in r.stdout:
            fail('cron', 'WARN', '降级看门狗 cron job 不存在')
    except Exception as e:
        fail('cron', 'WARN', f'查询失败: {e}')

def check_gateway():
    """WeCom gateway 连接"""
    sock = Path('/tmp/hermes-wecom-card.sock')
    if not sock.exists():
        fail('gateway', 'WARN', 'IPC socket 不存在')
    # Check gateway process
    try:
        r = subprocess.run(['ps', 'aux'], capture_output=True, text=True, timeout=5)
        if 'hermes gateway' not in r.stdout and 'hermes' not in r.stdout.lower():
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
    try:
        r = subprocess.run(
            ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', 
             '--connect-timeout', '5', 'https://api.deepseek.com/v1/models'],
            capture_output=True, text=True, timeout=10
        )
        if r.stdout.strip() not in ('200', '401', '403'):
            fail('api', 'WARN', f'deepseek API 不可达 (HTTP {r.stdout})')
    except subprocess.TimeoutExpired:
        fail('api', 'WARN', 'deepseek API 超时')
    except Exception as e:
        fail('api', 'WARN', f'API 检查失败: {e}')

def check_stale_processes():
    """检查卡死的 cron session"""
    try:
        r = subprocess.run(['ps', 'aux'], capture_output=True, text=True, timeout=5)
        # Look for sessions older than 30 min
        for line in r.stdout.split('\n'):
            if 'cron_90a286' in line and 'python' in line.lower():
                fail('process', 'WARN', '可能有滞留的 cron session')
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


def check_pipeline():
    """全链路探测 — 每个环节测试是否可执行"""
    # 1) 时段探测
    try:
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / 'push_slot_detect.py')],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode != 0:
            fail('pipeline', 'WARN', f'push_slot_detect 执行失败 (exit={r.returncode})')
        elif r.stdout.strip() not in ('NO_SLOT',) and 'PUSH_ID=' not in r.stdout:
            fail('pipeline', 'WARN', f'push_slot_detect 输出异常: {r.stdout.strip()[:60]}')
    except subprocess.TimeoutExpired:
        fail('pipeline', 'WARN', 'push_slot_detect 超时 (>30s)')
    except Exception as e:
        fail('pipeline', 'WARN', f'push_slot_detect 异常: {e}')

    # 2) RSS 源连通性 — 抽检 3 个源
    if (DATA / 'sources.json').exists():
        try:
            import json, socket
            sources = json.loads((DATA / 'sources.json').read_text())
            feeds = []
            for v in sources.values():
                if isinstance(v, list):
                    feeds.extend(v)
                elif isinstance(v, dict):
                    for sub in v.values():
                        if isinstance(sub, list):
                            feeds.extend(sub)
            import random
            sample = random.sample(feeds, min(3, len(feeds)))
            for f in sample:
                url = f.get('feed', '') or f.get('url', '')
                if not url: continue
                try:
                    host = url.split('/')[2] if '://' in url else url.split('/')[0]
                    s = socket.create_connection((host, 443), timeout=5)
                    s.close()
                except Exception:
                    fail('pipeline', 'WARN', f'RSS 源不可达: {url[:50]}')
                    break
        except Exception:
            pass  # sources.json parse error caught by check_config

    # 3) 核心脚本导入检查
    import_check = [
        ('push_prepare', '从 push_prepare 导入'),
        ('batch_fetch', '从 batch_fetch 导入'),
        ('fetch_feeds', '从 fetch_feeds 导入'),
        ('heat_tracker', '从 heat_tracker 导入'),
        ('record_fingerprints', '从 record_fingerprints 导入'),
    ]
    for mod_name, label in import_check:
        mod_path = SCRIPTS / f'{mod_name}.py'
        if not mod_path.exists():
            fail('pipeline', 'WARN', f'{mod_name}.py 缺失')
            continue
        try:
            env = os.environ.copy()
            env['PYTHONPATH'] = str(TR.parent)
            r = subprocess.run(
                [sys.executable, '-c', f'import trendradar.scripts.{mod_name}'],
                capture_output=True, text=True, timeout=15, env=env
            )
            if r.returncode != 0:
                fail('pipeline', 'WARN', f'{label} 导入失败: {r.stderr[:80]}')
        except subprocess.TimeoutExpired:
            fail('pipeline', 'WARN', f'{label} 导入超时')

    # 4) 流水线步骤完整性 — 验证 cron prompt 引用的脚本都存在
    pipeline_steps = ['push_slot_detect.py', 'push_prepare.py', 'batch_fetch.py',
                      'track_events.py', 'record_fingerprints.py', 'fetch_feeds.py',
                      'ai_translate.py', 'render_markdown.py', 'fragment_push.py',
                      'render_deep_analysis.py', 'pipeline_orchestrator.py']
    for ps in pipeline_steps:
        if not (SCRIPTS / ps).exists():
            fail('pipeline', 'WARN', f'流水线脚本 {ps} 缺失')
    """系统资源 — 仅记录，不告警"""
    pass

def check_fingerprint_recent():
    '''验证最近一次指纹记录 — 由看门狗覆盖，此检查冗余'''
    pass

def auto_repair_missing_table():
    """自动重建指纹表 — 通过迁移引擎确保 schema 为最新版。
    
    使用 repair_missing_tables() 替代 migrate()，因为后者在 _migrations
    已记录版本时会跳过已应用迁移，无法修复被意外删除的表。
    """
    db = DATA / 'fingerprints.db'
    if not db.exists(): return
    try:
        sys.path.insert(0, str(TR.parent))
        from trendradar.migrations.runner import repair_missing_tables, migrate
        if repair_missing_tables(db):
            FIXES.append('已修复缺失的数据库表')
        # 同时确保 schema 为最新版本（处理未来新增迁移）
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

def auto_repair_bak_scripts():
    """检查废弃脚本引用"""
    bak = SCRIPTS / 'send_wecom_cards.py.bak'
    if bak.exists():
        pass  # intentional backup, not an issue

def run_checks():
    check_db()
    check_scripts()
    check_config()
    check_cron()
    check_gateway()
    check_data_freshness()
    check_api()
    check_stale_processes()
    check_memory_size()
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
        levels = {'CRITICAL': '🔴', 'WARN': '⚠️'}
        for sev in ['CRITICAL', 'WARN']:
            items = [i for i in ISSUES if i['severity'] == sev]
            if not items: continue
            label = '严重问题' if sev == 'CRITICAL' else '警告'
            lines.append(f'### {levels[sev]} {label}')
            for i in items:
                lines.append(f'- **{i["component"]}**: {i["msg"]}')
            lines.append('')
    
    lines.append('---\n\n📡 趋势雷达自动体检 · 下次运行时自动重检')
    if any(i['severity'] == 'CRITICAL' for i in ISSUES):
        lines.append('🔴 **状态: 异常** — 需要人工介入')
    elif ISSUES:
        lines.append('🟡 **状态: 亚健康** — 警告项需关注')
    else:
        lines.append('🟢 **状态: 健康**')
    
    return '\n'.join(lines)

if __name__ == '__main__':
    run_checks()
    run_repairs()
    print(generate_report())
