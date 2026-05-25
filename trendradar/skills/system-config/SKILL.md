---
name: system-config
slug: system-config
version: 2.6.0
description: TrendRadar 项目路径、PYTHONPATH、Python 解释器、环境变量速查。
author: Hermes Agent
metadata:
  hermes:
    tags: [trendradar, config, setup, pythonpath]
---

## 项目结构

- **源码/运行时**: `~/.hermes/trendradar/`（Python 包，有 `__init__.py`）
- **Git 发布仓库**: `~/TrendRadar/`
- **从零搭建指南**: `~/TrendRadar/SETUP.md`

## Hermes 关键路径

| 组件 | 路径 |
|------|------|
| 主配置 | `~/.hermes/config.yaml` |
| Cron 配置 | `~/.hermes/cron/jobs.json` |
| 技能目录 | `~/.hermes/skills/trendradar/` |
| 运行日志 | `~/.hermes/logs/agent.log` / `errors.log` |

## Cron 任务

运行 `hermes cron list` 查看当前所有任务。
日报/周报/月报/性能优化器为 LLM 驱动（加载对应 skill），体检/维护/看门狗为 no_agent 脚本模式。

### Cron prompt 陷阱

LLM 驱动型 cron 的 final response 指令必须有**严格的「不加前缀后缀」约束**，否则 LLM 会自动添加"所有分析均已完成格式化""以下是最新报告"等外包文字。两条铁律：

1. **简报输出**：`将 JSON 中的 briefing 字段作为 final response 输出（不加任何前缀/后缀/说明文字，只输出 briefing 内容本身）`
2. **深度分析输出**：`作为独立 final response 分别输出（每条单独一条消息，不拼接在简报末尾，不跟在简报后面）`
3. **优化报告输出**：`只输出报告内容本身，不加任何前缀/后缀/说明文字`

否则 LLM 会自动添加元描述文字，破坏 WeCom 推送格式。

## PYTHONPATH（关键陷阱）

`trendradar/` 目录自身有 `__init__.py`，是 Python 包。**必须将父目录加入 PYTHONPATH**：

```python
# ✅ 正确
sys.path.insert(0, str(TR.parent))   # /home/asus/.hermes/
env['PYTHONPATH'] = str(TR.parent)   # 使 from trendradar.scripts.xxx import * 正常

# ❌ 错误
sys.path.insert(0, str(TR))          # /home/asus/.hermes/trendradar/ — import 失败
```

cron prompt 和 subprocess 调用必须 `export PYTHONPATH=/home/asus/.hermes`。

## Python 解释器

- `python3.14t`（free-threaded，多并发抓取性能更优）
- 需 `export PYTHON_GIL=0`
- 依赖: `pip install feedparser zstandard`

## 同步到 Git 仓库

三处路径需同步：Hermes 运行时 (`~/.hermes/`)、Hermes 中心脚本 (`~/.hermes/scripts/`)、Git 发布仓 (`~/TrendRadar/`)。

详细步骤 + 验证 + 常见遗漏表见 `references/repo-sync.md`。

### 关键注意事项

- **三处一致**：技能目录名、SKILL.md `name:` 字段、cron 的 `skills:` 列表必须一致
- **统一 references 目录**：所有 skill 共享 `references/`（central），无 per-skill `references/` 子目录。同步后运行 `diff -rq ~/.hermes/skills/trendradar/ ~/TrendRadar/trendradar/skills/` 检查不一致（尤其驻留在 skill 目录下的旧 `references/` 残留）
- **依赖文件**：`pyproject.toml` 修改后必须同步 `requirements.txt`（手动维护）。用 `diff <(grep...) <(grep...)` 检查一致性
- **脚本两处存在**：`trendradar_*.py` 同时存在于 `~/.hermes/scripts/`（cron 加载）和 `~/TrendRadar/hermes-scripts/`（仓库发布）。改脚本后两处都要更新

### 同步后引用验证

同步完 reference 文件后，验证所有 SKILL.md 的 `references/xxx.md` 引用确实指向存在的文件：

