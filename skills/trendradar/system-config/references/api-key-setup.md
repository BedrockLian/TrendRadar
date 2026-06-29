# DeepSeek API Key 配置

## Gateway 注入

将 key 注入 gateway systemd override.conf，所有 cron job 自动继承：

```bash
# ~/.config/systemd/user/hermes-gateway.service.d/override.conf
[Service]
Environment="DEEPSEEK_API_KEY=sk-xxx"

# 重启生效
systemctl --user daemon-reload && systemctl --user restart hermes-gateway.service
```

## Key 权限陷阱

DeepSeek 控制台创建 key 时可选权限范围。只读 key 可以调 `/v1/models`（HTTP 200），但调 `/v1/chat/completions` 返回 401 `Authentication Fails, Your api key is invalid`。

**诊断**：
```bash
KEY="sk-xxx"
# 测试 models（读权限 — 只读 key 也过）
curl -s -w "\nHTTP %{http_code}" https://api.deepseek.com/v1/models \
  -H "Authorization: Bearer ***
# 测试 chat（写权限 — 只有完整 key 才过）
curl -s -w "\nHTTP %{http_code}" https://api.deepseek.com/v1/chat/completions \
  -H "Authorization: Bearer *** -H "Content-Type: application/json" \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"hi"}],"max_tokens":10}'
```

**修复**：在 DeepSeek 控制台重新创建 key，确保勾选 chat/completions 权限。
