<!-- version: 2.8.0 | last-reviewed: 2026-05-26 -->

# render_markdown.py 故障模式

## 1. 文件空/0 字节

**症状：** cron 找不到脚本，回退到 LLM 渲染→格式跑偏（横线、单空行）

**诊断：**
```bash
ls -la ~/.hermes/trendradar/scripts/render_markdown.py
# 如果显示 0 bytes → 损坏
```

**修复：** 从仓库恢复：
```bash
cp ~/TrendRadar/trendradar/scripts/render_markdown.py ~/.hermes/trendradar/scripts/
```

## 2. 日期格式不匹配

**症状：** `Curated file not found: /path/curated_morning_2026-05-24.json`

**原因：** 文件名用 `%Y%m%d`（如 `20260524`），但脚本用 `%Y-%m-%d`（如 `2026-05-24`）

**修复：** main() 中必须区分两个变量：
```python
today_display = datetime.now(CST).strftime('%Y-%m-%d')  # 用于显示标题
today_file    = datetime.now(CST).strftime('%Y%m%d')     # 用于查找文件
```

## 3. 数据结构假设错误

**症状：** `AttributeError: 'str' object has no attribute 'get'` 或 `TypeError: '>=' not supported between 'dict' and 'int'`

**原因：**
- curated JSON 结构是 `{domain: [items, ...], total: N}`，不是扁平 `{items: [...]}`
- 每个 item 的 `_heat` 字段是 dict（含 `appearances`, `heat_score`, `is_new` 等键），不是 int

**修复：**
- 遍历 `data.get(domain, [])` 而非 `data.get('items', data)`
- `_detect_emoji()` 中对 `_heat` 做 `isinstance` 判断：
  - dict → 检查 `appearances >= 2` 或 `heat_score >= 0.8`
  - int/float → 直接比较

## 4. cron prompt 脚本名不匹配

**症状：** cron agent 找不到脚本 → 回退 LLM

**原因：** cron prompt 中写死了 `render_briefing.py`，但脚本已改名为 `render_markdown.py`

**修复：** 必须单独更新 cron prompt（skill 内容不会自动同步到 prompt）：
```bash
hermes cron update --job-id 90a2866775df --prompt "...render_markdown.py..."
```

## 5. 验证脚本正常

```bash
cd ~/.hermes/trendradar
PYTHONPATH=/home/asus/.hermes python3 scripts/render_markdown.py --push-id morning 2>/dev/null | head -5
# 预期输出以 "### Hermes日报" 开头
```
