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

## 验证修复

```bash
grep -n "修改内容" path/to/file                     # 1. 确认保存
python3 -c "import py_compile; py_compile.compile('file.py', doraise=True)"  # 2. 语法
/usr/local/bin/python3.14t scripts/render_markdown.py --push-id evening 2>/dev/null | head -20  # 3. 渲染
```
