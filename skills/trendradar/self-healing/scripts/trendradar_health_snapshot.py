#!/usr/bin/env python3
"""TrendRadar 5-秒健康快照 (Windows-aware)

独立运行：不需要 trendradar 包导入、不修改任何状态。
返回结构化报告 + exit code:
  0 = 全绿
  1 = 有警告
  2 = 有红灯（需立即处理）

覆盖维度（2026-06-09 实战协议）：
  - Gateway 状态（hermes gateway status）
  - Cron job 注册（jobs.json 解析）
  - HERMES_HOME/scripts/（no_agent cron 实际执行目录）
  - 双 data 目录分裂（md5）
  - 内/外 config/scripts 副本同步
  - DB 健康（integrity_check + journal_mode）
  - Python import 链路
  - WeCom 平台连接（gateway log）

用法：
  python scripts/trendradar_health_snapshot.py [--json] [--verbose]
"""
import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# 跨平台 HERMES_HOME 解析（2026-06-09 协议）
if os.name == 'nt':
    HERMES_HOME = Path(os.environ.get('LOCALAPPDATA', r'C:\Users\ASUS\AppData\Local')) / 'hermes'
else:
    HERMES_HOME = Path(os.environ.get('HERMES_HOME', Path.home() / '.hermes'))

TRENDRADAR_HOME = HERMES_HOME / 'trendradar'

# ──────────────────────────────────────── 工具
def run(cmd, timeout=10, shell=False):
    """subprocess 包装，utf-8 兼容 Windows cp1252"""
    try:
        r = subprocess.run(cmd if shell else cmd.split(),
                           capture_output=True, timeout=timeout,
                           shell=shell, text=False)
        out = (r.stdout or b'').decode('utf-8', errors='replace')
        err = (r.stderr or b'').decode('utf-8', errors='replace')
        return r.returncode, out, err
    except subprocess.TimeoutExpired:
        return -1, '', f'TIMEOUT after {timeout}s'
    except FileNotFoundError as e:
        return -1, '', f'NOT FOUND: {e}'


def check(label):
    """装饰器：每项检查统一记录"""
    def decorator(fn):
        def wrapper(*a, **kw):
            try:
                result = fn(*a, **kw)
                return {'label': label, **result}
            except Exception as e:
                return {'label': label, 'status': 'red',
                        'detail': f'check raised: {type(e).__name__}: {e}'}
        return wrapper
    return decorator


# ──────────────────────────────────────── 检查项
@check('Gateway 状态')
def check_gateway():
    code, out, err = run('hermes gateway status')
    if '✓ Gateway is running' in out:
        return {'status': 'green', 'detail': 'Gateway running'}
    return {'status': 'red', 'detail': out[:200] or err[:200]}


@check('Cron jobs 已注册')
def check_cron_jobs():
    jobs_path = HERMES_HOME / 'cron' / 'jobs.json'
    if not jobs_path.exists():
        return {'status': 'red', 'detail': 'jobs.json 不存在 — job 从未注册'}
    try:
        data = json.loads(jobs_path.read_text(encoding='utf-8'))
        jobs = data.get('jobs', [])
        return {'status': 'green',
                'detail': f'{len(jobs)} jobs registered',
                'jobs': [{'id': j['id'][:8], 'name': j['name'],
                          'deliver': j.get('deliver')} for j in jobs]}
    except Exception as e:
        return {'status': 'red', 'detail': f'jobs.json 解析失败: {e}'}


@check('HERMES_HOME/scripts/ 存在（no_agent cron 必须）')
def check_scripts_dir():
    p = HERMES_HOME / 'scripts'
    if not p.exists():
        return {'status': 'red',
                'detail': f'{p} 不存在 — no_agent cron 会被 path guard 拦截'}
    files = list(p.glob('*.py'))
    if not files:
        return {'status': 'yellow',
                'detail': f'{p} 存在但无 .py 文件'}
    return {'status': 'green', 'detail': f'{len(files)} scripts',
            'files': [f.name for f in files]}


@check('双 data 目录 md5 一致')
def check_data_dirs():
    outer_db = TRENDRADAR_HOME / 'data' / 'fingerprints.db'
    inner_db = TRENDRADAR_HOME / 'trendradar' / 'data' / 'fingerprints.db'
    if not outer_db.exists():
        return {'status': 'yellow', 'detail': f'外层 DB 不存在: {outer_db}'}
    if not inner_db.exists():
        return {'status': 'yellow', 'detail': f'内层 DB 不存在: {inner_db}'}
    import hashlib
    h1 = hashlib.md5(outer_db.read_bytes()).hexdigest()
    h2 = hashlib.md5(inner_db.read_bytes()).hexdigest()
    if h1 == h2:
        return {'status': 'green', 'detail': 'md5 一致', 'md5': h1[:8]}
    return {'status': 'yellow',
            'detail': f'md5 不一致（生产在写外层、内层是 git 快照，正常但需手动 cp）',
            'outer': h1[:8], 'inner': h2[:8]}


