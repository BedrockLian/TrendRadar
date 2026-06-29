# 翻译效率基线（deepseek-v4-flash）

2026-06-02 实测 6 次 12 条 expand 任务，作为 ai_translate 调参依据。
未来切换模型或 prompt 变更时重测此表。

## 实测数据

| 批次 | 批次数 | wall time | 备注 |
|------|:---:|-----------|------|
| 5 | 3 (5+5+2) | ~14s | 多次启动成本 |
| **10** | **2 (10+2)** | **10.9-11.3s** | **当前生产配置 ✓** |
| 12 | 1 | 12.8-13.0s | 1 批 12 vs 2 批 10+2：慢 1.5s |
| 15 | 1 | 14.1-14.6s | 更慢 |
| 20 | 1 | 15.0-16.1s | 最慢 |

## 关键发现

### 1. 网络/启动延迟是常数项
- 单条 API 响应（无关输出长度）= ~1.7s
- 10 条 batch = ~8.4s（增量 ~0.7s/条）
- 增量项 = LLM attention O(n²) 主导

### 2. 并发 vs 单批的取舍
- `MAX_CONCURRENT_BATCHES=6`：12 条 → 2 批 → 2 路并发（10+2）
- 2 路并发同时启动 → 总 wall ≈ 单批耗时（max）
- 单批 12 = 1 路 → 总 wall = 1 批耗时
- **2 批并发 < 1 批 12**（1.5s 差距）：因为 attention O(n²) 让单批 12 慢过 2 批 10+2

### 3. max_tokens 雷区
- max_tokens=1024, temp=0.3: 10 条 8.4s, 708 out_tokens
- max_tokens=4096, temp=0.1: 1 条 9.8s, **1020 out_tokens** ⚠
  - 低温下模型把 cap 当目标，强制续写
  - 输出 10× 长但质量不增
- **当前默认 4096/0.3 在 10 条场景下不踩 cap**（仅 ~700 tokens），无优化空间

### 4. 已验证配置（2026-06-02 起锁死）
```python
TRANSLATE_BATCH_SIZE = 10           # P-01 假设 20 更快，实测 +30% 慢
TRANSLATE_BATCH_MAX_CONCURRENT = 6  # 实际只需 2，6 留 buffer
max_tokens = 4096 (provider 默认)    # 短输出不踩 cap
temperature = 0.3 (provider 默认)    # 0.1 反而让模型啰嗦
```

## 切模型时重测命令

```bash
# 准备: 复制一份 5/31 晚上 curated 30 条 + 清空 summary_cn + 截短到 <90 字符
# 备份原文件: 切完模型立即还原
cd ~/.hermes/trendradar
cp data/curated_evening_20260601.json /tmp/bench.bak.json
python3 -c "
import json
d=json.load(open('data/curated_evening_20260601.json'))
for dom in ['top_headlines','foreign_china','tech','economy','gaming']:
    for it in d[dom]:
        s=(it.get('summary','') or '').strip()
        if s and not it.get('source_lang'):
            it['summary_cn']=''
            if len(s) > 50: it['summary']=s[:40]
json.dump(d, open('data/curated_evening_20260601.json','w'), ensure_ascii=False)
"

# 3 轮 × N 次取 min
for bs in 10 12 15 20; do
  for i in 1 2 3; do
    cp /tmp/bench.bak.json data/curated_evening_20260601.json
    /usr/bin/time -f "%e" python3 -m trendradar.scripts.ai_translate --push-id evening --batch-size $bs 2>&1 | tail -1
  done
done

# 还原
cp /tmp/bench.bak.json data/curated_evening_20260601.json
```

## 已知未优化（不值得做）

| 项 | 预期收益 | 成本 | 决策 |
|----|---------|------|------|
| provider session 复用 | ~50ms/批 | 改 4 个 provider 协议类 | 延后 |
| 减 prompt 体积（template rule 9 冗余） | ~30 tokens/批 | 损 1% 翻译质量 | 延后 |
| 启用 deepseek prompt caching | 减半 input token | 改 provider + cache 失效策略 | 等切多模型时统一做 |

## 切到更慢模型时（如 deepseek-chat / gpt-4）

启动成本（~1.7s）占墙钟比例上升 → **可考虑 BS=20**：
- 12 条拆 2 批：12.5s
- 12 条 1 批：~14s
- 但单批 20 不会比 2 批 10+2 慢

**经验法则**：每条增量 < 启动成本时拆批，> 启动成本时合批。
