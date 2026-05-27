<!-- version: 2.8.0 | last-reviewed: 2026-05-26 -->

# 管线运维陷阱（2026-05-25 累积）

## 1. fetch_feeds 共用 TCPConnector 崩溃

**现象**：`RuntimeError: Session is closed`，所有国际源抓取失败，管线产出 0 条。

**根因**：`fetch_all()` 中直连和代理两个 `ClientSession` 共享同一个 `TCPConnector`。第一个 session 退出时 `__aexit__` 关闭连接池，第二个 session 直接报 Session is closed。

**修复**（2026-05-25）：每个 session 用独立 `TCPConnector`。同时将 `asyncio.TaskGroup` 改为 `asyncio.gather(return_exceptions=True)`。

**验证**：手动跑 fetch 输出 400+ 条、0 个 Session is closed 即为正常。

## 2. 翻译语言映射源变迁

| 阶段 | 方式 | 问题 |
|------|------|------|
| ~2026-05-24 | CJK 内容启发式 | 日语被错误跳过 |
| 2026-05-24 | 硬编码 frozenset | 加源要改两处代码 |
| 2026-05-25 | translate.yaml | yaml 和代码不同步 |
| **2026-05-25 (最终)** | **sources.json language 字段** | **单真相源** |

加新源只需在 `data/sources.json` 的条目中设 `language: "zh"/"en"/"ja"`，无需独立映射文件。

## 3. Agent 在简报输出中加注释

**现象**：推送内容开头出现 `Orchestrator completed with status ok, push_id=noon. No deep analysis needed. Outputting the briefing...`。

**根因**：cron prompt 只说"输出简报"，agent 把推理过程写进了 final response。

**修复**（2026-05-25）：prompt 显式禁止输出 `Orchestrator completed`、`push_id`、`---` 等。"只用 print(briefing) 一个字都不要多。"

**最终修复**（2026-05-25 晚）：`sanity_check.py` 拦截器在推送前自动扫描 16 种禁语模式，Agent 即使遗漏也会被拦截。Agent 层的冗长约束已移除。

## 4. 深度分析未走 render_deep_analysis.py 管道

**现象**：晚间深度分析输出长文段落 + `---` 横线分隔。

**根因**：agent 直接输出子 agent 原始文本，未通过管道格式化。

**修复**（2026-05-25）：prompt 强调"必须通过管道传给 render_deep_analysis.py 格式化"，并禁止添加 `---`。

## 5. 游戏分类误判

**现象**：非游戏条目被分入 gaming：
- 降压新药含"改变**游戏**规则"→命中 GAME_KW
- 索尼音乐版权含"**索尼**"→命中 GAME_KW

**修复**（2026-05-25）：`curate_and_push.py` 加入 `_GAME_FALSE_POSITIVES`（排除"改变游戏规则"成语）和 `_is_sony_music`（排除索尼+音乐）。

## 6. 科技分类误判（2026-05-25）

**现象**：非科技内容被分入 tech 板块：
- 药监局整治网售减肥药 → 命中 `网络`+`电商`(TECH_KW)
- 八项规定查处通报 → 命中 `数据`(TECH_KW)

**根因**：POLITICS_KW 缺少中文党内关键词（八项规定/党纪/纪委），JUNK_KW 缺少药监类关键词。这些条目首先被 game/junk/safety/politics 过滤，落空后才走 tech 判断，一旦命中任何 TECH_KW 就进入 tech。

**修复**（2026-05-25）：
- `keywords.py` 的 POLITICS_KW 新增：`八项规定`、`党纪`、`政务处分`、`纪委`、`中央纪委`、`监委`、`反腐`、`从严治党`、`通报`、`查处`
- `keywords.py` 的 JUNK_KW 新增：`减肥药`、`处方药`、`药监局`、`药品监管`

**验证**：确认 `POLITICS_KW` 和 `JUNK_KW` 中存在上述关键词。

## 7. fragment_push `_find_last` 字节/字符混用 bug（2026-05-25 发现并修复）

**现象**：`_find_last(text, delimiter, max_bytes)` 传入 `max_bytes=3800`（字节限制），但内部用 `len(text)`（字符数）做 `rfind` 搜索窗口。对中文字符（3 bytes/char）会导致搜索窗口错误扩大 3 倍，结果 `_split_overlong` 产生的子片段仍远超 MAX_BYTES。

**根因**：
```python
# ❌ 错误：len(text) 是字符数，max_bytes 是字节数，二者单位不同
search_end = min(len(text), max_bytes)  # 中文时 search_end=字符数，远超 3800
idx = text.rfind(delimiter, 0, search_end)
```

**修复**：先按字节截断→解码回安全字符边界→再用字符位置做 rfind。
```python
# ✅ 正确：按字节截断再解码回字符边界
encoded = text.encode('utf-8')
truncated = encoded[:max_bytes]
# 处理多字节截断 → 安全解码
for trim in range(4):
    try:
        char_limit = len(truncated.decode('utf-8'))
        break
    except UnicodeDecodeError:
        truncated = truncated[:-1]
idx = text.rfind(delimiter, 0, char_limit)
```

**教训**：任何处理 UTF-8 文本的函数，一旦同时涉及 `len()` 和 `encode()`，必须明确单位（字符 vs 字节）。Python 的 `len(str)` 永远返回字符数，但 `str.encode()` 返回字节数。中文 1 字符 = 3 字节，日文假名 1 字符 = 3 字节，此 bug 对所有 CJK 文本都会触发。

## 8. Circuit Breaker 模式（2026-05-25 新增）

**场景**：`ai_translate.py` 调用 DeepSeek API（Trap 28: openresty 流中断）。

**模式**：
```
指数退避: 2s → 4s → 8s → 16s → 30s (cap)
随机抖动: ±50%（防雷群效应）
超时递增: 120s + attempt×30s（流中断需要更长时间暴露）
熔断器: 连续 3 个 batch 失败 → 跳过剩余 batch
成功重置: 任一 batch 成功 → fail_count=0
```

**代码位置**：`ai_translate.py` 的 `_make_request()` + `circuit_broken()` + `translate_one_batch()`。

**关键**：熔断器状态是模块级全局变量 `_translate_failures`，同一进程内 batch 间共享。不同进程（每次 cron 调用启动新 Python 进程）自动重置。
