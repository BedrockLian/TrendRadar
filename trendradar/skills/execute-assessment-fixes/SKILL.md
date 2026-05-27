---
name: execute-assessment-fixes
slug: execute-assessment-fixes
version: 1.0.0
description: 执行 Qwen 独立评估报告的修复指南 — 逐步骤修复 → 验证 → 提交推送
author: Hermes Agent
tags: [trendradar, qa, fix, assessment]
metadata:
  hermes:
    companion_skills: [system-config]
---

## 触发

用户要求执行外部代码评估报告的修复建议时。报告通常来自 Qwen 3.7 Max，位于 `D:\下载\TrendRadar-main\trendradar\references\$NAME.md`。

## 执行流程

### 0. 准备 Qwen 审计提示词（如需）

如果还没有审计报告，先准备提示词让 Qwen 独立审查代码库：

1. 复制模板：`templates/qwen-audit-prompt.md`（8 维度自由扫描模板）
2. 按需调整代码库路径和核心链路描述
3. 将提示词发给 Qwen，等待产出报告

报告应包含按严重度（🔴/🟡/🟢）分级的问题列表，每行格式：
```
[严重度] 文件名:行号 — 问题描述 — 触发条件
```

### 1. 读取 + 分类报告

将 Windows 路径转为 WSL 路径：`D:\\下载\\` → `/mnt/d/下载/`。用 `read_file` 读取完整报告。

**如果报告项目超过 15 项**（Qwen 自由扫描常产出 40-50 项），先分类并让用户选择修复范围：

- 按严重度分组：🔴 致命 / 🟡 重要 / 🟢 小问题
- 按影响面分组：A 组（致命逻辑）/ B 组（鲁棒性）/ C 组（卫生）
- 用 `clarify` 工具给出编号选项（修全部/只修🔴/修A组/修A+B组）

用户偏好直接决策——给编号他们秒回。不要过度解释每组的内容。

### 2. 建立 todo 追踪

按用户选择的修复范围建 `todo` 列表，按文件/影响面分组（非逐一问题列出），方便批量推进。

### 3. 批量修复（关键优化）

**单个 patch() 调用不适合大规模修复。** 推荐两种并行模式：

**A. delegate_task 并行**（当修复涉及独立领域时）：
```
Subagent 1: 测试编写 → E2E + 边界测试
Subagent 2: 文档合并 → references 精简 + SKILL 更新
主 Agent: 代码修复 → 串联改动同一文件
```
每个子 agent 传入完整上下文（路径、PYTHONPATH 注意事项、已有测试模式）。

**B. execute_code 批量 patch()**（当修复涉及多个文件但无依赖时）：
```python
from hermes_tools import patch
# 一次性发 3-7 个 patch() 调用，比逐个调用快 5x
patch(path="a.py", old_string="...", new_string="...")
patch(path="b.py", old_string="...", new_string="...")
# ...
```
此模式对 settings.py / batch_fetch.py 等独立文件改动最有效。

### 4. 验证：永远假设 Qwen 可能误判

**必须先确认问题真实存在，再修。** Qwen 在没有实际执行代码的情况下做静态分析，可能：

- **精度假设错误**：报告 `push_slot_detect.py 秒精度 bug`，但代码实际比较的是分钟整数（`now.hour, now.minute`），不存在秒精度问题
- **Schema 假设错误**：健康检查假设 `sources.json` 是 `dict→list` 结构，但实际是 `{"data_sources": [...]}`
- **路径理解错误**：认为 `/tmp` 在 Windows 不可用，但实际运行环境是 WSL/Linux

验证方法：
1. `read_file` 确认行号附近的代码和报告描述是否匹配
2. 如果有测试覆盖，先跑测试看是否 fail
3. 修复后立即跑 `pytest` 确认不引入回归

### 5. 修复-测试-提交循环

每批修复完成后：
```bash
cd /home/asus/TrendRadar/trendradar && \
PYTHONPATH=/home/asus/.hermes/trendradar pytest tests/ -q --tb=line
```
测试通过后才 commit。如果测试失败，定位并修复后再 push——绝不在测试失败时提交。

