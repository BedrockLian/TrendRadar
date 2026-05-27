# 存档与安全补发机制

> Added: 2026-05-27  
> Trigger: Agent hallucinated The Verge articles when resending a failed morning briefing. Root cause: read from cron output log (mixed with skill context) instead of actual curated data.

## 存档流程

```
render_markdown.py --push-id {slot}
  │
  ├── 输出 markdown 到 stdout → fragment_push → WeCom
  └── 同时写入 archive/YYYY-MM-DD/{slot}.md ← 纯 markdown，不含任何元数据
```

每期简报渲染时自动存档。存档文件是**纯 markdown**，只有标题、摘要、链接、尾注，没有 pipeline 日志、skill 描述、运行时间等上下文。

## 补发流程

```bash
# 1. 列出可用存档
$PYTHON scripts/archive_resend.py --list

# 2. 补发（预览+确认+投递）
$PYTHON scripts/archive_resend.py --date 2026-05-27 --slot morning
```

`archive_resend.py` 的安全约束：
- 存档不存在 → `[ERROR] 禁止自行生成内容` → 退出码 1
- 存档为空 → 同样报错退出
- 投递前打印前 200 字预览

## 为什么不允许读 cron 输出日志

cron 输出文件（`~/.hermes/cron/output/90a2866775df/YYYY-MM-DD_HH-MM-SS.md`）包含：
- Agent 的完整 system prompt（含 skill 全文）
- pipeline 各步骤的调试输出
- 源平台列表（含 The Verge、TechCrunch 等源名）
- **最后才是**实际报告的 markdown

读到源名后，很容易产生"这个源有内容"的虚假印象，导致编造该源的虚构报道。存档是唯一可信的补发数据源。

## 目录结构

```
~/.hermes/trendradar/
  ├── archive/                ← 纯 markdown 存档（render_markdown 自动写入）
  │   ├── 2026-05-27/
  │   │   ├── morning.md
  │   │   ├── noon.md
  │   │   └── evening.md
  │   ├── 2026-05-28/
  │   │   └── ...
  ├── data/                   ← 运行时数据
  ├── backups/                ← 每日备份（含 curated JSON）
  └── scripts/
      └── archive_resend.py   ← 安全补发脚本
```