```python
import os, re
ref_dir = '/home/asus/.hermes/trendradar/references'
repo_dir = '/home/asus/TrendRadar/trendradar/references'
ref_set = set(os.listdir(ref_dir)) | set(os.listdir(repo_dir))
for skill in ['monthly-report','news-secretary','performance-optimizer',
              'system-config','weekly-report','self-healing']:
    p = f'/home/asus/.hermes/skills/trendradar/{skill}/SKILL.md'
    for m in re.finditer(r'`references/([^`]+)`', open(p).read()):
        r = m.group(1).strip()
        if r not in ref_set:
            print(f'❌ {skill}: `{r}` MISSING')
```

排除项：`xxx.md` 是格式示例（非真实引用）；self-healing 专用文件（api-diagnosis.md 等）在 `self-healing/references/` 下独立存在。

## 维护注意

任何对 skill SKILL.md 或 reference 文件的修改，必须在**两个位置同步**执行：

| 位置 | 路径 | 用途 |
|------|------|------|
| Hermes 运行时 | `~/.hermes/skills/trendradar/<skill>/` | cron 实际加载的版本 |
| Git 发布仓 | `~/TrendRadar/trendradar/skills/<skill>/` | 版本控制 & 分发 |

即：`patch` / `write_file` 后，若文件同时存在于两处，两处都要改。只改一处会导致下一次 `repo-sync.md` 的 `cp -r` 覆盖另一边的改动。

集中 references 位于 `~/.hermes/trendradar/references/`，发布仓对应 `~/TrendRadar/trendradar/references/`。SKILL.md 中引用路径统一为 `references/xxx.md`，不再使用 `news-secretary references/xxx.md` 格式。

## 代理配置（V7 — 米霍姆分流 + Docker 兼容）

TrendRadar 自 v5.5.0 起支持**自动代理分流**：国内 RSS 源直连，外媒源走米霍姆（127.0.0.1:7890）。

### 架构

```
RSS 采集 (fetch_feeds.py)
  ├─ 国内源 (anyfeeder.com / .cn)   → 直连 session
  └─ 外媒 (BBC/NYT/RSSHub等)         → 代理 session (PROXY_URL)
                                          ↓
                                    米霍姆 127.0.0.1:7890

文章详情 (batch_fetch.py)
  └─ 自动检测 127.0.0.1:7890 是否可达
       ├─ 可达 → 走米霍姆代理抓取外媒全文
       └─ 不可达 → 直连兜底
```

### 核心配置

| 配置 | 位置 | 说明 |
|------|------|------|
| `PROXY_URL` | `scripts/settings.py` | 默认 `http://127.0.0.1:7890`，可被环境变量 `TRENDRADAR_PROXY` 覆盖 |
| `needs_proxy()` | `scripts/settings.py` | 判断 RSS 源是否需要代理。逻辑：`localhost:1200`(RSSHub) → 走代理；anyfeeder/.cn → 直连；其余外网域名 → 走代理 |
| `DOMESTIC_PROXY_PATTERNS` | `scripts/settings.py` | 国内中转域名白名单（`plink.anyfeeder.com`、`.cn`、`.com.cn`） |

### 流量分流效果

| 分类 | 数量 | 典型源 | 路由 |
|------|------|--------|------|
| 国内中转直连 | ~8 | 爱范儿、虎嗅、机核、澎湃、钛媒体、GameLook | 直连 |
| RSSHub 代理 | ~12 | Reuters/BBC中文/中国新闻网/半月谈/游民星空/触乐/日经亚洲 | 米霍姆 |
| 外媒直连代理 | ~18 | BBC/NYT/Guardian/SCMP/PCGamer/Eurogamer/4Gamer 等 | 米霍姆 |

### 代理不可达的后果

- `fetch_feeds.py`：外媒源和 RSSHub 源采集全部失败 → 日报只有国内源内容
- `batch_fetch.py`：自动降级为直连（curl 兜底），外媒全文可能抓不到
- `self-healing` 的 `check_api` 项会检测外网出口是否可达

### 米霍姆监听配置（Docker 容器可访问）

RSSHub 等 Docker 容器需要通过 `host.docker.internal` 访问 WSL 的 mihomo。mihomo 必须监听 0.0.0.0 才能接受 Docker 容器连接：

```yaml
# ~/.config/mihomo/config.yaml
port: 7890
socks-port: 7891
allow-lan: true
bind-address: "0.0.0.0"
mode: rule
```

改配置后需重启：`systemctl --user restart mihomo.service`

验证：`ss -tlnp | grep 7890` 应显示 `*:7890` 而非 `127.0.0.1:7890`。

### 排查代理问题

```bash
# 1. 米霍姆是否运行
systemctl --user status mihomo.service

# 2. 端口是否监听
ss -tlnp | grep 7890

# 3. 指定源走代理测试
python3 -c "from scripts.settings import needs_proxy; print('needs proxy:', needs_proxy('https://feeds.bbci.co.uk/news/rss.xml'))"

# 5. 查看当前采集时代理分流日志
# 启动 fetch_feeds 时会打印: [FETCH] 38源（直连 8 + 代理 30）

# 6. Docker → mihomo 连通性
curl -s -o /dev/null -w "HTTP %{http_code} (%{time_total}s)" --max-time 5 \
  -x http://172.30.21.131:7890 http://www.gstatic.com/generate_204

# 7. RSSHub 外媒路由是否可用
for r in reuters/business reuters/technology reuters/world/china nikkei/asia; do
  echo -n "$r: "; curl -s -o /dev/null -w "HTTP %{http_code} (%{time_total}s)\\n" --max-time 10 "http://localhost:1200/$r"
done
```

## RSSHub 源管理

TrendRadar 通过本地 RSSHub 实例（`http://localhost:1200`，Docker: `diygod/rsshub`）获取部分 RSS 源。

### 可用路綫（无特殊凭证）

| 路綫 | HTTP | 说明 |
|------|------|------|
| `/zhihu/hot` | 200 | 知乎热榜 |
| `/bilibili/ranking` | 200 | B站排行榜 |
| `/36kr/news/latest` | 200 | 36氪最新 |
| `/sspai/index` | 200 | 少数派首页 |
| `/solidot/www` | 200 | Solidot 科技 |
| `/jianshu/home` | 200 | 简书首页 |
| `/xianbao` | 200 | 线报 |

路綫返回 503 = 该路由需额外凭证（cookie/token）；000 = RSSHub 无法直达目标站点（需给 RSSHub 配代理）。

### 添加新源

1. 确认 RSSHub 路綫可用：
   ```bash
   curl -s -o /dev/null -w "HTTP %{http_code}" --max-time 6 http://localhost:1200/<route>
   ```

2. 确定分类和权威分（参考已有同类源）：
   - `tech`: 爱范儿 authority=2
   - `news`: 澎湃新闻 authority=3
   - `game`: 机核 authority=2

3. 添加到 `data/sources.json`：
   ```python
   import json
   from pathlib import Path
   path = Path.home() / '.hermes' / 'trendradar' / 'data' / 'sources.json'
   data = json.loads(path.read_text())
   data['data_sources'].append({
       "id": "sspai",
       "name": "少数派",
       "platform": "sspai",
       "type": "rss",
       "category": "tech",
       "enabled": True,
       "feed_url": "http://localhost:1200/sspai/index",
       "authority": 2
   })
   path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
   ```

4. 如果外媒源需翻译，同步更新 `data/sources.json` 中各源的 `language` 字段。

5. 运行 `fetch_feeds` 测试：
   ```bash
   python3 -m scripts.fetch_feeds --push-id test_new_source
   ```

### 给 RSSHub 容器配代理（undici EnvHttpProxyAgent）

Node.js 24 使用 undici 作为内置 HTTP 客户端，**不自动读取 `HTTP_PROXY`/`HTTPS_PROXY` 环境变量**。但 undici 提供了 `EnvHttpProxyAgent` 可手动注入。`proxychains4` 在 Node.js 24 上因 undici 使用新式 I/O 而不可靠（TLS 断开）。

#### 第一步：构建带代理预加载的镜像

```bash
# 1. 启动原始 RSSHub
docker run -d --name rsshub --restart always -p 1200:1200 \
  --add-host host.docker.internal:172.30.21.131 \
  -e NODE_ENV=production -e TZ=Asia/Shanghai \
  diygod/rsshub

# 2. 安装 CA 证书（容器缺少证书导致 HTTPS 失败）
docker exec rsshub apt-get update -qq
docker exec rsshub apt-get install -y -qq ca-certificates

# 3. 创建代理预加载脚本
docker exec rsshub sh -c 'cat > /app/proxy-fix.mjs << "EOF"
import undici from "undici";
const proxyUrl = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
if (proxyUrl) {
  const agent = new undici.EnvHttpProxyAgent();
  globalThis[Symbol.for("undici.globalDispatcher.1")] = agent;
}
EOF'

# 4. 提交为新镜像
docker commit rsshub rsshub-final
docker stop rsshub && docker rm rsshub
```

#### 第二步：用 --import 预加载代理

```bash
docker run -d --name rsshub --restart always -p 1200:1200 \
  --add-host host.docker.internal:172.30.21.131 \
  -e HTTP_PROXY=http://host.docker.internal:7890 \
  -e HTTPS_PROXY=http://host.docker.internal:7890 \
  -e NO_PROXY=localhost,127.0.0.1 \
  -e NODE_ENV=production -e TZ=Asia/Shanghai \
  rsshub-final \
  dumb-init -- node --max-http-header-size=32768 \
    --import /app/proxy-fix.mjs dist/index.mjs
```

⚠️ **关键陷阱**：`npm run start` 用 `cross-env` 覆盖了 `NODE_OPTIONS`，导致 `--import` 被冲掉。必须直接用 `node dist/index.mjs` 启动，不要用 `npm run start`。

⚠️ **网络检测**：`172.30.21.131` 是 WSL 网卡 IP，每次 WSL 重启可能变化。需 `ip addr show eth0 | grep 'inet '` 确认后更新 `--add-host` 值。

#### 预期结果

| 路由 | 效果 |
|------|------|
| Reuters (`/reuters/business`, `/reuters/technology`, `/reuters/world/china`) | ✅ HTTP 200（~0.4-1.4s） |
| Nikkei Asia (`/nikkei/asia`) | ✅ HTTP 200（~2-4s） |
| BBC 中文 (`/bbc/chinese`) | ❌ HTTP 503 — BBC 主动封禁代理节点 IP，非配置问题 |
| 国内路由 (`/sspai/index` 等) | ✅ HTTP 200（直连不受影响） |

#### BBC 特殊处理

BBC 系列域名（`feeds.bbci.co.uk`, `bbc.co.uk`）直连可达（~0.4s），但所有代理节点均被 BBC 屏蔽。处理方案：

1. **mihomo 规则层**：已修改 `~/.config/mihomo/config.yaml`，将 `bbc.co.uk` 和 `bbci.co.uk` 从 `🌍 国外媒体` 改到 `🎯 全球直连`
2. **TrendRadar 采集层**：`DOMESTIC_PROXY_PATTERNS` 已加入 `bbc.co.uk` 和 `bbci.co.uk`，使 BBC RSS feed 直连

### 流量分流效果

## 源管理

**近期变更**（按时间倒序）:
- `rfi`（法广）— 新增，feedx.net 中转，news 分类，authority=2
- `kyodo`（共同网）— 新增，feedx.net 中转，news 分类，authority=2
- `bbc_chinese`（BBC 中文）— 删除，RSSHub 路由失效且所有代理节点屏蔽 BBC
- `sspai`（少数派）— 新增，RSSHub `/sspai/index`，tech 分类，authority=2
- `theverge_games`（The Verge·游戏）— 重新启用（GFW 阻断已不存在），game 分类

**外媒源测试**: BBC/NYT/Guardian/SCMP 等可通过直连获取（~0.5-1.2s），但通过米霍姆代理更稳定更快（~0.2-0.5s）。

## 参数沿革

### 推送参数

| 时间 | BRIEFING_RATIO | MAX_PER_DOMAIN (合计) | 说明 |
|------|---------------|----------------------|------|
| v6.0 | 24/32/24 | 65 (10+15+14+12+14) | 初始值，MAX 远大于配额导致溢出 |
| v6.1 | 30/30/20 | 30 (6+7+6+6+5) | 推送量偏差+108%，user 全修后收紧。新增 per-slot 截断(curate_all)，总额≤ BRIEFING_RATIO[push_id] |

### foreign_china 关键词

| 时间 | 词数 | 新增词 |
|------|------|--------|
| 初始 | 38 | — |
| 2026-05-24 | 48 | 美中、中美关系、对华、外贸、制裁、出口管制、地缘、脱钩、外媒、国际 |

## TrendRadar 技能

| 名称 | 用途 |
|------|------|
| `news-secretary` | 日报推送管线（编排器 + 晚间深度分析） |
| `self-healing` | 自动体检 + 自修复（DB/配置/API/Gateway/记忆/代理） |
| `performance-optimizer` | 推送质量评分 + 推送偏好收敛调优 |
| `weekly-report` | 每周深度趋势周报 |
| `monthly-report` | 月度聚合趋势报告 |

## 参考文件

| 文件 | 内容 |
|------|------|
| `references/rsshub-proxy-setup.md` | RSSHub Docker 容器代理配置（undici EnvHttpProxyAgent + --import 预加载，含陷阱清单） |
