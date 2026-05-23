# 已知陷阱

## 1. Cron 模板变量陷阱
`{PUSH_ID}` 等模板变量不会被 Hermes scheduler 展开，LLM 据此判断时段必然失效。**修复**：步骤 0 先跑 `push_slot_detect.py` 获取真实参数。

## 2. delegate_task max_iterations 崩溃
非晚间误触发时子代理消耗 50 calls 后崩溃。**修复**：仅 step 10 判断为 evening 时才调用，禁止 LLM 自行判断。

## 3. 英文摘要残留
外媒摘要必须翻译中文。`config/translate.yaml` 定义的源和未列出的英文源都需要翻译。

## 4. WeCom 分片丢失
>4000 字符 WeCom 静默截断。必须按板块分片，片间 1.5s 延迟。delegate_task 结果走独立 send_message，不拼在简报末尾。

| 💥 5. 零前置文本违规
LLM 输出 "Now let me" / "Here is" 等过程描述会被推送到 WeCom。**修复**：cron prompt 顶部列出禁止短语，步骤描述与输出严格分离。

## 6. AC 自动机 + Free-Threaded 的 GIL 恢复
`pyahocorasick` 是 C 扩展，未声明 `Py_MOD_GIL_NOT_USED`。**修复**：`PYTHON_GIL=0` 强制保持 GIL disabled。

## 7. zstd 压缩副本是单向的
`write_compressed()` 写 `.json.zst` 但无脚本读它——冷备份用途，非热数据路径。

## 8. Bracketless except 的 `as e` 限制
`except A, B, C as e:` 是语法错误。`as e` 时仍需括号：`except (A, B, C) as e:`。

## 9. Free-threaded Python (python3.14t) 缺 C 扩展
`--disable-gil` 编译的 Python ABI 为 `cpython-314t`，与标准 `cpython-314` 不兼容。以下 C 扩展缺失：
- **`_zstd`**：`from compression import zstd` 报 `ModuleNotFoundError: No module named '_zstd'`。修复：`config.py` 已加三级 fallback（`compression.zstd` → `zstandard` → 普通 JSON），但首次部署需 `python3.14t -m pip install zstandard`。
- **`feedparser`**：venv 的包不被 python3.14t 共享。需手动装：`python3.14t -m pip install feedparser`。

## 10. python3.14t 需要 PYTHONPATH
脚本使用 `from trendradar.scripts.common import ...`，但 python3.14t 没有项目根在 sys.path 里。cron prompt 必须显式 `export PYTHONPATH=/home/asus/.hermes`。不加则 `ModuleNotFoundError: No module named 'trendradar'`。`export` 不是可选的——子 shell 不继承未 export 的变量。

## 11. translate.yaml 源名与 sources.json 不同步
`config/translate.yaml` 的 `sources` 和 `japanese_sources` 列的是源名字符串，与 `data/sources.json` 的 `name` 字段一一对应。如果 sources.json 重构（比如 `纽约时报` 拆分出 `纽约时报·世界` 和 `纽约时报·科技`），translate.yaml 的旧名不会自动失效——翻译静默跳过不存在的源，没有任何报错。**修复**：`pytest tests/ -k translate_config` 会校验全部映射。建议在改 sources.json 后立即跑此测试。

## 12. 标题翻译遗漏（v5.4.0 修复）
旧版 `ai_translate.py` 只翻译 `summary` 字段，不翻译 `title`。`render_briefing.py` 将原始英文标题传给 LLM 后可能仍保留英文。**v5.4.0 修复**：ai_translate 同时检测标题 CJK 占比并写入 `title_cn`。render_briefing 优先取 `title_cn`。渲染 prompt 也要求 LLM 翻译残留英文标题。

## 13. 分片缺失导致 WeCom 截断（v5.4.0 修复）
旧版 cron 将渲染后的完整简报作为 final response 由系统 auto-deliver，超过 4000 字符时 WeCom 静默截断。**v5.4.0 修复**：新增 `fragment_push.py`，渲染输出经分片后逐片用 `send_message` 投递，片间 1.5s 延迟，尾注仅末片。cron prompt 最后返回 [SILENT] 防重复。

## 14. fragment_push.py 不可作为独立 CLI 推送
`fragment_push.py` 从 stdin 读全文、输出 JSON 数组到 stdout。它不分发消息——分发由 cron agent 用 `send_message` 工具完成。不要试图在 shell 中直接 `fragment_push.py | ...` 推送。

## 15. 游戏源被误分"外媒看华"
`curate_and_push.py` 分类链按优先级而非最佳匹配设计。`foreign_china` 规则先于 `gaming` 检查。
如果游戏外媒（Automaton West、4Gamer）标题含 "Chinese" → 优先匹配 `foreign_china`。
**修复**：L143 加 `and not any(sp in plat for sp in GAME_SRC)` 排除游戏源，优先走游戏分类。

## 16. charset-normalizer 短文本误判
`_decode()` 用 charset-normalizer 对短文本（<50字符）编码检测不可靠。
**修复**：显式编码枚举（utf-8/gbk/euc-jp...）提至 charset-normalizer 之前。仅当所有显式编码都失败后才用其兜底。
