---
name: news-secretary
slug: news-secretary
version: 6.21.0
description: 聚合多RSS源+博客，推送Markdown简报至企业微信。编排器一键管线 + 晚间Pro深度分析。
author: Hermes Agent
metadata:
  hermes:
    tags: [news, trend, RSS, wecom]
    delivery: wecom
    push_schedule: { merged: "0 9,12,21 * * *" }
    companion_skills: [self-healing, report-generator, system-config]
---

## 触发
cron `0 9,12,21 * * *` (早30/午30/晚20, 日上限80)。晚间追加 3×Pro 深度分析。

## 管线

**curated JSON 字段跳过陷阱**：`batch_fetch.py` `load_items()` 遍历 curated JSON 时必须跳过所有非 domain 元数据字段。当前跳过：`curated_at, push_id, total, run_id, run_id_marker, truncated`。curated JSON schema 新增字段时（如 `truncated`）必须同步更新此列表，否则 `for item in True` 报 `TypeError: 'bool' object is not iterable`。

```
pipeline_orchestrator.py（v2.10.0 — 一键7阶段 + 层级多样性）
  ① push_slot_detect → ② push_prepare(fetch+curate) → ③ 并行(ai_translate ∥ batch_fetch)
  → ④ render_markdown → ⑤ fragment_push（UTF-8 字节计数分片） → ⑥ record_fingerprints（Storage 统一接入）
  → 输出 JSON: {status, fragments, briefing, stats, needs_deep_analysis}
```

LLM 运行编排器，解析 `fragments` 数组投递。编排器不可用时走 cron prompt 中的 fallback 手动管线。自动特性详见 `../../references/PIPELINE.md`。

简报由 `render_markdown.py` 纯脚本生成，Agent 不修改内容。cron prompt 修改后需同步更新。

## 简报投递纪律（Agent 输出约束）

Agent 在 final response 中输出简报时，必须遵守以下硬约束：

1. **零附加文本 + 分片投递** — 遍历 `fragments` 数组，对每个分片调用 `send_message(target="wecom", message=fragment)` 逐条投递。**禁止输出 `briefing` 字段作为 final response**。每条消息直接从分片内容开始（如 `### Hermes日报 ·` 或 `### 📰 头条`），不得在前面添加状态描述行，也不得在后面追加总结。

2. **URL 透传** — 链接中的 URL 必须原样输出。Agent 重新格式化/换行/重排时容易在 URL 中插入空格（如 `pcgamer.com` → `pc gamer.com`），导致 Markdown 连接断裂。`render_markdown.py` 已加入防御性空格清洗，但 agent 仍应避免触碰 URL。

3. **逐字逐句透传** — 不得对简报内容做任何 AI 润色/重写/重组。简报已经由脚本可靠生成，任何 AI 二次处理只会引入格式错误或虚构内容。

4. **sanity_check 兜底** — `sanity_check.py` 在发布前自动剥离编排器前言（中英文 13 种模式），但 agent 不应依赖此兜底。零附加文本是第一道防线。

### Google News RSS 延时处理

Google News RSS（如 `news.google.com/rss/search?q=...`）返回的文章通常滞后 2-3 天。为此：

- **`freshness_days`** 设为 3（`sources.json` 源级字段），让老化过滤窗口容纳 3 天内的文章
- **`RECENCY_HOURS_LOW = 72`**（`config/scoring.py`），评分时效分档中末档从 24h 延长至 72h，确保 2-3 天前的文章仍获得 recency=1
- 注意：即使 `freshness_days=3`，如果没有 `RECENCY_HOURS_LOW` 同步放大，文章会通过新鲜度过滤但死在评分关（`recency=0` 不通过）

**适用场景**：AP News、Reuters、BBC（已转 Google News）、WSJ 世界新闻等无法获取实时 RSS 的源。

### 合并源名解析（2026-05-31）

`fetch_feeds.py` 的 `_dedup()` 会合并相同标题的文章，生成复合 `source_platform`（如 `南华早报+SCMP 中国`）。`classifier.py` 的 `classify_items()` 中 `ALL_SRC_CAT.get(source_platform)` 查不到合并名 → 分类失败 → `_likely_domain='other'` → 永远不出现在简报中。

**修复**（`classifier.py`）：fallback 分支中 `ALL_SRC_CAT.get()` 未命中时，对合并名按 `+` 切分取第一个源名重新查询：
```python
if not src_cat and '+' in (item.get('source_platform', '') or ''):
    src_cat = ALL_SRC_CAT.get(
        item['source_platform'].split('+')[0].strip(), '')
```

