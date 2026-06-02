"""render_deep_analysis.py 单元测试 — 锁定 2026-06-02 晚间"孤儿 **"bug 不回归。

WeCom 不解析 markdown 加粗（成对或不成对都按原字符输出），flash sub-agent
生成的章节标题尾巴常多写一个 **，或在段中加 ** 当粗体中点。本测试覆盖：
- Case A: 标题末尾孤儿 ** （趋势主线 1-4）
- Case B: 标题堆俩 ** + 段中 ** 当粗体中点（风险信号 AI 伦理）
- Case C: 段中 ** 当粗体中点（跨域影响 1-4）
- 脚本自己拼装的成对 ** 保留（让 WeCom 渲染加粗）
"""
from trendradar.scripts.render_deep_analysis import format_analysis, clean


def test_clean_strips_unmatched_trailing_double_star():
    """标题末尾一个孤儿 ** 必须剥干净。"""
    out = clean("一、AI 从虚拟溢出，攻入物理与基础科学**")
    assert "**" not in out, f"残留 ** : {out!r}"
    assert "攻入物理与基础科学" in out


def test_clean_strips_paired_double_star():
    """成对 **...** 也剥（WeCom 不解析，留着就是两个字面字符）。"""
    out = clean("**重要警告**：芯片围堵升级")
    assert "**" not in out
    assert "重要警告" in out


def test_clean_strips_mid_paragraph_bold_marker():
    """段中 ** 当粗体中点用，剥掉。"""
    src = "Anthropic 秘密提交 IPO，揭示 AI 资本化加速。** 一边是 AI 明星公司走向公开市场定价。"
    out = clean(src)
    assert "**" not in out
    assert "Anthropic 秘密提交 IPO" in out
    assert "一边是 AI 明星公司" in out


def test_clean_strips_double_stacked_double_star():
    """标题堆俩 **（LLM 既想加粗又没闭合）剥干净。"""
    out = clean("⚠️ **🧠 AI 伦理真空：心理健康应用的灰区风险****")
    assert "**" not in out
    assert "AI 伦理真空" in out
    assert "灰区风险" in out


def test_format_keeps_intentional_paired_bold():
    """脚本自己拼装的成对 **（emoji 路径）必须保留 — WeCom 渲染加粗。"""
    out = format_analysis("风险点：埃博拉疫情蔓延。", topic="风险信号", push_id="evening")
    # 风险关键词触发 emoji 路径，输出应是 ⚠️ **风险点：…**
    assert "⚠️ **风险点：埃博拉疫情蔓延。**" in out, f"丢失脚本自有加粗: {out!r}"


def test_format_e2e_evening_deep_realistic():
    """端到端：模拟 evening.deep.md 实测输入，输出不能含任何 ** 残留。"""
    text = """一、AI 从虚拟溢出，攻入物理与基础科学**

OpenAI 重返机器人赛道（年薪 200 万）、材料版 AlphaFold 问世、VAST 2 亿美元押注世界模型——三条消息指向同一拐点。

⚠️ **🧠 AI 伦理真空：心理健康应用的灰区风险****

风险点：年轻人转向 AI 聊天机器人获取心理支持。"""
    out = format_analysis(text, topic="测试", push_id="evening")
    # 残留必须成对出现（脚本自加 topic + 风险关键词触发 emoji），无孤儿
    assert out.count("**") % 2 == 0, f"** 数量奇数，孤儿: {out!r}"
    # 业务内容没被破坏
    assert "OpenAI 重返机器人赛道" in out
    assert "年轻人转向 AI 聊天机器人" in out
    # LLM 自带的孤儿/错配标记全剥
    assert "攻入物理与基础科学**" not in out
    assert "灰区风险****" not in out


def test_format_preserves_chinese_text_intact():
    """剥 ** 时不能误伤其他字符。"""
    out = format_analysis(
        "**埃博拉疫情再蔓延**：跨境扩散可能触发国际公共卫生紧急事件。",
        topic="风险",
        push_id="evening",
    )
    assert "埃博拉疫情再蔓延" in out
    assert "跨境扩散" in out
    # 至少 1 对成对 **（脚本自有的 topic 头）
    assert out.count("**") >= 2
