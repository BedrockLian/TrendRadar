# TrendRadar 已知陷阱全集

## Traps 1-16 (早期历史，存档略)

## Trap 17: Gateway 崩溃丢推送
cron 脚本可能报"发送成功"但消息实际没到 WeCom。排查推送丢失要先确认 Gateway 在推送时间点是否存活。

## Trap 18: Cron 技能名不匹配（精简后）
skills 列表引用了已重命名的 skill。`hermes cron list` 检查 skills 字段，逐条 `hermes skills list | grep <name>` 确认存在。

## Trap 19: tirith 安全扫描拦截中文命令
`tirith_enabled=true` 时 cron 内部命令会被中文内容拦截。`hermes config set security.tirith_enabled false` 后可恢复。

## Trap 20: NO_SLOT 跳过时段
`push_slot_detect` 有 ±10min 窗口。超窗返回 NO_SLOT。skill 已加"即使 NO_SLOT 也尝试推送"逻辑。

## Trap 21: render_markdown 跨板块间距异常
条目间用 `\n\n\n`（双空行），标题后用 `\n\n\n`。检查 `_generate_section()` 和 `_format_item()` 中的空行逻辑。

## Trap 22: Cron prompt 含旧技能名引用
cron prompt 独立于 skill 内容，修改 skill 后必须单独更新 cron prompt（`cronjob action=update prompt=...`）。

## Trap 23: Cron prompt 引用已删除的 pipeline 脚本
cron prompt 第5步引用 `render_briefing.py`（已删除为 `render_markdown.py`）。2026-05-24 修复: 同步更新 prompt。

## Trap 24: Skill 更新了脚本名但 cron prompt 没同步
cron prompt 独立于 skill 内容，必须单独更新。

## Trap 25: `references/` 目录在 workdir 不存在
skill 里 `cat references/xxx.md` 会失败。检查 `ls ~/.hermes/trendradar/references/` 非空。

## Trap 26: Cron prompt 引用已删除的辅助脚本
`blind_spot_audit.py` / `aggregate_monthly.py` 被引用但不存在。2026-05-24 创建补充。

## Trap 27: render_markdown.py 日期格式不匹配
curated 文件名为 `%Y%m%d`（无连字符），显示用 `%Y-%m-%d`。脚本中 `today_file` 和 `today_display` 两个变量必须区分。2026-05-24 修复。

## Trap 28: ~~ai_translate.py _is_cjk() 包含平假名/片假名~~
~~Hiragana 和 Katakana 被算作 CJK 字符导致日语不被翻译。2026-05-24 修复。~~
**2026-05-25: 已全部移除。** `_is_cjk` / `cjk_ratio` / `_has_japanese_kana` / `needs_translation` / `detect_source_lang` 整组函数删除。不再靠内容启发式。

## Trap 29: 翻译文件不同步
`ai_translate.py`（读非日期版，已有翻译→跳过）与 `render_markdown.py`（读日期版，无翻译→原文输出）读取不同文件。翻译存在却不可见。2026-05-24 修复: 统一先读日期版。

## Trap 30: source_lang 未追加到 tuple
`_load_and_scan` 中 `items_to_translate` 元组必须有第8个元素 `source_lang`（'English'/'Japanese'/None），否则 `_batch_translate_all` 索引越界。2026-05-24 修复。

## Trap 31: cron agent 用 LLM 重写简报
agent 没有 `send_message` 工具，旧 prompt 让它"返回 [SILENT]"，agent 自作主张用 LLM 重写内容（丢失翻译、格式跑偏）。2026-05-24 修复: prompt 改为直接输出脚本渲染的 BRIEFING。

## Trap 32: render_markdown 不看 title_cn
`_format_item` 只取 `item.get('title')`，完全忽略 `title_cn`/`summary_cn` 字段。翻译存在但渲染时用原文。2026-05-24 修复: 改为 `item.get('title_cn') or item.get('title')`。

## Trap 33: curated JSON 数据结构假设
curated 文件是 `{domain_key: [item_dict, ...]}` 结构，不是扁平列表。`_heat` 是 dict（键: appearances/heat_score/is_new 等），不是 int。脚本直接 `items = data.get('items', data)` 会拿到域名列表。

## Trap 34: _heat 字段类型
`_heat` 是 dict 不是 int。检查热度必须用 `item['_heat'].get('appearances', 0) >= 2` 或 `item['_heat'].get('heat_score', 0) >= 0.8`，不要用 `heat_value >= 2`。

## Trap 35: Fetch 异常被静默吞掉 → 产出 0 条
`push_prepare.py` 的 `run_curation()` 用 `ThreadPoolExecutor` 跑 `ensure_raw_exists()`。如果 `fetch_all()` 抛出异常，executor 的 `f1.result()` 只打 `log.info(f"fetch 失败: {e}")`，不创建 raw 缓存文件。后续 `raw = []` → `curate_all([])` → 所有板块 0 条。
**诊断**：`ls ~/.hermes/trendradar/cache/raw_{%Y%m%d}.json` 不存在 → fetch 失败。删除后重跑一次即可。TIMEOUT_SEC=6 可能偏紧。

