<!-- version: 2.8.0 | last-reviewed: 2026-05-26 -->

# fix-recipes.md — 已验证的质量问题修复脚本

> 配合 `performance-optimizer` skill 使用。每条修复模式均已验证，可直接执行。

## 1. 短摘要扩写（摘要 < 20 字）

**检测**：`python3 -c "import json; d=json.load(open('data/curated_{slot}_{date}.json')); short=[(s, a['title'][:50], len((a.get('summary','') or '').strip())) for s in d if isinstance(d[s],list) for a in d[s] if len((a.get('summary','') or '').strip())<20]; print(f'{len(short)}条短摘要'); [print(f'  [{s[0]}] {s[2]}字') for s in short]"`

**修复**：直接修改 curated JSON 中 summary 字段为 30-60 字展开摘要。写回：`json.dump(data, f, ensure_ascii=False, indent=2)`

**注意**：虎嗅/钛媒体原始摘要是短语式金句（如"梁文锋买时间，别人买答案"），不要强抓。重跑 pipeline 会覆盖手动修改。

## 2. tech 板块过度集中

**检测**：tech ≥ 16 条。**修复**：`scripts/settings.py` 中 `MAX_PER_DOMAIN['tech']` 从 18 降至 7（当前值，可调范围 5-10）。

## 3. foreign_china 板块过少

**检测**：foreign_china ≤ 2 条。

**修复 A** — `scripts/curate_and_push.py` 的 `_china_kw()` 扩充关键词：
`中国,北京,上海,广州,深圳,习近平,中俄,中美,中日,中欧,中央,解放军,外交部,商务部,国务院,发改委,国家,台湾,台独,香港,澳门,经济,股市,制造业,贸易,关税,芯片,半导体,华为,TikTok,人民币,比亚迪,阿里巴巴,腾讯,宁德时代,一带一路,大湾区,China,Chinese,Beijing,Shanghai,Xi Jinping,Taiwan,Hong Kong,Sino-,Made in China,tariff,trade war,supply chain,yuan`

**修复 B** — `_foreign_sources()` 加源：`reuters, bbc, nytimes, arstechnica, techcrunch, nhk`（NHK ビジネス 常覆盖中国经济话题）。

## 4. tirith 拦截 cron 命令

**检查**：`hermes config get security.tirith_enabled`。**修复**：`hermes config set security.tirith_enabled false`。

## 5. Cron 技能名不匹配

**症状**：`⚠️ Skill(s) not found and skipped`。详见 traps.md 中的 Trap 14。
**检查**：`hermes cron list | grep Skills:` + `ls ~/.hermes/skills/trendradar/`。**修复**：`cronjob action=update job_id=xxx skills=["new-name"]`。

## 6. 扩写/翻译结果 [扩写失败] + 内容串位（批次响应乱序）

**2026-05-31 案例**：午报经济民生第2条 DeepSeek 显示 `[扩写失败]`，同时科技第2条（铜价）的 summary_cn 写成了 DeepSeek 的内容。

**根因**：`ai_translate.py` 的 `_parse_line_pairs()` 按 AI 返回顺序分配结果。若 AI 响应顺序与请求不一致，条目 A 收到 B 的数据，B 则因无剩余响应 fallback 为 `[扩写失败]`（`fallback_label="[扩写失败]"`）。

**检测**：
```bash
python3 -c "
import json
d=json.load(open('data/curated_{slot}_{date}.json'))
for s in ['tech','economy','gaming','foreign_china','top_headlines']:
    for i,item in enumerate(d.get(s,[])):
        sc = item.get('summary_cn','')
        if sc == '[扩写失败]':
            print(f'{s}#{i}: [扩写失败] — {item[\"title\"][:50]}')
        elif sc and item.get('title') and sc[:15] not in item['title'] and sc[:15] not in (item.get('summary','') or '')[:15]:
            print(f'{s}#{i}: ⚠️ 内容可能串位 — {item[\"title\"][:40]}')
            print(f'      summary_cn={sc[:60]}')
"
```

**修复**：
```bash
# 1. 清除失败 marker 和串位内容（注意：可能涉及多个条目）
python3 -c "
import json
d=json.load(open('data/curated_{slot}_{date}.json'))
for s in d:
    if isinstance(d[s], list):
        for item in d[s]:
            if item.get('summary_cn') == '[扩写失败]':
                del item['summary_cn']
            if 'title_cn' in item and item['title_cn'] == '[扩写失败]':
                del item['title_cn']
            # 也清除串位的正确内容（手动判断）
json.dump(d, open('data/curated_{slot}_{date}.json','w'), ensure_ascii=False, indent=2)
"

# 2. 重新翻译+扩写
python3 scripts/ai_translate.py --push-id {slot}

# 3. 重新渲染
python3 scripts/render_markdown.py --push-id {slot}

# 4. 补推
python3 scripts/archive_resend.py --date YYYY-MM-DD --slot {slot} --yes
```

**预防**：单条扩写不受影响。多条批次时风险存在。当前 `TRANSLATE_BATCH_SIZE=10`，若频繁出现可考虑降低。

## 7. RSS URL 路径含未编码空格（Sixth Tone 案例）

**2026-05-31 案例**：Sixth Tone RSS 的 `<link>` 元素返回如 `//www.sixthtone.com/news/1018594/He Quit Baidu...`，路径含空格。Markdown 链接 `[【Sixth Tone】](url)` 断裂（空格后的内容被当作独立 token）。

**检测**：渲染后的简报中某条链接不可点击，或 Markdown 源码中 URL 含空格。

**修复**（已内置在代码中，无需手动操作）：
- **`fetch_feeds.py` `_parse_rss()`** — RSS 解析时检测 URL 路径含空格，用 `urllib.parse.quote` 编码为 `%20`
- **`render_markdown.py` `_format_item()`** — 渲染层兜底，读取 item URL 时再次清洗

**影响源**：所有使用 `urllib.parse.quote` 编码路径中空格。Sixth Tone 的 RSS 路径用标题做 slug，空格最多。Google News RSS、部分独立博客也可能出现。

```bash
python3 -c "
import json
d=json.load(open('data/raw_{date}.json'))
for i in d['items']:
    if ' ' in i.get('url',''):
        print(f'[空格] {i[\"source_platform\"]}: {i[\"url\"][:80]}')
"
```

```bash
grep -n "修改内容" path/to/file                     # 1. 确认保存
python3 -c "import py_compile; py_compile.compile('file.py', doraise=True)"  # 2. 语法
/usr/local/bin/python3.14t scripts/render_markdown.py --push-id evening 2>/dev/null | head -20  # 3. 渲染
```
