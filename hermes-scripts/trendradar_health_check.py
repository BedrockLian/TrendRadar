1|#!/usr/bin/env python3
2|"""TrendRadar 自动体检 + 自修复脚本 v2.1
3|
4|检查项：DB/脚本/配置/Cron/网关/API/数据时效/全链路/盲点/记忆/进程滞留/拦截器
5|Cron 每日 15:00（c987a2883174）no_agent=true 静默运行。
6|健康→stdout 空→不推送；异常→Markdown→推送 WeCom。
7|"""
8|import json, sqlite3, subprocess, sys, os, re, time, logging
9|from pathlib import Path
10|from datetime import datetime, timezone, timedelta
11|
12|CST = timezone(timedelta(hours=8))
13|TR = Path(os.environ.get('TRENDRADAR_HOME', Path.home() / '.hermes' / 'trendradar'))
14|SCRIPTS = TR / 'scripts'
15|DATA = TR / 'data'
16|CACHE = TR / 'cache'
17|
18|ISSUES = []
19|FIXES = []
20|
21|# ── 已知 cron job 名称（用于动态匹配，不依赖 job ID） ──────────
22|CRON_JOB_NAMES = [
23|    '日报推送', '推送降级看门狗', '每日维护',
24|    '自动体检', '周报推送', '月度趋势报告',
25|]
26|
27|# ── 核心配置键（settings.py 必须导出的常量） ──────────────────
28|SETTINGS_CONSTANTS = ['DOMAINS', 'DOMAIN_LABELS', 'MAX_PER_DOMAIN',
29|                      'BRIEFING_RATIO', 'DAILY_LIMIT', 'MIN_SCORE',
30|                      'TRENDRADAR_HOME']
31|
32|def fail(component, severity, msg):
33|    ISSUES.append({'component': component, 'severity': severity, 'msg': msg})
34|
35|# ═══════════════════════════════════════════════════════════════
36|# 检查函数
37|# ═══════════════════════════════════════════════════════════════
38|
39|def check_db():
40|    """指纹库完整性 — 统一通过 Storage 检查"""
41|    db = DATA / 'fingerprints.db'
42|    if not db.exists():
43|        fail('fingerprints.db', 'CRITICAL', '数据库文件不存在')
44|        return
45|    if db.stat().st_size < 1000:
46|        fail('fingerprints.db', 'CRITICAL', f'数据库仅 {db.stat().st_size}B')
47|        return
48|    try:
49|        # 通过 Storage 统一接入
50|        sys.path.insert(0, str(TR.parent))
51|        from trendradar.scripts.storage import Storage
52|        store = Storage(DATA)
53|        conn = store.db('fingerprints.db')
54|        tables = [r[0] for r in conn.execute('SELECT name FROM sqlite_master WHERE type="table"').fetchall()]
55|        if 'fingerprints' not in tables:
56|            fail('fingerprints.db', 'CRITICAL', 'fingerprints 表不存在')
57|        else:
58|            cnt = conn.execute('SELECT COUNT(*) FROM fingerprints').fetchone()[0]
59|        if 'heat_tracker' not in tables:
60|            fail('heat_tracker', 'WARN', 'heat_tracker 表不存在')
61|        else:
62|            hc = conn.execute('SELECT COUNT(*) FROM heat_tracker').fetchone()[0]
63|        # WAL 模式检查
64|        journal = conn.execute('PRAGMA journal_mode').fetchone()[0]
65|        if journal.upper() != 'WAL':
66|            fail('fingerprints.db', 'WARN', f'journal_mode={journal}（建议 WAL）')
67|        store.close_db('fingerprints.db')
68|    except Exception as e:
69|        fail('fingerprints.db', 'CRITICAL', f'数据库异常: {e}')
70|
71|
72|def check_scripts():
73|    """所有脚本可执行 — 含 v2.9.0 新增脚本"""
74|    required = [
75|        'push_prepare.py', 'fetch_feeds.py', 'push_slot_detect.py',
76|        'record_fingerprints.py', 'track_events.py', 'heat_tracker.py', 'ai_translate.py',
77|        'render_markdown.py', 'fragment_push.py', 'render_deep_analysis.py',
78|        'curate_and_push.py', 'pipeline_orchestrator.py', 'common.py',
79|        'settings.py', 'storage.py',
80|        # v2.9.0 新增
81|        'sanity_check.py', 'blind_spot_audit.py', 'aggregate_monthly.py',
82|    ]
83|    for name in required:
84|        p = SCRIPTS / name
85|        if not p.exists():
86|            fail(f'trendradar/scripts/{name}', 'WARN', '文件缺失')
87|
88|
89|def check_config():
90|    """关键配置存在 + 内容可用"""
91|    # YAML 配置文件
92|    for name in ['timeline.yaml', 'ai_interests.yaml']:
93|        p = TR / 'config' / name
94|        if not p.exists():
95|            fail(f'config/{name}', 'WARN', '文件缺失')
96|        elif p.stat().st_size < 10:
97|            fail(f'config/{name}', 'WARN', '文件过小（疑为空）')
98|
99|    # JSON 源
100|    sources = TR / 'config' / 'sources.json'
101|    if not sources.exists():
102|        fail('config/sources.json', 'WARN', '文件缺失')
103|    elif sources.stat().st_size < 50:
104|        fail('config/sources.json', 'WARN', 'sources.json 过小')
105|
106|    # 新增数据文件
107|    for name, label in [
108|        ('source_health.json', 'source_health'),
109|        ('push_log.json', 'push_log'),
110|    ]:
111|        p = DATA / name
112|        if not p.exists():
113|            fail(f'data/{name}', 'INFO', f'{label} 尚未创建（首次运行正常）')
114|
115|    # keywords.py
116|    kw = TR / 'config' / 'keywords.py'
117|    if not kw.exists():
118|        fail('config/keywords.py', 'WARN', '文件缺失')
119|    elif kw.stat().st_size < 1000:
120|        fail('config/keywords.py', 'WARN', f'keywords.py 仅 {kw.stat().st_size}B，疑似过小')
121|    else:
122|        try:
123|            content = kw.read_text()
124|            if 'has_keyword_match_ci' not in content:
125|                fail('config/keywords.py', 'WARN', '缺少 has_keyword_match_ci 函数')
126|            set_defs = [l for l in content.split('\n') if '= frozenset' in l or '= {' in l and 'GAME_KW' in l]
127|            if len(set_defs) < 2:
128|                fail('config/keywords.py', 'WARN', f'疑似关键词定义不足（仅 {len(set_defs)} 个集合）')
129|        except Exception as e:
130|            fail('config/keywords.py', 'WARN', f'读取失败: {e}')
131|
132|
133|def check_settings_constants():
134|    """验证 settings.py 导出关键常量"""
135|    try:
136|        sys.path.insert(0, str(TR.parent))
137|        from trendradar.scripts.settings import (
138|            DOMAINS, DOMAIN_LABELS, MAX_PER_DOMAIN,
139|            BRIEFING_RATIO, DAILY_LIMIT, MIN_SCORE, TRENDRADAR_HOME
140|        )
141|        expected = {'top_headlines', 'foreign_china', 'tech', 'economy', 'gaming'}
142|        if set(DOMAINS) != expected:
143|            fail('settings.py', 'WARN', f'DOMAINS 不完整: {DOMAINS}')
144|        if set(BRIEFING_RATIO.keys()) != {'morning', 'noon', 'evening'}:
145|            fail('settings.py', 'WARN', f'BRIEFING_RATIO 缺少时段: {list(BRIEFING_RATIO.keys())}')
146|    except Exception as e:
147|        fail('settings.py', 'WARN', f'导入/验证失败: {e}')
148|
149|
150|def check_cron():
151|    """cron 调度器 — 所有关键 job 注册（按名称匹配，不依赖 job ID）"""
152|    try:
153|        r = subprocess.run(['hermes', 'cron', 'list'], capture_output=True, text=True, timeout=15)
154|        if r.returncode == 0:
155|            # Parse table output: lines with "Name:      xxx"
156|            import re
157|            job_names = set()
158|            for line in r.stdout.split('\n'):
159|                m = re.match(r'\s+Name:\s+(.+)', line)
160|                if m:
161|                    job_names.add(m.group(1).strip())
162|            if not job_names:
163|                # Fallback: search for known names in full output
164|                for name in CRON_JOB_NAMES:
165|                    if name not in r.stdout:
166|                        fail('cron', 'WARN', f'job "{name}" 未注册')
167|            else:
168|                for name in CRON_JOB_NAMES:
169|                    if not any(name in jn for jn in job_names):
170|                        # Try fuzzy: name "日报推送" should match "TrendRadar 日报推送（早/午/晚）"
171|                        fuzzy_found = False
172|                        for jn in job_names:
173|                            for token in name.split():
174|                                if token in jn:
175|                                    fuzzy_found = True
176|                                    break
177|                            if fuzzy_found:
178|                                break
179|                        if not fuzzy_found:
180|                            fail('cron', 'WARN', f'job "{name}" 未注册')
181|    except Exception as e:
182|        fail('cron', 'WARN', f'查询失败: {e}')
183|
184|
185|def check_gateway():
186|    """WeCom gateway 连接 — 通过 systemd 状态检测"""
187|    try:
188|        r = subprocess.run(
189|            ['systemctl', '--user', 'is-active', 'hermes-gateway.service'],
190|            capture_output=True, text=True, timeout=5,
191|        )
192|        status = r.stdout.strip()
193|        if status == 'active':
194|            return  # ✅ 正常
195|        elif status == 'inactive' or status == 'dead':
196|            fail('gateway', 'WARN', 'hermes-gateway.service 未运行 (inactive)')
197|        elif status == 'failed':
198|            fail('gateway', 'WARN', 'hermes-gateway.service 已崩溃 (failed)')
199|        else:
200|            # Fallback: try gateway status command
201|            r2 = subprocess.run(
202|                ['hermes', 'gateway', 'status'],
203|                capture_output=True, text=True, timeout=10,
204|            )
205|            if 'is running' not in r2.stdout and 'active' not in r2.stdout:
206|                fail('gateway', 'WARN', 'hermes gateway 进程可能未运行')
207|    except FileNotFoundError:
208|        # No systemd — fallback to socket check
209|        sock_paths = [
210|            '/tmp/hermes-wecom-card.sock',
211|            '/tmp/hermes_wecom.sock',
212|            '/tmp/hermes_gateway.sock',
213|        ]
214|        if not any(Path(p).exists() for p in sock_paths):
215|            fail('gateway', 'WARN', f'IPC socket 不存在（检查了 {len(sock_paths)} 个路径）')
216|    except Exception as e:
217|        fail('gateway', 'WARN', f'检查失败: {e}')
218|
219|
220|def check_data_freshness():
221|    """检查最新数据文件时效"""
222|    now = time.time()
223|    curated_files = sorted(DATA.glob('curated_*.json'), key=lambda f: f.stat().st_mtime, reverse=True)
224|    if curated_files:
225|        age_hours = (now - curated_files[0].stat().st_mtime) / 3600
226|        if age_hours > 15:
227|            fail('data', 'WARN', f'最新 curated 数据已 {age_hours:.1f}h 未更新')
228|    else:
229|        fail('data', 'WARN', '无 curated 数据文件')
230|
231|
232|def check_api():
233|    """快速外网连通性测试 — 用 DeepSeek API（经 NO_PROXY 直连可达）代替被代理阻断的 httpbin"""
234|    for url, label in [
235|        ('https://api.deepseek.com/v1/models', '外网 API 可达（DeepSeek）'),
236|    ]:
237|        try:
238|            # DeepSeek 直连（绕过代理），在 cron 环境也有效
239|            env = os.environ.copy()
240|            env.pop('HTTP_PROXY', None)
241|            env.pop('HTTPS_PROXY', None)
242|            env.pop('http_proxy', None)
243|            env.pop('https_proxy', None)
244|            r = subprocess.run(
245|                ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}',
246|                 '--connect-timeout', '5', url],
247|                capture_output=True, text=True, timeout=10, env=env
248|            )
249|            code = r.stdout.strip()
250|            if code not in ('200', '401', '403'):
251|                fail('api', 'WARN', f'{label} 不可达 (HTTP {code})')
252|        except subprocess.TimeoutExpired:
253|            fail('api', 'WARN', f'{label} 超时')
254|        except Exception as e:
255|            fail('api', 'WARN', f'{label} 检查失败: {e}')
256|
257|
258|def check_stale_processes():
259|    """检查卡死的 python 进程"""
260|    try:
261|        r = subprocess.run(['ps', 'aux'], capture_output=True, text=True, timeout=5)
262|        for line in r.stdout.split('\n'):
263|            if 'cron_' not in line and 'trendradar' not in line.lower():
264|                continue
265|            parts = line.split()
266|            if len(parts) < 11:
267|                continue
268|            if 'python' in line.lower() or 'python3' in line.lower():
269|                for jid in CRON_JOB_NAMES:
270|                    if jid[:8] in line or jid[:6] in line:
271|                        fail('process', 'WARN', f'疑似滞留进程: {line[:120]}')
272|                        break
273|    except (subprocess.SubprocessError, FileNotFoundError):
274|        pass
275|
276|
277|def check_memory_size():
278|    """监控记忆文件和用户画像膨胀"""
279|    mem_file = Path.home() / '.hermes' / 'memories' / 'MEMORY.md'
280|    user_file = Path.home() / '.hermes' / 'memories' / 'USER.md'
281|
282|    for label, path in [('MEMORY.md', mem_file), ('USER.md', user_file)]:
283|        if not path.exists():
284|            fail('memory', 'WARN', f'{label} 文件缺失')
285|            continue
286|        size = len(path.read_text(encoding='utf-8'))
287|        limit = 2200 if label == 'MEMORY.md' else 1375
288|        pct = int(size / limit * 100)
289|        if pct >= 90:
290|            fail('memory', 'WARN', f'{label} 已膨胀至 {pct}% ({size}/{limit})，建议压缩')
291|        elif pct >= 75:
292|            fail('memory', 'WARN', f'{label} 使用率 {pct}% ({size}/{limit})，接近阈值')
293|
294|
295|def check_push_log_backpressure():
296|    """push_log.json 体积监控"""
297|    log_file = DATA / 'push_log.json'
298|    if not log_file.exists():
299|        return
300|    size = log_file.stat().st_size
301|    if size > 1_000_000:
302|        fail('push_log', 'WARN', f'push_log.json 已 {size/1024/1024:.1f}MB，建议清理或轮转')
303|    elif size > 100_000:
304|        fail('push_log', 'WARN', f'push_log.json 已 {size/1024:.0f}KB，接近 1MB 阈值')
305|
306|
307|def check_sanity_interceptor():
308|    """发布前拦截器就位检查"""
309|    script = SCRIPTS / 'sanity_check.py'
310|    if not script.exists():
311|        fail('sanity_check', 'WARN', 'sanity_check.py 缺失 — 发布前拦截器未就位')
312|        return
313|
314|    try:
315|        env = os.environ.copy()
316|        env['PYTHONPATH'] = str(TR.parent)
317|        pipeline_python = os.environ.get('PYTHON', '/usr/local/bin/python3.14t')
318|        r = subprocess.run(
319|            [pipeline_python, str(script), '--json', '--no-check-links'],
320|            input='test content', capture_output=True, text=True, timeout=10, env=env
321|        )
322|        if r.returncode not in (0, 3):
323|            fail('sanity_check', 'WARN', f'sanity_check.py 异常退出 (exit={r.returncode})')
324|    except Exception as e:
325|        fail('sanity_check', 'WARN', f'sanity_check.py 不可用: {e}')
326|
327|
328|def check_pipeline():
329|    """全链路探测"""
330|    pipeline_python = os.environ.get('PYTHON', '/usr/local/bin/python3.14t')
331|    if not os.access(pipeline_python, os.X_OK):
332|        pipeline_python = sys.executable
333|
334|    # 1) 时段探测
335|    try:
336|        penv = os.environ.copy()
337|        penv['PYTHONPATH'] = str(TR.parent)
338|        r = subprocess.run(
339|            [pipeline_python, str(SCRIPTS / 'push_slot_detect.py')],
340|            capture_output=True, text=True, timeout=30, env=penv
341|        )
342|        if r.returncode != 0 and r.stdout.strip() != 'NO_SLOT':
343|            fail('pipeline', 'WARN', f'push_slot_detect 执行失败 (exit={r.returncode})')
344|        elif r.stdout.strip() not in ('NO_SLOT',) and 'PUSH_ID=' not in r.stdout:
345|            fail('pipeline', 'WARN', f'push_slot_detect 输出异常: {r.stdout.strip()[:60]}')
346|    except subprocess.TimeoutExpired:
347|        fail('pipeline', 'WARN', 'push_slot_detect 超时 (>30s)')
348|    except Exception as e:
349|        fail('pipeline', 'WARN', f'push_slot_detect 异常: {e}')
350|
351|    # 2) RSS 源连通性（跳过 localhost 源 — 本地通常不运行）
352|    if (TR / 'config' / 'sources.json').exists():
353|        try:
354|            import socket
355|            sources = json.loads((TR / 'config' / 'sources.json').read_text())
356|            feeds = sources.get('data_sources', [])
357|            if isinstance(feeds, dict):
358|                feeds = list(feeds.values())
359|            if not isinstance(feeds, list):
360|                feeds = []
361|            if feeds:
362|                rss_feeds = [f for f in feeds if isinstance(f, dict) and f.get('feed_url')
363|                             and f.get('enabled', True)
364|                             and 'localhost' not in f.get('feed_url', '')]
365|                # 取前 3 个非 localhost 的源（确定性，不随机）
366|                sample = rss_feeds[:3]
367|                failed_urls = []
368|                for f in sample:
369|                    url = f.get('feed_url', '')
370|                    if not url:
371|                        continue
372|                    try:
373|                        host = url.split('/')[2] if '://' in url else url.split('/')[0]
374|                        s = socket.create_connection((host, 443), timeout=5)
375|                        s.close()
376|                    except Exception:
377|                        failed_urls.append(url[:60])
378|                if failed_urls:
379|                    if len(failed_urls) == len(sample):
380|                        fail('pipeline', 'WARN', f'所有抽样 RSS 源不可达: {failed_urls[0]} 等 {len(failed_urls)} 个')
381|                    else:
382|                        # 部分失败只记录，不报 WARN（单个源不稳定是常态）
383|                        logging.debug(f'RSS 抽样 {len(failed_urls)}/{len(sample)} 不可达: {failed_urls}')
384|                        for url in failed_urls:
385|                            print(f'[HEALTH] ⚠️ RSS 源偶发不可达: {url}', file=sys.stderr)
386|        except Exception:
387|            pass
388|
389|    # 3) 核心脚本导入检查
390|    import_check = [
391|        'push_prepare', 'fetch_feeds', 'heat_tracker',
392|        'record_fingerprints', 'ai_translate', 'common',
393|        'fragment_push', 'curate_and_push',
394|        'blind_spot_audit', 'aggregate_monthly', 'storage',
395|    ]
396|    for mod_name in import_check:
397|        try:
398|            env = os.environ.copy()
399|            env['PYTHONPATH'] = str(TR.parent)
400|            r = subprocess.run(
401|                [pipeline_python, '-c', f'import trendradar.scripts.{mod_name}'],
402|                capture_output=True, text=True, timeout=15, env=env
403|            )
404|            if r.returncode != 0:
405|                fail('pipeline', 'WARN', f'{mod_name}.py 导入失败: {r.stderr[:80]}')
406|        except subprocess.TimeoutExpired:
407|            fail('pipeline', 'WARN', f'{mod_name}.py 导入超时')
408|        except Exception as e:
409|            fail('pipeline', 'WARN', f'{mod_name}.py 导入异常: {e}')
410|
411|    # 4) 流水线步骤完整性
412|    pipeline_steps = [
413|        'push_slot_detect.py', 'push_prepare.py',
414|        'track_events.py', 'record_fingerprints.py', 'fetch_feeds.py',
415|        'ai_translate.py', 'render_markdown.py', 'fragment_push.py',
416|        'render_deep_analysis.py', 'pipeline_orchestrator.py',
417|        'curate_and_push.py', 'common.py',
418|        'storage.py',
419|        'sanity_check.py', 'blind_spot_audit.py', 'aggregate_monthly.py',
420|    ]
421|    for ps in pipeline_steps:
422|        if not (SCRIPTS / ps).exists():
423|            fail('pipeline', 'WARN', f'流水线脚本 {ps} 缺失')
424|
425|    # 5) 系统资源
426|    _check_system_resources()
427|
428|
429|def check_blind_spot():
430|    """板块覆盖率盲点检测"""
431|    pipeline_python = os.environ.get('PYTHON', '/usr/local/bin/python3.14t')
432|    if not os.access(pipeline_python, os.X_OK):
433|        pipeline_python = sys.executable
434|
435|    audit_script = SCRIPTS / 'blind_spot_audit.py'
436|    if not audit_script.exists():
437|        fail('blind_spot', 'WARN', 'blind_spot_audit.py 脚本缺失')
438|        return
439|
440|    try:
441|        env = os.environ.copy()
442|        env['PYTHONPATH'] = str(TR.parent)
443|        r = subprocess.run(
444|            [pipeline_python, str(audit_script), '--days', '3', '--json',
445|             '--coverage-threshold', '10'],
446|            capture_output=True, text=True, timeout=30, env=env,
447|        )
448|        if r.returncode != 0:
449|            fail('blind_spot', 'WARN', f'盲点审计执行失败: {r.stderr[:100]}')
450|            return
451|
452|        result = json.loads(r.stdout)
453|        low_domains = result.get('low_coverage_domains', [])
454|
455|        if low_domains:
456|            for d in low_domains:
457|                pct = result['coverage'].get(d, {}).get('percentage', '?')
458|                fail('blind_spot', 'WARN',
459|                     f'板块 {d} 近 3 天覆盖率仅 {pct}%（低于 10% 阈值）'
460|                     f' — 该领域 RSS 源可能大面积失效')
461|    except json.JSONDecodeError:
462|        fail('blind_spot', 'WARN', f'盲点审计输出非 JSON: {r.stdout[:100]}')
463|    except subprocess.TimeoutExpired:
464|        fail('blind_spot', 'WARN', '盲点审计执行超时')
465|    except Exception as e:
466|        fail('blind_spot', 'WARN', f'盲点审计异常: {e}')
467|
468|
469|def _check_system_resources():
470|    """系统资源占用"""
471|    try:
472|        r = subprocess.run(['df', '-h', str(TR)], capture_output=True, text=True, timeout=5)
473|        for line in r.stdout.split('\n')[1:]:
474|            if not line.strip(): continue
475|            parts = line.split()
476|            if len(parts) >= 5 and parts[4].rstrip('%').isdigit():
477|                pct = int(parts[4].rstrip('%'))
478|                if pct >= 90:
479|                    fail('disk', 'WARN', f'磁盘 {parts[5]} 使用率 {pct}%')
480|    except Exception:
481|        pass
482|
483|
484|# ═══════════════════════════════════════════════════════════════
485|# 自动修复
486|# ═══════════════════════════════════════════════════════════════
487|
488|def auto_repair_missing_table():
489|    """自动重建指纹表"""
490|    db = DATA / 'fingerprints.db'
491|    if not db.exists(): return
492|    try:
493|        sys.path.insert(0, str(TR.parent))
494|        from trendradar.migrations.runner import repair_missing_tables, migrate
495|        if repair_missing_tables(db):
496|            FIXES.append('已修复缺失的数据库表')
497|        ver = migrate(db)
498|        if ver > 0 and not any('数据库迁移' in f for f in FIXES):
499|            FIXES.append(f'数据库 schema 版本 v{ver}')
500|    except Exception as e:
501|