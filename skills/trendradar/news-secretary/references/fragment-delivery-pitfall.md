# Fragment Delivery Pitfall

> 2026-06-01 — 完整诊断与修复记录
> 2026-06-02 — 追加：v6.5 治标不治本，v6.6 根治

## 现象

用户收到的简报被截断（只看到前几个板块），简报尾部板块（如🎮游戏、📌尾注）消失。

Pipeline 输出 JSON 包含 `fragments` 数组（正确分片），但 Agent 将 `briefing` 字段作为一条 final response 输出 → WeCom 4KB 限制下尾部被静默截断。

## 完整诊断步骤

1. **检查 push_log.json** — `TRENDRADAR_HOME/data/push_log.json`。如果 `fragment_count` > 1 但用户收不到完整内容，问题在投递层而非 Pipeline。

2. **检查 cron job enabled_toolsets** — **v6.6 起应该不含 `messaging` toolset**。如还有，agent 物理上能调 `send_message` 走 LLM 投递路径——已被 v6.6 替换，agent 调它就是 bug。

3. **检查 cron prompt 指引** — v6.5 prompt 写"遍历 fragments 数组逐条 send_message"。v6.6 改写为"DO NOT deliver fragments yourself，slot_direct_push 接管"。

4. **检查 delivery_watchdog 补发** — watchdog 的 `_send_from_archive()` 是否使用了 `split_fragments()` 分片后再发。未分片时补发同样截断。

## 修复检查清单（所有三处）

### ① cron prompt（日报 `90a2866775df`）

**v6.6（推荐）**：
```
3. ok 状态下的唯一动作（重要！）:
   - 解析 JSON 拿到 push_id、fragments 数组长度、needs_deep_analysis
   - 不要调 send_message
   - 不要在 final response 输出 fragment 任何内容
   - final response 必须是单行状态文字
   - 结束
```

**v6.5（旧，已不推荐）**：
```
3. 解析 fragments 数组，逐条投递：
   - 用 send_message(target="wecom", message=fragment) 分别投递每一条分片
   - 禁止输出 briefing 字段作为 final response
```

### ② cron job enabled_toolsets

**v6.6（推荐）**：`["terminal", "web", "delegation"]` — 物理上无 messaging 工具
**v6.5（已废）**：`["terminal", "web", "delegation", "messaging"]`

### ③ delivery_watchdog `_send_from_archive()`

原代码：
```python
tmp.write_text(content)  # 整篇 archive
result = subprocess.run(['hermes', 'send', '--to', 'wecom:bl', '--file', str(tmp)])
```

修复后：
```python
from trendradar.scripts.fragment_push import split_fragments
fragments = split_fragments(content)
for i, frag in enumerate(fragments):
    tmp = Path(tempfile.gettempdir()) / f'{archive_path.stem}_frag{i}.md'
    tmp.write_text(frag)
    subprocess.run(['hermes', 'send', '--to', 'wecom:bl', '--file', str(tmp)])
```

## 同样影响周报/月报

`report-generator` 的 cron jobs (`c20e2c82deda` 周报, `0b14c67429ba` 月报) 同样需要 v6.6 迁移——但**当前未迁移**，仍走 v6.5 LLM 调 send_message 路径。详见 SKILL.md「周/月报迁移 TODO」。

报告更大（~15KB 周报、更大月报），截断影响更严重。

## 同样影响夜间深度分析

晚间深度分析虽然各自独立投递，但也应使用 `send_message` 而非 auto-delivery，确保不受 4KB 限制影响（部分分析 + 表格可能超限）。

## 验证方法

1. 查 `push_log.json` 确认 `fragment_count` > 1
2. 在 WeCom 中确认收到等量分片消息
3. 检查最后一条是否含 `📌 *共` 尾注
4. v6.6 额外检查：`delivery_markers/delivered_{date}_{slot}.marker` 存在且 `status=ok`

## ⚠️ 6/1 修复（v6.5）治标不治本

v6.5 试图通过 prompt 强制 agent 调 send_message 逐片投递。实测 deepseek-v4-flash **仍会**：

- 把整篇 briefing 作为一条 final response 输出（auto-delivery 触发 WeCom 4KB 截断）
- 在简报前加自述前缀（"以下是..."/"好消息..."/"Orchestrator completed"）

**这不是 prompt 写得不严，是 LLM 行为不可控**。

## 6/2 根治方案（v6.6）

彻底切走 LLM 投递路径。详见 SKILL.md「投递协议 v6.6」section + `references/slot-direct-push-protocol.md`。

核心：**LLM agent 不投递**。enabled_toolsets 移除 `messaging` toolset（物理上无法调 send_message），新增 no_agent cron `slot_direct_push`（`2 9,12,21`）脚本接管。

## 再次出现"分片/前缀"问题的排查清单

1. **先查 v6.6 是否被绕过**（如某 cron job enabled_toolsets 又被加回 `messaging`）— 用 `hermes cron list` 查 `enabled_toolsets` 字段
2. 检查 archive 头部是否被污染（slot_direct_push 投递前会自动剥，但人工补发 archive_resend.py 不剥 — 可手动 `archive_resend.py --slot {slot} --yes` 重投）
3. 看 `delivery_markers/delivered_{date}_{slot}.marker` 状态（`status=ok|partial|error`）
4. delivery_watchdog `0,30 10,14,21,22` 会查 push_log + marker 报错

## cron prompt 自相矛盾陷阱（gen_cron_prompt.py）

历史上 `gen_cron_prompt.py` 同时写了：
- L86: "**use `send_message` 逐片投递**"
- L149: "**Never use `send_message`**

LLM agent 看到这种矛盾 prompt，行为更不可控。v6.6 修复后，prompt 统一为"DO NOT deliver fragments yourself"——无矛盾。