**排查**：某个源有文章被抓取（`raw_{date}.json` 中有条目），但 `_likely_domain='other'`，且 `source_platform` 含 `+` 号 → 合并名分类失败。

## 源级分类覆盖（_preclassify）

`fetch_feeds.py` 的 `_preclassify()` 将已抓取文章分配到 5 个域（top_headlines/foreign_china/tech/economy/gaming），供 LLM 精选。

**关键词误匹配陷阱**：关键词匹配优先于源 category 兜底。商业/政治源（如日经亚洲）的文章含 AI/chip/game 等词时，被错误分到 tech/gaming 域 → LLM 精选阶段被其他专业源挤掉 → 文章永远不在简报中。

**category fallback 缺失陷阱**：`_preclassify` 的 fallback 分支只处理了 `game`/`tech`/`economy`/`news` 类别。`foreign_china` 类别源（BBC 世界/中国、NPR 国际、路透社·国际）掉到 `else` → `other` → LLM 精选时排除。修复：`elif cat in ('news', 'foreign_china'): domain = 'top_headlines'`。

**短关键词误触陷阱**：2 字符关键词（FF/AI/AR）通过 Aho-Corasick 子串匹配时，误触任何包含这些字母组合的英文单词（FF→affairs/effect, AI→affairs/main, AR→article/market）。`config/keywords.py` 中已移除 FF/AI/AR。长关键词（GPU/CPU/LLM/3 字+）误触概率低，保留。

**修复**：`fetch_feeds.py` `_preclassify()` 中 `SOURCE_DOMAIN_OVERRIDE` 字典可将特定源固定分配到正确的域（不参与关键词匹配）：
```python
SOURCE_DOMAIN_OVERRIDE = {
    '日经亚洲': 'foreign_china',  # 亚洲商业政治 → 外媒看华
}
```

发现平台不在简报中时，检查：
1. `fetch_all` 后该源文章是否被抓取（return 的 items 列表）
2. `_likely_domain` 是否正确
3. 若关键词误匹配，加 `SOURCE_DOMAIN_OVERRIDE` 条目

## 翻译管线（关键！）

外语文章翻译由 `ai_translate.py` 处理，规则：

1. **按来源定语言（来自 config/sources.json）** — `get_source_lang()` 读取 `get_config_dir() / 'sources.json'`（`TRENDRADAR_HOME/config/`）每个源的 `language` + `platform` + `name` 字段。单真相源：加新源设好 `language` 即可，不再维护独立的映射文件。
2. **文件同步** — ai_translate 和 render_markdown 必须读同一文件（今日日期版 → 最新日期版 → 通用版，三层回退）。陷阱 2026-05-26: 只有两层回退时翻译写入通用版但渲染读日期版。
3. **render 优先 title_cn** — `render_markdown.py` `_format_item` 取 `title_cn`/`summary_cn`，不回落到原始 title/summary。
4. **BATCH_SIZE = 10** — `config/translation.py` 中 `TRANSLATE_BATCH_SIZE` 默认 10。若未来换模型需重新验证。

5. **日→中翻译模型要求** ⚠️ — `deepseek-chat` 处理日文→中文批量翻译时**必然返回原文不变**（`title_cn == title`），不报错不告警。`deepseek-v4-flash` 可正常翻译日文（仍有抖动，偶尔返回原文）。**必须设置 `DEEPSEEK_MODEL=deepseek-v4-flash`**，在 gateway override.conf 中注入环境变量。不可用 deepseek-chat 做日文翻译。

6. **假翻译自动拦截** — `process_curated()` 写入 title_cn/summary_cn 前检测 `title_cn.strip() == title.strip()`，若相等则丢弃不保存。防止模型返回原文被当成&#8203;`已翻译`&#8203;，导致后续运行时 `_load_and_scan` 跳过该条目。拦截后条目保持在待翻译队列，下次运行自动重试。

    **⚠️ 日文短标题误拦截陷阱**（2026-05-31）：`deepseek-v4-flash` 对短日文标题经常直接返回原文（认为标题`自解释`），虽然摘要成功翻译。拦截器会丢弃 `title_cn`，导致日文标题在简报中保留原文。修复：`_TRANSLATE_TEMPLATE` 中增加规则 #4 强制要求翻译所有日文标题。排查：检查 `curated_{slot}.json` 中该条目 `title_cn` 为空而 `summary_cn` 非空。 — `process_curated()` 写入 title_cn/summary_cn 前检测 `title_cn.strip() == title.strip()`，若相等则丢弃不保存。防止模型返回原文被当成"已翻译"，导致后续运行时 `_load_and_scan` 跳过该条目。拦截后条目保持在待翻译队列，下次运行自动重试。
