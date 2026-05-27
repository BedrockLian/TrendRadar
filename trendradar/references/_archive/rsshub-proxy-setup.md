# RSSHub Docker 代理配置

## 背景

RSSHub 容器需要代理才能访问外媒源（Reuters、Nikkei Asia 等）。Node.js 24 的内置 HTTP 客户端（undici）**不自动读取 `HTTP_PROXY`/`HTTPS_PROXY` 环境变量**，需要手动注入 `EnvHttpProxyAgent`。

## 方案：undici EnvHttpProxyAgent + --import 预加载

### 构建镜像

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

### 启动容器

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

## 陷阱清单

### trap-1: npm run start 冲掉 NODE_OPTIONS

`npm run start` 内部用 `cross-env` 重设了 `NODE_OPTIONS`，只保留 `--max-http-header-size=32768`，丢弃了 `--import`。

**修复**：直接用 `node dist/index.mjs` 启动，不要用 `npm run start`。

### trap-2: host.docker.internal IP 变化

每次 WSL 重启后网卡 IP 会变。`--add-host host.docker.internal:172.30.21.131` 中的 IP 需要更新。

**检查**：
```bash
ip addr show eth0 | grep 'inet '
```

### trap-3: 容器缺少 CA 证书

默认 `diygod/rsshub` 镜像（Debian slim）没有安装 CA 证书，导致 HTTPS 请求失败（`error setting certificate file: /etc/ssl/certs/ca-certificates.crt`）。

**修复**：安装 `ca-certificates` 包。

### trap-4: proxychains4 不兼容 Node.js 24

`proxychains4` 拦截 `connect()` 系统调用，但 Node.js 24 的 undici 使用新式异步 I/O，导致 TLS 在建立过程中断开（`Client network socket disconnected before secure TLS connection was established`）。**不要用 proxychains4。**

### trap-5: redsocks 透明代理也无效

类似 proxychains，`redsocks` + iptables REDIRECT 同样因 undici 的 I/O 路径问题导致 TLS 失败。

## 验证

```bash
# 路由测试
for r in reuters/business reuters/technology reuters/world/china nikkei/asia; do
  echo -n "$r: "
  curl -s -o /dev/null -w "HTTP %{http_code} (%{time_total}s)\n" --max-time 10 "http://localhost:1200/$r"
done

# 国内基准
curl -s -o /dev/null -w "HTTP %{http_code} (%{time_total}s)" --max-time 8 http://localhost:1200/sspai/index
```
