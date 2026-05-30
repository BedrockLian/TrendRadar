---
name: news-secretary
slug: news-secretary
version: 6.13.0
description: 聚合多RSS源+博客，推送Markdown简报至企业微信。编排器一键管线 + 晚间Pro深度分析。
author: Hermes Agent
metadata:
  hermes:
    tags: [news, trend, RSS, wecom]
    delivery: wecom
    push_schedule: { merged: "0 9,12,21 * * *" }
    companion_skills: [self-healing, weekly-report, monthly-report, performance-optimizer, system-config]
---

## 触发
cron `0 9,12,21 * * *` (morning 30条 / noon 30条 / evening 20条, 日上限80)。晚间追加 3×Pro 深度分析。

## 管线

```
pipeline_orchestrator.py（v2.8.0 — 一键7阶段）
  ① push_slot_detect → ② push_prepare(fetch+curate) → ③ 并行(ai_translate ∥ batch_fetch)
  → ④ render_markdown → ⑤ fragment_push（UTF-8 字节计数分片） → ⑥ record_fingerprints（Storage 统一接入）
  → 输出 JSON: {status, fragments, briefing, stats, needs_deep_analysis}
```

LLM 运行编排器，解析 `fragments` 数组投递。编排器不可用时走 cron prompt 中的 fallback 手动管线。自动特性详见 `references/PIPELINE.md`。

简报由 `render_markdown.py` 纯脚本生成，Agent 不修改内容。cron prompt 修改后需同步更新。

## 简报投递纪律（Agent 输出约束）

Agent 在 final response 中输出简报时，必须遵守以下硬约束：

1. **零附加文本** — 输出 `briefing` 字段内容**本身**，不得在前面添加"编排器执行完成""输出简报正文""推送时段为午间""无需深度分析"等任何状态描述行，也不得在后面添加总结。最终响应应直接从 `### Hermes日报 ·` 或板块标题开始。

2. **URL 透传** — 链接中的 URL 必须原样输出。Agent 重新格式化/换行/重排时容易在 URL 中插入空格（如 `pcgamer.com` → `pc gamer.com`），导致 Markdown 连接断裂。`render_markdown.py` 已加入防御性空格清洗，但 agent 仍应避免触碰 URL。

3. **逐字逐句透传** — 不得对简报内容做任何 AI 润色/重写/重组。简报已经由脚本可靠生成，任何 AI 二次处理只会引入格式错误或虚构内容。

4. **sanity_check 兜底** — `sanity_check.py` 在发布前自动剥离编排器前言（中英文 13 种模式），但 agent 不应依赖此兜底。零附加文本是第一道防线。

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

1. **按来源定语言（来自 sources.json）** — `get_source_lang()` 读取 `DATA_DIR / 'sources.json'`（运行时数据目录 `~/.hermes/trendradar/data/`）每个源的 `language` + `platform` + `name` 字段。单真相源：加新源设好 `language` 即可，不再维护独立的映射文件。**陷阱**：`data/sources.json` 已在 git 中跟踪（`git clean` 不再误删），但 `git reset --hard` 后仍需 `git checkout HEAD -- data/sources.json` 恢复。
2. **文件同步** — ai_translate 和 render_markdown 必须读同一文件（今日日期版 → 最新日期版 → 通用版，三层回退）。陷阱 2026-05-26: 只有两层回退时翻译写入通用版但渲染读日期版。
3. **render 优先 title_cn** — `render_markdown.py` `_format_item` 取 `title_cn`/`summary_cn`，不回落到原始 title/summary。
4. **BATCH_SIZE 上限 5** — DeepSeek 在 batch >5 时只翻译摘要不翻译标题（标题保持原文不变但摘要正确翻译）。`ai_translate.py` `BATCH_SIZE = 5`。若未来换模型需重新验证。

5. **日→中翻译返回原文陷阱** — DeepSeek 在处理日文→中文批量翻译时，有时直接返回原文不变（`title_cn == title`，`summary_cn == summary`），不报错不告警。2026-05-28 午间推送中 5/6 条 NHK 条目出现此问题。区别性特征：英文翻译正常，仅日文条目 `title_cn == title`。
   - **原因**：模型对引理对齐但未执行语言转换。
   - **首次修复**：prompt 新增规则 `CRITICAL: You MUST translate every item. NEVER return the original text unchanged.`
   - **二次防护**：`translate_one_batch()` 添加循环检测，逐条对比 `title_cn==orig_title || summary_cn==orig_summary`，命中时输出 `⚠️ N items NOT translated` 警告日志。
   - **未来方向**：如频发，可考虑将日文与英文分开调 API（不同 temperature），或回落至专用翻译模型。
