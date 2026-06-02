"""render_deep_analysis.py 单元测试 — 锁定 2026-06-02 晚间"孤儿 **"bug 不回归。

WeCom 支持成对 **X** 渲染加粗（用户 2026-06-02 22:50 反馈修正）。
flash sub-agent 常写出未闭合的 **（末尾多写当加粗没闭合）。
策略（用户方案"末尾残留加粗"）：就地补齐成对，让 WeCom 渲染为加粗。
- 末尾孤儿 X** → 补开 → **X** （X 被加粗）
- 段中粗体起点 X** Y → 第 1 个开 + 第 2 个闭 → 加粗 X** 之间的内容（实际是 "X"，第 2 个 ** 当闭）
- 堆俩 **** → 重叠合并 → **X**
- 已成对 **X** → 保留
"""
from trendradar.scripts.render_deep_analysis import format_analysis, clean


def test_clean_pads_trailing_orphan_to_paired():
    """末尾孤儿 X** → **X**（就地闭合）。"""
    out = clean("一、AI 从虚拟溢出，攻入物理与基础科学**")
    # 实际行为：补到前面形成 **X** 模式（用户方案"末尾残留加粗"）
    assert "攻入物理与基础科学" in out
    # ** 数量成对（开闭各 1）
    assert out.count("**") % 2 == 0
    # 业务内容保留
    assert "一、AI 从虚拟溢出" in out


def test_clean_preserves_paired_double_star():
    """已成对 **X** 必须保留（WeCom 渲染加粗）。"""
    out = clean("**重要警告**：芯片围堵升级")
    assert "**重要警告**" in out, f"成对 ** 被破坏: {out!r}"
    assert "重要警告" in out
    assert "芯片围堵升级" in out


def test_clean_pads_mid_paragraph_bold():
    """段中 ** 当粗体起点（无闭合）→ 剥掉（用户方案：避免乱加粗）。"""
    src = "Anthropic 秘密提交 IPO，揭示 AI 资本化加速。** 一边是 AI 明星公司走向公开市场定价。"
    out = clean(src)
    # 业务内容保留
    assert "Anthropic 秘密提交 IPO" in out
    assert "一边是 AI 明星公司" in out
    # 段中孤儿 ** 被剥
    assert "**" not in out
    # 文字连贯
    assert "加速。 一边" in out


def test_clean_merges_stacked_double_star():
    """堆俩 **（LLM 既想加粗又没闭合）→ 重叠合并为 2 对。"""
    out = clean("⚠️ **🧠 AI 伦理真空：心理健康应用的灰区风险****")
    # 业务内容保留
    assert "AI 伦理真空" in out
    assert "灰区风险" in out
    # ** 数量成对（4 个 = 2 对）
    assert out.count("**") == 4
    assert out.count("**") % 2 == 0


def test_format_keeps_intentional_paired_bold():
    """脚本自己拼装的成对 **（emoji 路径）必须保留 — WeCom 渲染加粗。"""
    out = format_analysis("风险点：埃博拉疫情蔓延。", topic="风险信号", push_id="evening")
    # 风险关键词触发 emoji 路径，输出应是 ⚠️ **风险点：…**
    assert "⚠️ **风险点：埃博拉疫情蔓延。**" in out, f"丢失脚本自有加粗: {out!r}"


def test_format_e2e_evening_deep_realistic():
    """端到端：模拟 evening.deep.md 实测输入，所有 ** 必须成对或被剥。"""
    text = """一、AI 从虚拟溢出，攻入物理与基础科学**

OpenAI 重返机器人赛道（年薪 200 万）、材料版 AlphaFold 问世、VAST 2 亿美元押注世界模型——三条消息指向同一拐点。

⚠️ **🧠 AI 伦理真空：心理健康应用的灰区风险****

风险点：年轻人转向 AI 聊天机器人获取心理支持。"""
    out = format_analysis(text, topic="测试", push_id="evening")
    # ** 数量必须偶数（成对），不能有孤儿
    assert out.count("**") % 2 == 0, f"** 数量奇数，孤儿: {out!r}"
    # 业务内容没被破坏
    assert "OpenAI 重返机器人赛道" in out
    assert "年轻人转向 AI 聊天机器人" in out
    # 段中孤儿 ** 已被剥（避免 WeCom 看到 X** Y）
    assert "加速。** 一边" not in out


def test_format_preserves_chinese_text_intact():
    """已成对 ** 包裹中文标题保留（WeCom 渲染加粗），未成对的剥。"""
    out = format_analysis(
        "**埃博拉疫情再蔓延**：跨境扩散可能触发国际公共卫生紧急事件。",
        topic="风险",
        push_id="evening",
    )
    # 成对保留
    assert "**埃博拉疫情再蔓延**" in out, f"成对丢失: {out!r}"
    assert "跨境扩散" in out
    # 至少 4 个 **（topic 1对 + 埃博拉 1对）
    assert out.count("**") >= 4


def test_clean_no_change_when_no_stars():
    """没有 ** 时 clean() 不应修改文本。"""
    src = "普通中文文本，没有 markdown。"
    out = clean(src)
    assert out == src


def test_clean_pads_leading_orphan():
    """开头孤儿 **X → 剥掉（用户方案：避免乱加粗）。"""
    out = clean("**OpenAI 重返机器人赛道")
    # ** 业务内容保留
    assert "OpenAI 重返机器人赛道" in out
    # 开头 ** 被剥（段中/行首孤儿走剥掉路径）
    assert "**" not in out