## Trap 36: fetch_feeds 两个 session 共用 TCPConnector → Session is closed
`fetch_feeds.py` 的 `fetch_all()` 创建直连和代理两个 `aiohttp.ClientSession`，但共用同一个 `TCPConnector`。第一个 session 退出时 `__aexit__` 关闭了连接池，第二个 session 的所有请求全部抛出 `RuntimeError: Session is closed`。所有外媒源全失败，国内源正常。
**修复 (2026-05-25)**：直连和代理各用独立 `TCPConnector`。同时弃用 `asyncio.TaskGroup` 改用 `asyncio.gather(return_exceptions=True)` 避免 Python 3.14t free-threaded 模式下 TaskGroup 的取消传染问题。
**诊断**：查看 cron 输出中是否有 "Session is closed" 错误且全量失败但国内源正常。若有，升级 fetch_feeds.py 到独立 connector 版本。

## Trap 37: Cron agent 在简报前输出状态注释
cron prompt 要求 agent 输出 `briefing` 字段本身，但 agent 可能在简报前自行添加注释（如 "Orchestrator completed with status ok, push_id=noon. Outputting the briefing directly as per protocol."）。这些注释作为 final response 的一部分送达 WeCom。
**修复 (2026-05-25)**：cron prompt 第 3 步改成：
```
3. ⚠️ 输出简报：**只输出 JSON 中的 briefing 字段内容本身**，不加任何前缀/后缀/说明文字。
   禁止输出类似"Orchestrator completed with status ok"、"push_id=noon"、"Outputting the briefing"、"\n---\n## Response\n" 等任何注释/状态/分隔线。
   **只用 print(briefing) 一个字都不要多。**
```
**诊断**：查看 WeCom 收到的消息是否有 agent 添加的额外文字。cron output 中 `## Response` 行后的内容即为全部送达文本。

## Trap 38: 深度分析未走 render_deep_analysis.py 管道
晚间深度分析内容由 `delegate_task` 子 Agent 生成，cron prompt 要求它们经 `echo "$TEXT" | $PYTHON scripts/render_deep_analysis.py --topic "主题"` 格式化后作为独立 final response 输出。如果 agent 直接输出子 Agent 的原始文本（长段落 + `---` 横线分隔 + 缺 emoji 前缀），说明跳过了管道。

**修复 (2026-05-25)**：cron prompt 第 4 步明确要求：
```
各分析结果必须通过管道传给 render_deep_analysis.py 格式化
严禁在分析前后添加 `---` 横线、注释、状态说明
```

注意：`render_deep_analysis.py` 会自动清洗 `---`、代码块、表格，并自动匹配 emoji 前缀。

## Trap 39: 游戏分类误判 — 成语"改变游戏规则"和"索尼+音乐"上下文
`curate_and_push.py` 的 GAME_KW 包含 `游戏` 和 `索尼` 等常见中文字。非游戏内容中：
- "改变**游戏**规则"（paradigm-shifting 的惯用语）→ 命中 `游戏` → 误入 gaming
- "**索尼**音乐版权"（Sony Music，不是 PlayStation）→ 命中 `索尼` → 误入 gaming

分类代码先检查 game、再检查 junk/safety/politics/tech/economy，所以 game 关键词优先匹配。

**修复 (2026-05-25)**：
- `curate_and_push.py` 加入 `_GAME_FALSE_POSITIVES = frozenset({'改变游戏规则'})` 排除成语
- 加入 `_is_sony_music` lambda 排除"索尼+音乐"的非游戏上下文
- 分类逻辑改为：`has_keyword_match(text, 'game', KW['game']) and not has_keyword_match(text, 'game', _GAME_FALSE_POSITIVES) and not (_is_sony_music(text) and not any(sp in plat for sp in GAME_SRC))`

## Trap 40: 科技分类误判 — 缺少政治/药监关键词
非科技条目（药监局公告、党内通报）因包含 `网络`/`电商`/`数据` 等 TECH_KW 词被误入 tech 板块：
- 药监局整治网售减肥药 → `处方药网络零售`含 `网络`+`电商`
- 八项规定查处通报 → `公布数据`含 `数据`

分类代码先检查 game/junk/safety/politics，再走 tech。POLITICS_KW 缺少中文党内关键词、JUNK_KW 缺少药监类关键词 → 未命中前4层，走 tech 时命中。

**修复 (2026-05-25)**：
- `keywords.py` 的 POLITICS_KW 新增：`八项规定`、`党纪`、`政务处分`、`纪委`、`中央纪委`、`监委`、`反腐`、`通报`、`查处`
- `keywords.py` 的 JUNK_KW 新增：`减肥药`、`处方药`、`药监局`、`药品监管`
- 这些关键字确保政治/药监类文章在 tech 判断前即被分流到 headline 或 junk。
