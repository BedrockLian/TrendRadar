<!-- version: 2.8.0 | last-reviewed: 2026-05-26 -->

# 已修复陷阱存档

> 已修复的历史陷阱存档。保留以防回退。日常运维无需阅读。

## 11. 游戏源误分"外媒看华" [已修复]
分类链按优先级设计，游戏外媒标题含 "Chinese" → 先匹配 `foreign_china`。
**修复**：L143 加 `and not any(sp in plat for sp in GAME_SRC)` 排除。

## 12. charset-normalizer 短文本误判 [已修复]
短文本（<50字符）编码检测不可靠。**修复**：显式编码枚举提至 charset-normalizer 之前。

## 18. render_markdown.py 跨板块间距异常 [已修复]
`render_all()` 拼接板块时 `\n\n\n` + 板块末尾 `\n\n\n` → >4 空行。
**修复**：`_generate_section()` 返回前 `.rstrip('\n')`。

## 21. render_markdown.py 日期格式不匹配 [已修复]
curated 文件名 `%Y%m%d`（无连字符）vs 脚本中 `%Y-%m-%d` → 找不到文件。
**修复**：两个变量：`today_file = strftime('%Y%m%d')`（文件路径），`today_display = strftime('%Y-%m-%d')`（标题）。

## 23. render_markdown.py 不读 title_cn [已修复]
`_format_item()` 只读 `item.get('title')`，忽略 `title_cn`。
**修复**：改为 `item.get('title_cn') or item.get('title')`。详见 `translation-pipeline-sync.md`。

## 24. 翻译管线文件读取优先级不一致 [已修复]
ai_translate 优先读非日期版 curated，render_markdown 优先读日期版 → 重跑时翻译丢失。
**修复**：两者统一优先读日期版。详见 `translation-pipeline-sync.md`。

## 25. ai_translate 来源检测 [已修复]
CJK 比率检测对日语/中英混合失效 → 改为按来源平台固定分类（`_ENGLISH_SOURCES` / `_JAPANESE_SOURCES`）。详见 `translation-pipeline-sync.md`。

## 26. 裸导入 `from settings import` [已修复]
脚本直接运行时 OK（sys.path 自动加 scripts/），但 `python -c "import trendradar.scripts.xxx"` 会 `ModuleNotFoundError`。
**修复**：全部改为 `from trendradar.scripts.settings import`。扫荡命令见 `import-architecture.md`。