6. **中文短摘要 AI 扩写**（v6.10.0） — `ai_translate.py` 新增中文条目短摘要扩写通道。对中文源（source_lang 为 None）中原始摘要 `<50 字` 的条目，自动用 AI 扩写成 50-80 字的完整信息句。扩写 prompt 在 `_EXPAND_TEMPLATE` 中，约束：不虚构事实、基于标题上下文展开、保持新闻风格。2026-05-27 用户反馈摘要过短后添加，虎嗅/钛媒体短条目从 23/26 字扩至 37/51 字。

    **⚠️ Expand prompt 歧义陷阱**（2026-06-01）：`_EXPAND_TEMPLATE` 原措辞 "Rewrite each item's TITLE and SUMMARY into a complete sentence"（单数）会导致 AI 将 title+summary 合并为一行输出。`_write_anchored` 期望每条目 2 行但只收到 1 行 → summary = `[扩写失败]`。修复：改为 "into TWO separate sentences, Do NOT merge them"。排查：发现 `summary_cn = "[扩写失败]"` 但 `title_cn` 正确时（而非两者都错），即为此问题。
7. **摘要长度与 render 联动** — `render_markdown.py` 的 `_shorten(max_len=80)` 控制最终展示长度（参见输出规范第5条）。英文/日文翻译产出通常 40-70 字，render 基本保留；中文条目从 `summary` 字段取前 80 字（旧 50 字截断的改进，但 300 字长摘要仍会被截）。扩写通道只覆盖 `<50 字` 的极短条目。用户反馈摘要过短时，需同步检查两个配置点：`ai_translate.py` 的扩写逻辑和 `render_markdown.py` 的 `max_len`。

    **⚠️ 扩写/翻译批处理响应乱序陷阱**（2026-05-31，已修复）：`batch_expand()` / `batch_translate()` 将一组条目发送给 AI。旧版 `_parse_line_pairs()` 按返回顺序配对，AI 乱序时条目串位。
    - 条目 A 收到了条目 B 的扩写/翻译内容（标题谈铜价、摘要讲 DeepSeek）
    - 条目 B 因无对应响应剩余，fallback 为 `[扩写失败]`
    - **两个条目的数据都坏了**，只看一个看不出问题

    **修复（2026-05-31）**：`common.py` 中 `_parse_line_pairs()` 升级为双策略解析：
    1. **Index-anchored（优先）** — 检测 `Item N:` 标记按索引映射，乱序/漏项不影响其他条目
    2. **Sequential（fallback）** — 旧版顺序配对，向后兼容

    对应改动：prompt 要求 AI 输出 `Item N:` 标记，request 格式统一，新运行自动受益。

    排查方法（旧数据）：发现 `summary_cn = "[扩写失败]"` 时，**必须**同时检查同一批次中其他条目的 `summary_cn` 是否持有不属于它的内容。

    修复流程（仅旧数据需要）：
    ```
    ① 清除所有受影响条目的 title_cn/summary_cn（同时清掉失败的 marker 和串位的正确内容）
    ② 重新运行 python3 scripts/ai_translate.py --push-id {slot}
    ③ 重新 python3 scripts/render_markdown.py --push-id {slot}
    ④ archive_resend.py 补推
    ```

    预防：单条扩写不受影响（批次仅 1 个 item），多条时风险随 batch 大小增加。当前 `TRANSLATE_BATCH_SIZE=10`，如果频繁出现可考虑降低。
8. **cron context 投递机制：fragment delivery** — Pipeline 产出 JSON，包含 `fragments` 数组（分片后的 WeCom 安全消息）。Agent 必须遍历 `fragments` 数组，对每个分片调用 `send_message(target="wecom", message=fragment)` 逐条投递。**不能输出 `briefing` 字段作为 final response**——整篇简报超出 WeCom 4KB 限制，会被静默截断。`send_message` 工具通过 `messaging` toolset 可用。
9. **items_to_translate tuple** — `needs_title`/`needs_summary` 由 `bool(source_lang)` 驱动（非 None 就翻译），第8个元素 `source_lang` (`'English'`/`'Japanese'`/`None`) 必须存在。来源语言由 `data/sources.json` 每个源的 `language` 字段决定（`_scan()` 提取 `en`/`ja` 源的 `platform`+`name` 做子串匹配）。`translate.yaml` 已淘汰（2026-05-25）。旧 CJK 启发式函数（`_is_cjk`/`cjk_ratio`/`needs_translation`/`detect_source_lang`）已于 2026-05-25 全部移除。
10. **TITLE:/SUMMARY: 前缀残留陷阱** — DeepSeek 翻译/扩写返回可能包含 `TITLE: ` / `SUMMARY: ` 前缀（模仿输入格式）。`_parse_line_pairs()` 有两种处理策略：
    - **写入层**（2026-05 修复）：`process_curated()` 在写入 title_cn/summary_cn 前 strip 这些前缀。
    - **解析层**（2026-06-01 修复）：`_parse_line_pairs()` 原代码第 261 行将 `TITLE:`/`SUMMARY:` 开头的整行跳过（认为属于"注释行"），AI 返回此类前缀时标题/摘要内容完全丢失 → `[扩写失败]`。修复：改为 strip 前缀后保留内容行，不跳过。排查：原始数据 `title_cn`/`summary_cn` 为 `[扩写失败]`，且 curated 文件无翻译/扩写历史记录 → 检查 `_parse_line_pairs` 对 `TITLE:`/`SUMMARY:` 的处理。
