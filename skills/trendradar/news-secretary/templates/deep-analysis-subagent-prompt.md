# 晚间 Pro 深度分析 sub-agent prompt 模板

3 个并行 Pro 子 agent 任务模板（趋势/跨域/风险）。已 2026-06-02 实测验证：
deepseek-v4-pro 模型，inline compact curated JSON 4KB，3 篇并行总耗时 ~150s。

## 使用方式

```python
# 1. 准备 compact curated JSON（外层路径！见 SKILL.md 双路径陷阱）
import json
d = json.load(open('/home/asus/.hermes/trendradar/data/curated_evening_20260602.json'))
out = {'curated_at': d.get('curated_at'), 'push_id': 'evening', 'total': d.get('total')}
for dom in ['top_headlines','foreign_china','tech','economy','gaming']:
    out[dom] = [
        {'title_cn': it.get('title_cn',''), 'summary_cn': it.get('summary_cn',''),
         'source': it.get('source_platform',''), 'url': it.get('url',''),
         'heat': (it.get('_heat',{}) or {}).get('heat_score', 0)}
        for it in d.get(dom, [])
    ]
compact = json.dumps(out, ensure_ascii=False, separators=(',',':'))
# 通常 ~4KB，可直接 inline 进 sub-agent context

# 2. delegate_task 批模式并行 3 个（见下方 3 个 prompt 模板）
# 3. 收 3 篇 raw 分析文本
# 4. 各自 cat | render_deep_analysis.py --topic X --push-id evening --context
# 5. 各自 echo "$F" | hermes send -t wecom:bl --subject "🔍 <板块> · <主题>"
#    板块由 orchestrator 根据主题关键词判定（同一定义见 references/deep-analysis-prompt-fix.md）：
#    - AI/芯片/科技/硅谷/苹果/微软/英伟达/AMD/半导体/数据/算法/机器人 → 科技
#    - 伊朗/核/联合国/地缘/制裁/外交/国际/全球治理/中东/俄罗斯/乌克兰 → 国际
#    - 腾讯/网易/米哈游/游戏/主机/任天堂/Sony/光追/渲染/引擎/Unity → 游戏
#    - FED/央行/通胀/GDP/关税/供应链/贸易/经济/降息/加息 → 经济
#    - 默认 → 要闻
```

## 通用约束（所有 3 个 sub-agent）

1. **仅输出分析文本**（不要"以下是..."/"下面是..."等任何前言；不要 "🔬 **主题**" 标题——由 render_deep_analysis.py 统一加）
2. **≤1600 字符**（WeCom 单消息硬限，超出会被静默截断到 1600）
3. **5-8 段**，每段 ≤40 字
4. **关键加粗**（公司名、数字、关键结论）用 **xx**
5. **纯关键词触发 emoji 前缀**（不要预先加 emoji 或 `**`！）：
   - 趋势/方向 → 让脚本自动加 📈🎯
   - 交叉/分析/影响/启示 → 让脚本自动加 🔗🔍⚡✨
   - 风险/高/中/低/综合判断 → 让脚本自动加 ⚠️🔴🟡🟢📌
6. **禁止**：pipe 表格、代码块、横线 `---`、# ## 标题、> 引用

## Sub-agent 1: 趋势方向 (Trend)

```text
基于 2026-06-02 evening 简报 15 条新闻（curated JSON 已内嵌在 context），
输出一份 Pro 级「趋势方向」深度分析。

## 严格输出规范

1. 仅输出分析文本（不要任何前言；不要 "🔬 **主题**" 标题）
2. 5-8 段，每段 ≤40 字
3. 段落标题用**纯关键词**触发自动前缀：
   - "趋势" → 📈
   - "方向" → 🎯
   - "分析" → 🔍
   - "总结/结论" → 📌
   - "影响" → ⚡
   - "机会" → 💡
4. 关键加粗（公司名、数字、关键结论）用 **xx**
5. 禁止：pipe 表格、代码块、横线、# ## 标题、> 引用
6. 总长度 ≤1600 字符
7. 数据驱动：从 15 条里挑 3-5 个核心数据点做锚定

## 分析视角

聚焦「跨域」信号（科技×经济×国际政治×AI 资本）的当日趋势走向。

## 输出结构示例

趋势 [3-5 字标题，不加 emoji/**]
   1 段 100-150 字符核心信号（公司名/数字加粗）

方向 [3-5 字标题]
   1 段核心方向 + 3-4 个 bullet（用 - 开头）

分析 [3-5 字标题]
   1-2 段深度分析

影响 [3-5 字标题]
   1 段传导影响

[总结/结论 核心判断]
   1 段一句话提炼

[context 字段] inline compact JSON:
{curated_at, push_id, total, top_headlines:[...], foreign_china:[...], tech:[...], economy:[...], gaming:[...]}
```