6. **中文短摘要 AI 扩写**（v6.10.0） — `ai_translate.py` 新增中文条目短摘要扩写通道。对中文源（source_lang 为 None）中原始摘要 `<50 字` 的条目，自动用 AI 扩写成 50-80 字的完整信息句。扩写 prompt 在 `_EXPAND_TEMPLATE` 中，约束：不虚构事实、基于标题上下文展开、保持新闻风格。2026-05-27 用户反馈摘要过短后添加，虎嗅/钛媒体短条目从 23/26 字扩至 37/51 字。
7. **摘要长度与 render 联动** — `render_markdown.py` 的 `_shorten(max_len=80)` 控制最终展示长度（参见输出规范第5条）。英文/日文翻译产出通常 40-70 字，render 基本保留；中文条目从 `summary` 字段取前 80 字（旧 50 字截断的改进，但 300 字长摘要仍会被截）。扩写通道只覆盖 `<50 字` 的极短条目。用户反馈摘要过短时，需同步检查两个配置点：`ai_translate.py` 的扩写逻辑和 `render_markdown.py` 的 `max_len`。
8. **cron prompt 直接输出 BRIEFING** — `send_message` 在 cron context 不可用。prompt 第7步直接输出脚本渲染结果，不经过 LLM 重写。
9. **items_to_translate tuple** — `needs_title`/`needs_summary` 由 `bool(source_lang)` 驱动（非 None 就翻译），第8个元素 `source_lang` (`'English'`/`'Japanese'`/`None`) 必须存在。来源语言由 `data/sources.json` 每个源的 `language` 字段决定（`_scan()` 提取 `en`/`ja` 源的 `platform`+`name` 做子串匹配）。`translate.yaml` 已淘汰（2026-05-25）。旧 CJK 启发式函数（`_is_cjk`/`cjk_ratio`/`needs_translation`/`detect_source_lang`）已于 2026-05-25 全部移除。
10. **TITLE:/SUMMARY: 前缀残留陷阱** — DeepSeek 翻译返回的 title_cn/summary_cn 可能包含 `TITLE: xxx` / `SUMMARY: xxx` 前缀（模型忠实执行 prompt 中的标记）。2026-05-27 晚间 NHK 条目出现此问题。手动修复命令：
   ```bash
   python3 -c "import json; d=json.load(open('data/curated_evening_20260527.json')); [item.update({k:item[k].replace(k.split('_')[0].upper()+': ','',1)}) for domain in ['top_headlines','foreign_china','tech','economy','gaming'] for item in d.get(domain,[]) for k in ['title_cn','summary_cn'] if item.get(k,'').startswith(('TITLE: ','SUMMARY: '))]; json.dump(d,open('data/curated_evening_20260527.json','w'),ensure_ascii=False,indent=2)"
   python3 scripts/render_markdown.py --push-id evening
   ```
   长期方案需 `ai_translate.py` 写入前 strip 掉这些前缀。
11. **手动运行 ai_translate.py 需显式传 DEEPSEEK_API_KEY** — 脚本从 `TRENDRADAR_HOME/.env`（`~/.hermes/trendradar/.env`）读取 API key，但实际 key 在 `~/.hermes/.env`。手动运行时需 `export DEEPSEEK_API_KEY=$(grep '^DEEPSEEK_API_KEY=' ~/.hermes/.env | cut -d= -f2- | tr -d '"')`，或设置 `TRENDRADAR_ENV=~/.hermes/.env`。

## 晚间深度分析

仅 evening。`delegate_task` 并行 3 个 Pro 子 Agent（趋势/跨域/风险），各基于当日 curated JSON（不联网）。
输出经 `render_deep_analysis.py --topic "主题"` 管道格式化后作为 final response 逐篇投递（系统自动推送 WeCom）。
完整协议见 `references/PIPELINE.md`（深度分析格式化章节）。

**重要：每条分析作为独立 final response 分别输出，不得与简报正文拼接在一起。** 简报走 step 3, 分析走 step 4, 互不干扰。

**格式化铁律**：每个 delegate_task 返回的分析文本必须通过 `render_deep_analysis.py` 管道格式化——`echo "$ANALYSIS_TEXT" | $PYTHON scripts/render_deep_analysis.py --topic "主题" --push-id evening --context`。禁止直接输出原始分析文本。格式化后的输出包含 `🔬 **主题**` 标题和 `📌 相关回顾` 部分，这是正确的格式。

**3 条分开投递**：趋势、跨域、风险各作为一条独立 final response 分别输出，不要合并成一条。

