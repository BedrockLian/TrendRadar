<!-- version: 2.9.0 | last-reviewed: 2026-05-26 -->

# Pipeline — TrendRadar 日报推送管线

v2.9.0 起使用 `pipeline_orchestrator.py` 一键编排。`0 9,12,21 * * *`。
脚本阶段用 python3.14t（free-threaded），渲染用 render_markdown.py（纯脚本，~0s）。

Agent 可通过 `--list-steps` 动态获取管道步骤定义（SSOT），不再依赖手动维护的步骤表。

## 性能要点

- **RSS 抓取**：`TCPConnector(limit=20 per connector ×2)` ≥ Semaphore 容量，防连接槽缺口
- **关键词分类**：AC 自动机替代 `any()`，curation CPU 4.4x
- **AI 翻译 ∥ 全文抓取**：`ThreadPoolExecutor(max_workers=2)` 真并行（替代旧 Shell `& wait`），省 5-8s
- **DB 层**：WAL + `synchronous=NORMAL` + mmap=256MB + 复合索引 `(status, last_seen)`
  - 所有模块通过 `Storage.db()` 统一接入，自动启用 WAL + busy_timeout
  - `Storage.vacuum()` 可手动回收碎片空间
- **指纹**：`make_fingerprint(title, url)` 含 URL 前 3 段路径防日语标题碰撞
- **分片**：`fragment_push.py` 三级 UTF-8 字节拆分（段落 \n\n → 句子 。 → 硬切 3800B），防 WeCom 静默截断
- **迁移**：编排器启动时自动 `migrate()`，确保 Schema 最新

## 自动特性

- **Step -1 迁移检查**：`migrate(db)` — 启动前确保 DB schema 最新
- **Step 0 环境预检**：`push_slot_detect` + `PYTHONPATH` + `PYTHON_GIL`
- **SILENT 闭环**：无新内容时物理删除中间文件 + `fragments=[]` 显式空数组
- **熔断退避**：AI 翻译 5 次指数退避（2s→30s + jitter）+ 连续 3 失败熔断跳过
- **多样性惩罚**：curate 同源 >3 条权重减半，防单一来源霸榜
- **推送日志**：`push_log.json` 记录每次推送结果（状态/片数/耗时）

## 故障恢复

### 数据损坏
```bash
rm -f ~/.hermes/trendradar/cache/batch_{slot}.json
rm -f ~/.hermes/trendradar/data/curated_{slot}.json
cronjob action=run job_id=90a2866775df
```

### Gateway 崩溃后补推（简报已出但未送达）
```
hermes gateway start  # 先恢复通道
cd ~/.hermes/trendradar
# 绕过 slot 检测，三步直推：
/usr/local/bin/python3.14t scripts/render_markdown.py --push-id {slot} 2>/dev/null | \
  /usr/local/bin/python3.14t scripts/fragment_push.py 2>&1
# 末尾 JSON 数组 → 作为 final response 逐片输出，系统自动投递 WeCom，片间 1.5s
# 注意：不要重跑完整 pipeline（会破坏指纹/热度一致性）
```

### 翻译 API 断流（Trap 28）
自动重试已内置（5 次指数退避 + 熔断器）。若全部 batch 失败：
```bash
# 已有的 curated JSON 不会丢失，下个时段重新翻译
# 或手动重跑：
/usr/local/bin/python3.14t scripts/ai_translate.py --push-id {slot}
```

## 脚本清单

`push_slot_detect.py` | 时段路由
`push_prepare.py` | fetch + curation 编排
`fetch_feeds.py` | 38 RSS 异步抓取
`curate_and_push.py` | 5 domain 并行精选 + 来源多样性惩罚
`ai_translate.py` | AI 批量翻译 + 指数退避重试 + 熔断器
`batch_fetch.py` | 10 并发全文抓取
`render_markdown.py` | 纯脚本渲染（替代 Agent 手动渲染）
`render_deep_analysis.py` | Pro 深度分析格式化排版
`fragment_push.py` | UTF-8 字节计数分片（3800B/片），三级递降拆分
`track_events.py` | 跨日事件追踪
`record_fingerprints.py` | 指纹记录（Storage 统一接入）
`blog_watcher_bridge.py` | blogwatcher 集成
`pipeline_orchestrator.py` | 一键编排器 v2.9.0
`blind_spot_audit.py` | 盲点审计 + --json 机器可读模式
`aggregate_monthly.py` | 月度统计 + --suggest-interests 兴趣漂移

---

## 性能瓶颈

### TCP 连接池耗尽
**症状**：RSS源 aiohttp 超时但 curl 正常。
**案例**(2026-05-21): 曾因多 Semaphore 总和超过 TCPConnector 导致超时，已修复。
**修复**: `TCPConnector(limit) >= 所有Semaphore`总和，留20%余量。当前已统一为单 `EXTERNAL_CONCURRENT=20`。

