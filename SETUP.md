# TrendRadar 从零搭建指南

> 从全新 Hermes Agent 环境开始，一步步完成 TrendRadar 的安装、配置、测试和部署。

---

## 目录

1. [前置要求](#1-前置要求)
2. [克隆仓库](#2-克隆仓库)
3. [安装依赖](#3-安装依赖)
4. [环境配置](#4-环境配置)
5. [数据库初始化](#5-数据库初始化)
6. [测试验证](#6-测试验证)
7. [部署 Hermes Skills](#7-部署-hermes-skills)
8. [注册定时任务](#8-注册定时任务)
9. [首次运行 & 验证](#9-首次运行--验证)
10. [附录：常用操作](#10-附录常用操作)

---

## 1. 前置要求

### 1.1 Hermes Agent

TrendRadar 深度依赖 Hermes Agent 的 cron 调度、技能系统和企业微信推送。需要先安装并运行 Hermes Agent：

```bash
# 参考 https://hermes-agent.nousresearch.com/docs 安装
# 确保 hermes CLI 可用
hermes --version
```

### 1.2 Python 3.14t（免费线程版）

TrendRadar 使用 Python 3.14 free-threaded 构建（无 GIL，多并发抓取性能更优）。推荐编译安装：

```bash
# 检查是否已安装
python3.14t --version

# 如需安装，参考 skills/trendradar/news-secretary/references/free-threaded-build.md
```

> 如果使用普通 Python 3.12+ 也可以，但需要调整 cron prompt 中的解释器路径。

### 1.3 企业微信机器人

推送目标为企业微信（WeCom），需要：

- 已创建企业微信机器人
- Hermes Agent 已配置 WeCom 平台并连接成功
- `hermes gateway status` 确认 WeCom 已连接

### 1.4 API Key

TrendRadar 使用 DeepSeek API 进行 AI 策展和翻译。需要有：

```bash
export DEEPSEEK_API_KEY="sk-xxxxxxxxxxxxxxxx"
```

也支持通过 `.env` 文件加载（见 [4. 环境配置](#4-环境配置)）。

---

## 2. 克隆仓库

```bash
# 克隆私有仓库（需要 GitHub 认证）
git clone https://github.com/BedrockLian/TrendRadar.git ~/TrendRadar
cd ~/TrendRadar
```

目录结构：

```
TrendRadar/
├── trendradar/                        # 核心 Python 包
│   ├── scripts/                       # 管线脚本（23 个）
│   ├── config/                        # 关键词/时段/翻译/兴趣配置
│   ├── migrations/                    # SQLite 数据库迁移引擎
│   ├── skills/                        # Hermes Agent 技能定义
│   │   ├── news-secretary/            # 日报推送技能（核心）
│   │   ├── self-healing/              # 自动体检/自修复
│   │   ├── performance-optimizer/     # 偏好收敛优化
│   │   ├── system-config/             # 系统配置速查
│   │   ├── weekly-report/             # 周报深度研判
│   │   └── monthly-report/            # 月报全景分析
│   ├── references/                     # 参考文档（26 份）
│   ├── tests/                         # 测试用例（90+）
│   ├── pyproject.toml                 # 项目元数据/依赖
│   └── requirements.txt               # 依赖清单
├── hermes-scripts/                    # Hermes 外围脚本
│   ├── trendradar_health_check.py     # 自动体检（15项检查）
│   ├── trendradar_maintenance.py      # 每日维护（备份+清理）
│   └── delivery_watchdog.py           # 推送降级看门狗
├── .gitignore
├── LICENSE
└── README.md
```

### 2.1 部署到运行目录

TrendRadar 在 Hermes 中的运行时路径是 `~/.hermes/trendradar/`，即 **实时运行目录**。仓库和运行目录是独立的：

```bash
# 创建运行时目录（全新安装时）
mkdir -p ~/.hermes/trendradar

# 也可以创建符号链接来直接使用仓库
ln -sf ~/TrendRadar/trendradar ~/.hermes/trendradar
```

<details>
<summary><b>仓库 vs 运行时目录说明（点开）</b></summary>

| 用途 | 路径 | 说明 |
|------|------|------|
| Git 发布仓库 | `~/TrendRadar/` | 代码版本管理，只追踪源文件 |
| 运行时目录 | `~/.hermes/trendradar/` | 实际运行，含运行时数据（DB/缓存/日志） |
| Hermes Skills | `~/.hermes/skills/trendradar/` | Hermes 技能存放位置 |

修改代码后，需要同步到仓库：`cp -r ~/.hermes/trendradar/scripts/ ~/TrendRadar/trendradar/`

</details>

---

## 3. 安装依赖

### 3.1 Python 包

```bash
# 方式 A：editable install（推荐，直接使用仓库路径）
cd ~/TrendRadar/trendradar
python3.14t -m pip install -e .

# 方式 B：仅安装依赖
python3.14t -m pip install -r requirements.txt

# 方式 C：完整开发依赖
python3.14t -m pip install -r requirements-dev.txt
```

### 3.2 免费线程兼容修复（python3.14t 必须）

python3.14t 的 PyPI wheel 在某些平台上不完整，需要手动补装：

```bash
python3.14t -m pip install feedparser zstandard
```

### 3.3 验证安装

```bash
cd ~/TrendRadar/trendradar
PYTHONPATH=/home/asus/.hermes python3.14t -c "
from trendradar.scripts.common import gen_run_id
print('ok:', gen_run_id())
"
```

> ⚠️ **PYTHONPATH 陷阱**：`trendradar/` 自身有 `__init__.py`，即它是 Python 包。
> 必须设置 `PYTHONPATH` 为其**父目录**（即 `/home/asus/.hermes`），而不是项目根目录本身。
> 详见 `trendradar/skills/system-config/SKILL.md`。

---

## 4. 环境配置

### 4.1 创建 `.env` 文件

TrendRadar 从环境变量或 `.env` 文件加载 API 凭证：

```bash
# 运行时目录
cat > ~/.hermes/trendradar/.env << 'EOF'
DEEPSEEK_API_KEY=sk-your-key-here
DEEPSEEK_API_ENDPOINT=https://api.deepseek.com/v1/chat/completions
DEEPSEEK_MODEL=deepseek-chat
TRENDRADAR_LOG_LEVEL=INFO
EOF

chmod 600 ~/.hermes/trendradar/.env
```

或者直接设置环境变量：

```bash
export DEEPSEEK_API_KEY="sk-xxxxxxxxxxxxxxxx"
export PYTHONPATH=/home/asus/.hermes
export PYTHON_GIL=0
```

### 4.2 数据目录

运行时目录会自动创建以下子目录：

```
~/.hermes/trendradar/
├── data/          # 指纹库(fingerprints.db)、推送日志、策展数据
├── cache/         # 原始抓取缓存、批量处理缓存
├── logs/          # 脚本运行日志
├── config/        # 配置（已入库）
└── scripts/       # 管线脚本（已入库）
```

首次运行时会自动创建。

### 4.3 兴趣偏好

```bash
cd ~/.hermes/trendradar
# 查看当前兴趣
python3 scripts/interest_cli.py list

# 添加兴趣（加分+2）
python3 scripts/interest_cli.py add "新能源汽车"

# 排除关键词（0分过滤）
python3 scripts/interest_cli.py exclude "加密货币"
```

---

## 5. 数据库初始化

TrendRadar 使用 SQLite 作为数据存储。首次使用需要初始化 schema：

```bash
cd ~/.hermes/trendradar
PYTHONPATH=/home/asus/.hermes python3.14t -c "
from trendradar.migrations.runner import migrate
from pathlib import Path
v = migrate(Path('data/fingerprints.db'))
print(f'Database migrated to v{v}')
"
```

输出示例：
```
Applied migration 001_initial.sql
Database migrated to v1
```

初始化后生成：
- `data/fingerprints.db` — 包含 `fingerprints`（去重指纹）和 `heat_tracker`（热度追踪）两张表

---

## 6. 测试验证

### 6.1 运行测试套件

```bash
cd ~/TrendRadar/trendradar

# 运行全部测试
python3.14t -m pytest -v

# 仅运行烟雾测试（快速验证）
python3.14t -m pytest -v -m smoke

# 排除慢速测试
python3.14t -m pytest -v -m "not slow"
```

### 6.2 测试预期

```
tests/
├── test_ai_translate.py          # AI 翻译模块
├── test_batch_fetch.py           # 批量抓取
├── test_curate_and_push.py       # 策展和推送逻辑
├── test_fetch_feeds.py           # RSS 抓取
├── test_heat_tracker.py          # 热度追踪
├── test_push_prepare.py          # 推送准备
├── test_push_slot_detect.py      # 时段探测
└── test_record_and_common.py     # 公共模块 + 指纹记录
```

> 初始化时因 SQLite 数据库尚为空白，部分测试写入后即通过。

### 6.3 常见测试问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `ModuleNotFoundError: trendradar` | PYTHONPATH 缺失 | `export PYTHONPATH=/home/asus/.hermes` |
| `DEEPSEEK_API_KEY not found` | API key 未配置 | 检查 `.env` 文件或环境变量 |
| RSS 相关测试超时 | 外网不可达 | 确认网络连通性 / `TIMEOUT_SEC` 调大 |

---

## 7. 部署 Hermes Skills

TrendRadar 的功能通过 Hermes Skill 系统暴露给 Agent。

### 7.1 复制 Skills 到 Hermes

```bash
# 逐个部署
cp -r ~/TrendRadar/trendradar/skills/news-secretary ~/.hermes/skills/trendradar/
cp -r ~/TrendRadar/trendradar/skills/self-healing ~/.hermes/skills/trendradar/
cp -r ~/TrendRadar/trendradar/skills/performance-optimizer ~/.hermes/skills/trendradar/
cp -r ~/TrendRadar/trendradar/skills/system-config ~/.hermes/skills/trendradar/
```

### 7.2 部署技能评估框架（可选）

TrendRadar 集成了 Anthropic skill-creator 框架，可对技能进行定量评估（with/without 对比 + 评分）：

```bash
# 如果已拉取（通过本指南首次设置时需手动拉取）
hermes skills list | grep anthropic-skill-creator
```

该框架提供：
- 9 组 test case × 2（with/without）并行跑 → 评分 → 聚合报告
- 评分 Agent（grader）、盲比 Agent（comparator）、分析 Agent（analyzer）
- Web 评估查看器

> 拉取方式：参考 https://github.com/anthropics/claude-plugins-official/tree/main/plugins/skill-creator

### 7.3 部署外围脚本

```bash
cp ~/TrendRadar/hermes-scripts/trendradar_health_check.py ~/.hermes/scripts/
cp ~/TrendRadar/hermes-scripts/trendradar_maintenance.py ~/.hermes/scripts/
cp ~/TrendRadar/hermes-scripts/delivery_watchdog.py ~/.hermes/scripts/
chmod +x ~/.hermes/scripts/trendradar_health_check.py
chmod +x ~/.hermes/scripts/trendradar_maintenance.py
chmod +x ~/.hermes/scripts/delivery_watchdog.py
```

### 7.4 验证部署

```bash
# 确认 skills 可被 Hermes 加载
hermes skills list | grep trendradar

# 预期输出：
# news-secretary          聚合多RSS源+推送Markdown简报至企业微信
# self-healing            自动体检TrendRadar各组件
# performance-optimizer   渐进优化日报质量与推送偏好
# weekly-report           每周一深度趋势周报
# monthly-report          每月1日聚合月报
# system-config           系统配置速查
```

## 8. 注册定时任务

TrendRadar 的完整功能依赖 7 个 cron 定时任务，构成三层推送体系：

| 层级 | 任务 | 频率 | 模型 | 产出 |
|------|------|------|------|------|
| 🗞️ 日报 | 推送管线 | 日3次 (9/12/21) | Flash | 24/32/24 条简报 + [晚间] 3×Pro深度分析 |
| 📆 周报 | 深度趋势 | 每周一 09:30 | Pro | 5板块×3-5主题 + 信息茧房突围 |
| 📊 月报 | 全景复盘 | 每月1日 09:00 | Pro | 热度Top10 + 跨域趋势 + 下月预测 |
| ⚙️ 运维 | 优化/体检/维护/看门狗 | 每日/按需 | no_agent | 质量评分/健康检查/备份/告警 |

### 8.1 日报推送（核心）

每天 09:00 / 12:00 / 21:00 执行，负责 RSS 抓取 → AI 策展 → 简报渲染 → 微信推送。

```bash
hermes cron create \
  --name "TrendRadar 日报推送（早/午/晚）" \
  --schedule "0 9,12,21 * * *" \
  --skills news-secretary,multi-search-engine \
  --model deepseek-v4-flash:provider=deepseek \
  --workdir ~/.hermes/trendradar \
  --toolsets terminal,web,delegation \
  --deliver wecom \
  --repeat forever
```

### 8.2 周报推送（每周一）

每周一 09:30 用 Pro 模型执行深度趋势研判。在日报累积数据基础上，聚合 7 天 curated JSON，识别跨板块趋势，运行信息茧房突围检测。

**数据源：**
- 近 7 天 `data/curated_*.json` 精选结果
- `scripts/blind_spot_audit.py --days 7` 偏好盲区检测
- `deep-research-cli` 六步协议逐主题搜索验证

**输出结构：** 五大板块 × 3-5 主题，每主题含事件链→数据支撑→影响分析→展望→置信度→对立视角。另附「🌱 本周意外发现」反偏好板块。

```bash
hermes cron create \
  --name "TrendRadar 周报推送（深度研究员）" \
  --schedule "30 9 * * 1" \
  --skills multi-search-engine,deep-research-cli,weekly-report \
  --model deepseek-v4-pro:provider=deepseek \
  --workdir ~/.hermes/trendradar \
  --toolsets terminal,web \
  --deliver wecom \
  --repeat forever
```

### 8.3 月报推送（每月1日）

每月 1 日 09:00 用 Pro 模型执行全景复盘。在 4 期周报数据基础上，聚合月度统计，生成热度 Top10 和趋势研判。

**数据源（三层聚合）：**
- 近 4 周周报（叙事骨架）
- `scripts/aggregate_monthly.py` 月度量化统计
- `deep-research-cli` 深度搜索验证（≤10 次 web_search）

**输出结构：** 月度概览 → 热度 Top10 → 各板块深度 → 趋势研判（跨域交叉+下月预测）→ 推送批次追溯

```bash
hermes cron create \
  --name "TrendRadar 月度趋势报告" \
  --schedule "0 9 1 * *" \
  --skills multi-search-engine,deep-research-cli,monthly-report \
  --model deepseek-v4-pro:provider=deepseek \
  --workdir ~/.hermes/trendradar \
  --toolsets terminal,web \
  --deliver wecom \
  --repeat forever
```

### 8.4 日报推送后优化器

```bash
hermes cron create \
  --name "TrendRadar 性能优化器" \
  --schedule "15 21 * * *" \
  --skills performance-optimizer,multi-search-engine,news-secretary \
  --workdir ~/.hermes/trendradar \
  --toolsets terminal,file,web \
  --deliver wecom \
  --repeat forever
```

### 8.5 每日维护（静默）

```bash
hermes cron create \
  --name "TrendRadar 每日维护（备份+清理）" \
  --schedule "0 3 * * *" \
  --script trendradar_maintenance.py \
  --no-agent \
  --deliver wecom \
  --repeat forever
```

### 8.6 自动体检（每日 15:00）

```bash
hermes cron create \
  --name "TrendRadar 自动体检" \
  --schedule "0 15 * * *" \
  --script trendradar_health_check.py \
  --no-agent \
  --deliver wecom \
  --repeat forever
```

### 8.7 降级看门狗（可选）

监测 WeCom 推送投递健康，异常时通过 QQ 邮箱告警。静默运行，无异常不输出。

```bash
hermes cron create \
  --name "TrendRadar 推送降级看门狗" \
  --schedule "0 10,14,22 * * *" \
  --script delivery_watchdog.py \
  --no-agent \
  --deliver local \
  --repeat forever
```

### 8.8 验证所有任务

```bash
hermes cron list
```

预期输出 6~7 个任务（不含可选看门狗为 6 个），状态均为 `scheduled`。

---

## 9. 首次运行 & 验证

### 9.1 手动运行体检

```bash
cd ~/.hermes/trendradar
python3.14t ~/.hermes/scripts/trendradar_health_check.py
```

预期输出（健康状态）：
```
# Hermes 趋势雷达 · 自动体检报告

**时间:** 2026-05-23 15:00:00

### 🔧 自动修复
- ✅ 已执行数据库迁移至 v1

---
🟢 **状态: 健康**
```

### 9.2 手动触发日报推送

```bash
hermes cron run 90a2866775df
```

### 9.3 查看近期推送

推送结果会以简报形式发送到企业微信。也通过体检报告追踪推送状态。

---

## 10. 附录：常用操作

### 10.1 修改配置后同步到仓库

```bash
# 同步脚本
cp -r ~/.hermes/trendradar/scripts/ ~/TrendRadar/trendradar/

# 同步参考文档
cp -r ~/.hermes/trendradar/references/ ~/TrendRadar/trendradar/

# 同步配置和迁移
cp -r ~/.hermes/trendradar/config/ ~/TrendRadar/trendradar/
cp -r ~/.hermes/trendradar/migrations/ ~/TrendRadar/trendradar/

# 同步技能（6个）
cp -r ~/.hermes/skills/trendradar/ ~/TrendRadar/trendradar/skills/

# 同步外围脚本
cp ~/.hermes/scripts/trendradar_health_check.py ~/TrendRadar/hermes-scripts/
cp ~/.hermes/scripts/trendradar_maintenance.py ~/TrendRadar/hermes-scripts/
cp ~/.hermes/scripts/delivery_watchdog.py ~/TrendRadar/hermes-scripts/

# 提交推送
cd ~/TrendRadar
git add -A
git commit -m "<描述>"
git push
```

### 10.2 故障排查

| 症状 | 排查 |
|------|------|
| 日报无推送 | 运行体检 → 检查 `PYTHONPATH` → 确认 API key 有效 |
| 推送内容为空 | 检查 RSS 源连通性 → 检查 `sources.json` 是否存在 |
| 数据库异常 | 删除 `data/fingerprints.db` → 重新初始化 |
| import 错误 | `export PYTHONPATH=/home/asus/.hermes` |
| cron 不触发 | `hermes cron list` 检查状态 → 确认 Hermes 网关运行中 |

### 10.3 版本升级

```bash
cd ~/TrendRadar
git pull
cp -r trendradar/scripts/ ~/.hermes/trendradar/
cp -r trendradar/references/ ~/.hermes/trendradar/
cp -r trendradar/skills/ ~/.hermes/skills/trendradar/
cp hermes-scripts/* ~/.hermes/scripts/
# 重新安装依赖（如有变更）
cd ~/.hermes/trendradar && python3.14t -m pip install -r requirements.txt
```

### 10.4 卸载

```bash
# 删除定时任务
hermes cron remove 90a2866775df
hermes cron remove c20e2c82deda
hermes cron remove 718b663e8c04
hermes cron remove 68db70cd8556
hermes cron remove c987a2883174

# 删除运行时数据
rm -rf ~/.hermes/trendradar
rm -f ~/.hermes/scripts/trendradar_health_check.py
rm -f ~/.hermes/scripts/trendradar_maintenance.py

# 删除技能
rm -rf ~/.hermes/skills/trendradar

# ⚠️ 以下两行默认注释掉，防止误删代码历史
# 如需彻底清除，取消注释手动执行：
# rm -rf ~/TrendRadar                    # 删除 git 仓库克隆
# rm -rf /mnt/c/Users/ASUS/Documents/TrendRadar-System  # 删除 Windows 文档备份
```
