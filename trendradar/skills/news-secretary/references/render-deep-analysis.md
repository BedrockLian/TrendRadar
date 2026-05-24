# render_deep_analysis.py — Pro 深度分析格式化器

## 位置
`scripts/render_deep_analysis.py`

## 用途
将 delegate_task Pro 子 agent 的分析文本格式化为 WeCom 手机端友好的紧凑格式。

## 特性
- 清洗 LLM 输出中的 WeCom 不支持元素（代码块、表格、横线、HTML 标签）
- 保留自然段落结构，不做强制截断
- 自动检测短句关键词（趋势/方向/总结/风险/机会等），映射对应 emoji 作为子标题标记
- 1600 字符硬上限（WeCom 单消息上限）

## 用法
```bash
# 管道输入
echo "分析文本..." | python3 scripts/render_deep_analysis.py --topic "AI · 科技趋势"

# 文件输入
python3 scripts/render_deep_analysis.py --topic "地缘政治/经济" --input analysis.txt
```

## Emoji 映射表
| 关键词 | Emoji | 触发条件 |
|--------|-------|---------|
| 趋势 | 📈 | 行长度 < 25 字且含关键词 |
| 方向 | 🎯 | 同上 |
| 分析 | 🔍 | 同上 |
| 总结/结论 | 📌 | 同上 |
| 影响 | ⚡ | 同上 |
| 风险 | ⚠️ | 同上 |
| 机会 | 💡 | 同上 |
| 观点 | 💭 | 同上 |
| 启示 | ✨ | 同上 |
| 展望 | 🔭 | 同上 |

## Pipeline 集成
Pro 子 agent 输出 → `render_deep_analysis.py --topic "主题"` → final response（系统自动投递 WeCom）

## 已知限制
- 对 LLM 输出的段落实体识别依赖关键词匹配，非常规关键词的短标题不会自动加 emoji
- 不进行重写/润色，仅做格式清洗