11. **手动运行 ai_translate.py 需显式传 DEEPSEEK_API_KEY** — 脚本从 `TRENDRADAR_HOME/.env`（`~/.hermes/trendradar/.env`）读取 API key，但实际 key 在 `~/.hermes/.env`。手动运行时需 `export DEEPSEEK_API_KEY=*** '^DEEPSEEK_API_KEY=*** ~/.hermes/.env | cut -d= -f2- | tr -d '\\\"')`，或设置 `TRENDRADAR_ENV=~/.hermes/.env`。

12. **被地理封锁的 RSS 源 → Google News RSS 替代** — 某些源（如 BBC 的 Akamai CDN 对中国 IP 做 SNI 阻断、Cloudflare 托管站点）直连和代理均不可达。可用 Google News RSS 代替直接源：
    ```
    https://news.google.com/rss/search?q=site:bbc.com           # BBC 世界
    https://news.google.com/rss/search?q=site:bbc.com+china     # BBC 中国
    https://news.google.com/rss/search?q=source:Reuters         # Reuters
    https://news.google.com/rss/search?q=source:Associated+Press # AP News
    ```
    Google News RSS 各返回 100 条，XML 格式标准。同 `needs_proxy=True` 走代理。
    
    **判断方法**：`curl -v --proxy http://127.0.0.1:7890 <RSS_URL>` 返回 TLS `unexpected eof` 或 HTTP 502 → 大概率 CDN 地理封锁。用 `curl -s --proxy http://127.0.0.1:7890 "https://dns.google/resolve?name=<domain>&type=A"` 解析 IP 确认归属地。`www.bbc.com` 能通但 `feeds.bbci.co.uk` 不通 → Akamai CDN 对不同子域名应用不同策略。

## 晚间深度分析

仅 evening。`delegate_task` 并行 3 个 Pro 子 Agent（趋势/跨域/风险），各基于当日 curated JSON（不联网）。
输出经 `render_deep_analysis.py --topic "主题"` 管道格式化后作为 final response 逐篇投递（系统自动推送 WeCom）。
完整协议见 `../../references/PIPELINE.md`（深度分析格式化章节）。

**重要：每条分析作为独立 final response 分别输出，不得与简报正文拼接在一起。** 简报走 step 3, 分析走 step 4, 互不干扰。

**格式化铁律**：每个 delegate_task 返回的分析文本必须通过 `render_deep_analysis.py` 管道格式化——`echo "$ANALYSIS_TEXT" | $PYTHON scripts/render_deep_analysis.py --topic "主题" --push-id evening --context`。禁止直接输出原始分析文本。格式化后的输出包含 `🔬 **主题**` 标题和 `📌 相关回顾` 部分，这是正确的格式。

**3 条分开投递**：趋势、跨域、风险各作为一条独立 final response 分别输出，不要合并成一条。

**⚠️ 格式铁律 — 用户对此容忍度极低**：深度分析必须使用标准 pipe 表格 `|` 排版，模板见 `references/deep-analysis-wecom-format.md`。用户曾多次纠正 "排版，注意排版"——纯文本段落式分析被拒绝。每次生成后必须自检管道表格是否完整。

**WeCom 格式规范（v3.0）**：深度分析使用标准 pipe 表格 `|` 排版，格式模板见 `references/deep-analysis-wecom-format.md`。三条规则：
1. 趋势方向：顶部数据卡片表格 + 2~3段分析 + 总结句
2. 跨域交叉：关联表格 + 2个深层交叉点剖析
3. 风险预警：风险矩阵表格（🔴🟡🟢三色等级 + 触发条件 + 影响面）+ 综合判断引用