### Script 并行
互不依赖脚本用 `& wait`:
```bash
python3 scripts/ai_translate.py & T1=$!
python3 scripts/batch_fetch.py & T2=$!
wait $T1 $T2
```
收益 = max(T1,T2) 替代 T1+T2。

### 三步审计
1. 脚本 — 死代码/重复（grep import + grep调用点）
2. cron — job重叠/静默运行
3. 配置 — 零引用文件/零值字段

---

## 简报渲染格式规范

> 本格式同时作为 **格式契约** 固化在 `scripts/render_markdown.py` 的 docstring 中。
> 任何格式修改，必须先更新 docstring 中的 7 条铁律再改代码。

### 整体结构

```markdown
### Hermes日报 · YYYY-MM-DD（时段）


📋 **共 N 条** · 📰X  🌏X  💻X  📊X  🎮X


### 📰 板块名


🔥 N. **标题**

摘要正文（截断120字符，句号/换行边界）

[【媒体名】](url)
```

### 空行铁律

- **板块标题后**：`\n\n\n`（双空行）
- **条目间**：`\n\n\n`（双空行）
- **条目内部**：标题→摘要→链接之间各 `\n\n`（单空行）
- 不允许使用 `---` 或 `***` 作为分隔线

### 链接格式（2026-05-25 用户指定）

```python
# 正确 ✅
link = f"[【{source}】]({url})"

# 错误 ❌ —— 用户明确拒绝
# link = f"[查看原文]({url})【{source}】"
```

媒体名称用 `【】` 包裹，整个作为超链接文本。不加"查看原文"前缀。

### Emoji 规则

| 条件 | Emoji |
|------|-------|
| 热度高（_heat.appearances >= 2 或 _heat.heat_score >= 0.8） | 🔥 |
| 新条目标记（非热门） | 🆕 |
| evening 回顾（_track 以 _recap 结尾） | 🔄 |

### 摘要截断

`_shorten(text, max_len=150)` — 截断到 max_len 字符，优先在句号或换行边界截断。如果 60% 长度内找不到句号，在空格处截断加 `…`。

### 来源媒体名

`source_platform` 按 `+` 拆分后取第一段：
```python
source = (item.get('source_platform') or '').split('+')[0].strip()
```

### 禁止事项
- 不在简报中添加任何前缀/后缀说明文字
- 不允许 LLM 重写、摘要、重排或加解释
- 不要在条目之间插入空行以外的任何分隔符
- 不要把深度分析与简报正文拼接

---

## 深度分析格式化（render_deep_analysis.py）

> Pro 子 agent 产出分析文本后，经 `render_deep_analysis.py` 格式化再推送 WeCom。
> 避免子 agent 自由输出中的表格/代码块/横线等 WeCom 不支持的标记。

### 用法

```bash
# 管道模式
echo "$ANALYSIS_TEXT" | python3 scripts/render_deep_analysis.py --topic "AI · 科技趋势"

# 文件模式
python3 scripts/render_deep_analysis.py --topic "经济 · 地缘" --input analysis.txt
```

### 输出格式（用户批准的样式）

```
🔬 **主题标题**

一段核心信号/背景介绍（2-3行，含加粗关键数据）

📈 **子标题1**
关键点1：带数字/数据加粗
关键点2：带公司名加粗
关键点3：简洁结论

🎯 **子标题2**
要点...
```

### 格式铁律

| 规则 | 要求 |
|------|------|
| 标题行 | `🔬 **粗体标题**` 开头 |
| 子标题 | `emoji **粗体关键词**` 后接内容 |
| 加粗 | 公司名、数据、关键结论 |
| 行长度 | ≤40字/行 |
| 段落数 | 5-8段 |
| 禁止 | 表格、代码块、横线 `---` |

### 脚本功能

| 处理 | 行为 |
|------|------|
| 代码块 | 删除 |
| 表格 | 删除（匹配 `|...|` 行） |
| 横线 `---` | 替换为空行 |
| 内联代码 `` ` `` | 去掉反引号 |
| 列表标记 `- * •` | 去除标记保留内容 |
| 编号 `1. 2.` | 去除编号保留内容 |
| 章节标题检测 | 匹配关键词（趋势/方向/分析/总结等）→ 自动加emoji前缀 |
| 总长度 | 上限 1600 字符（WeCom 单消息安全边界） |

### emoji 映射

| 关键词 | emoji |
|--------|-------|
| 趋势 | 📈 |
| 方向 | 🎯 |
| 分析 | 🔍 |
| 总结/结论 | 📌 |
| 影响 | ⚡ |
| 风险 | ⚠️ |
| 机会 | 💡 |
| 观点 | 💭 |
| 启示 | ✨ |
