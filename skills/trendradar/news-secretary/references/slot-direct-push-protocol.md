# slot_direct_push 协议 v6.6

## 概述
v6.6 投递重构：将简报投递从 LLM Agent 的 final response 移交到 `no_agent` 脚本直接执行，消除 Agent 输出格式违规导致的静默截断问题。

## 架构
- **Cron job**: `slot_direct_push`（no_agent），schedule `2 9,12,21 * * *`（主管线后 2 分钟）
- **脚本**: `slot_direct_push_wrapper.py`
- **职责**: 读取已渲染的 archive markdown → 分片 → 调用 WeCom API 投递

## 与主管线的关系
主管线 cron（`0 9,12,21 * * *`，job 90a2866775df）运行完整 pipeline（fetch→curate→translate→render→fragment_push），产出 archive markdown 和 fragments。

slot_direct_push cron 在主管线 2 分钟后触发，从 archive 读取已渲染内容，自行分片投递。`deliver: local`（不自动推送，由脚本控制投递目标）。

## 关键特性
1. **Archive 头部自愈** — 自动剥离前 8 行中的 Agent 前言（"好消息"/"Pipeline returned"/"编排器执行完成"等）
2. **delivery_marker 水印** — 每次投递写入 `data/delivery_markers/delivered_{date}_{slot}.marker`，防重复投递
3. **零 LLM 成本** — 纯脚本执行，不消耗 token

## 排查
- slot_direct_push 的 `last_status=error` → 检查 wrapper 脚本日志
- 主管线 ok 但 slot_direct_push 未投递 → 检查 archive 文件是否已生成
- 重复投递 → 检查 delivery_marker 文件是否被意外删除

## ⚠️ cron 可能根本没装（2026-06-06 实战发现）

**`crontab -l` 为空是当前环境的真实状态**（2026-06-06 实测）。整个 slot_direct_push 架构（no_agent cron + delivery_marker + 自动重试）都是**理论存在但没真正运行**。

**症状**：
- 早 9:00/午 12:00/晚 21:00 后 `~/.hermes/trendradar/archive/YYYY-MM-DD/{slot}.md` 不存在
- `~/.hermes/trendradar/data/push_log.json` 最后一条是几天前
- 用户主动说"今天没收到日报"/"补推早报"

**根因猜测**：
- `hermes cron list` 的 job 是 Hermes 内部调度（systemd 跑），但 `slot_direct_push` 可能依赖外部 system cron 转发
- system cron（`crontab -l`）从未被用户显式安装 `slot_direct_push` 的 shell 调用
- Hermes cron 调度和 system cron 是两套，system cron 默认是空的

**手动补推替代方案**：见 `references/manual-retro-push.md`。**当前默认（2026-06-06）**：用户说"补推 X"就走该工作流，不等 cron。
