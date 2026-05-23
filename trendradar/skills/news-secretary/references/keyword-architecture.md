# 关键词架构（v4.7）— 505 词，6 域

双位置维护：`curate_and_push.py::_kw()`（全集） / `fetch_feeds.py::_kw_sets()`（~150 词子集，仅 game/tech/economy）

| domain | 词数 | 语言 |
|--------|------|------|
| game | 131 | 中/英/日 |
| tech | 87 | 中/英 |
| economy | 94 | 中/英 |
| politics | 124 | 中/英 |
| safety | 31 | 中文 |
| junk | 38 | 中文 |

## game（131 词）

中：游戏, 独立游戏, 原神, 黑神话, 塞尔达, 艾尔登法环, 博德之门, 魔兽, 暴雪, 使命召唤, 我的世界, 评测, 游戏版号, 米哈游, 崩坏, 星穹铁道, 绝区零, 机核, 触乐, 主机, 手游, 掌机, 索尼, 任天堂

英：Game/GTA/Steam/Epic/Switch/Xbox/PlayStation/PS5/Nintendo/MOD/DLC/FPS/RPG/3A/Genshin/Elden Ring/Dark Souls/Baldur's Gate/HoYoverse/Honkai/Star Rail/Zenless/ZZZ/GameLook/Famitsu/Steam Deck/Game Pass/Monster Hunter/Final Fantasy/esports/tournament/MMO/MOBA/roguelike/soulslike/JRPG/Unreal Engine/Unity/remaster/remake/Early Access/beta/Twitch/Gamescom

日：ゲーム, ファミ通, 4Gamer, 発売, 配信, リリース, レビュー, 体験版, アップデート, ゲーム機, スクエニ, カプコン, バンナム, セガ, コナミ, フロム, アトラス, モンハン, ドラクエ, ファイナルファンタジー

## tech（87 词）

中：AI, 大模型, 芯片, 半导体, 英伟达, GPU, CPU, 手机, 操作系统, 苹果, 华为, 特斯拉, 自动驾驶, 机器人, 电动汽车, 云计算, 5G, 开源, 编程
英：ChatGPT, LLM, AMD, Meta, Google, Nvidia, Intel, Apple, Samsung, Microsoft, Tesla, semiconductor, chip, foundry, SpaceX, NASA, cryptocurrency, blockchain, Bitcoin, cybersecurity, ransomware, startup, SaaS, cloud, API, open source, Kubernetes, Docker, GitHub

## economy（94 词）

中：就业, 消费, 工资, 物价, CPI, 房价, 裁员, 社保, GDP, 财政, 税收, 养老金, 贸易, 进出口, 贷款, 融资, 农业, 物流, 制造
英：employment, unemployment, layoff, inflation, interest rate, Federal Reserve, housing market, trade war, tariff, supply chain, recession, GDP growth, commodity, energy crisis, manufacturing, poverty

## politics（124 词）/ safety（31 词）

politics 英：Trump, Biden, Putin, Xi Jinping, Zelensky, Ukraine, Russia, Taiwan, Israel, Gaza, North Korea, Iran, NATO, EU, election, sanctions, war, missile, military, Pentagon, UN, G7, G20, BRICS
politics 中：访华, 会见, 外交, 中美, 中俄, 北约, 联合国, 制裁, 习近平, 总理, 欧盟, 美国, 日本, 韩国, 印度, 乌克兰, 俄罗斯, 选举, 战争, 冲突, 军演, 航天
safety：纯中文 31 词（灾害/安全类）

## 扩充原则

1. 检查 raw 中 `other` 域比例，确定漏分类领域
2. 避免通用词（不加 `studio`/`発表`/`sales` 等跨行业词）
3. 双语配对，日厂用简称
4. 改 `_kw()` 时同步 `_kw_sets()`
5. politics 不进 `_kw_sets()`，由 `curate_all()` 处理
