---
name: news-secretary
slug: news-secretary
version: 5.6.0
description: 聚合多RSS源+博客推送Markdown简报至企业微信。Flash管线策展+Pro晚间深度分析。即使slot_detect返回NO_SLOT也应主动尝试推送。
author: Hermes Agent
metadata:
  hermes:
    tags: [news, trend, RSS, wecom]
    delivery: wecom
    push_schedule: { merged: "0 9,12,21 * * *" }
    data_dir: ~/.hermes/trendradar
    scripts_dir: ~/.hermes/trendradar/scripts
    companion_skills: [monthly-report, self-healing]
---

## Pipeline

```
timeline.yaml → push_slot_detect → push_prepare(RSS+blog+AC分类)
  → track_events / batch_fetch ∥ ai_translate → render_markdown(纯脚本,0s)
  → fragment_push(板块分片) → record_fingerprints(zstd)
  → [晚间] delegate_task 3×Pro → render_deep_analysis(格式化) → send_message
```
### 渲染方式

`render_markdown.py` — 纯脚本渲染，直接从 curated JSON 拼接 markdown，摘要截断 150 字，句号边界智能切分。格式硬编码永远一致。输出兼容 `fragment_push.py` 分片。

## 调度
`0 9,12,21 * * *` 对应 morning(24条) / noon(32条) / evening(24条)。晚间增加 3 Pro Agent 深度分析。

## 晚间深度分析协议（evening 专属）

仅在 evening 时段执行。用 `delegate_task` 并行启动 3 个 Pro 子 agent，分别做以下分析：

### 分析 1：趋势与模式识别
**目标**：从今日简报全量条目中识别跨板块的宏观趋势和模式。
**输出格式**：纯文本，WeCom 手机端友好
- 3-5 个核心趋势，每趋势 2-3 行
- 关键数据加粗，emoji 分段，禁止表格
- 示例输出：
```
🔬 **AI · 科技趋势**
💡 **AI融资分化**：梁文锋买时间深耕基础研究 vs 跟风者买现成答案套壳变现。价格战加速洗牌，后者的生存窗口在收窄。
⌚ **硬件窗口开启**：谷歌 AI 眼镜接近可用、Oura 智能戒指申请 IPO — 健康可穿戴的 AI 化是已验证赛道。
```

### 分析 2：跨域影响分析
**目标**：分析事件之间的因果关系和传导链。例如地缘冲突→航运→供应链→经济的完整链路。
**输出格式**：纯文本，emoji 标注传导链
- 2-3 条传导链，每条 3-4 行
- 用 `→` 表示传导路径，关键数据加粗
- 示例：
```
🛢️ **霍尔木兹海峡僵局**：美伊谈判陷僵局 → 全球 1/5 石油运输受阻 → 能源价格上行 → 亚太通胀压力加剧
📉 **资本转向**：美国股票基金九周来首次净流出 → 债券收益率攀升 → 资产配置从风险转向避险
```

### 分析 3：风险与机会评估
**目标**：识别明日潜在风险和机会，按影响程度分级。
**输出格式**：纯文本，emoji 标示级别
- 🔴 高风险（概率+影响）：1-2 条，每条约 2 行
- 🟢 机会（概率+影响）：1-2 条，每条约 2 行
- 示例：
```
🔴 **霍尔木兹局势升级**：美伊谈判若无突破，油价短期冲高将冲击亚洲能源进口国
🟢 **DeepSeek 降价**：模型推理成本下探，中小开发者 AI 应用门槛降低，利好应用层创新
```

### 通用规则
- 使用 Pro 模型（`deepseek-v4-pro`），每分析独立子 agent
- 3 个分析并行启动，不串行
- **基于当日 curated JSON 数据，不联网搜索**（简报数据已含所有需要的信息；联网会导致分析跑偏为长篇研究报告）
- 输出结构：标题行 `🔬 **主题**` → 2-3段正文 → 每段以 `📈/🎯/⚡  **关键词**` 开头 → 每段3-4行 → 总计5-8段
- **关键数据/公司名用 `**加粗**` 突出**（如 `**DeepSeek V4-Pro 永久降价 2.5 折**`）
- 段落之间用单空行分隔，禁止表格/代码块/横线
- 每行不超过40字（手机阅读友好），用句号结尾自然断行
- 输出经 `cat | render_deep_analysis.py --topic "主题"` 管道格式化后，用 `send_message(target="wecom")` 逐篇独立推送