**子 Agent 沙箱陷阱**：`delegate_task` 子 Agent 在 cron 上下文中有独立的进程上下文，其 `terminal`/`read_file` 等工具**无法读取父 session 的文件系统**。文件路径传递（如 `cat /path/to/report.md`）会返回空。子 Agent 必须通过 inline 文本传递内容——将分析文本放在 prompt 的 `context` 字段中，而不是让子 Agent 自己去读文件。详见 `../../references/PIPELINE.md`。

## 交付验证（新增！）

**Pipeline 返回 `status=ok` 不等于用户收到了简报。** 已知静默失败模式：

1. **Gateway WebSocket 断连**：`[Wecom] WebSocket error` → 自动重连通常成功，但若刚好在 final response 投递窗口断开，消息丢失且无错误日志
2. **send_message 投递失败**：cron agent 对每个分片调用 `send_message()` 投递。如果 Gateway 在处理投递时崩溃，部分分片可能丢失而 pipeline 依旧报告 ok。cron job 必须启用 `messaging` toolset 才能使用 `send_message`。
3. **DeepSeek API 流中断**：`RemoteProtocolError: peer closed connection without sending complete message body` → 只返回 stub response，半篇丢失

**投递后验证**：\n- Cron 结束后，检查 delivery_watchdog 是否会捕获失败\n- 用户反馈"没收到"时：优先走 `archive_resend.py`（见下一节），不要查 cron 输出日志。——cron 输出文件（`cron/output/`）混有 pipeline 日志和 skill 上下文，读到源名容易产生"有这个源就有内容"的虚假印象，是幻觉高危来源。**存档（`archive/YYYY-MM-DD/{slot}.md`）是纯 markdown，是你唯一应该查的数据源。**

### Agent 输出格式违规（2026-05-29 案例 + 2026-06-01 修复）

2026-05-29 晚间 cron agent 输出 briefing 前添加了"好消息——所有三个深度分析均已完成格式化"前缀，还把 3 篇深度分析混入同一条 final response。auto-delivery 把格式异常的内容推到 WeCom，用户没收到可读简报，但系统标记 last_status=ok + delivery_error=null（静默失败）。

2026-06-01 早报再次出现：cron prompt 第3步指引 Agent"输出 `briefing` 字段"，Agent 将 8KB 简报作为一条消息输出 → WeCom 静默截断尾部（4KB 限制），用户只收到前半篇。Pipeline 的 fragment_push.py 实际已产出 6 片，但 Agent 未遍历 fragments 数组。

**两次修复**：
- `sanity_check.py` 作为发布前拦截器检测违规前缀（"好消息""所有三个""Pipeline returned""编排器执行完成"等）或内容不以 "### Hermes日报"/"🔬" 开头时，自动 fallback
- **2026-06-01 根因修复**：`gen_cron_prompt.py` 将"output briefing"改为"遍历 fragments 数组，用 send_message 逐条投递"。cron job 启用 `messaging` toolset 提供 send_message 工具。

**看门狗时序**：原 22:00 才查，已改为 0,30 10,14,21,22——21:30 加一班，30 分钟内捕获。

**诊断线索**：last_status=ok 但用户说没收到 → 查 cron/output/90a2866775df/ 中 agent 的 final response 是否包含违规前缀。

**快速补发**：`archive_resend.py --date YYYY-MM-DD --slot evening`（自 v2 起接管所有补发，自动分片投递。见 `references/archive-resend-mechanism.md`）

**❌ 不要用 `cat archive | hermes send`** —— 整文件推送超过 WeCom 4KB 限制时尾部板块会被静默截断（不报错不告警），见参考文档中的关键警告。

## 手动补发

详见 `references/archive-resend-mechanism.md`。

## 投递水印机制

详见 `../../references/DELIVERY-WATERMARK.md`。

## 输出规范

简报和深度分析由纯脚本生成，Agent 只做透传。`sanity_check.py` 发布前自动剥离编排器前言、执行禁语/死链/敏感词扫描、检测 agent 输出格式并自动 fallback。拦截器维护详见 `references/sanity-check-maintenance.md`。

