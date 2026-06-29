# `data/sources.json` 丢失导致的翻译静默失败

## 场景

`git clean -fd`、`git reset --hard`、仓库重建等操作后，`data/sources.json` 被删除。
`ai_translate.py` 依赖该文件检测外文条目语言，缺失时静默跳过所有翻译。

## 症状链

```
data/sources.json 被删除
→ _load_source_languages() 返回空 frozensets
→ get_source_lang() 对所有条目返回 None
→ items_to_translate 列表为空
→ "No English items found for push-id 'morning'"（误导性消息 — 可能同时含日文条目）
→ 0 条翻译
→ 渲染时 title_cn/summary_cn 全部缺失 → render_markdown 用原始外文
→ 用户质问"翻译呢？"
```

## 诊断

```bash
# 1. 确认 sources.json 是否存在
ls -la ~/.hermes/trendradar/data/sources.json

# 2. 手动跑一次翻译看输出
PYTHONPATH=/home/asus/.hermes/trendradar PYTHON_GIL=0 /usr/local/bin/python3.14t \
  ~/.hermes/trendradar/trendradar/scripts/ai_translate.py --push-id morning 2>&1
# 期望: "Found N items to translate" (>0)
# 若显示 "No English items found" → sources 缺失

# 3. 检查翻译是否已写入
python3 -c "
import json
d = json.load(open('~/.hermes/trendradar/data/curated_morning.json'))
for k, v in d.items():
    if isinstance(v, list):
        for item in v:
            if 'title_cn' in item:
                print(f'OK: {item[\"title_cn\"][:40]}')
                break
"
```

## 修复

```bash
# 从备份恢复
cp ~/backups/trendradar/$(date +%Y%m%d)/sources.json ~/.hermes/trendradar/data/sources.json

# 或从仓库配置复制（注意格式可能不同）
cp ~/.hermes/trendradar/trendradar/config/sources.json ~/.hermes/trendradar/data/sources.json

# 重新翻译
PYTHONPATH=/home/asus/.hermes/trendradar PYTHON_GIL=0 /usr/local/bin/python3.14t \
  ~/.hermes/trendradar/trendradar/scripts/ai_translate.py --push-id {slot}
```

## 预防

- `data/sources.json` 应纳入备份策略（每日维护脚本已备份 `data/sources.json`）
- `git clean -fd` 执行前预览：`git clean -n`
- health_check 应增加 `data/sources.json` 存在性检查（若缺失 → WARN 推送）