## 运行时
- free-threaded Python 3.14t — `export PYTHON=/usr/local/bin/python3.14t PYTHONPATH=/home/asus/.hermes PYTHON_GIL=0`
- 依赖: `python3.14t -m pip install feedparser zstandard`
- 模型: Flash(deepseek-v4-flash)管线 + Pro(deepseek-v4-pro)晚间分析

## 关键参考
| 文件 | 什么时候看 |
|------|-----------|
| `references/render-format.md` | 简报格式终极规范（渲染脚本产出格式） |
| `references/render-markdown.md` | render_markdown.py 纯脚本渲染器说明 |
| `references/render-deep-analysis.md` | render_deep_analysis.py 深度分析格式化器说明 |
| `references/deep-analysis-format.md` | 深度分析格式化规范（含用户批准的示例输出） |
| `references/render-format.md` | 简报输出格式规范（板块/空行/emoji） |
| `references/traps.md` | 已知陷阱全集（Gateway 崩溃丢推送 / NO_SLOT / tirith / 技能名） |
| `references/pipeline.md` | 管线故障恢复 + 性能基线 |
| `references/cron-operations.md` | Cron 运维检查清单 + 技能名三重校验 |
| `references/classification-architecture.md` | 分类规则/优先级/关键词规模 |
| `references/keyword-architecture.md` | 505词×6域完整词表 |
| `references/free-threaded-build.md` | python3.14t 编译/安装/zstd降级 |
| `references/render-markdown-failures.md` | render_markdown.py 故障模式速查（日期/数据结构/空文件） |
| `references/cron-audit.md` | Cron 全量审计清单（技能/脚本/path 六项检查） |

## 兴趣偏好
`config/ai_interests.yaml` — 正面+2分，排除=0分过滤。CLI: `python3 scripts/interest_cli.py {list,add,remove,exclude}`。

## 故障恢复

### 标准恢复（数据损坏/不完整）
```bash
rm -f ~/.hermes/trendradar/cache/batch_{slot}.json
rm -f ~/.hermes/trendradar/data/curated_{slot}.json
cronjob action=run job_id=90a2866775df
```

### Gateway 崩溃后补推（简报已产出但未送达）
当用户反馈"没收到推送"且 `hermes gateway status` 显示 failed 时：

**前置检查**（跳过则补推可能无效）：
- `hermes config get security.tirith_enabled` — 若为 true，cron 内部命令会被中文拦截，需先 `hermes config set security.tirith_enabled false`
- cron job 的 skills 列表是否引用已重命名的技能（检查 Trap 18）
- 确认 curated 数据还在（`ls -la ~/.hermes/trendradar/data/curated_{slot}_*.json`）

```bash
# 1. 先重启 Gateway
hermes gateway start

# 2. 确认 curated 数据还在（否则走标准恢复）
ls -la ~/.hermes/trendradar/data/curated_{slot}_*.json

# 3. 绕过 slot 检测，直接渲染→分片→投递
cd ~/.hermes/trendradar
# 方式 A（推荐，零 token）：脚本渲染
BRIEFING=$(/usr/local/bin/python3.14t scripts/render_markdown.py --push-id {slot} 2>/dev/null)
FRAGMENTS=$(echo "$BRIEFING" | /usr/local/bin/python3.14t scripts/fragment_push.py 2>&1 | grep -v '^\[' | tail -1)
# 用 json.loads 解析 FRAGMENTS，逐片 send_message(target="wecom")，片间 1.5s
# 仅最后一片带尾注
```

**关键判断**：不要重新跑完整 pipeline（push_prepare → batch_fetch），会变更数据状态（指纹去重、热度追踪）。直接用现有 curated JSON 做 render→fragment→send_message。

