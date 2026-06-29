# Deep Analysis Prompt Fix — 2026-06-09

## 问题
SSOT cron prompt (`references/cron-prompt-generated.md`) 在 `Main Flow` 段只描述了 `status: ok → 输出 status 行就结束`，完全没让 LLM 检查 `needs_deep_analysis` 字段。`Deep Analysis (evening only)` 段虽然存在，但只列了3 行抽象步骤（"Launch 3 flash sub-agents in parallel"），LLM 看到这种空泛描述倾向于跳过。

**症状**：2026-05-30 ~ 2026-06-08 的所有 evening archive 都没有 deep analysis 章节。
**触发条件**：`push_id=evening` 且 `final_status != "error"` 时，orchestrator 返回 `needs_deep_analysis: true`，但 LLM 不会读这个字段。

## 修复（已应用到 SSOT + 日报 cron job `ef14933d8082`）

### Main Flow 段新增决策点
```diff
- `status: "ok"` → DO NOT deliver fragments yourself. Your job is only to:
-   1. Confirm status: "ok" in stdout
-   2. Output a short final response: "已生成 ..."
-   3. End.
+ `status: "ok"` → DO NOT deliver fragments yourself. Your job is:
+   1. Confirm status: "ok" in stdout
+   2. **Check needs_deep_analysis field**:
+      - false → 输出 status 行，end
+      - true → launch 3 flash delegate_task sub-agents (see Deep Analysis)
+   3. End. Do NOT call send_message for the briefing.
```

### Deep Analysis 段从3 行扩成 Step 1/2/3 协议
- **Step 1 — Pick 3 themes**：从 `curated_path` JSON（用 `read_file`）识别3 个最有新闻价值的主题。
- **Step 2 — Launch 3 `delegate_task` sub-agents**：
  - 使用 `deepseek-v4-flash`（便宜/快；这是 deep analysis 不是 creative）。
  - 输入：主题名 + curated JSON 路径 + 严格指令（200-300 字中文，覆盖事件链/数据/影响/展望/置信度/gap 6 项）。
  - 主题→板块映射（决定标题前缀）：
    ```
    关键词命中                          → 板块   → 标题前缀
    AI/芯片/科技/硅谷/英伟达/AMD/半导体   → 科技   → 🔍 科技 ·
    伊朗/核/联合国/地缘/制裁/国际/中东     → 国际   → 🔍 国际 ·
    米哈游/游戏/主机/任天堂/Sony/光追/Unity → 游戏 → 🔍 游戏 ·
    FED/央行/通胀/GDP/关税/供应链/经济     → 经济   → 🔍 经济 ·
    默认                                  → 要闻   → 🔍 要闻 ·
    ```
  - pipe 过 `render_deep_analysis.py`:
    ```bash
    echo "$ANALYSIS" | $PYTHON scripts/render_deep_analysis.py --topic "<主题>" --push-id evening --context
    ```
  - **投递**：`hermes send --to wecom:bl --subject "🔍 <板块> · <主题>"`，作为独立 WeCom 消息（不与 briefing 拼）。板块标签取自上方映射表。
- **Step 3 — Final response**：输出每段一行状态（`✅ 深度 1：<主题>`），不输出分析内容。
- **Failure handling**：工具不可用 → 输出 🟡 行说明跳过哪个，不重试。

## 部署清单
1. 改 `references/cron-prompt-generated.md`（SSOT）
2. `hermes cron edit ef14933d8082 --prompt "<新 prompt>"`（cron job 实际读这个）
3. 确认 `jobs.json` 里 `ef14933d8082` 的 `enabled_toolsets` 含 `"delegation"` —— 不含的话 LLM 看不到 `delegate_task` 工具
4. `hermes gateway restart`（Windows 上 stop + run --accept-hooks）让 scheduler 重读

## 验证窗口
修复后**首次验证窗口是次日晚 21:00**。预期 WeCom 收到：
- 6 片 evening 简报（看门狗投递）
- 3 条 `🔍 <板块> · <主题>` 消息（3 个 sub-agent 各自投递）
- 日报 LLM job final response 里 4 行 ✅（1 简报 + 3 深度）

如果只收到6 片没收到3 条深度 → LLM 没启 sub-agent；看 cron output 里 LLM 的 final response 是否提到 "delegate_task not available" → 检查 `enabled_toolsets`。