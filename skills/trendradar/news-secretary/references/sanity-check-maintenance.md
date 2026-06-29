# sanity_check.py 拦截器维护

发布前拦截器 `scripts/sanity_check.py` 的维护要点和已知陷阱。

## 编排器前言剥离 (strip_orchestrator_preamble)

`ORCHESTRATOR_PREAMBLE_PATTERNS` 需要和 pipeline_orchestrator 的实际输出保持同步。

**当前模式（13 种）：**

中文：
- `^编排器执行完成.*$`
- `^输出简报正文.*$`
- `无需深度分析.*$`
- `^简报正文.*$`

英文：
- `^Orchestrator completed.*$`
- `^Pipeline orchestrator returned.*$`
- `^push_id\s*[:=].*$`
- `^DB schema v\d+`
- `^\[PIPELINE\].*$`
- `^\[SILENT\].*$`
- `^Outputting (the )?briefing.*$`（注意 `the` 可选，实际输出可能是 "Outputting briefing directly"）
- `No deep analysis needed.*$`
- `^-{3,}\s*$`

**维护信号**：当用户反馈午报/晚报正文前有编排器状态行未剥离时，一定有未覆盖的模式。添加新模式后必须同步到 cron 副本（`~/.hermes/trendradar/scripts/sanity_check.py`）。

**真实触发案例（2026-05-29）**：用户反馈午报正文前出现：
```
Pipeline orchestrator returned  status=ok  with  push_id=noon  . No deep analysis needed (noon slot). Outputting briefing directly.
```
当时已有的模式中 `^Outputting the briefing.*$` 因实际输出无"the"而未命中，`^Orchestrator completed.*$` 因开头是"Pipeline orchestrator"未命中，`无需深度分析.*$` 是中文版而实际输出是英文。修复：`^Outputting (the )?briefing.*$`（the 可选）、`^Pipeline orchestrator returned.*$`、`No deep analysis needed.*$`。

## 禁语表维护 (BANNED_PHRASES)

- **CN_AI_PATTERNS 死代码陷阱**：曾定义了中文 AI 禁语列表但从未在 `check_banned_phrases()` 中引用。新加禁语列表时必须确认检查函数实际引用了它。
- **匹配方式**：大小写不敏感的子串包含（`phrase.lower() in text.lower()`）。简单文本匹配，变体会绕过；新增变体请直接追加到 `BANNED_PHRASES`。

## 死链检测与代理

- 死链检测默认检查前 3 个 URL，使用 `urllib.request` HEAD 请求。
- **WSL cron 环境必须走代理**：使用 `_build_opener()` 读取 `HTTP_PROXY`/`HTTPS_PROXY` 环境变量创建 `ProxyHandler`。不加代理时所有外网链接都会报告 "unreachable"（假阳性）。
- `NO_PROXY` 不在处理范围，如果需要局部直连需扩展 `_build_opener()`。

## 双副本同步

`scripts/sanity_check.py` 在所有修改后必须同步到 `~/.hermes/trendradar/scripts/sanity_check.py`，否则 cron 作业跑旧代码。
