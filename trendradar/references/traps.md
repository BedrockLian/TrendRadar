# 已知陷阱

> 编号对应发现顺序。部分陷阱已被代码修复（标注 `[已修复]`），保留记录以防回退。

## 1. Cron 模板变量陷阱
`{PUSH_ID}` 不会被 scheduler 展开。**修复**：步骤 0 先跑 `push_slot_detect.py` 获取真实参数。

## 2. delegate_task max_iterations 崩溃
非晚间误触发时子代理消耗 50 calls 后崩溃。**修复**：仅 evening 时段调用。

## 3. 英文摘要残留
外媒摘要必须翻译中文。**修复**：`config/translate.yaml` 定义的 + 未列出的英文源一律翻译。

## 4. WeCom 分片丢失
>4000 字符 WeCom 静默截断。按板块分片，片间 1.5s。delegate_task 结果独立投递。cron 中通过 final response 自动投递，非 send_message。

## 5. 零前置文本违规
LLM 输出 "Now let me" / "Here is" 等过程描述会被推送到 WeCom。cron prompt 顶部禁止此类短语。

## 6. AC 自动机 + Free-Threaded 的 GIL
`pyahocorasick` C 扩展未声明 `Py_MOD_GIL_NOT_USED`。`PYTHON_GIL=0` 强制保持。

## 7. zstd 压缩副本单向
`write_compressed()` 写 `.json.zst` 但无脚本读——冷备份用途，非热数据路径。

## 8. Bracketless except 限制
`except A, B, C as e:` 是语法错误。需括号：`except (A, B, C) as e:`。

## 9. python3.14t 环境不完整
`--disable-gil` 编译的 Python ABI 不兼容标准 wheel。两个必需修复：
- **C 扩展缺失**：`_zstd`/`feedparser` 需 `python3.14t -m pip install zstandard feedparser`
- **PYTHONPATH 缺失**：cron prompt 必须 `export PYTHONPATH=/home/asus/.hermes`，否则 `ModuleNotFoundError: No module named 'trendradar'`。pyproject.toml 的 `[tool.pdm]` 配置对子 shell 无效。

## 10. translate.yaml 源名与 sources.json 不同步
重构 sources.json 时 translate.yaml 的旧源名不会自动失效——翻译静默跳过无报错。
**修复**：改 sources.json 后跑 `pytest tests/ -k translate_config`。

## 11. 游戏源误分"外媒看华" [已修复]
分类链按优先级设计，游戏外媒标题含 "Chinese" → 先匹配 `foreign_china`。
**修复**：L143 加 `and not any(sp in plat for sp in GAME_SRC)` 排除。

## 12. charset-normalizer 短文本误判 [已修复]
短文本（<50字符）编码检测不可靠。**修复**：显式编码枚举提至 charset-normalizer 之前。

## 13. Gateway 崩溃 → 推送丢失但脚本报"成功"
Pipeline 报告投递成功，但 Gateway 同时崩溃消息未达 WeCom。
**信号**：`hermes gateway status` 显示 `failed`，用户反馈没收到但 cron 日志 ok。
**修复**：重启 Gateway → 补推 bypass（直接 render→fragment→final response 自动投递）。

## 14. Cron 技能名不匹配
技能重命名后 cron `skills` 列表仍引用旧名 → `⚠️ Skill(s) not found and skipped`。
**修复**：`cronjob action=update job_id=xxx skills=[...]`。重命名后必须同步 cron skills 列表 + SKILL.md companion_skills + system-config 文档。

## 15. Cron prompt 与 skill 内容不同步
cron prompt 是独立文本字段。skill 更新脚本名/步骤后 prompt 不自动更新。Agent 看到 skill 内容但优先执行 prompt 中的旧命令。
**信号**：prompt 引用已删除脚本（如 `render_briefing.py`）、旧技能名（`trendradar-news-secretary`）。
**修复**：`cronjob action=update job_id=xxx prompt="..."` 单独更新。每次改 pipeline 脚本名后检查所有 cron prompt。

## 16. tirith 安全扫描拦截中文命令 [已关闭]
中文/Unicode 内容触发规则匹配 → terminal 命令被拦截。**修复**：`hermes config set security.tirith_enabled false`。

## 17. push_slot_detect 返回 NO_SLOT 跳过推送
补推或跨时段手动触发时有时效窗口限制。**修复**：绕过 slot 检测，直接 render→fragment→final response 自动投递。不要重跑完整 pipeline（会变更数据状态）。

## 18. render_markdown.py 跨板块间距异常 [已修复]
`render_all()` 拼接板块时 `\n\n\n` + 板块末尾 `\n\n\n` → >4 空行。
**修复**：`_generate_section()` 返回前 `.rstrip('\n')`。

## 19. references/ 目录在 workdir 不存在
skill 内 `cat references/xxx.md` 依赖 workdir references/。如果不存在返回空。
**修复**：`mkdir -p ~/.hermes/trendradar/references && cp -r ~/.hermes/skills/trendradar/news-secretary/references/* $_`。

## 20. Cron prompt 引用已删除的辅助脚本
`blind_spot_audit.py` / `aggregate_monthly.py` 被周报/月报 prompt 引用但可能不存在。
**修复**：确认脚本存在于 workdir，或从仓库恢复。

## 21. render_markdown.py 日期格式不匹配 [已修复]
curated 文件名 `%Y%m%d`（无连字符）vs 脚本中 `%Y-%m-%d` → 找不到文件。
**修复**：两个变量：`today_file = strftime('%Y%m%d')`（文件路径），`today_display = strftime('%Y-%m-%d')`（标题）。

## 22. Cron context 下投递机制 [已弃用 send_message]
`send_message` 工具在 cron 运行时**不可用**。pipeline 应始终将渲染好的简报作为 final response 输出，由系统自动投递到 WeCom。不要尝试在 cron 中用 send_message 逐片投递。
**信号**：日志有 "send_message isn't available" + agent 回退到 LLM 重新生成内容。
**修复**：cron prompt 指定——将 BRIEFING 作为最终输出，系统自动投递。详见 `cron-sendmessage-fallback.md`。

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
