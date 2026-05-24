# 月度数据查询

## 周报采集
```bash
python3 /home/asus/.hermes/trendradar/scripts/collect_weekly_reports.py --weeks 4
```
输出 JSON: `weekly_reports[]` + `month_stats`

## 热度排名
```sql
SELECT platform_count, heat_score, keyword FROM heat_tracker ORDER BY heat_score DESC LIMIT 30;
SELECT date(created_at) day, COUNT(*) n FROM heat_tracker WHERE created_at >= date('now','-1 month') GROUP BY day ORDER BY day;
```

## 精选统计
```bash
ls /home/asus/.hermes/trendradar/data/curated_*_202605*.json | wc -l
for f in /home/asus/.hermes/trendradar/data/curated_*_202605*.json; do
  python3 -c "import json;d=json.load(open('$f'));print('$f',d.get('total',0))"
done
```

## 板块分布
```bash
python3 -c "
import json,glob
domains=['top_headlines','foreign_china','tech','economy','gaming']
counts={d:0 for d in domains}
for f in sorted(glob.glob('/home/asus/.hermes/trendradar/data/curated_*_202605*.json')):
    d=json.load(open(f))
    for domain in domains: counts[domain]+=len(d.get(domain,[]))
print('分布:',counts,'总计:',sum(counts.values()))
"
```

## 研究方法
`deep-research-cli` 六步：问题分解→广度搜索→深度阅读→缺口分析→综合报告→质量检查
