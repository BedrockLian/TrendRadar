# TrendRadar 从零搭建指南

> 从全新 Hermes Agent 环境开始，一步步完成 TrendRadar 的安装、配置、测试和部署。

---

## 目录

1. [前置要求](#1-前置要求)
   1. [Hermes Agent](#11-hermes-agent)
   2. [Python 3.14t](#12-python-314t免费线程版)
   3. [企业微信机器人](#13-企业微信机器人)
   4. [API Key](#14-api-key)
   5. [代理配置（外媒数据源必需）](#15-代理配置外媒数据源必需)
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
export DEEPSEEK_API_KEY="sk-xxx...xxxx"
```

也支持通过 `.env` 文件加载（见 [4. 环境配置](#4-环境配置)）。

### 1.5 代理配置（外媒数据源必需）

TrendRadar 的部分 RSS 源（路透社、BBC、纽约时报、卫报等）被 GFW 封锁，直连无法访问。系统内置 **自动代理分流** 机制：国内源直连，外媒源走代理。

#### 1.5.1 安装 Mihomo（Clash Meta）

推荐使用 Mihomo（Clash Meta）作为代理客户端。WSL/Linux amd64 安装：

```bash
# 下载 Mihomo
MIHOMO_VER=$(curl -s https://api.github.com/repos/MetaCubeX/mihomo/releases/latest | grep tag_name | cut -d'"' -f4)
wget "https://github.com/MetaCubeX/mihomo/releases/download/${MIHOMO_VER}/mihomo-linux-amd64-${MIHOMO_VER}.gz"
gunzip mihomo-linux-amd64-${MIHOMO_VER}.gz
chmod +x mihomo-linux-amd64-${MIHOMO_VER}
mv mihomo-linux-amd64-${MIHOMO_VER} ~/.local/bin/mihomo
```

#### 1.5.2 配置订阅

创建配置目录并放入订阅配置文件：

```bash
mkdir -p ~/.config/mihomo
# 将你的订阅配置文件写入 ~/.config/mihomo/config.yaml
# 订阅链接通常可通过 curl 下载后 base64 解码获得
curl -sL "你的订阅链接" | base64 -d > /tmp/sub_decode.txt
# 使用转换工具或手动将代理节点写入 config.yaml
```

最小配置示例 (`~/.config/mihomo/config.yaml`)：

```yaml
port: 7890
socks-port: 7891
allow-lan: true
bind-address: "0.0.0.0"
mode: rule
log-level: warning
external-controller: 127.0.0.1:9090
dns:
  enable: true
  ipv6: false
  enhanced-mode: fake-ip
  # ... DNS 配置
proxies:
  # ... 你的代理节点列表
proxy-groups:
  # ... 策略组
rules:
  # ... 路由规则
```

> **注意**：`allow-lan: true` 和 `bind-address: "0.0.0.0"` 是必需的——TrendRadar 的 RSSHub Docker 容器需要从容器网络访问 Mihomo。

#### 1.5.3 注册 Systemd 服务

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/mihomo.service << 'EOF'
[Unit]
Description=Mihomo (Clash Meta) proxy
After=network.target

[Service]
Type=simple
ExecStart=%h/.local/bin/mihomo -d %h/.config/mihomo/
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now mihomo.service
systemctl --user status mihomo.service
```

验证代理可用：

```bash
curl -x http://127.0.0.1:7890 https://www.google.com
# 预期: HTTP 200/302（Google 可访问）
```

#### 1.5.4 TrendRadar 自动分流

TrendRadar 的 `trendradar/scripts/settings.py` 内置 `needs_proxy()` 函数：

- **直连**：`plink.anyfeeder.com`（国内中转）、`.cn` 域名
- **代理**：外媒直连 RSS（BBC/NYT/Guardian/SCMP 等）、RSSHub 路由（`localhost:1200`）
- **特殊**：BBC 被代理节点屏蔽，自动降级为直连

无需额外配置，代理地址默认为 `http://127.0.0.1:7890`，可通过环境变量 `TRENDRADAR_PROXY` 覆盖。

#### 1.5.5 RSSHub 容器代理（可选）

如果使用了 RSSHub 本地实例来获取外媒 RSS，需要给 RSSHub 容器配置代理。推荐使用 `undici.EnvHttpProxyAgent` 方案（Node.js 原生支持）：

```dockerfile
FROM diygod/rsshub:latest
RUN apt-get update && apt-get install -y ca-certificates
COPY proxy-fix.mjs /app/proxy-fix.mjs
```

配合启动命令：
```bash
docker run -d --name rsshub \
  -p 1200:1200 \
  -e HTTP_PROXY=http://host.docker.internal:7890 \
  -e HTTPS_PROXY=http://host.docker.internal:7890 \
  -e NODE_OPTIONS="--max-http-header-size=32768 --import /app/proxy-fix.mjs" \
  rsshub-image \
  dumb-init -- node --max-http-header-size=32768 --import /app/proxy-fix.mjs dist/index.mjs
```

`proxy-fix.mjs` 内容：
```javascript
import undici from 'undici';
const proxyUrl = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
if (proxyUrl) {
  const agent = new undici.EnvHttpProxyAgent();
  globalThis[Symbol.for('undici.globalDispatcher.1')] = agent;
}
```

#### 1.5.6 代理排障

```bash
# 1. Mihomo 是否运行
systemctl --user status mihomo.service

# 2. 端口监听
ss -tlnp | grep 7890

# 3. 测试代理
curl -x http://127.0.0.1:7890 https://www.google.com

# 4. TrendRadar 代理判断
cd ~/.hermes/trendradar
python3 -c "from trendradar.scripts.settings import needs_proxy; print(needs_proxy('https://feeds.bbci.co.uk/news/rss.xml'))"

# 5. 抓取时查看分流日志
python3 -m trendradar.scripts.fetch_feeds --push-id morning | grep 'FETCH'
# 输出示例: [FETCH] 41源（直连 9 + 代理 32）
```

---

## 2. 克隆仓库

```bash
git clone https://github.com/BedrockLian/TrendRadar.git ~/TrendRadar
cd ~/TrendRadar
```

目录结构：

```
TrendRadar/
├── .github/workflows/ci.yml       # CI 持续集成
├── deploy/                         # 一键部署
│   ├── hermes-scripts/             # Cron 脚本（→ $HERMES_HOME/scripts/）
│   ├── prompts/                    # Cron prompt 模板
│   └── one-key-setup.sh            # 部署入口
├── skills/trendradar/              # Hermes Agent 技能
│   ├── news-secretary/             # 日报推送（核心）
│   ├── self-healing/               # 自动体检
│   ├── report-generator/           # 报告生成
│   └── system-config/              # 系统配置
├── trendradar/                     # Python 包
│   ├── scripts/                    # 管线脚本（28 个）
│   ├── config/                     # 关键词/时段/翻译/兴趣配置
│   ├── migrations/                 # SQLite 数据库迁移引擎
│   ├── references/                 # 核心参考文档
│   ├── tests/                      # 测试用例（146+ 用例）
│   ├── pyproject.toml              # 包定义
│   └── requirements.txt            # 依赖清单
├── .gitignore
├── LICENSE
├── README.md
└── SETUP.md
```

> **注意**：skills/ 和 deploy/ 在仓库根目录，**不在** trendradar/ Python 包内。部署时复制到 Hermes 运行时路径。

### 2.1 部署到运行目录

TrendRadar 在 Hermes 中的运行时路径是 `~/.hermes/trendradar/`，即 **实时运行目录**。仓库和运行目录是独立的：

```bash
# 创建运行时目录（全新安装时）
mkdir -p ~/.hermes/trendradar

# 部署 Python 包
cp -r ~/TrendRadar/trendradar/* ~/.hermes/trendradar/

# 部署 Skills
cp -r ~/TrendRadar/skills/trendradar ~/.hermes/skills/

# 部署 Cron 脚本
cp ~/TrendRadar/deploy/hermes-scripts/*.py ~/.hermes/scripts/
```

<details>
<summary><b>仓库 vs 运行时目录说明（点开）</b></summary>

| 用途 | 路径 | 说明 |
|------|------|------|
| Git 发布仓库 | `~/TrendRadar/` | 代码版本管理 |
| 运行时目录 | `~/.hermes/trendradar/` | 实际运行，含数据/缓存/日志 |
| Hermes Skills | `~/.hermes/skills/trendradar/` | Hermes 技能存放位置 |
| Cron 脚本 | `~/.hermes/scripts/` | no_agent cron 执行位置 |

修改代码后同步到仓库：
```bash
cp -r ~/.hermes/trendradar/trendradar/scripts/* ~/TrendRadar/trendradar/scripts/
```

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
> 从仓库路径运行时，`PYTHONPATH` 需设为 `trendradar/` 的**父目录**（即 `/home/asus/.hermes`）。
> 从运行时目录（`~/.hermes/trendradar/`）则设 `PYTHONPATH` 为 `~/.hermes`。
> 详见 `skills/trendradar/system-config/SKILL.md`。

---

## 4. 环境配置

### 4.1 创建 `.env` 文件

TrendRadar 从环境变量或 `.env` 文件加载 API 凭证：

```bash
# 运行时目录
cat > ~/.hermes/trendradar/.env << 'EOF'
DEEPSEEK_API_KEY=***
DEEPSEEK_API_ENDPOINT=https://api.deepseek.com/v1/chat/completions
DEEPSEEK_MODEL=deepseek-chat
TRENDRADAR_LOG_LEVEL=INFO
EOF

# 安全加固：限制 .env 文件权限
chmod 600 ~/.hermes/trendradar/.env
```

或者直接设置环境变量：

```bash
export DEEPSEEK_API_KEY="sk-xxx...xxxx"
export PYTHONPATH=/home/asus/.hermes
export TRENDRADAR_HOME=~/.hermes/trendradar
export PYTHON_GIL=0
# 可选：翻译批量大小（默认 5，最大 20）
# export TRENDRADAR_TRANSLATE_BATCH_SIZE=10
# 可选：覆盖代理地址（默认 http://127.0.0.1:7890）
# export TRENDRADAR_PROXY=http://127.0.0.1:7890
```

### 4.2 数据目录

运行时目录会自动创建以下子目录：

```
~/.hermes/trendradar/
├── data/          # 指纹库(fingerprints.db)、推送日志、策展数据
├── cache/         # 原始抓取缓存、批量处理缓存
├── logs/          # 脚本运行日志
├── config/        # 配置
└── scripts/       # 管线脚本
```

首次运行时会自动创建。

### 4.3 兴趣偏好

```bash
cd ~/.hermes/trendradar
# 查看当前兴趣
python3 -m trendradar.scripts.interest_cli list

# 添加兴趣（加分+2）
python3 -m trendradar.scripts.interest_cli add "新能源汽车"

# 排除关键词（0分过滤）
python3 -m trendradar.scripts.interest_cli exclude "加密货币"
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
├── test_pipeline_e2e.py          # 编排器基础测试
├── test_pipeline_e2e_real.py     # 真实管线 E2E（11 用例，@integration）
├── test_ai_translate.py          # AI 翻译模块
├── test_ai_translate_boundary.py # BATCH_SIZE 边界 + 熔断（22 用例）
├── test_curate_and_push.py       # 策展 + 多样性惩罚 + 词边界匹配
├── test_fetch_feeds.py           # RSS 抓取
├── test_heat_tracker.py          # 热度追踪
├── test_push_prepare.py          # 推送准备（含 penalty/health 加载）
├── test_push_slot_detect.py      # 时段探测（±1 分钟精度）
├── test_render_markdown.py       # 渲染格式
├── test_sanity_check.py          # 发布前拦截
├── test_record_and_common.py     # 公共模块 + 指纹记录
└── test_track_events.py          # 事件追踪
```

> 初始化时因 SQLite 数据库尚为空白，部分测试写入后即通过。

### 6.3 常见测试问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `ModuleNotFoundError: trendradar` | PYTHONPATH 缺失 | `export PYTHONPATH=$TRENDRADAR_HOME` |
| `DEEPSEEK_API_KEY not found` | API key 未配置 | 检查 `.env`（chmod 600）或环境变量 |
| RSS 相关测试超时 | 外网不可达 | 确认网络连通性 / `TIMEOUT_SEC` 调大 |

---

## 7. 部署 Hermes Skills

TrendRadar 的功能通过 Hermes Skill 系统暴露给 Agent。

### 7.1 复制 Skills 到 Hermes

Skills 在仓库的 `skills/trendradar/` 目录（不是 `trendradar/skills/`）：

```bash
# 一键部署所有技能
cp -r ~/TrendRadar/skills/trendradar ~/.hermes/skills/

# 验证
ls ~/.hermes/skills/trendradar/
# 应看到: news-secretary  report-generator  self-healing  system-config
```

> **注意**：旧版 skills 在 `trendradar/skills/` 内，v2026-06-29 重构后移至根目录 `skills/trendradar/`。

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

### 7.3 部署外围脚本（Cron 脚本）

```bash
# 从 deploy/ 目录复制
cp ~/TrendRadar/deploy/hermes-scripts/trendradar_health_check.py ~/.hermes/scripts/
cp ~/TrendRadar/deploy/hermes-scripts/trendradar_maintenance.py ~/.hermes/scripts/
cp ~/TrendRadar/deploy/hermes-scripts/delivery_watchdog.py ~/.hermes/scripts/
chmod +x ~/.hermes/scripts/trendradar_health_check.py
chmod +x ~/.hermes/scripts/trendradar_maintenance.py
chmod +x ~/.hermes/scripts/delivery_watchdog.py
```

---

## 8. 注册定时任务

### 8.1 启动 Gateway

```bash
hermes gateway install
hermes gateway status
# ✓ Gateway process running
```

### 8.2 注册 LLM Cron Jobs

```bash
# 日报推送（早/午/晚 三段）
hermes cron create "0 9,12,21 * * *" \
  --name "TrendRadar 日报推送" \
  --skill news-secretary \
  --deliver local

# 周报推送（每周一 09:30）
hermes cron create "30 9 * * 1" \
  --name "TrendRadar 周报推送" \
  --skill report-generator \
  --deliver wecom

# 月度报告（每月 1 日 09:00）
hermes cron create "0 9 1 * *" \
  --name "TrendRadar 月度报告" \
  --skill report-generator \
  --deliver wecom
```

### 8.3 注册 No-Agent Cron Jobs

```bash
# 自动体检（每日 15:00）
hermes cron create "0 15 * * *" \
  --name "TrendRadar 自动体检" \
  --script trendradar_health_check.py \
  --no-agent \
  --deliver wecom

# 每日维护（凌晨 03:00）
hermes cron create "0 3 * * *" \
  --name "TrendRadar 每日维护" \
  --script trendradar_maintenance.py \
  --no-agent \
  --deliver local

# 推送看门狗（09:05 / 12:05 / 21:05，管线完成后 5 分钟）
hermes cron create "5 9,12,21 * * *" \
  --name "TrendRadar 推送看门狗" \
  --script delivery_watchdog.py \
  --no-agent \
  --deliver wecom
```

---

## 9. 首次运行 & 验证

```bash
# 手动触发一次日报管线
cd ~/.hermes/trendradar
export TRENDRADAR_HOME=$PWD
export PYTHONPATH=$PWD
unset PYTHON_GIL

python3.14t -m trendradar.scripts.pipeline_orchestrator --push-id morning --output text

# 查看健康检查
python3 "$HERMES_HOME/scripts/trendradar_health_check.py"
```

---

## 10. 附录：常用操作

### 一键部署

```bash
curl -sSL https://raw.githubusercontent.com/BedrockLian/TrendRadar/main/deploy/one-key-setup.sh | bash
```

### 手动同步运行时代码到仓库

```bash
SRC=~/.hermes/trendradar/trendradar
DST=~/TrendRadar/trendradar

# 同步脚本
cp $SRC/scripts/*.py $DST/scripts/

# 同步配置
cp $SRC/config/* $DST/config/

# 同步迁移
cp $SRC/migrations/* $DST/migrations/
```

### 推送变更到 GitHub

```bash
cd ~/TrendRadar
git add -A
git commit -m "描述你的改动"
git push origin main
```
