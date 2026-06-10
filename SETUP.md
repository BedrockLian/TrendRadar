1|# TrendRadar 从零搭建指南
2|
3|> 从全新 Hermes Agent 环境开始，一步步完成 TrendRadar 的安装、配置、测试和部署。
4|
5|---
6|
7|## 目录
8|
9|1. [前置要求](#1-前置要求)
10|   1. [Hermes Agent](#11-hermes-agent)
11|   2. [Python 3.14t](#12-python-314t免费线程版)
12|   3. [企业微信机器人](#13-企业微信机器人)
13|   4. [API Key](#14-api-key)
14|   5. [代理配置（外媒数据源必需）](#15-代理配置外媒数据源必需)
15|2. [克隆仓库](#2-克隆仓库)
16|3. [安装依赖](#3-安装依赖)
17|4. [环境配置](#4-环境配置)
18|5. [数据库初始化](#5-数据库初始化)
19|6. [测试验证](#6-测试验证)
20|7. [部署 Hermes Skills](#7-部署-hermes-skills)
21|8. [注册定时任务](#8-注册定时任务)
22|9. [首次运行 & 验证](#9-首次运行--验证)
23|10. [附录：常用操作](#10-附录常用操作)
24|
25|---
26|
27|## 1. 前置要求
28|
29|### 1.1 Hermes Agent
30|
31|TrendRadar 深度依赖 Hermes Agent 的 cron 调度、技能系统和企业微信推送。需要先安装并运行 Hermes Agent：
32|
33|```bash
34|# 参考 https://hermes-agent.nousresearch.com/docs 安装
35|# 确保 hermes CLI 可用
36|hermes --version
37|```
38|
39|### 1.2 Python 3.14t（免费线程版）
40|
41|TrendRadar 使用 Python 3.14 free-threaded 构建（无 GIL，多并发抓取性能更优）。推荐编译安装：
42|
43|```bash
44|# 检查是否已安装
45|python3.14t --version
46|
47|# 如需安装，参考 skills/trendradar/news-secretary/references/free-threaded-build.md
48|```
49|
50|> 如果使用普通 Python 3.12+ 也可以，但需要调整 cron prompt 中的解释器路径。
51|
52|### 1.3 企业微信机器人
53|
54|推送目标为企业微信（WeCom），需要：
55|
56|- 已创建企业微信机器人
57|- Hermes Agent 已配置 WeCom 平台并连接成功
58|- `hermes gateway status` 确认 WeCom 已连接
59|
60|### 1.4 API Key
61|
62|TrendRadar 使用 DeepSeek API 进行 AI 策展和翻译。需要有：
63|
64|```bash
65|export DEEPSEEK_API_KEY="sk-xxx...xxxx"
66|```
67|
68|也支持通过 `.env` 文件加载（见 [4. 环境配置](#4-环境配置)）。
69|
70|### 1.5 代理配置（外媒数据源必需）
71|
72|TrendRadar 的部分 RSS 源（路透社、BBC、纽约时报、卫报等）被 GFW 封锁，直连无法访问。系统内置 **自动代理分流** 机制：国内源直连，外媒源走代理。
73|
74|#### 1.5.1 安装 Mihomo（Clash Meta）
75|
76|推荐使用 Mihomo（Clash Meta）作为代理客户端。WSL/Linux amd64 安装：
77|
78|```bash
79|# 下载 Mihomo
80|MIHOMO_VER=$(curl -s https://api.github.com/repos/MetaCubeX/mihomo/releases/latest | grep tag_name | cut -d'"' -f4)
81|wget "https://github.com/MetaCubeX/mihomo/releases/download/${MIHOMO_VER}/mihomo-linux-amd64-${MIHOMO_VER}.gz"
82|gunzip mihomo-linux-amd64-${MIHOMO_VER}.gz
83|chmod +x mihomo-linux-amd64-${MIHOMO_VER}
84|mv mihomo-linux-amd64-${MIHOMO_VER} ~/.local/bin/mihomo
85|```
86|
87|#### 1.5.2 配置订阅
88|
89|创建配置目录并放入订阅配置文件：
90|
91|```bash
92|mkdir -p ~/.config/mihomo
93|# 将你的订阅配置文件写入 ~/.config/mihomo/config.yaml
94|# 订阅链接通常可通过 curl 下载后 base64 解码获得
95|curl -sL "你的订阅链接" | base64 -d > /tmp/sub_decode.txt
96|# 使用转换工具或手动将代理节点写入 config.yaml
97|```
98|
99|最小配置示例 (`~/.config/mihomo/config.yaml`)：
100|
101|```yaml
102|port: 7890
103|socks-port: 7891
104|allow-lan: true
105|bind-address: "0.0.0.0"
106|mode: rule
107|log-level: warning
108|external-controller: 127.0.0.1:9090
109|dns:
110|  enable: true
111|  ipv6: false
112|  enhanced-mode: fake-ip
113|  # ... DNS 配置
114|proxies:
115|  # ... 你的代理节点列表
116|proxy-groups:
117|  # ... 策略组
118|rules:
119|  # ... 路由规则
120|```
121|
122|> **注意**：`allow-lan: true` 和 `bind-address: "0.0.0.0"` 是必需的——TrendRadar 的 RSSHub Docker 容器需要从容器网络访问 Mihomo。
123|
124|#### 1.5.3 注册 Systemd 服务
125|
126|```bash
127|mkdir -p ~/.config/systemd/user
128|cat > ~/.config/systemd/user/mihomo.service << 'EOF'
129|[Unit]
130|Description=Mihomo (Clash Meta) proxy
131|After=network.target
132|
133|[Service]
134|Type=simple
135|ExecStart=%h/.local/bin/mihomo -d %h/.config/mihomo/
136|Restart=on-failure
137|RestartSec=5s
138|
139|[Install]
140|WantedBy=default.target
141|EOF
142|
143|systemctl --user daemon-reload
144|systemctl --user enable --now mihomo.service
145|systemctl --user status mihomo.service
146|```
147|
148|验证代理可用：
149|
150|```bash
151|curl -x http://127.0.0.1:7890 https://www.google.com
152|# 预期: HTTP 200/302（Google 可访问）
153|```
154|
155|#### 1.5.4 TrendRadar 自动分流
156|
157|TrendRadar 的 `scripts/settings.py` 内置 `needs_proxy()` 函数：
158|
159|- **直连**：`plink.anyfeeder.com`（国内中转）、`.cn` 域名
160|- **代理**：外媒直连 RSS（BBC/NYT/Guardian/SCMP 等）、RSSHub 路由（`localhost:1200`）
161|- **特殊**：BBC 被代理节点屏蔽，自动降级为直连
162|
163|无需额外配置，代理地址默认为 `http://127.0.0.1:7890`，可通过环境变量 `TRENDRADAR_PROXY` 覆盖。
164|
165|#### 1.5.5 RSSHub 容器代理（可选）
166|
167|如果使用了 RSSHub 本地实例来获取外媒 RSS，需要给 RSSHub 容器配置代理。推荐使用 `undici.EnvHttpProxyAgent` 方案（Node.js 原生支持）：
168|
169|```dockerfile
170|FROM diygod/rsshub:latest
171|RUN apt-get update && apt-get install -y ca-certificates
172|COPY proxy-fix.mjs /app/proxy-fix.mjs
173|```
174|
175|配合启动命令：
176|```bash
177|docker run -d --name rsshub \
178|  -p 1200:1200 \
179|  -e HTTP_PROXY=http://host.docker.internal:7890 \
180|  -e HTTPS_PROXY=http://host.docker.internal:7890 \
181|  -e NODE_OPTIONS="--max-http-header-size=32768 --import /app/proxy-fix.mjs" \
182|  rsshub-image \
183|  dumb-init -- node --max-http-header-size=32768 --import /app/proxy-fix.mjs dist/index.mjs
184|```
185|
186|`proxy-fix.mjs` 内容：
187|```javascript
188|import undici from 'undici';
189|const proxyUrl = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
190|if (proxyUrl) {
191|  const agent = new undici.EnvHttpProxyAgent();
192|  globalThis[Symbol.for('undici.globalDispatcher.1')] = agent;
193|}
194|```
195|
196|#### 1.5.6 代理排障
197|
198|```bash
199|# 1. Mihomo 是否运行
200|systemctl --user status mihomo.service
201|
202|# 2. 端口监听
203|ss -tlnp | grep 7890
204|
205|# 3. 测试代理
206|curl -x http://127.0.0.1:7890 https://www.google.com
207|
208|# 4. TrendRadar 代理判断
209|cd ~/.hermes/trendradar
210|python3 -c "from scripts.settings import needs_proxy; print(needs_proxy('https://feeds.bbci.co.uk/news/rss.xml'))"
211|
212|# 5. 抓取时查看分流日志（fetch_feeds 输出）
213|python3 -m scripts.fetch_feeds --push-id morning | grep 'FETCH'
214|# 输出示例: [FETCH] 41源（直连 9 + 代理 32）
215|```
216|
217|---
218|
219|## 2. 克隆仓库
220|
221|```bash
222|# 克隆私有仓库（需要 GitHub 认证）
223|git clone https://github.com/BedrockLian/TrendRadar.git ~/TrendRadar
224|cd ~/TrendRadar
225|```
226|
227|目录结构：
228|
229|```
230|TrendRadar/
231|├── trendradar/                        # 核心 Python 包
232|│   ├── scripts/                       # 管线脚本（23 个）
233|│   ├── config/                        # 关键词/时段/翻译/兴趣配置
234|│   ├── migrations/                    # SQLite 数据库迁移引擎
235|│   ├── skills/                        # Hermes Agent 技能定义
236|│   │   ├── news-secretary/            # 日报推送技能（核心）
237|│   │   ├── self-healing/              # 自动体检/自修复
238|│   │   ├── performance-optimizer/     # 偏好收敛优化
239|│   │   ├── system-config/             # 系统配置速查
240|│   │   ├── weekly-report/             # 周报深度研判
241|│   │   ├── monthly-report/            # 月报全景分析
242|│   │   └── execute-assessment-fixes/  # Qwen 审计修复闭环
243|│   ├── reports/                       # 审计报告/提示词
244|│   ├── references/                     # 核心参考文档（10 根 + 36 存档 + INDEX.md）
245|│   ├── tests/                         # 测试用例（146 用例）
246|│   ├── pyproject.toml                 # 项目元数据/依赖
247|│   └── requirements.txt               # 依赖清单
248|├── hermes-scripts/                    # Hermes 外围脚本
249|│   ├── trendradar_health_check.py     # 自动体检
250|│   ├── trendradar_maintenance.py      # 每日维护（备份+清理）
251|│   └── delivery_watchdog.py           # 推送看门狗 + auto-redeliver（早/午/晚）
252|├── .gitignore
253|├── LICENSE
254|└── README.md
255|```
256|
257|### 2.1 部署到运行目录
258|
259|TrendRadar 在 Hermes 中的运行时路径是 `~/.hermes/trendradar/`，即 **实时运行目录**。仓库和运行目录是独立的：
260|
261|```bash
262|# 创建运行时目录（全新安装时）
263|mkdir -p ~/.hermes/trendradar
264|
265|# 也可以创建符号链接来直接使用仓库
266|ln -sf ~/TrendRadar/trendradar ~/.hermes/trendradar
267|```
268|
269|<details>
270|<summary><b>仓库 vs 运行时目录说明（点开）</b></summary>
271|
272|| 用途 | 路径 | 说明 |
273||------|------|------|
274|| Git 发布仓库 | `~/TrendRadar/` | 代码版本管理，只追踪源文件 |
275|| 运行时目录 | `~/.hermes/trendradar/` | 实际运行，含运行时数据（DB/缓存/日志） |
276|| Hermes Skills | `~/.hermes/skills/trendradar/` | Hermes 技能存放位置 |
277|
278|修改代码后，需要同步到仓库：`cp -r ~/.hermes/trendradar/scripts/ ~/TrendRadar/trendradar/`
279|
280|</details>
281|
282|---
283|
284|## 3. 安装依赖
285|
286|### 3.1 Python 包
287|
288|```bash
289|# 方式 A：editable install（推荐，直接使用仓库路径）
290|cd ~/TrendRadar/trendradar
291|python3.14t -m pip install -e .
292|
293|# 方式 B：仅安装依赖
294|python3.14t -m pip install -r requirements.txt
295|
296|# 方式 C：完整开发依赖
297|python3.14t -m pip install -r requirements-dev.txt
298|```
299|
300|### 3.2 免费线程兼容修复（python3.14t 必须）
301|
302|python3.14t 的 PyPI wheel 在某些平台上不完整，需要手动补装：
303|
304|```bash
305|python3.14t -m pip install feedparser zstandard
306|```
307|
308|### 3.3 验证安装
309|
310|```bash
311|cd ~/TrendRadar/trendradar
312|PYTHONPATH=/home/asus/.hermes python3.14t -c "
313|from trendradar.scripts.common import gen_run_id
314|print('ok:', gen_run_id())
315|"
316|```
317|
318|> ⚠️ **PYTHONPATH 陷阱**：`trendradar/` 自身有 `__init__.py`，即它是 Python 包。
319|> 必须设置 `PYTHONPATH` 为其**父目录**（即 `/home/asus/.hermes`），而不是项目根目录本身。
320|> 详见 `trendradar/skills/system-config/SKILL.md`。
321|
322|---
323|
324|## 4. 环境配置
325|
326|### 4.1 创建 `.env` 文件
327|
328|TrendRadar 从环境变量或 `.env` 文件加载 API 凭证：
329|
330|```bash
331|# 运行时目录
332|cat > ~/.hermes/trendradar/.env << 'EOF'
333|DEEPSEEK_API_KEY=***
334|DEEPSEEK_API_ENDPOINT=https://api.deepseek.com/v1/chat/completions
335|DEEPSEEK_MODEL=deepseek-chat
336|TRENDRADAR_LOG_LEVEL=INFO
337|EOF
338|
339|# 安全加固：限制 .env 文件权限
340|chmod 600 ~/.hermes/trendradar/.env
341|```
342|
343|或者直接设置环境变量：
344|
345|```bash
346|export DEEPSEEK_API_KEY="sk-xxx...xxxx"
347|export PYTHONPATH=/home/asus/.hermes
348|export TRENDRADAR_HOME=~/.hermes/trendradar
349|export PYTHON_GIL=0
350|# 可选：翻译批量大小（默认 5，最大 20）
351|# export TRENDRADAR_TRANSLATE_BATCH_SIZE=10
352|# 可选：覆盖代理地址（默认 http://127.0.0.1:7890）
353|# export TRENDRADAR_PROXY=http://127.0.0.1:7890
354|```
355|
356|### 4.2 数据目录
357|
358|运行时目录会自动创建以下子目录：
359|
360|```
361|~/.hermes/trendradar/
362|├── data/          # 指纹库(fingerprints.db)、推送日志、策展数据
363|├── cache/         # 原始抓取缓存、批量处理缓存
364|├── logs/          # 脚本运行日志
365|├── config/        # 配置（已入库）
366|└── scripts/       # 管线脚本（已入库）
367|```
368|
369|首次运行时会自动创建。
370|
371|### 4.3 兴趣偏好
372|
373|```bash
374|cd ~/.hermes/trendradar
375|# 查看当前兴趣
376|python3 scripts/interest_cli.py list
377|
378|# 添加兴趣（加分+2）
379|python3 scripts/interest_cli.py add "新能源汽车"
380|
381|# 排除关键词（0分过滤）
382|python3 scripts/interest_cli.py exclude "加密货币"
383|```
384|
385|---
386|
387|## 5. 数据库初始化
388|
389|TrendRadar 使用 SQLite 作为数据存储。首次使用需要初始化 schema：
390|
391|```bash
392|cd ~/.hermes/trendradar
393|PYTHONPATH=/home/asus/.hermes python3.14t -c "
394|from trendradar.migrations.runner import migrate
395|from pathlib import Path
396|v = migrate(Path('data/fingerprints.db'))
397|print(f'Database migrated to v{v}')
398|"
399|```
400|
401|输出示例：
402|```
403|Applied migration 001_initial.sql
404|Database migrated to v1
405|```
406|
407|初始化后生成：
408|- `data/fingerprints.db` — 包含 `fingerprints`（去重指纹）和 `heat_tracker`（热度追踪）两张表
409|
410|---
411|
412|## 6. 测试验证
413|
414|### 6.1 运行测试套件
415|
416|```bash
417|cd ~/TrendRadar/trendradar
418|
419|# 运行全部测试
420|python3.14t -m pytest -v
421|
422|# 仅运行烟雾测试（快速验证）
423|python3.14t -m pytest -v -m smoke
424|
425|# 排除慢速测试
426|python3.14t -m pytest -v -m "not slow"
427|```
428|
429|### 6.2 测试预期
430|
431|```
432|tests/
433|├── test_pipeline_e2e.py          # 编排器基础测试
434|├── test_pipeline_e2e_real.py     # 真实管线 E2E（11 用例，@integration）
435|├── test_ai_translate.py          # AI 翻译模块
436|├── test_ai_translate_boundary.py # BATCH_SIZE 边界 + 熔断（22 用例）
438|├── test_curate_and_push.py       # 策展 + 多样性惩罚 + 词边界匹配
439|├── test_fetch_feeds.py           # RSS 抓取
440|├── test_heat_tracker.py          # 热度追踪
441|├── test_push_prepare.py          # 推送准备（含 penalty/health 加载）
442|├── test_push_slot_detect.py      # 时段探测（±1 分钟精度）
443|├── test_render_markdown.py       # 渲染格式 + 🔄 emoji
444|├── test_sanity_check.py          # 发布前拦截（含中文 AI 模式）
445|├── test_record_and_common.py     # 公共模块 + 指纹记录（CST 时区）
446|└── test_track_events.py          # 事件追踪（URL 指纹）
447|```
448|
449|> 初始化时因 SQLite 数据库尚为空白，部分测试写入后即通过。
450|
451|### 6.3 常见测试问题
452|
453|| 问题 | 原因 | 解决 |
454||------|------|------|
455|| `ModuleNotFoundError: trendradar` | PYTHONPATH 缺失 | `export PYTHONPATH=/home/asus/.hermes` |
456|| `DEEPSEEK_API_KEY not found` | API key 未配置 | 检查 `.env`（chmod 600）或环境变量 |
457|| RSS 相关测试超时 | 外网不可达 | 确认网络连通性 / `TIMEOUT_SEC` 调大 |
458|
459|---
460|
461|## 7. 部署 Hermes Skills
462|
463|TrendRadar 的功能通过 Hermes Skill 系统暴露给 Agent。
464|
465|### 7.1 复制 Skills 到 Hermes
466|
467|```bash
468|# 逐个部署
469|cp -r ~/TrendRadar/trendradar/skills/news-secretary ~/.hermes/skills/trendradar/
470|cp -r ~/TrendRadar/trendradar/skills/self-healing ~/.hermes/skills/trendradar/
471|cp -r ~/TrendRadar/trendradar/skills/performance-optimizer ~/.hermes/skills/trendradar/
472|cp -r ~/TrendRadar/trendradar/skills/system-config ~/.hermes/skills/trendradar/
473|```
474|
475|### 7.2 部署技能评估框架（可选）
476|
477|TrendRadar 集成了 Anthropic skill-creator 框架，可对技能进行定量评估（with/without 对比 + 评分）：
478|
479|```bash
480|# 如果已拉取（通过本指南首次设置时需手动拉取）
481|hermes skills list | grep anthropic-skill-creator
482|```
483|
484|该框架提供：
485|- 9 组 test case × 2（with/without）并行跑 → 评分 → 聚合报告
486|- 评分 Agent（grader）、盲比 Agent（comparator）、分析 Agent（analyzer）
487|- Web 评估查看器
488|
489|> 拉取方式：参考 https://github.com/anthropics/claude-plugins-official/tree/main/plugins/skill-creator
490|
491|### 7.3 部署外围脚本
492|
493|```bash
494|cp ~/TrendRadar/hermes-scripts/trendradar_health_check.py ~/.hermes/scripts/
495|cp ~/TrendRadar/hermes-scripts/trendradar_maintenance.py ~/.hermes/scripts/
496|cp ~/TrendRadar/hermes-scripts/delivery_watchdog.py ~/.hermes/scripts/
497|chmod +x ~/.hermes/scripts/trendradar_health_check.py
498|chmod +x ~/.hermes/scripts/trendradar_maintenance.py
499|chmod +x ~/.hermes/scripts/delivery_watchdog.py
500|```
501|