**子 Agent 沙箱陷阱**：`delegate_task` 子 Agent 在 cron 上下文中有独立的进程上下文，其 `terminal`/`read_file` 等工具**无法读取父 session 的文件系统**。文件路径传递（如 `cat /path/to/report.md`）会返回空。子 Agent 必须通过 inline 文本传递内容——将分析文本放在 prompt 的 `context` 字段中，而不是让子 Agent 自己去读文件。详见 `references/PIPELINE.md  # was deep-analysis-subagent-sandbox → pipeline`。

## 交付验证（新增！）

**Pipeline 返回 `status=ok` 不等于用户收到了简报。** 已知静默失败模式：

1. **Gateway WebSocket 断连**：`[Wecom] WebSocket error` → 自动重连通常成功，但若刚好在 final response 投递窗口断开，消息丢失且无错误日志
2. **auto-delivery 未送达**：cron 的 final response 靠 Gateway 转发 WeCom。如果 Gateway 在处理投递时崩溃，pipeline 依旧报告 ok
3. **DeepSeek API 流中断**：`RemoteProtocolError: peer closed connection without sending complete message body` → 只返回 stub response，半篇丢失

**投递后验证**：
- Cron 结束后，检查 delivery_watchdog 是否会捕获失败
- 用户反馈"没收到"时：优先走 `archive_resend.py`（见下一节），不要查 cron 输出日志。——cron 输出文件（`cron/output/`）混有 pipeline 日志和 skill 上下文，读到源名容易产生"有这个源就有内容"的虚假印象，是幻觉高危来源。**存档（`archive/YYYY-MM-DD/{slot}.md`）是纯 markdown，是你唯一应该查的数据源。**

## 手动补发纪律（2026-05-27 更新 — 硬约束）

### 标准路径（优先）：archive_resend.py

```bash
# 列出可用存档
python3 scripts/archive_resend.py --list

# 补发某日某时段
export PYTHON=/usr/local/bin/python3.14t PYTHONPATH=/home/asus/.hermes PYTHON_GIL=0
$PYTHON scripts/archive_resend.py --date YYYY-MM-DD --slot morning
```

`archive_resend.py` 会自动：
1. 读 `archive/YYYY-MM-DD/{slot}.md`（纯 markdown，由 `render_markdown.py` 每次推送时自动存档）
2. 校验文件存在且非空（不存在时报错退出——**禁止自行生成内容**）
3. 打印前 200 字预览
4. 走 `hermes send --to wecom:bl` 投递

**安全约束**：存档不存在时直接报错，不生成替代内容。这是防幻觉的第一道防线。

> **archive_resend.py 路径不一致陷阱**：`archive_resend.py` 用自己的 `__file__` 解析 `TRENDRADAR_HOME`（指向 `~/TrendRadar/`），而 `render_markdown.py` 使用 `settings.py` 的 `TRENDRADAR_HOME`（指向 `~/.hermes/trendradar/`）。存档写到了 `~/.hermes/trendradar/archive/`，但补发脚本去 `~/TrendRadar/archive/` 找。修复：设置 `TRENDRADAR_HOME` 覆盖路径，或直接用 `hermes send` 管道投递。

### 回退路径（存档缺失时）

存档缺失通常意味着当天 pipeline 没跑成功。手工重建：

1. **还原数据** — 从 `backups/trendradar/{date}/` 恢复 `curated_{slot}.json` 到 `data/` 目录
2. **跑翻译** — `ai_translate.py --push-id {slot}` 必须成功。验证 `title_cn`/`summary_cn` 已写入
3. **跑渲染** — `render_markdown.py --push-id {slot}` → 自动写 archive + 输出 stdout
4. **补发** — `archive_resend.py --date YYYY-MM-DD --slot {slot}`（存档已就绪）

### 禁止事项

- **严禁编造标题、摘要、来源**。The Verge/OpenAI/RTX 等虚构条目用户一眼能识别。
- **严禁从 cron 输出日志读取内容**。cron 输出文件混有 pipeline 日志和 skill 上下文，不是可信数据源。
- **严禁拼接虚构新闻**。觉得"这个源今天怎么没新闻"时，检查 raw JSON 确认该源是否被抓取、是否被预分类分流到其他域。不要自行填充。
- **不要改动条目顺序和内容结构**。保持原始顺序，只做格式适配（分片、长度裁剪）。

## 投递水印机制（delivery_marker）

pipeline 报告 `status=ok` 不等于用户收到了简报。投递水印（delivery_marker）作为投递确认的真值源。

### MarkerDir: `data/delivery_markers/`

每次推送创建 `{date}_{slot}.marker`：`{"push_id":"morning","delivered":true,"delivered_at":"...","verified_by":"delivery_watchdog"}`

### delivery_watchdog.py 自动补投

看门狗 cron (`cab79825520e`, `no_agent=true`) 每 15 分钟检查 `push_log.json`：
- 有 pipeline 记录但无水印 → 自动从 `archive/{date}/{slot}.md` 补投
- 水印 `delivered: false` → 同上
- 补投成功 → 更新水印

