<!-- version: 2.9.0 | consolidated: 2026-05-27 -->

# TrendRadar 安装与运维

---

## 1. 代理配置

TrendRadar v5.5.0+ 支持**自动代理路由**：国内 RSS 源直连，国外源通过 Mihomo（127.0.0.1:7890）代理。

### 架构

```
RSS 抓取 (fetch_feeds.py)
  ├─ 国内源 (anyfeeder.com / .cn)   → 直连 session
  └─ 国外源 (BBC/NYT/Guardian 等)     → 代理 session (PROXY_URL)
                                           ↓
                                      Mihomo 127.0.0.1:7890

  └─ 自动检测 127.0.0.1:7890 可达性
       ├─ 可达 → 国外全文走代理
       └─ 不可达 → 直连回退
```

### 核心配置

| 配置 | 位置 | 说明 |
|------|------|------|
| `PROXY_URL` | `scripts/settings.py` | 默认 `http://127.0.0.1:7890`，可通过 `TRENDRADAR_PROXY` 环境变量覆盖 |
| `needs_proxy()` | `scripts/settings.py` | 判断 RSS 源是否需要代理 |
| `DOMESTIC_PROXY_PATTERNS` | `scripts/settings.py` | 国内域名白名单 |

### 流量路由

| 类别 | 典型来源 | 路由 |
|------|----------|------|
| 国内直连 | 爱范儿, 虎嗅, 机核, 澎湃, 钛媒体, 联合早报 | 直连 |
| 国外直连代理 | BBC/NYT/Guardian/SCMP/PC Gamer/4Gamer/NHK/Japan Times | Mihomo |

### 代理不可达的后果

- `fetch_feeds.py`：国外源全部失败 → 日报仅有国内内容
- `self-healing` 的 `check_api` 项检测互联网出口是否可达

### Mihomo 监听配置（局域网可访问）

```yaml
# ~/.config/mihomo/config.yaml
port: 7890
socks-port: 7891
allow-lan: true
bind-address: "0.0.0.0"
mode: rule
```

修改配置后重启：`systemctl --user restart mihomo.service`
验证：`ss -tlnp | grep 7890` 应显示 `*:7890` 而非 `127.0.0.1:7890`

### 代理故障排查

```bash
# 1. Mihomo 是否在运行？
systemctl --user status mihomo.service

# 2. 端口是否在监听？
ss -tlnp | grep 7890

# 3. 测试特定来源的代理路由
python3 -c "from scripts.settings import needs_proxy; print('needs proxy:', needs_proxy('https://feeds.bbci.co.uk/news/rss.xml'))"

```

---

## 3. 缓存清理流程

按优先级顺序执行，每步后检查释放的磁盘空间。

### 步骤

```bash
# 1. TrendRadar 旧缓存
cd ~/.hermes/trendradar/cache
rm -f raw_$(date -d yesterday +%Y%m%d).json

# 2. __pycache__（排除 venv）
find ~/.hermes -path "*/venv/*" -prune -o -name __pycache__ -type d -exec rm -rf {} +

# 3. pip 缓存
pip cache purge  # 通常释放 10-14MB

# 4. apt 缓存
sudo apt-get clean
sudo apt-get autoremove --purge -y

# 5. 缩略图
rm -rf ~/.cache/thumbnails/*

# 6. 日志
gzip ~/.hermes/logs/agent.log.1
rm -f ~/.hermes/logs/agent.log.1
rm -f ~/.hermes/logs/gateway-shutdown-diag.log
rm -f ~/.hermes/logs/gateway-exit-diag.log

# 7. 临时 session 文件
rm -f ~/.hermes/sessions/*.jsonl

# 8. SQLite VACUUM
sqlite3 ~/.hermes/state.db "VACUUM;"
sqlite3 ~/.hermes/trendradar/data/fingerprints.db "VACUUM;"
```