1. **分片投递简报** — 从 JSON 中取 `fragments` 数组，每个分片用 `send_message(target="wecom", message=fragment)` 分别投递。**绝不输出 `briefing` 字段**（整篇超出 WeCom 4KB 限制会被静默截断）。`sanity_check.py` 自动拦截 "As an AI language model" / "Here is your report" 等禁语。
2. **链接格式** — `[【媒体名】](url)`，不加"查看原文"前缀。URL 中包含空格或全角空格时，`render_markdown.py` 会在渲染前自动清除（2026-05-28 修复：`url.replace(' ', '').replace('　', '')`，防止 Agent 输出时在 URL 中插入空格导致链接断裂）。

    **2026-05-31 升级**：部分 RSS 源（如 Sixth Tone）的 URL 路径本身含未编码空格（`/He Quit Baidu. But First...`），渲染层清理不够，Markdown 链接仍然断裂。已在 `fetch_feeds.py` `_parse_rss()` 的 RSS 解析层和 `render_markdown.py` `_format_item()` 的渲染层双层添加 `urllib.parse.quote` 路径编码。排查方法：渲染后的 `[【源名】](url)` 中 url 被空格截断 → 查 raw JSON 中该条目的 url 字段是否含空格。
3. **深度分析独立投递** — 晚间 3 条深度分析各自作为单独 final response 输出。
4. **空行铁律** — 板块标题后 `\\n\\n\\n`，条目间 `\\n\\n\\n`，全文无 `---`/`***` 横线。
5. **摘要约束** — 每条摘要 80 字内且为逻辑自洽的完整句子，不允许断句（不能被 `…` 截断成半截话）。由 `render_markdown.py` 的 `_shorten(max_len=80)` 保证，无句号时优先找逗号边界，最后兜底干净截断不加 `…`。
6. **格式契约** — 完整规则在 `render_markdown.py` 模块 docstring 中，修改格式必须先更新契约。

## 质量自愈（吸收自 performance-optimizer）

### 质量评分协议
评分 >85 达标。加分: 空摘要<5%(+15)、重复<3%(+10)、头条命中≥60%(+10)、每板块≥3条(+10)、外媒满14条(+5)、分布均匀(+10)。扣分: 空摘要≥20%(-15)、板块为0(-20)、单源≥50%(-15)（curate_all() 已有全局 30%/slot 硬上限）。集中度预警(≥40%) 标注但不建议稀释。

杠杆: MIN_SCORE(5-8,±1)、MAX_PER_DOMAIN(±2)、blog recency(1-3,±1)、关键词(±5词)、白名单(增/删)。

交互: 评分<85 → 列出扣分项+建议 → 问修哪个(编号/all/跳过)。单参数调整，3轮无改善→收敛，跳过 7 天恢复。"全修"模式并行执行全部建议。

### 推送偏好协议
基准: `settings.py` 的 `BRIEFING_RATIO`（早30/午30/晚20）和 `DAILY_LIMIT=80`。5 板块: top_headlines/foreign_china/tech/economy/gaming。

偏差检测: 总量±30%→偏差；板块连续多天<3条→饿死；同源连续首位→垄断；单源≥40%→来源集中。交互: 列出偏差+选项 → 问"怎么调"。

已验证修复脚本: `references/fix-recipes.md`（短摘要扩写、tech 上限、foreign_china 扩充、tirith 关闭、cron 技能名匹配）。

### 域-源匹配加分（2026-05-31 新增）

`scorer.py` `score_item()` 中新增**域-源匹配加分**机制，替代旧的 `_econ_boost` 特殊逻辑：

- **旧逻辑**：`_econ_boost` 给 `category=news` 的源（界面/澎湃/南华早报等）在经济域无条件 +1。结果：新闻源在经济/科技域反而比 Bloomberg/FT 等专业源分高。
- **新逻辑**：源分类匹配当前域才 +1。
  - `tech` 源在科技域 +1，`economy` 源在经济域 +1
  - `news` 源只在头条域 +1，`game` 源只在游戏域 +1
  - 跨界无加成

映射关系：
```
domain_to_cat = {
    'top_headlines': 'news',
    'tech': 'tech',
    'economy': 'economy',
    'gaming': 'game',
    'foreign_china': 'foreign_china',
}
```

源分类通过 `_all_source_category()`（从 `sources.json` category 字段读取）按源名匹配。

### 跨域优先级降级（2026-05-31）

`_get_source_priority(platform, domain)` 新增 domain 参数：当源分类与当前域不匹配时（如 tech 源的文章因关键词匹配进入头条域），强制返回 P2（末尾/仅标题）。防止跨界源挤占本域 P0 源的位置。

```python
domain_map = {'top_headlines': 'news', 'tech': 'tech',
              'economy': 'economy', 'gaming': 'game',
              'foreign_china': 'foreign_china'}
if domain_map.get(domain, '') != s.get('category', ''):
    return 2  # 跨域强制 P2
```

**排查**：头条出现大量 tech/economy 源文章 → `_get_source_priority()` 未传 domain 参数或无跨域检测。