## Sub-agent 2: 跨域交叉 (Cross-domain)

```text
基于 2026-06-02 evening 简报 15 条新闻（curated JSON 已内嵌在 context），
输出一份 Pro 级「跨域交叉」深度分析。

## 严格输出规范

1. 仅输出分析文本
2. 5-8 段，每段 ≤40 字
3. 纯关键词触发前缀：
   - "交叉" → 🔗
   - "分析" → 🔍
   - "影响" → ⚡
   - "启示" → ✨
4. 关键加粗（公司名、领域、联动机制）用 **xx**
5. 禁止：表格/代码块/横线/标题/引用
6. ≤1600 字符
7. 必须选 2 个跨域交叉点做深度剖析

## 分析视角

找 2-3 个「跨域联动」事件 — 表面看是不同领域新闻，实际共享底层驱动：
- AI × 资本 × 地缘
- 公共卫生 × 国际治理
- AI × 教育/心理
- 具身智能 × 中美
- 材料 AI × 工业

## 输出结构示例

交叉一：[A × B 主题]
   1 段 150-200 字符核心联动分析

[传导机制/逻辑]（关键词让脚本加 ⚡/🔍）
   1 段机制 + 3-4 bullet 传导路径

交叉二：[C × D 主题]
   1 段 150-200 字符

[传导逻辑]
   1 段 + 3-4 bullet

启示
   1 段 1-2 句话核心判断

[context] inline compact curated JSON
```

## Sub-agent 3: 风险预警 (Risk)

```text
基于 2026-06-02 evening 简报 15 条新闻（curated JSON 已内嵌在 context），
输出一份 Pro 级「风险预警」深度分析。

## 严格输出规范

1. 仅输出分析文本
2. 5-8 段，每段 ≤40 字
3. 纯关键词触发前缀：
   - "风险" → ⚠️
   - "高/中/低/关注" → 配合 🔴🟡🟢
   - "影响" → ⚡
   - "综合判断" → 📌
4. 关键加粗（风险名、触发条件）用 **xx**
5. 禁止：表格/代码块/横线/标题/引用
6. ≤1600 字符
7. 必须给 3 个风险项（高/中/关注各一）+ 综合判断

## 分析视角

从 15 条新闻里识别 3-5 个真实风险信号（非一般市场波动）：
- 公共卫生（疫情/病毒扩散）
- 资本（泡沫/估值重定价）
- 地缘（中美脱钩/区域冲突）
- 社会（AI 心理依赖/青少年危机）
- 监管（AI/数据/合规）

## 输出结构示例

[风险 🔴 高][3-5 字风险名]
   1 段 100-150 字符：现状 + **触发升级条件** + **影响面**

[风险 🟡 中][3-5 字风险名]
   1 段：现状 + **触发条件** + **影响面**

[风险 🟢 关注][3-5 字风险名]
   1 段：现状 + **触发条件** + **影响面**

[综合判断]
   1 段 2-3 句话总结：早期信号 + 持续观察 + 暂无即刻行动

[context] inline compact curated JSON
```

## 已知陷阱

### emoji + `**` 双 prefix（2026-06-02 案例）

如果 sub-agent 输出 `🎯 **方向信号**`，render_deep_analysis.py 又自动加 `🎯 **方向信号**`，最终变 `🎯 **🎯 **方向信号****`（双 emoji + 多余 `**`）。

**修复**：sub-agent prompt 严格要求**只输出纯文字关键词**（"方向信号"），让脚本自动加前缀。

### 1600 字符硬截断

实测跨域篇 2211B raw 文本被脚本截到 1600B，**末尾启示段可能丢失**。预防：sub-agent prompt 严格 `≤1600 字符`，让 sub-agent 在生成时就控制长度。

### Sub-agent sandbox（无 filesystem）

delegate_task 在 cron 上下文中启动的子 agent 有独立进程上下文，**terminal/read_file 无法读取父 session 的文件**。`cat /path/to/file` 会返回空。**必须**将 curated JSON inline 在 prompt 的 context 字段中。

## 验证清单

发完 3 条后：
```bash
# WeCom 应收到 3 条独立消息（不是 1 条合并）
hermes send --list wecom  # 验证 target 存在

# 检查 3 条 raw 分析文本字节数
for f in /tmp/deep_*.txt; do
  size=$(wc -c < "$f")
  if [ "$size" -gt 1600 ]; then
    echo "WARN: $f = $size bytes (脚本会截断到 1600)"
  fi
done
```