@check('内外 config/scripts 副本同步')
def check_config_sync():
    pairs = [
        (TRENDRADAR_HOME / 'config', TRENDRADAR_HOME / 'trendradar' / 'config'),
        (TRENDRADAR_HOME / 'scripts', TRENDRADAR_HOME / 'trendradar' / 'scripts'),
    ]
    diffs = []
    for a, b in pairs:
        if not a.exists() or not b.exists():
            diffs.append(f'{a.name}: missing')
            continue
        code, out, _ = run(f'diff -rq "{a}" "{b}"', shell=True)
        # exit 0 = 一致，1 = 有差异
        if code == 1 and out.strip():
            diffs.append(f'{a.name}: {len(out.strip().splitlines())} diffs')
    if diffs:
        return {'status': 'yellow',
                'detail': '有差异（scripts_sync.sh 可同步）', 'diffs': diffs}
    return {'status': 'green', 'detail': '完全一致'}


@check('DB 健康（integrity + WAL）')
def check_db():
    db_path = TRENDRADAR_HOME / 'data' / 'fingerprints.db'
    if not db_path.exists():
        return {'status': 'red', 'detail': '外层 DB 不存在'}
    try:
        import sqlite3
        con = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        cur = con.cursor()
        cur.execute('PRAGMA integrity_check')
        integ = cur.fetchone()[0]
        cur.execute('PRAGMA journal_mode')
        jm = cur.fetchone()[0]
        cur.execute('SELECT count(*) FROM fingerprints')
        fp = cur.fetchone()[0]
        con.close()
        if integ != 'ok':
            return {'status': 'red', 'detail': f'integrity={integ}'}
        return {'status': 'green',
                'detail': f'integrity=ok · {jm} · {fp} fingerprints'}
    except Exception as e:
        return {'status': 'red', 'detail': str(e)}


@check('Python import 链路')
def check_import():
    code, _, err = run(
        f'"{HERMES_HOME / "hermes-agent" / "venv" / "Scripts" / "python.exe"}" '
        f'-c "import sys; sys.path.insert(0, r\'{TRENDRADAR_HOME}\'); '
        f'sys.path.insert(0, r\'{TRENDRADAR_HOME / "trendradar"}\'); '
        f'import trendradar, trendradar.config, trendradar.scripts.settings"',
        timeout=15
    )
    if code == 0:
        return {'status': 'green', 'detail': 'trendradar package 可 import'}
    return {'status': 'red', 'detail': err[:300]}


@check('WeCom 平台连接')
def check_wecom():
    log = HERMES_HOME / 'logs' / 'gateway.log'
    if not log.exists():
        return {'status': 'yellow', 'detail': 'gateway.log 不存在（gateway 未启动过？）'}
    txt = log.read_text(encoding='utf-8', errors='replace')
    if '✓ wecom connected' in txt:
        # 取最近一次连接时间
        for line in reversed(txt.splitlines()):
            if '✓ wecom connected' in line or 'Connected to wss://openws' in line:
                ts = line.split(' INFO ')[0] if ' INFO ' in line else 'unknown'
                return {'status': 'green', 'detail': f'last connected: {ts}'}
        return {'status': 'green', 'detail': 'connected (no ts)'}
    return {'status': 'red', 'detail': 'wecom 未连接（看 gateway.log）'}


# ──────────────────────────────────────── 主
def main():
    json_mode = '--json' in sys.argv
    verbose = '--verbose' in sys.argv or '-v' in sys.argv

    checks = [
        check_gateway(),
        check_cron_jobs(),
        check_scripts_dir(),
        check_data_dirs(),
        check_config_sync(),
        check_db(),
        check_import(),
        check_wecom(),
    ]

    if json_mode:
        print(json.dumps({'timestamp': datetime.now().isoformat(),
                          'hermes_home': str(HERMES_HOME),
                          'trendradar_home': str(TRENDRADAR_HOME),
                          'checks': checks}, indent=2, ensure_ascii=False))
    else:
        print(f'TrendRadar 健康快照 — {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        print(f'HERMES_HOME={HERMES_HOME}')
        print(f'TRENDRADAR_HOME={TRENDRADAR_HOME}')
        print('─' * 60)

        emoji = {'green': '✅', 'yellow': '⚠️ ', 'red': '🚨'}
        for c in checks:
            print(f'{emoji[c["status"]]} {c["label"]}: {c["detail"]}')
            if verbose and 'jobs' in c:
                for j in c['jobs']:
                    print(f'     • {j["id"]} {j["name"]:24s} deliver={j["deliver"]}')
            if verbose and 'diffs' in c:
                for d in c['diffs']:
                    print(f'     • {d}')

        print('─' * 60)
        reds = sum(1 for c in checks if c['status'] == 'red')
        yellows = sum(1 for c in checks if c['status'] == 'yellow')
        print(f'汇总: {reds} 红灯 · {yellows} 警告 · {len(checks) - reds - yellows} 绿')

    # Exit code
    if any(c['status'] == 'red' for c in checks):
        sys.exit(2)
    if any(c['status'] == 'yellow' for c in checks):
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()