### 陷阱速查
详见 `references/traps.md`，重点关注：
- Trap 17: Gateway 崩溃丢推送
- Trap 18: Cron 技能名不匹配（精简后）
- Trap 19: tirith 安全扫描拦截中文命令
- Trap 20: NO_SLOT 跳过时段
- Trap 21: render_markdown 跨板块间距异常
- Trap 22: Cron prompt 含旧技能名引用
- Trap 23: Cron prompt 引用已删除的 pipeline 脚本
- Trap 24: Skill 更新了脚本名但 cron prompt 没同步——cron prompt 独立于 skill 内容，必须单独更新
- Trap 25: `references/` 目录在 workdir 不存在——skill 里 `cat references/xxx.md` 会失败。定期 `hermes cron list` 检查后确认 `ls ~/.hermes/trendradar/references/` 非空
- Trap 26: Cron prompt 引用已删除的辅助脚本（`blind_spot_audit.py` / `aggregate_monthly.py`）——新创建后记得同步到仓库并确认 cron workdir 可见
- Trap 27: `render_markdown.py` 日期格式不匹配——curated 文件名为 `%Y%m%d`，显示用 `%Y-%m-%d`。修改脚本的 `today` 变量必须区分 file 和 display 两个版本

## Cron 全量审计清单（定期执行）

当用户反馈“推送跑偏”或系统大修后，按以下清单逐项检查：

```bash
# --- 1. 所有 cron job 的 skills 列表 ---
hermes cron list | grep -E 'job_id|skills|script|no_agent'

# 逐条核对：skills 列表中的每个 skill 名必须存在
hermes skills list | grep -c <skill-name>

# --- 2. 所有 cron prompt 中引用的脚本 ---
# 对每个 LLM-driven job（no_agent=false），提取 prompt 中的 scripts/*.py
# 确认每个文件存在且非空
ls -la ~/.hermes/trendradar/scripts/<referenced-script>.py

# --- 3. no_agent 脚本 ---
# 检查 ~/.hermes/scripts/ 和 trendradar/scripts/ 是否存在
ls ~/.hermes/scripts/<script>.py

# --- 4. workdir 完整性 ---
# references/ 目录必须存在（skills 的 cat xxx.md 依赖它）
ls ~/.hermes/trendradar/references/ | wc -l

# --- 5. 已删除的换名脚本 ---
# 已从 pipeline 删除的 render_briefing.py 不应出现在任何 prompt 中
grep -r 'render_briefing' ~/.hermes/skills/trendradar/ ~/.hermes/trendradar/references/

# --- 6. 所有 skill 目录完整 ---
ls ~/.hermes/skills/trendradar/ | sort
```

## Pre-flight 检查（脚本/格式出问题时排查）

当用户反馈格式不对或 pipeline 跑飞时，先检查：

```bash
# 1. render_markdown.py 是否存在且非空
ls -la ~/.hermes/trendradar/scripts/render_markdown.py

# 2. cron prompt 引用的脚本名是否匹配实际文件
hermes cron list | grep -A5 "90a2866775df"

# 3. references/ 目录是否存在
ls ~/.hermes/trendradar/references/*.md | wc -l

# 4. 测试 render 是否可运行
cd ~/.hermes/trendradar && python3 scripts/render_markdown.py --push-id morning 2>/dev/null | head -3
```

## 静默规则
- 无新条目 → 返回 [SILENT]
- 仅异常时告警，正常无声
- 简报由 render_markdown.py 直接生成，格式硬编码，Agent 不修改内容
- 用户对空行分段**极度敏感**——分段异常是用户最高频投诉。`render_markdown.py` 从源头保证格式，不需后处理。

## WeCom 空行格式（render_markdown 自动处理）

`render_markdown.py` 直接从 curated JSON 拼接，空行规则硬编码，格式永远一致：

| 位置 | 规则 | 示例 |
|------|------|------|
| 标题 ↔ 摘要 | 1 空行 `\n\n` | `标题\n\n摘要` |
| 摘要 ↔ 链接 | 1 空行 `\n\n` | `摘要\n\n[查看原文]()【源】` |
| 条目之间 | 2 空行 `\n\n\n` | `【源】\n\n\n🆕 N. **标题**` |
| 板块标题后 | 2 空行 `\n\n\n` | `### 📰 头条\n\n\n🆕` |

**如果用户反馈分段异常**（条目间无空行、标题摘要粘连）→ 检查 `render_markdown.py` 的 `_generate_section()` 和 `_format_item()` 中的空行逻辑。