### 4. 全量验证

所有步骤完成后，跑报告中的全量验证命令。至少包括：
- 语法检查：`python3 -c "import trendradar.scripts.xxx"`
- 关键字段确认：grep 检查修复是否在代码中
- 副本一致性：MD5 比对同名文件

### 5. 提交推送

```bash
cd ~/TrendRadar && git add -A && git commit -m "描述"
```

推送时优先直连，若 remote 有新提交（push rejected），执行 rebase 而非 merge：

```bash
TOKEN=$(gh auth token) && \
GIT_TERMINAL_PROMPT=0 git -c credential.helper='' -c http.proxy= -c https.proxy= \
pull --rebase "https://BedrockLian:${TOKEN}@github.com/BedrockLian/TrendRadar.git" main
```

冲突解决后继续：

```bash
git add <resolved_files> && GIT_EDITOR=true git rebase --continue
```

最后推送：

```bash
TOKEN=$(gh auth token) && \
GIT_TERMINAL_PROMPT=0 git -c credential.helper='' -c http.proxy= -c https.proxy= \
push "https://BedrockLian:${TOKEN}@github.com/BedrockLian/TrendRadar.git" main
```

**推送优先级**（详见 system-config skill）：
- 优先直连（`http.proxy=`）
- 超时时走代理（`http.proxy=http://127.0.0.1:7890`）
- 代理 TLS 故障时回退直连

### 6. 同步运行时

```bash
rsync -av --delete --exclude='.git' --exclude='__pycache__' --exclude='.pytest_cache' \
  --exclude='.env' --exclude='cache/' --exclude='data/' --exclude='logs/' \
  --exclude='mail_queue/' --exclude='output/' --exclude='skills/' --exclude='*.pyc' \
  /home/asus/TrendRadar/trendradar/ /home/asus/.hermes/trendradar/

rsync -av --delete --exclude='__pycache__' \
  /home/asus/TrendRadar/trendradar/skills/ /home/asus/.hermes/skills/trendradar/
```

## 常见报告类型

| 报告名模式 | 范围 | 典型修复数 |
|-----------|------|----------|
| `independent-assessment-*.md` | 代码+文档+Skill 交叉审计 | 7-8 步 |
| `skill-reference-assessment-*.md` | Skill & References 文档 | 8 步 |
| `references-consistency-guide.md` | References 一致性治理 | 4-6 步 |

## 模板

| 文件 | 用途 |
|------|------|
| `templates/qwen-audit-prompt.md` | Qwen 独立代码审查提示词（8 维度自由扫描，结构化输出） |

## 陷阱

- **patch 工具中的转义问题**：在 new_string 中使用 f-string 时不要用 `\"` 转义（会被 patch 工具二次转义）。直接用正常引号。
- **Git push rejected → rebase 而非 force push**：远程有更新的提交时，用 `git pull --rebase`。冲突解决后 `git add` + `GIT_EDITOR=true git rebase --continue`，再 push。不要 force push 覆盖远程其他人的工作。
- **Qwen 可能误判**：静态分析无法执行代码。报告的"精度 bug""schema 错误"可能基于错误假设。永远先用 `read_file` 验证问题确实存在于报告描述的行号附近，再决定是否修复。本 session 实际案例：Qwen 报告 push_slot_detect.py 有"秒精度 bug"，但代码比较的 `now.hour, now.minute` 已经是分钟整数——误判。
- **SKILL.md 修改后必须同步 Skill 副本**：根 references/ 文件改了，Skill references/ 的同名文件也要同步，否则 Agent 读到旧版本。
- **删除 Skill references 前先复制到根**：如果要消除双份副本，先把内容归集到根 references/，再删 Skill 副本。
- **版本标记会导致 MD5 漂移**：为 references 文件加 `<!-- version: -->` 标记后，所有同名副本的 MD5 都会变。记得同步。
