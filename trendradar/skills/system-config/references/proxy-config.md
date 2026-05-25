# 米霍姆代理配置

TrendRadar 自 v5.5.0 起支持**自动代理分流**：国内 RSS 源直连，外媒源走米霍姆（127.0.0.1:7890）。

## 架构

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

## 核心配置

| 配置 | 位置 | 说明 |
|------|------|------|
| `PROXY_URL` | `scripts/settings.py` | 默认 `http://127.0.0.1:7890`，可被环境变量 `TRENDRADAR_PROXY` 覆盖 |
| `needs_proxy()` | `scripts/settings.py` | 判断 RSS 源是否需要代理：`localhost:1200`(RSSHub) → 走代理；anyfeeder/.cn → 直连；其余外网域名 → 走代理 |
| `DOMESTIC_PROXY_PATTERNS` | `scripts/settings.py` | 国内中转域名白名单（`plink.anyfeeder.com`、`.cn`、`.com.cn`） |

## 流量分流效果

| 分类 | 典型源 | 路由 |
|------|--------|------|
| 国内中转直连 | 爱范儿、虎嗅、机核、澎湃、钛媒体、联合早报 | 直连 |
| RSSHub 代理 | Reuters/中国新闻网/半月谈/游民星空/触乐/日经亚洲/少数派 | 米霍姆 |
| 外媒直连代理 | BBC/NYT/Guardian/SCMP/PC Gamer/4Gamer/NHK/Japan Times | 米霍姆 |
| feedx.net 中转 | 法广(rfi)、共同网(kyodo) | 米霍姆 |

## 代理不可达的后果

- `fetch_feeds.py`：外媒源和 RSSHub 源采集全部失败 → 日报只有国内源内容
- `batch_fetch.py`：自动降级为直连（curl 兜底），外媒全文可能抓不到
- `self-healing` 的 `check_api` 项会检测外网出口是否可达

## 米霍姆监听配置（Docker 容器可访问）

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

## 排查代理问题

```bash
# 1. 米霍姆是否运行
systemctl --user status mihomo.service

# 2. 端口是否监听
ss -tlnp | grep 7890

# 3. 指定源走代理测试
python3 -c "from scripts.settings import needs_proxy; print('needs proxy:', needs_proxy('https://feeds.bbci.co.uk/news/rss.xml'))"

# 4. Docker → mihomo 连通性
curl -s -o /dev/null -w "HTTP %{http_code} (%{time_total}s)" --max-time 5 \
  -x http://172.30.21.131:7890 http://www.gstatic.com/generate_204
```
