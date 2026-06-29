# 2026-06-02 Evening Cron 失败完整时间线

> 21:00 evening cron (90a2866775df) 实际跑了什么、为什么失败、怎么补的。
> 用于未来类似时间线复盘的参考。

## 现象

- 21:15 cron `last_status=error: RuntimeError: Request timed out.`
- 21:16 `slot_direct_push` (`fb4e21d7af94`) 报 `Script exited with code 3`，stdout 包含 `[SKIP] 2026-06-02 evening 已投递，跳过`（exit 3 = SKIP 正常返回码，被 cron 框架判为 error）
- 用户没收到 deep analysis，evening archive 是有 15 个 `[翻译失败]` 标记的旧版（22KB → 实际投递是 18:44 较早的 archive 4.3KB）

## 时间线（来自 `agent.log` 21:00-21:15）

| 时间 | 事件 | 状态 |
|---|---|---|
| 21:00:24 | cron 启动，调 DeepSeek v4-flash | ok |
| 21:00:24-21:03:24 | API call #1, **stream stale 180s × 2 retry** | timeout |
| 21:03:24-21:06:27 | Retry 2 stale 180s | timeout |
| 21:06:27-21:07:32 | Retry 3, primary_recovery 触发 | ok |
| 21:08:45 | API call #1 **终于返回**（501.2s latency，含 8 分钟服务端排队） | ok |
| 21:08:46-21:09:25 | 9 次成功 API call（cache 99-100%，latency 1.6-15.8s） | ok |
| 21:09:25 | API call #10 完成，**agent 进入 deep analysis 步骤** | ok |
| 21:09:25-21:10:25 | API call #11, 60s Request timed out | timeout |
| 21:10:25-21:11:28 | Retry 1 timeout | |
| 21:11:28-21:12:33 | Retry 2 timeout | |
| 21:12:33-21:13:39 | Retry 3 timeout，**第一轮 retry 结束** | |
| 21:13:39-21:14:42 | 第二轮 Retry 1 timeout | |
| 21:14:42-21:15:47 | 第二轮 Retry 3 timeout | |
| 21:15:47 | `API call failed after 3 retries. Request timed out.` | |
| 21:15:47 | `Job 'TrendRadar 日报推送（早/午/晚）' failed: RuntimeError: Request timed out.` | |
| 21:16:48 | slot_direct_push 跑：检测 marker 存在 → SKIP（exit 3） | 静默 |

**关键观察**：21:09:25 之后 agent **没有新 tool call**——所有 retry 都是同一个 call（`msgs=22 tokens=~16353`），agent 试图生成 deep analysis 步骤的 prompt 但 LLM 不响应。

## 4 层根因链

### 第 1 层（暴露层）：archive 有 15 个 `[翻译失败]`

`curated_evening_20260602.json` 21:08 写入时含 15 个 `[翻译失败]` 标记 + 2 个 gaming 中文条目 `title_cn` 为空。  
**但** 21:00 evening pipeline 实际**没进 ai_translate 步骤**——是更早某次 ai_translate 跑过但全部 401 失败留下的产物。

### 第 2 层（核心 bug）：ai_translate 401 假阳性

`llm_providers._resolve_api_key_env` 只查 `os.environ.get`，不查 .env 文件。  
`ai_translate` 拿 key 路径：`get_api_key()` (settings.py，有 .env fallback) → 拿到真 key  
`create_provider` 拿 key 路径：`_resolve_api_key_env()` (llm_providers.py，只查 env) → None  
→ provider `api_key = None` → 401

**修复**：commit `d257e3e` 加 .env fallback。详见 `references/llm-provider-abstraction.md` "症状：cron LLM agent 跑 ai_translate 报 401" 节。

### 第 3 层（系统层）：DeepSeek API 上游不可用

21:00 evening 第一次 API call 卡 8 分钟才回（501.2s latency），后续 6+ 分钟持续 60s timeout。  
**这是上游 DeepSeek 服务的可用性问题，不是客户端 bug**。  
任何客户端在这个时间窗口都会 timeout。

### 第 4 层（设计层）：agent 整体卡死等子任务

agent 在 deep analysis 步骤卡 6+ 分钟没有任何降级路径：  
- 没降级：自己用 flash 写分析
- 没降级：跳过 deep analysis
- 一直在等同一个 API call 返回

**修复**：skill `news-secretary` v6.22.0 晚间深度分析段加 3 级降级路径（首选/次选/兜底）。详见 SKILL.md "晚间深度分析" 段。

## 修复全过程（22:10-22:30 CST）

1. **诊断 4 层根因**：用 `agent.log` 时间戳倒推 + 严格模拟 `sys.path` / `env` / `_resolve_api_key_env` 调用链
2. **修代码**：`_resolve_api_key_env` 加 .env fallback (commit `d257e3e`)
3. **修 skill**：Pro → flash + 降级路径（commit `6992939`）
4. **重跑**：
   - 清 `[翻译失败]` 字段（6 个）+ 补 5 个中文空 `title_cn`
   - 跑 `ai_translate --push-id evening` → 6/6 翻译成功（3.3s）
   - 跑 `render_markdown` → 新 archive 4.6KB
   - 跑 3 个 Pro deep analysis（实测 73.5s）— 用 `delegate_task` 3 并行
   - 跑 `render_deep_analysis` 3 个 → 拼成 `evening.deep.md` 4.9KB
   - 删旧 marker → `slot_direct_push --slot evening` → 6/6 投递成功
   - `hermes send --file evening.deep.md` → 投递成功
5. **验证**：健康体检 `python3.14t trendradar_health_check.py` exit=0 静默

## 教训（5 条）

1. **不要相信"AI 不响应"的字面意思**——可能是 401/timeout/network 任何一种。必须看 stderr + 用 `os.environ.get` + `urllib.request.urlopen` 三步定位。
2. **双通道 bug 比单点 bug 难诊断**——ai_translate 拿到 key ≠ create_provider 拿到 key。审计时必须查整条链路。
3. **LLM agent 必须有降级路径**——上游 100% 可用是幻觉。降级路径在 SKILL/SKILL 提示里写明，agent 才能执行。
4. **DeepSeek API 上游不可用 → 降级到 flash 子 agent 或主 agent 自行生成**（不要干等）。
5. **18:44 marker 写的"ok"会锁住 21:00 后续投递**——slot_direct_push 看到 marker 就 SKIP，不会重投。**补投必须先 `rm marker`**。

## 跟 MEMORY 关联

- MEMORY "TrendRadar 43源，fetch ~3s..." 段记录 `slot_direct_push.py bug (2026-06-02 修)`，描述过 `_resolve_trendradar_home` 路径错。本文档记的是**同一晚上 4 小时后**发现的另一组 bug（401 + 降级），MEMORY 可补一条"晚间 cron 失败 4 层根因 + 降级路径修复 (2026-06-02 22:00)"。
- MEMORY "ai_translate 401 假阳性 — API key 未注入 (2026-06-02 实战)" 段描述"修占位符"是治标方案。本文件根因是 llm_providers.py 的 fallback 链不完整，治本方案在 commit `d257e3e`。MEMORY 可更新为"已治本，勿再修 .env 占位符"。
