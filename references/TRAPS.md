<!-- version: 2.8.0 | last-reviewed: 2026-05-26 -->

# 已知陷阱

> 编号对应发现顺序。仅含当前有效的陷阱。历史已修复陷阱见 `traps-archive.md`。

## 1. Cron 模板变量陷阱
`{PUSH_ID}` 不会被 scheduler 展开。**修复**：步骤 0 先跑 `push_slot_detect.py` 获取真实参数。

## 2. delegate_task max_iterations 崩溃
非晚间误触发时子代理消耗 50 calls 后崩溃。**修复**：仅 evening 时段调用。

## 3. 英文摘要残留
外媒摘要必须翻译中文。**修复**：`data/sources.json` 中 `language` 字段定义翻译规则。

## 4. WeCom 分片丢失
>4000 字符 WeCom 静默截断。按板块分片，片间 1.5s。delegate_task 结果独立投递。cron 中通过 final response 自动投递，非 send_message。

## 5. 零前置文本违规
LLM 输出 "Now let me" / "Here is" 等过程描述会被推送到 WeCom。cron prompt 顶部禁止此类短语。

## 6. AC 自动机 + Free-Threaded 的 GIL
`pyahocorasick` C 扩展未声明 `Py_MOD_GIL_NOT_USED`。`PYTHON_GIL=0` 强制保持。

## 7. zstd 压缩副本单向
`write_compressed()` 写 `.json.zst` 但无脚本读——冷备份用途，非热数据路径。

## 8. Bracketless except 限制
`except A, B, C as e:` 是语法错误。需括号：`except (A, B, C) as e:`。

## 9. python3.14t 环境不完整
`--disable-gil` 编译的 Python ABI 不兼容标准 wheel。两个必需修复：
- **C 扩展缺失**：`_zstd`/`feedparser` 需 `python3.14t -m pip install zstandard feedparser`
- **PYTHONPATH 缺失**：cron prompt 必须 `export PYTHONPATH=/home/asus/.hermes`，否则 `ModuleNotFoundError: No module named 'trendradar'`。pyproject.toml 的 `[tool.pdm]` 配置对子 shell 无效。

## 10. translate.yaml 源名与 sources.json 不同步
重构 sources.json 时 translate.yaml 的旧源名不会自动失效——翻译静默跳过无报错。
**修复**：改 sources.json 后跑 `pytest tests/ -k translate_config`。

## 13. Gateway 崩溃 → 推送丢失但脚本报"成功"
Pipeline 报告投递成功，但 Gateway 同时崩溃消息未达 WeCom。
**信号**：`hermes gateway status` 显示 `failed`，用户反馈没收到但 cron 日志 ok。
**修复**：重启 Gateway → 补推 bypass（直接 render→fragment→final response 自动投递）。

## 14. Cron 技能名不匹配
技能重命名后 cron `skills` 列表仍引用旧名 → `⚠️ Skill(s) not found and skipped`。
**修复**：`cronjob action=update job_id=xxx skills=[...]`。重命名后必须同步 cron skills 列表 + SKILL.md companion_skills + system-config 文档。

## 15. Cron prompt 与 skill 内容不同步
cron prompt 是独立文本字段。skill 更新脚本名/步骤后 prompt 不自动更新。Agent 看到 skill 内容但优先执行 prompt 中的旧命令。
**信号**：prompt 引用已删除脚本（如 `render_briefing.py`）、旧技能名（`trendradar-news-secretary`）。
**修复**：`cronjob action=update job_id=xxx prompt="..."` 单独更新。每次改 pipeline 脚本名后检查所有 cron prompt。

## 16. tirith 安全扫描拦截中文命令 [已关闭]
中文/Unicode 内容触发规则匹配 → terminal 命令被拦截。**修复**：`hermes config set security.tirith_enabled false`。

## 17. push_slot_detect 返回 NO_SLOT 跳过推送
补推或跨时段手动触发时有时效窗口限制。**修复**：绕过 slot 检测，直接 render→fragment→final response 自动投递。不要重跑完整 pipeline（会变更数据状态）。

## 19. references/ 目录在 workdir 不存在
skill 内 `cat references/xxx.md` 依赖 workdir references/。如果不存在返回空。
**修复**：`cp -r ~/TrendRadar/trendradar/references/ ~/.hermes/trendradar/`。
**预防**：同步时确保 `~/.hermes/trendradar/references/` 与 `~/TrendRadar/trendradar/references/` 一致。

## 20. Cron prompt 引用已删除的辅助脚本
`blind_spot_audit.py` / `aggregate_monthly.py` 被周报/月报 prompt 引用但可能不存在。
**修复**：确认脚本存在于 workdir，或从仓库恢复。