### 优先级排版系统（P0/P1/P2 — 2026-05-31 新增）

`scorer.py` + `render_markdown.py` 联合实现三级优先级排版，源级配置（`sources.json` `priority` 字段）：

- **P0（priority=0）**：首位/全文摘要（80字）。定调源：AP News, Reuters, Bloomberg, FT, MIT Tech Review, Nikkei Asia 等。
- **P1（priority=1）**：次位/精简摘要（40字）。立场补充：NYT·世界, Al Jazeera, Science News, Ars Technica 等。
- **P2（priority=2）**：末尾/仅标题+链接。查漏补缺：联合早报, 界面, PC Gamer, TechCrunch 等。

**排序逻辑**：`curate_domain()` 和 `score_headlines()` 的 sort key 改为：
```
key = (priority, -score, -heat)
```
P0 源文章优先填充配额，P1 补充，P2 仅当仍有空位时入选。

**配额**（2026-05-31 调整）：
- 头条: **8**（覆盖全球大事件）
- 科学/技术: 7（技术突破+AI）
- 经济: **5**（只看市场实质影响）
- 游戏: **5**（核心爆料+深度）
- 国际/外媒看华: 5（侧重地缘政治）

总量 30 条不变。

**渲染差异**（`render_markdown.py` `_format_item()`）：
- P0: 标题 + 摘要(80字) + 链接
- P1: 标题 + 摘要(40字) + 链接
- P2: 标题 + 链接（无摘要）

**配置点**：每个源在 `sources.json` 中新增 `priority` 整数字段。新增源时需同步设置。

### 层级多样性保护

`scorer.py` 的 `curate_domain()` 自 v6.17.0 起新增 **TIER_DIVERSITY_MIN=1** 机制：

- 每个域精选后，若所有入选条目都来自高权威源（authority≥3），自动将**得分最低的高权威条目**替换为候选池中最好的**非高权威条目**
- 确保中低权威源（联合早报、爱范儿、虎嗅、机核等）在竞争中有至少 1 个槽位的保底机会
- 配置点：`config/domains.py` 中 `TIER_DIVERSITY_MIN`（0=关闭）、`HIGH_AUTHORITY_THRESHOLD`（默认 3）
- 与同源多样性惩罚（`MAX_SAME_SOURCE=2`）互补——一个防单源垄断，一个防层级垄断

**2026-05-31 硬上限增强**：旧版 `curate_domain()` 对超限条目仅降权不删除，高分源仍然霸榜。新增**硬上限**——排序后遍历，同源超过 `MAX_SAME_SOURCE` 的直接丢弃（最低分优先）。效果：界面/澎湃在头条域最多各 2 条，剩余席位分给其他源。

**score_headlines() 补丁**（2026-05-31）：头条域不走 `curate_domain()`，硬上限最初漏了头条。已在 `score_headlines()` 末尾添加同源硬上限逻辑，与 `curate_domain()` 一致。

**⚠️ `BRIEFING_RATIO` 误改陷阱**：`config/domains.py` 中 `BRIEFING_RATIO` 和 `MAX_PER_DOMAIN` 在同一个文件。调整 `MAX_PER_DOMAIN` 配额时容易顺手改到 `BRIEFING_RATIO`。后者控制 per-slot 截断上限（evening=20），前者控制精选阶段各域条目数。2026-05-31 案例：MAX_PER_DOMAIN 调整时 `BRIEFING_RATIO['evening']` 被误改为 30，导致晚报没有截断（30→20），用户反馈\"晚报太多条\"。

**排查方法**：简报总条数异常（晚报显示 30 条而非 15-20 条）→ 查 `domains.py` 中 `BRIEFING_RATIO['evening']` 是否为 20。

**配套调整**（2026-05-31）：
- 联合早报·中国/国际: authority 1→2，The Verge·游戏: 1→2（提升至合理权重）
- BBC 科学环境: 3→2，NHK 政治: 3→2，Korea Herald: 3→2（降低高密度源天花板）
- `MAX_SAME_SOURCE`: 3→**2**（同源超过 2 条即减半）
- `MAX_SOURCE_PCT`: 30%→**25%**（单源硬上限收紧）
- `BRIEFING_RATIO`: evening 20→**30**（早中晚统一 30 条）

## 运行时
```bash
export PYTHON=/usr/local/bin/python3.14t PYTHONPATH=/home/asus/.hermes PYTHON_GIL=0
```