### 手动标记

```bash
mkdir -p data/delivery_markers
echo '{"push_id":"morning","date":"2026-05-27","delivered":true,"verified_by":"manual"}' \
  > data/delivery_markers/2026-05-27_morning.marker
ls -la data/delivery_markers/$(date +%Y-%m-%d)_*.marker
```

完整文档：`references/DELIVERY-WATERMARK.md`。

## 输出规范（脚本固化 + `sanity_check.py` 拦截）

简报和深度分析由纯脚本生成，Agent 只做透传。`sanity_check.py` 在发布前自动剥离编排器前言（中文：编排器执行完成/输出简报正文/无需深度分析/简报正文 + 英文：Orchestrator completed/Pipeline orchestrator returned/push_id/DB schema v/\\[PIPELINE]/\\[SILENT]/Outputting briefing/No deep analysis needed/---），共 13 种正则模式，再执行禁语/死链/敏感词/HTML残留扫描
- 编排器元数据不会误触 BANNED_PHRASES
- 2026-05-28 新增 4 条中文前缀正则（编排器执行完成/输出简报正文/无需深度分析/简报正文）
- 2026-05-29 新增 Pipeline orchestrator returned/Outputting(可选the)briefing/No deep analysis needed 三条英文模式

1. **透传简报** — 输出 JSON `briefing` 字段内容本身。`sanity_check.py` 自动拦截 "As an AI language model" / "Here is your report" 等禁语。
2. **链接格式** — `[【媒体名】](url)`，不加"查看原文"前缀。URL 中包含空格或全角空格时，`render_markdown.py` 会在渲染前自动清除（2026-05-28 修复：`url.replace(' ', '').replace('　', '')`，防止 Agent 输出时在 URL 中插入空格导致链接断裂）。
3. **深度分析独立投递** — 晚间 3 条深度分析各自作为单独 final response 输出。
4. **空行铁律** — 板块标题后 `\n\n\n`，条目间 `\n\n\n`，全文无 `---`/`***` 横线。

5. **摘要约束** — 每条摘要 80 字内且为逻辑自洽的完整句子，不允许断句（不能被 `…` 截断成半截话）。由 `render_markdown.py` 的 `_shorten(max_len=80)` 保证，无句号时优先找逗号边界，最后兜底干净截断不加 `…`。
6. **格式契约** — 完整规则在 `render_markdown.py` 模块 docstring 中，修改格式必须先更新契约。

## 运行时
```bash
export PYTHON=/usr/local/bin/python3.14t PYTHONPATH=/home/asus/.hermes PYTHON_GIL=0
```

## 关键参考

> 文档已于 2026-05-27 从 41 份合并为 9 份。完整映射见 `references/INDEX.md`。

| 文件 | 何时读 |
|------|--------|
| `references/ARCHITECTURE.md` | 系统架构全貌（分类/关键词/渲染/迁移/体检/API模式） |
| `references/PIPELINE.md` | 管线流程 + 性能瓶颈 + 简报/深度分析格式规范 |
| `references/SETUP.md` | 代理配置/Cron运维/迁移回滚/源管理/投递协议 |
| `references/TRAPS.md` | 已知陷阱全集（48 个） |
| `references/REPO-SYNC.md` | Git 仓库同步（三处路径流程） |
| `references/REFERENCES-CONSISTENCY-GUIDE.md` | References 一致性维护 |
| `references/SKILL-AUDIT.md` | Skill 修改后审计（7 维度检查表） |
| `references/DELIVERY-WATERMARK.md` | 投递水印机制：MarkerDir + delivery_watchdog + 手动标记 |
| `references/cron-prompt-generated.md` | 日报 cron prompt（自动生成，SSOT） |
| `scripts/render_markdown.py` | 格式契约 docstring |
| `scripts/sanity_check.py` | 发布前拦截器 |
| `references/sanity-check-maintenance.md` | 拦截器维护：前言模式/禁语表/死链代理/双副本同步 |
| `scripts/archive_resend.py` | 安全补发：从 `archive/` 读纯 markdown 投递 |
| `scripts/gen_cron_prompt.py` | 从 --list-steps 自动生成 cron prompt |

## 兴趣偏好
`config/ai_interests.yaml` — 正面+2分，排除=0分过滤。CLI: `python3 scripts/interest_cli.py {list,add,remove,exclude}`。

**滑窗误触陷阱**：`_load_interests()` 用 2-3 字滑窗从排除短语提取关键词，通用词（新闻/游戏/体育 等）可能误入排除集。修改 `ai_interests.yaml` 后需检查排除集是否含通用词。详见 `references/interest-sliding-window-trap.md`。