## 22. Cron context 下投递机制 [已弃用 send_message]
`send_message` 工具在 cron 运行时**不可用**。pipeline 应始终将渲染好的简报作为 final response 输出，由系统自动投递到 WeCom。不要尝试在 cron 中用 send_message 逐片投递。
**信号**：日志有 "send_message isn't available" + agent 回退到 LLM 重新生成内容。
**修复**：cron prompt 指定——将 BRIEFING 作为最终输出，系统自动投递。详见 `cron-sendmessage-fallback.md`。

## 27. 健康检查子进程调用用错 Python 解释器
`trendradar_health_check.py` 的 `check_pipeline()` 在子进程中用 `sys.executable`（系统 python3）调用脚本。系统 python3 缺少 `feedparser`、`zstandard` 等仅装在 python3.14t 上的依赖 → 导入检查误报 `ModuleNotFoundError`。同时 `push_slot_detect` 也需要 `PYTHONPATH` 才能 `import trendradar.scripts.settings`。
**修复**：所有子进程调用统一走 `$PYTHON` 环境变量（fallback `/usr/local/bin/python3.14t`），设 `PYTHONPATH` + `PYTHON_GIL=0`。
```python
pipeline_python = os.environ.get('PYTHON', '/usr/local/bin/python3.14t')
if not os.access(pipeline_python, os.X_OK):
    pipeline_python = sys.executable
penv = os.environ.copy()
penv['PYTHONPATH'] = str(TR.parent)
penv.setdefault('PYTHON_GIL', '0')
subprocess.run([pipeline_python, ...], env=penv)
```

## 28. DeepSeek API 服务端流中断 [持续发生]
`RemoteProtocolError: peer closed connection without sending complete message body (incomplete chunked read)`，上游 `server=openresty`。DeepSeek 的 openresty 反向代理在 HTTP 200 响应中途断连。近期（5/24）一天出现 4 次。
**影响**：自动重试（3 次）兜住了大部分情况。但 12:02 那次 cron 日报因流中断只返回了 stub response，半篇丢失。
**信号**：`errors.log` 中 `Stream drop` + `RemoteProtocolError` + `upstream=[server=openresty]`。
**修复**：服务器端问题，本地无解。确认自动重试生效（3 次尝试），偶发的 stub response 需人工补推。
**检测**：健康检查已新增 `check_api()` 验证 DeepSeek 可达性。

## 29. WeCom WebSocket 频繁断连 [环境问题]
`[Wecom] WebSocket error: WeCom websocket closed` → 2s 后自动重连。今日已断开 10 次，间隔 12-20 分钟。
**影响**：自动重连始终成功（≤2.3s），推送丢失概率低。但 Gateway 崩溃信号（推送丢失）需要靠看门狗区分 WebSocket 断连和 Gateway 崩溃。
**信号**：`agent.log` 中 `WebSocket error` + 紧跟 `Reconnected` 即为正常 flapping。仅 `Reconnected` 缺失才考虑 Gateway 崩溃。
**修复**：环境正常现象。`delivery_watchdog.py` 已兼容此模式，不会因短暂断连误报。

## 30. 缓存文件过期未清理 [发现 2026-05-25]
`remove_older_than()` 仅清理 data/ 目录的匹配文件。但 `cache/` 目录下的 RSS 原始缓存和 fetch 快照不受此管控，可能无限堆积。
**信号**：`cache/` 目录文件数持续增长，磁盘空间缓慢下降。
**修复**：维护脚本 `trendradar_maintenance.py` 应增加对 `cache/*.json` 的过期清理（保留 48h）。Storage.vacuum() 每周清理 DB 碎片。

<!-- Consolidated from pipeline-pitfalls.md, translation-pipeline-sync.md, render-markdown-failures.md, health-check-pitfalls.md, smoke-test-maintenance.md, ai-translate-cjk-detection.md, migration-idempotency-bug.md, api-diagnosis.md, fix-recipes.md, fragment-byte-splitting.md, pitfalls-utf8-bytes.md -->

## 31. fetch_feeds 共用 TCPConnector 崩溃 [管线运维]
**现象**：`RuntimeError: Session is closed`，所有国际源抓取失败，管线产出 0 条。
**根因**：`fetch_all()` 中直连和代理两个 `ClientSession` 共享同一个 `TCPConnector`。第一个 session 退出时 `__aexit__` 关闭连接池，第二个 session 直接报 Session is closed。
**修复**（2026-05-25）：每个 session 用独立 `TCPConnector`。同时将 `asyncio.TaskGroup` 改为 `asyncio.gather(return_exceptions=True)`。