**Cron job toolset 要求**：日报推送 cron job 的 `enabled_toolsets` 必须包含 `messaging`（提供 `send_message` 工具用于分片投递）。当前配置：`["terminal", "web", "delegation", "messaging"]`。缺 `messaging` 时 Agent 无法遍历 fragments 分别投递，会退化为输出整篇 briefing 导致 WeCom 截断。

**双副本同步要点**：scripts/ 目录修改后需同步到两个位置：(1) /home/asus/TrendRadar/ — 工作副本，推 GitHub；(2) ~/.hermes/trendradar/ — cron 运行时副本（TRENDRADAR_HOME）。遗忘同步会导致 cron 跑旧代码。

**config/ scripts/ symlink 陷阱**：`~/.hermes/trendradar/`（外层）的 `config/` 和 `scripts/` 是 symlink 指向 `trendradar/config/` 和 `trendradar/scripts/`（内层）。2026-05-29 清理 root 级重复目录后，这两条 symlink 若丢失，cron 所有阶段会静默失败（sources.json/timeline.yaml 找不到）。症状是 `pipeline_orchestrator.py` 在 push_prepare 阶段报 `FATAL: Cannot load sources.json`。修复：`cd ~/.hermes/trendradar && ln -sf trendradar/config config && ln -sf trendradar/scripts scripts`。

## 并发抓取参数

当前 fetch_feeds.py 配置（43 源验证有效）：

| 参数 | 值 | 说明 |
|------|:----:|------|
| `EXTERNAL_CONCURRENT` | 43 | 全源并行（匹配源总数） |
| `TCPConnector limit` | 43 | 连接池上限 = 源数 |
| `limit_per_host` | 0 | 不限制单域（每源独立域名） |
| `force_close` | True | 用完即关快速回收 |
| `Parse pool workers` | 24 | RSS 解析线程池 |
| `FETCH_RETRIES` | 1 | 失败直接跳过（源更可靠） |
| `TIMEOUT_SEC` | 8 | 单次请求超时 |
| `batch_fetch CONCURRENCY` | 20 | 全文抓取并发 |

fetch 耗时约 12-14s/43 源（2026-05-31 实测）。源数增减时 `EXTERNAL_CONCURRENT` 和 `TCPConnector limit` 应同步设为源总数。

## 关键参考

> 文档已于 2026-05-27 从 41 份合并为 9 份。完整映射见 `../../references/INDEX.md`。

| 文件 | 何时读 |
|------|--------|
| `../../references/ARCHITECTURE.md` | 系统架构全貌（分类/关键词/渲染/迁移/体检/API模式） |
| `../../references/PIPELINE.md` | 管线流程 + 性能瓶颈 + 简报/深度分析格式规范 |
| `../../references/SETUP.md` | 代理配置/RSSHub/Cron运维/迁移回滚/源管理/投递协议 |
| `../../references/TRAPS.md` | 已知陷阱全集（48 个） |
| `../../references/REPO-SYNC.md` | Git 仓库同步（三处路径流程） |
| `../../references/MAINTENANCE.md` | References 一致性维护 + Skill 审计清单 |
| `references/fix-recipes.md` | 已验证质量修复脚本（短摘要扩写、tech上限、foreign_china扩充、tirith关闭） |
| `../../references/DELIVERY-WATERMARK.md` | 投递水印机制：MarkerDir + delivery_watchdog + 手动标记 |
| `references/sanity-check-maintenance.md` | Sanity check 拦截器维护 |
| `scripts/sanity_check.py` | 发布前拦截器 — 禁语/死链/敏感词扫描 + 输出格式验证 |
| `scripts/curate_and_push.py` | 精选+评分入口 |
| `references/deep-analysis-wecom-format.md` | 深度分析 WeCom 投递格式模板（表格排版v3.0） |
| `references/source-management.md` | 新增/修改 RSS 源：schema、权威分、外媒注册、双副本同步 |
| `references/deep-analysis-delivery-failure.md` | 深度分析未格式化 + 简报未送达排查手册 |
| `scripts/archive_resend.py` | 安全补发：从 `archive/` 读纯 markdown 投递 |
| `references/fragment-delivery-pitfall.md` | 简报分片投递陷阱：cron prompt 误用 briefing 字段致 WeCom 截断 |

## 兴趣偏好
`config/ai_interests.yaml` — 正面+2分，排除=0分过滤。CLI: `python3 scripts/interest_cli.py {list,add,remove,exclude}`。

**滑窗误触陷阱**：`_load_interests()` 用 2-3 字滑窗从排除短语提取关键词，通用词（新闻/游戏/体育 等）可能误入排除集。修改 `ai_interests.yaml` 后需检查排除集是否含通用词。详见 `../../references/TRAPS.md #49`。
