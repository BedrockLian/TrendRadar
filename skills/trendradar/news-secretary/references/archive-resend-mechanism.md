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

## ⚠️ 关键：禁止 cat | hermes send

**不要**这样补发：
```bash
# ❌ 整文件推送 — WeCom 消息体限制约 4KB，尾部内容被静默截断
cat archive/2026-05-30/noon.md | hermes send --to wecom:bl
```

简报存档通常在 8-12KB，远超 WeCom 限制。截断无声无息——pipeline 和 `hermes send` 都报告成功，但尾部板块（通常是游戏/经济）完全消失。

**必须**用 `archive_resend.py`（它走 fragment_push 的分片逻辑）。

## 补发流程

```bash
# 1. 列出可用存档
$PYTHON scripts/archive_resend.py --list

# 2. 补发（预览+确认+投递）
$PYTHON scripts/archive_resend.py --date 2026-05-27 --slot morning

# 3. 跳过确认直接发
$PYTHON scripts/archive_resend.py --date 2026-05-30 --slot noon --yes
```

## 路径配置

补发脚本从 `TRENDRADAR_HOME` 环境变量读取存档路径。手动运行时必须正确设置：

```bash
cd ~/.hermes/trendradar
TRENDRADAR_HOME=$PWD/trendradar \    # ← 指向内层 trendradar/ 目录
PYTHONPATH=$PWD \                      # ← 指向外层（含包）
PYTHON_GIL= \                           # ← 必须 unset，否则 config_read_gil 崩溃
  python3 trendradar/scripts/archive_resend.py --date 2026-05-30 --slot noon
```

`TRENDRADAR_HOME` 必须指向包含 `scripts/`、`data/`、`archive/` 的内层 `trendradar/` 目录，不是外层。

## `archive_resend.py` 的安全约束

- 存档不存在 → `[ERROR] 禁止自行生成内容` → 退出码 1
- 存档为空 → 同样报错退出
- 投递前打印预览 + 分片信息（每片大小和超限警告）
- 逐片投递，单片失败不阻断后续

## v2 变更（2026-05-30）

- 旧版：整文件 `hermes send content` → 超 WeCom 限制，尾部静默截断
- v2：接入 `fragment_push.split_fragments()` 按 3800 bytes 分片 → 逐片 `hermes send` → 每片独立送达
- 修复：`TRENDRADAR_HOME` 显式设置时被 `__init__.py` auto-detect 上提一层的路径解析 bug

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
      └── archive_resend.py   ← 安全补发脚本（v2: 分片投递）
```