## 32. 翻译语言映射源多次变迁 [管线运维]
| 阶段 | 方式 | 问题 |
|------|------|------|
| ~2026-05-24 | CJK 内容启发式 | 日语被错误跳过 |
| 2026-05-24 | 硬编码 frozenset | 加源要改两处代码 |
| 2026-05-25 | translate.yaml | yaml 和代码不同步 |
| **2026-05-25 (最终)** | **sources.json language 字段** | **单真相源** |

加新源只需在 `data/sources.json` 的条目中设 `language: "zh"/"en"/"ja"`，无需独立映射文件。

## 33. Agent 在简报输出中加注释 [管线运维]
**现象**：推送内容开头出现 `Orchestrator completed with status ok, push_id=noon. No deep analysis needed.`。
**修复**（2026-05-25 晚）：`sanity_check.py` 拦截器在推送前自动扫描 16 种禁语模式。Agent 层的冗长约束已移除。

## 34. 深度分析未走 render_deep_analysis.py 管道 [管线运维]
**现象**：晚间深度分析输出长文段落 + `---` 横线分隔。
**修复**：prompt 强调"必须通过管道传给 render_deep_analysis.py 格式化"，禁止添加 `---`。

## 35. 游戏分类误判 [管线运维]
**现象**：非游戏条目被分入 gaming（如"改变**游戏**规则"命中 GAME_KW，索尼音乐版权含"索尼"）。
**修复**：`curate_and_push.py` 加入 `_GAME_FALSE_POSITIVES` 和 `_is_sony_music`。

## 36. 科技分类误判 [管线运维]
**现象**：非科技内容被分入 tech（药监局整治网售减肥药→命中`网络`+`电商`）。
**修复**：POLITICS_KW 新增党内关键词（八项规定/党纪/纪委等），JUNK_KW 新增药监类关键词。

## 37. render_markdown.py 不读 title_cn/summary_cn [翻译管线]
**问题**：`ai_translate.py` 正确翻译写入 `title_cn`/`summary_cn`，但 `render_markdown.py` 的 `_format_item()` 只读 `item.get('title')` 忽略翻译字段。
**表现**：curated JSON 中有 `title_cn`（✅），但渲染 Markdown 显示原文（❌）。
**修复**：`title = _shorten(item.get('title_cn') or item.get('title') or '', 80)`，summary 同理。

## 38. ai_translate 与 render_markdown 文件读取优先级不一致 [翻译管线]
**问题**：每天 pipeline 生成两个文件：`curated_noon.json`（非日期版）和 `curated_noon_20260524.json`（日期版）。ai_translate 读非日期版（已有翻译→跳过），render 读日期版（无翻译→原文）。
**修复**：两者统一：优先读日期版，fallback 到非日期版。

## 39. ai_translate 内容启发式检测不可靠 [翻译管线-历史]
CJK 比率 < 50% 判断翻译需求：汉字占比高的日语标题（`茂木外相 イラン外相と電話会談` → CJK 77% → 跳过）；含英文专有名词的中文标题（CJK < 50% → 误标）。**最终方案**：按 `sources.json` 的 `language` 字段分类，放弃内容启发式。

## 40. render_markdown.py 故障模式
### 文件空/0 字节
**症状**：cron 找不到脚本，回退 LLM 渲染→格式跑偏。**修复**：从仓库恢复 `cp ~/TrendRadar/trendradar/scripts/render_markdown.py ~/.hermes/trendradar/scripts/`

### 日期格式不匹配
**症状**：`Curated file not found`。文件名 `%Y%m%d`（20260524），脚本用 `%Y-%m-%d`（2026-05-24）。**修复**：main() 区分 `today_display` 和 `today_file`。

### 数据结构假设错误
**症状**：`AttributeError: 'str' object has no attribute 'get'`。curated JSON 是 `{domain: [items], total: N}`，不是扁平 `{items: [...]}`。每个 item 的 `_heat` 是 dict 不是 int。

### cron prompt 脚本名不匹配
**症状**：cron 找不到脚本→回退 LLM。cron prompt 写死 `render_briefing.py` 但已改名 `render_markdown.py`。**修复**：单独更新 cron prompt。

## 41. 健康检查脚本维护陷阱 [已修复 2026-05-24]
- SKILL_DIR 路径过时（已从脚本移除）
- 导入检查使用旧式裸导入→改为全限定导入
- 新增脚本未加入检查列表
- 未导入 logging 致静默 NameError
- 子进程调用解释器不匹配→用管线 Python 跑所有子进程
- keywords.py 检查阈值不匹配 frozenset 结构
- Cron job ID 硬编码→重装后失步
- 维护脚本 runtests() 解释器不匹配+缺乏 PYTHONPATH+失败不 exit(1)

