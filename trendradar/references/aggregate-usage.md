# aggregate_monthly.py

```bash
python3 ~/.hermes/trendradar/scripts/aggregate_monthly.py
```

输出示例:
```json
{
  "month": "202605",
  "total_raw": 18000,
  "curated": {
    "top_headlines": 120, "foreign_china": 80,
    "tech": 200, "economy": 150, "gaming": 100,
    "total_curated": 650, "total_files": 90
  },
  "heat_top30": [...],
  "top_sources": [["中国新闻网", 85], ...]
}
```

可选参数 `--month YYYYMM`（默认上月）。
