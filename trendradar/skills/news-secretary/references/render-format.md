# render_briefing.py 输出格式规范（统一版）

> 简报渲染已由 `render_briefing.py` 完全接管（5 路并行 API，~9s）。本文档是格式的唯一权威来源。

## 输出格式（三段式）

```
### Hermes日报 · YYYY-MM-DD（早报/午报/晚报）

### 📰 头条

🆕 1. **标题**
摘要（30-60字中文，英文已翻译）
[查看原文](url)【媒体名】


🆕 2. **标题**
...
（条目间两个空行 \n\n\n）

### 🌏 外媒看华

...

**📋 共 N 条 · 头条A  外媒看华B  科技C  经济民生D  游戏E**
```

## 格式铁律

### 标题行
`### Hermes日报 · YYYY-MM-DD（早报/午报/晚报）`

### 板块顺序
📰头条 → 🌏外媒看华 → 💻科技 → 📊经济民生 → 🎮游戏

### 条目模板
```
{热度emoji} {全局序号}. **标题**

摘要（50-100字，英文源翻译中文）

[查看原文](url)【媒体名】

[双空行]
{next item}
```

- 三行式间：**1 个空行** `\n\n`（标题⇢摘要⇢链接之间）
- 条目之间：**2 个空行** `\n\n\n`
- 板块标题前后：**2 个空行** `\n\n\n`
- WeCom 单空行在手机上折叠成一行，必须用双空行才能看见分段

### 全局连续编号
从头条 1 到游戏 N，不按板块重置。

### 热度 emoji
- 🆕 = 当日首发
- 🔥 = 跨源热点
- 🔄 = 持续进展
- 📌 = 深度分析

### 尾注
`**📋 共 N 条 · 头条A  外媒看华B  科技C  经济民生D  游戏E**`
- 加粗，栏目间**双空格**
- 从 `curated_{push_id}.json` 读取各 domain 实际条数生成，不硬编码配比

### 分片规则
- 超 4000 字符按板块分片，片间 ≥1.5s 延迟
- 片首不重复标题行
- 尾注仅出现在最后一片

### 禁止
- **横线** `---`（WeCom 不渲染，用双空行分隔即可）
- **表格/引用/斜体/删除线**（WeCom 不支持）
- **零前置文本**：首字符必须是 `###`。禁止 "Now let me" / "Here is" / "I will now" 等自我叙述。简报结束后不追加文字。

## 关键特性

### 1. 板块标题硬编码
LLM 经常自行输出 `### 🚀 头条`（用错 emoji）。脚本强制逻辑：
1. 接收 LLM 输出
2. 检查第一行是否以 `###` 开头 → 如果是则剥离
3. 用 `DOMAIN_EMOJI` / `DOMAIN_LABEL` 中的硬编码值重新生成
4. 正确的 emoji 映射：`📰 头条` `🌏 外媒看华` `💻 科技` `📊 经济民生` `🎮 游戏`

### 2. 板块间距
`\n\n\n`（双空行）分隔各板块。LLM 输出的板块间多余空行会被保留。

### 3. 空板块
板块无条目时输出 `暂无内容`（外媒看华和游戏板块可能在早报阶段为空）。

## 使用方式

```bash
export PYTHON=/usr/local/bin/python3.14t
export PYTHONPATH=/home/asus/.hermes
export PYTHON_GIL=0
$PYTHON scripts/render_briefing.py --push-id morning 2>/dev/null
```

stdout = 完整 Markdown 简报，stderr = 日志。Agent 只需要**捕获 stdout 直接投递**，不需要对输出做任何格式修改。

## 手机端空行铁律（WeCom）

- 三行式间：**1 个空行** `\n\n`（标题⇢摘要⇢链接之间）
- 条目之间：**2 个空行** `\n\n\n`
- 板块标题前后：**2 个空行** `\n\n\n`
- WeCom 单空行在手机上折叠成一行，必须用双空行才能看见分段

## 自检命令

```bash
grep -ciE 'All data gathered|Now producing|Let me|Here is|I will now'  # 应为 0
grep -c '\[查看原文\].*【.*】'        # 超链接格式
grep -cP '\*\*📋 共.*  .*'           # 尾注
head -1 | grep -cP '^### Hermes日报'  # 首行
grep -cP '^[A-Z][a-z]+ [a-z]+ [a-z]+ [a-z]+ '  # 英文残留，应为 0
grep -c '---'                        # 横线残留，应为 0
```

## 规格参数

- 模型: deepseek-v4-flash（与管线同模型，共享 KV 缓存池）
- temperature: 0.5, max_tokens: 2048
- API 超时: 60s, 重试: 3 次（指数退避 2^n）
- 并行度: 5（每板块 1 路 API 调用）

## 回退策略

如果 `render_briefing.py` 失败（返回码非零或 stdout 为空），Agent 应回退到手动渲染。
手动渲染的格式必须与脚本输出完全一致（硬编码 emoji、双空行板块间距、规范尾注）。

## 输出前自检（手动渲染时使用）

```bash
grep -ciE 'All data gathered|Now producing|Let me|Here is|I will now'  # 应为 0
grep -c '\[查看原文\].*【.*】'        # 超链接格式
grep -cP '\*\*📋 共.*  .*'           # 尾注
head -1 | grep -cP '^### Hermes日报'  # 首行
grep -cP '^[A-Z][a-z]+ [a-z]+ [a-z]+ [a-z]+ '  # 英文残留，应为 0
grep -c '\-\-\-'                      # 横线残留，应为 0
```