## 42. 烟雾测试维护
### 代码重构后测试未同步
重构删除了函数/类/变量，但测试仍引用旧 API。常见重构方向：CJK启发式→sources.json language字段；DB_PATH模块变量→Storage类。

### 模块缺少 import
`except sqlite3.OperationalError` 但未 `import sqlite3`。Python 在异常处理时才检查该名字。

### 运行时路径 ≠ 仓库路径
`Path(__file__).resolve().parent.parent / 'data'` 指向仓库路径，但运行时数据在 `~/.hermes/trendradar/data/`。始终用 `get_data_dir()`。

### ALTER TABLE 的 try/except 懒迁移反模式
每次 `record()` 都执行 `ALTER TABLE ADD COLUMN`，靠 `except sqlite3.OperationalError: pass` 吞掉"列已存在"错误。**修复**：用 `PRAGMA table_info` 先检查再 ALTER。

### 翻译管线：标题未翻译但摘要已翻译
DeepSeek API batch > 5 时模型翻译摘要但标题输出原文不变。**修复**：`BATCH_SIZE = 5`。假翻译的 `title_cn` 会让后续 ai_translate 跳过→需先清理：`if item.get('title_cn') == item.get('title'): item.pop('title_cn', None)`

## 43. 迁移幂等性漏洞
`migrate()` 只执行 `ver > current` 的迁移。当 `_migrations` 记录 v1 已应用但 `fingerprints` 表被外部删除，迁移引擎跳过重建。**修复**：新增 `repair_missing_tables()` 绕过版本检查直接重建缺失表。

## 44. API 连接问题诊断 [持续环境现象]
### DeepSeek openresty 流中断
`RemoteProtocolError: peer closed connection without sending complete message body`，HTTP 状态码 200（迷惑性）。DeepSeek 的 openresty/nginx 在 chunked transfer 中主动断连。非持续，突发式（0-4次/天）。自动重试通常恢复，但三次全挂也可能→cron 返回 stub response→半篇丢失。

### WeCom WebSocket 频繁断连
`[Wecom] WebSocket error: WeCom websocket closed` → 2s 后自动重连。间隔 12-20 分钟。自动重连始终成功。重连窗口（~2s）内的推送可能丢失。

### 排查流程
```
用户说"没收到推送"
├─ cron 日志有"send_message isn't available"？ → 没走 auto-delivery
├─ cron 日志显示"5/5 sent"？ → 比对时刻与 WS 断连是否重叠
├─ cron 日志是 stub response（0 chars）？ → DeepSeek openresty 断流
└─ cron 日志为空？ → cron 调度/Gateway 故障
```

## 45. 已验证修复脚本 (fix-recipes)
| 问题 | 检测 | 修复 |
|------|------|------|
| 短摘要 < 20 字 | 检查 curated JSON | 手动扩写到 30-60 字 |
| tech 板块过度集中 | ≥16 条 | MAX_PER_DOMAIN['tech'] 降至 5-10 |
| foreign_china 过少 | ≤2 条 | 扩充 _china_kw() 关键词 + _foreign_sources() 加源 |
| tirith 拦截 | `hermes config get` | `set security.tirith_enabled false` |
| Cron 技能名不匹配 | Skill not found | `cronjob action=update job_id=xxx skills=[...]` |

## 46. 性能瓶颈：TCP 连接池耗尽
**症状**：RSS 源 aiohttp 超时但 curl 正常。**案例**：`RSSHUB=12 + EXTERNAL=20 = 32 > TCPConnector(30)` → 6/38 超时。**修复**：`TCPConnector(limit) >= sum(所有Semaphore)`，留 20% 余量。

## 47. UTF-8 字节计数陷阱
### `_find_last` 的 `len()` vs `bytes` 混用
`len(text)` 返回字符数。中文 1 字符 = 3 bytes。`min(len(text), max_bytes)` 在中文场景下搜索窗口错误扩大 3 倍。
**修复**：先 `text.encode('utf-8')[:max_bytes]` 按字节截断→解码回安全字符边界→用字符位置做 `rfind`。

### `_split_overlong` 的迭代硬切
原始实现在 `else` 分支只一次硬切就 `break`，残留超大片段。**修复**：改为 `while` 循环持续硬切直到每个 piece ≤ MAX_BYTES。

## 48. 三级递降分片策略 [fragment_push.py]
按优先级尝试：① `\n\n`（段落边界）→ ② `。\n` 或 `。`（句子边界）→ ③ 硬切+迭代循环。硬切时保留 CONT_MARKER（`...(续)`），UTF-8 安全解码（逐字节回退最多 4 字节），熔断保护防止死循环。
