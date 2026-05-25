---
name: system-config
slug: system-config
version: 2.8.0
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
- **一条龙部署脚本**: `~/TrendRadar/one-key-setup.sh`（环境检测 + 依赖 + 配置 + 迁移 + 环境变量持久化）

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

### Cron prompt 格式

LLM 驱动型 cron 的 final response 只需透传脚本输出。`sanity_check.py` 在推送层自动拦截禁语（"As an AI language model" / "以下是今日晚报" / "所有分析已完成" 等），Agent 无需在 prompt 层重复约束。

铁律只有一条：**每条 final response 独立输出，不与简报拼接。**

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
- **GIL 环境锁**：`settings.py` 启动时自动检查。若 3.14t 检测到 `PYTHON_GIL != 0`，输出 `RuntimeWarning` 到 stderr（不阻止运行，仅诊断提示）。

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

4. 如果外媒源需翻译，设 `language` 字段：
   - `"en"` — 英文源（BBC/Reuters/NYT/Guardian/PC Gamer 等）
   - `"ja"` — 日文源（NHK/4Gamer/Inside Games 等）
   - `"zh"` — 中文源（不翻译）
   `ai_translate.py` 启动时自动扫描所有源的 `language` + `name` + `platform` 构建匹配集。
   `config/translate.yaml` 已淘汰（2026-05-25），不再需要单独维护语言映射文件。

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

| 分类 | 典型源 | 路由 |
|------|--------|------|
| 国内中转直连 | 爱范儿、虎嗅、机核、澎湃、钛媒体、联合早报 | 直连 |
| RSSHub 代理 | Reuters/中国新闻网/半月谈/游民星空/触乐/日经亚洲/少数派 | 米霍姆 |
| 外媒直连代理 | BBC/NYT/Guardian/SCMP/PC Gamer/4Gamer/NHK/Japan Times | 米霍姆 |
| feedx.net 中转 | 法广(rfi)、共同网(kyodo) | 米霍姆 |

## 源管理

**近期变更**：
- `rfi`（法广）、`kyodo`（共同网）— 新增，feedx.net 中转，news 分类
- `bbc_chinese`（BBC 中文）— 删除，路由失效
- `sspai`（少数派）— 新增，RSSHub `/sspai/index`
- `theverge_games`（The Verge·游戏）— 重新启用
- `bbc_china`（BBC 中国）、`bbc_world`（BBC 世界）— 新增，直连 RSS，foreign_china 分类
- `bbc_science`（BBC 科学环境）— 新增，直连 RSS，tech 分类
- `nytimes_business`（纽约时报·商务）— 新增，直连 RSS，economy 分类
- `nytimes_science`（纽约时报·科学）— 新增，直连 RSS，tech 分类
- `sources.json` 已同步至 repo: `trendradar/config/sources.json`（原仅运行时 data/ 目录）

## 参数沿革

| 版本 | BRIEFING_RATIO | MAX_PER_DOMAIN | 说明 |
|------|---------------|---------------|------|
| v6.0 | 24/32/24 | 65 | 初始值，MAX 远大于配额导致溢出 |
| v6.1+ | 30/30/20 | 30 | 推送量偏差+108%后收紧。新增 per-slot 截断 |

**foreign_china 关键词扩充**（2026-05-24）：美中、中美关系、对华、外贸、制裁、出口管制、地缘、脱钩、外媒、国际

## 所有脚本清单