### 范围
- 自动维护：`trendradar_maintenance.py` 每日 03:00 自动运行 `cleanup()` — 清理 >7 天的 cache/*.json、data/curated_*_YYYYMMDD.json 等。
- 此手动流程用于更激进的额外清理（日志/缩略图/pip 缓存/VACUUM）
- 完整流程每次可回收 20-40MB

---

## 4. Cron 运维与夜间检查清单

### Skill 名称三重一致性

每个加载 skill 的 cron job 需要三处一致：
1. 目录名：`~/.hermes/skills/trendradar/<name>/`
2. Frontmatter 名称：SKILL.md 的 `name: <name>` 字段
3. Cron skills 列表：`hermes cron list` → skills: [<name>, ...]

三者必须完全匹配。不匹配会导致静默警告 `⚠️ Skill(s) not found and skipped:`。

**验证**：`echo "=== Directory ===" && ls ~/.hermes/skills/trendradar/ && echo "=== Cron skills ===" && hermes cron list 2>&1 | grep "Skills:"`

### Gateway 重启后检查清单

1. **Gateway 状态**：`hermes gateway status` → `active (running)`
2. **卡住的 cron job？**：如果 cron job 显示重启前的 `[active]`，杀掉后重新触发
3. **企业微信连接**：检查 gateway 日志中的 `✓ wecom connected`
4. **遗漏推送恢复**：如果停机期间错过了定时推送，绕过 slot 检测：渲染 → 分片 → 最终回复

### 管道格式基线（v5.5.0）

| 阶段 | 工具 | 说明 |
|------|------|------|
| 渲染 | `render_markdown.py` | 纯脚本，~0s，零 token |
| 分片 | `fragment_push.py` | 按 `### ` 标题拆分 |
| 深度分析 | `render_deep_analysis.py` | 企业微信友好格式 |
| 推送 | 最终回复（自动投递） | Cron 返回简报作为输出；系统投递到企业微信 |

### 常见故障模式

| 症状 | 根因 | 修复 |
|------|------|------|
| cron job 报 `Skill not found` | Skill 已重命名；cron 仍用旧名 | 更新 cron skills 列表 |
| Cron prompt 引用已删除的脚本 | Prompt 中有旧脚本名 | `cronjob action=update job_id=xxx prompt="..."` |
| Cron 卡在 `[active]` | .tick.lock 未清理 | 删除锁文件，重新触发 |
| "5/5 sent" 但未收到 | Gateway 在发送和投递之间崩溃 | 检查 gateway.log；重新渲染并推送 |

### Cron Prompt 审计

**需要检查的关键位置：**
- `cronjob action=list` prompt_preview — 实际 cron prompt 文本
- Skill SKILL.md — 脚本名、引用文件路径
- Reference .md 文件 — 可能提到旧脚本名

**检查清单：**
1. `hermes cron list` → 验证每个 skill 存在目录+SKILL.md
2. 将 cron prompt 脚本名与 `ls scripts/*.py` 比对 — 无死名
3. `ls ~/.hermes/trendradar/references/` 存在且非空
4. 对每个 reference .md：grep 搜索旧脚本名、路径引用

---

## 5. 迁移回滚约定

### 问题
`migrations/runner.py` 最初仅支持正向迁移（up），不支持回滚（down）。如果迁移破坏了 schema，只能手动 DROP + 重新迁移，丢失数据。

### 解决方案：`-- down:` 内联回滚注释

在 `.sql` 迁移文件末尾添加 `-- down:` 注释及回滚 DDL：

```sql
-- 001_initial.sql
CREATE TABLE IF NOT EXISTS fingerprints (...);
CREATE TABLE IF NOT EXISTS heat_tracker (...);

-- down: DROP TABLE IF EXISTS heat_tracker; DROP TABLE IF EXISTS fingerprints;
```

### 约定
- **位置**：迁移文件的最后一行或多行
- **格式**：`-- down: <SQL 语句>`
- **多语句**：分号分隔，由 `executescript()` 执行
- **幂等**：使用 `IF EXISTS` / `IF NOT EXISTS`

### 安全保证
- **缺少注释 → 拒绝**：抛出 `ValueError` 而非静默跳过
- **逆序回滚**：最新版本优先，向下回滚
- **版本精确**：`target_version` 含边界 — 回滚停在该版本
- **非破坏性**：`_migrations` 表本身不会被 down SQL 删除

### 添加新迁移
1. 创建 `migrations/NNN_description.sql`
2. 编写 CREATE/ALTER 正向迁移 SQL
3. 在文件末尾添加 `-- down: <回滚 SQL>`
4. 回滚 SQL 必须撤销本次迁移的所有结构性变更

### 测试
`tests/test_pipeline_e2e.py::TestMigrationRollback` — 3 项：完整 up→down 循环、回滚到当前版本 = 空操作、缺少 `-- down:` 注释拒绝回滚

---

## 6. 每日 Cron Prompt（规范版本）

> ⚠️ 注意：规范 cron prompt 现已通过 `pipeline_orchestrator.py --list-steps` 自动生成。
> 最新自动生成版本见 `references/cron-prompt-generated.md`。
> 以下手动版本仅供引用参考。

每次修改 news-secretary skill 必须同时更新 cron prompt（Trap 15）。Prompt 独立于 skill 内容，不会自动同步。

```bash
cronjob action=update job_id=90a2866775df prompt="..."
```

### 完整文本（手动版本）

按 news-secretary skill 执行本推送时段（v6.5 自动投递模式）。

```
export PYTHON=/usr/local/bin/python3.14t
export PYTHONPATH=/home/asus/.hermes
export PYTHON_GIL=0

## 主流程

1. 运行编排器: RESULT=$($PYTHON scripts/pipeline_orchestrator.py 2>&1)，从 stdout 捕获 JSON
2. 解析 JSON 状态:
   - "silent" → 返回 [SILENT]
   - "error" → 输出 errors 字段
   - "ok" → 继续步骤 3

3. 输出 JSON briefing 字段（sanity_check.py 自动拦截禁止的前缀/后缀）

4. 仅 push_id=evening（JSON needs_deep_analysis=true）:
   并行启动 3 个 Pro delegate_task 子 agent（趋势/跨域/风险）。
   每个分析结果通过 render_deep_analysis.py 管道处理:
     echo "$ANALYSIS_TEXT" | $PYTHON scripts/render_deep_analysis.py --topic "主题" --push-id evening --context
   然后作为独立的最终回复输出 — 每份分析作为单独消息。

## 回退（编排器失败）

0. $PYTHON scripts/push_slot_detect.py
1. $PYTHON scripts/push_prepare.py --push-id {PUSH_ID} {DEDUP_FLAG}
2. [翻译] $PYTHON scripts/ai_translate.py --push-id {PUSH_ID}
3. BRIEFING=$($PYTHON scripts/render_markdown.py --push-id {PUSH_ID})
4. NEW_COUNT=0 → [SILENT]
5. $PYTHON scripts/record_fingerprints.py --push-id {PUSH_ID}
6. 输出 BRIEFING

## 预检

- cat references/render-format.md（现已在 PIPELINE.md 中）
- cat references/deep-analysis-format.md（现已在 PIPELINE.md 中）
- cat references/translation-pipeline-sync.md（现已在 TRAPS.md 中）
- 空行规则：条目间 \n\n\n，板块标题后 \n\n\n
- 绝不使用 send_message，始终使用最终回复自动投递
- sanity_check.py 在推送前自动扫描禁用词/死链/敏感词
```

---

## 7. Cron 上下文投递：自动投递协议

> `send_message` 在 cron 上下文中**不可用**。所有投递通过最终回复自动投递完成。

### 工作原理

Cron job 完成 → 系统将 Agent 的最终回复自动投递到配置的投递目标（企业微信）。Agent 不会（也不能）在 cron 中使用 `send_message` 工具。

### 正确做法
1. 管道产出渲染好的简报（`render_markdown.py` stdout）
2. Agent 将简报文本作为最终回复返回
3. 系统自动投递到企业微信

### 错误做法
- ❌ 在 cron 中尝试 `send_message(target="wecom")` — 工具不可用
- ❌ 返回 `[SILENT]` 作为最终回复 — 无任何投递
- ❌ Agent 用自己语言重写简报 — 格式漂移，翻译丢失
- ❌ 仅返回 fragments JSON 数组而无实际内容

### 历史
之前设计为逐片段 send_message 投递，但 cron 上下文缺少此工具。v5.7.0+ 切换为自动投递：Agent 输出完整简报，系统处理投递。

---

## 8. RSS 信源管理

### 信源配置位置

`sources.json` — 54+ 信源定义。存在于两处：
- **运行时**：`~/.hermes/trendradar/data/sources.json`（管道读取此文件）
- **仓库**：`~/TrendRadar/trendradar/config/sources.json`（版本控制）

修改后必须同步：修改运行时文件，然后 cp 到仓库并 git push。

### 信源对象格式（v2.0）

```json
{
  "version": "2.0",
  "last_updated": "ISO-8601",
  "data_sources": [{
    "id": "bbc_china",
    "name": "BBC 中国",
    "platform": "bbc",
    "type": "rss",
    "category": "foreign_china",
    "enabled": true,
    "feed_url": "https://feeds.bbci.co.uk/news/world/asia/china/rss.xml",
    "authority": 3,
    "language": "en"
  }]
}
```

字段说明：`id`（唯一标识）、`name`（显示名称）、`type`（rss/blog/hotlist）、`feed_url`、`category`（news/tech/economy/game/foreign）、`enabled`、`language`（zh/en/ja）、`update_interval_minutes`、`last_fetched`。

### 信源命名约定
- `name` 字段必须作为显示名称出现在 `source_platform` 中
- 使用中文名称，不要用日文假名（如 `NHK 商业` 而非 `NHK ビジネス`）
- 保持简短以便 `kw in plat.lower()` 子串匹配

### 翻译配置解耦

翻译语言检测由 `sources.json` 的 `language` 字段驱动。添加新信源只需在信源条目中设置 `language` — 无需单独的映射文件。

### 已知可用信源

**BBC** (feeds.bbci.co.uk) — 全部直连：/news/rss.xml, /news/world/rss.xml, /news/world/asia/china/rss.xml, /news/business/rss.xml, /news/technology/rss.xml 等。

**NYT** (rss.nytimes.com) — 全部直连：/services/xml/rss/nyt/World.xml, Technology.xml, Business.xml, Science.xml 等。

**NPR** (feeds.npr.org)：格式 `https://feeds.npr.org/{ID}/rss.xml` — 1001 (News), 1004 (World), 1006 (Business), 1007 (Science) 等。

**NHK** (www3.nhk.or.jp)：格式 `https://www3.nhk.or.jp/rss/news/cat{N}.xml` — 0 (综合), 3 (科学), 4 (政治), 5 (经济), 6 (商业)。

**Reuters** — 公开 RSS 全部 404，已移除。

**Korea Herald** (koreaherald.com)：`https://www.koreaherald.com/rss/newsAll`

### 已废弃/不可用
- **AP**：所有公开 RSS 已下线
- **Yonhap News**：此环境下 DNS 不可达。替代方案：Korea Herald
- **RSSHub**：已移除（本地 RSSHub 已删除）

### 添加步骤
1. 验证信源 URL 可用（curl 确认返回 RSS XML）
2. 确定 `category`
3. 使用中文 `name`，添加到 `sources.json` 的 `data_sources` 数组
4. 设置 `language` 字段用于翻译
5. `cp data/sources.json ~/TrendRadar/trendradar/config/sources.json`
6. `cd ~/TrendRadar && git add -A && git commit -m "feat: add <name> feed" && git push`
7. 下次管道自动抓取（无需重启）