| 脚本 | 用途 | 版本 |
|------|------|------|
| `pipeline_orchestrator.py` | 一键编排器（7 阶段 + auto-migrate + 自检 + SILENT 闭环） | v2.8.0 |
| `push_slot_detect.py` | 时段路由 + IO 预取（`--minutes-until` / `--next-slot`） | v2.0 |
| `push_prepare.py` | fetch + curation 编排 | — |
| `fetch_feeds.py` | 38 RSS 异步抓取 + 代理分流 | — |
| `curate_and_push.py` | 5 domain 精选 + 多样性惩罚 + 健康反馈 | — |
| `ai_translate.py` | AI 翻译 + 指数退避重试 + 熔断器 | — |
| `batch_fetch.py` | 10 并发全文抓取 | — |
| `render_markdown.py` | 纯脚本 Markdown 渲染（格式契约在 docstring） | — |
| `render_deep_analysis.py` | Pro 深度分析格式化 + 实体提取 + 历史关联 | v2.0 |
| `fragment_push.py` | UTF-8 字节计数分片（3800B/片） | — |
| `track_events.py` | 跨日事件追踪 | — |
| `record_fingerprints.py` | 指纹记录（Storage 统一接入） | — |
| `heat_tracker.py` | 热度追踪 + per-thread WAL 连接池 | — |
| `blog_watcher_bridge.py` | blogwatcher 集成 | — |
| `blind_spot_audit.py` | 盲点审计 + `--json` + `--output-penalty` + `--update-health` | — |
| `aggregate_monthly.py` | 月度统计 + `--suggest-interests` 兴趣漂移 | — |
| `sanity_check.py` | 发布前拦截器（禁语/死链/敏感词/HTML残留） | — |
| `storage.py` | 统一存储层（文件IO + DB连接池 WAL） | — |
| `exitcodes.py` | 退出码协议（0/2/3/10/11/12/99） | — |

## 自动化反馈环

### 源健康评分（source_health.json）
`blind_spot_audit.py --update-health` 维护 `data/source_health.json`：
- 每个源追踪 `total_appearances` / `total_curated` / `health_score(0-100)`
- 状态: `healthy(≥60)` / `degrading(30-59)` / `failing(<30)`
- `curate_and_push.py` 通过 `load_source_health()` 消费：failing → authority ×0.3

### 来源多样性惩罚
`curate_and_push.py --penalty-file` 可加载盲点审计产的惩罚 JSON：
- 同源 >20% 占比 → authority 线性递减（最低 ×0.5）
- 内部也执行：同源 >3 条 → 权重减半（`_diversity_penalized`）

### 兴趣漂移检测
`aggregate_monthly.py --suggest-interests` 对比高频词 vs 当前 `ai_interests.yaml`：
- `suggest_add`: ≥5 次出现且不在兴趣中的 2-4 字中文片段
- `suggest_remove`: 当前正向关键词近 30 天零命中

## 数据文件

| 文件 | 内容 | 生产者 | 消费者 |
|------|------|--------|--------|
| `data/sources.json` | RSS 源定义（含 language 字段） | 手动 / system-config | fetch_feeds, ai_translate, curate |
| `data/source_health.json` | 源质量评分 | blind_spot_audit --update-health | curate_and_push |
| `data/fingerprints.db` | 指纹 + 热度追踪 | record_fingerprints, heat_tracker | render_deep_analysis --context |
| `data/push_log.json` | 推送结果日志 | pipeline_orchestrator | delivery_watchdog |
| `config/timeline.yaml` | 时段配置 | 手动 / one-key-setup.sh | push_slot_detect |
| `config/ai_interests.yaml` | 兴趣偏好 | 手动 / aggregate_monthly | curate_and_push |

## 开发参考

| 文件 | 内容 |
|------|------|
| `references/pitfalls-utf8-bytes.md` | UTF-8 字节计数陷阱：`_find_last` 的 `len()` vs `bytes` 混用 bug + 修复 |
| `references/pipeline.md` | 管线全量文档 v2.8.0（性能/故障恢复/脚本清单） |
| `references/traps.md` | 已知陷阱全集（30 条） |

| 名称 | 用途 |
|------|------|
| news-secretary | 日报推送管线（编排器 + 晚间深度分析） |
| self-healing | 自动体检 + 自修复 |
| performance-optimizer | 推送质量评分 + 偏好收敛 |
| weekly-report | 每周深度趋势周报 |
| monthly-report | 月度聚合趋势报告 |

## 参考文件

| 文件 | 内容 |
|------|------|
| `references/rsshub-proxy-setup.md` | RSSHub Docker 代理配置（undici + --import，含 proxychains4/redsocks 失败记录） |
| `references/repo-sync.md` | 三处同步 + 验证流程 |
