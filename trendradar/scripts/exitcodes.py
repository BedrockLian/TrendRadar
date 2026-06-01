"""TrendRadar 脚本退出码协议 — Agent 根据退出码决策后续行为"""
EXIT_SUCCESS = 0        # 成功，有产出
EXIT_NO_CONTENT = 2     # 成功，无新内容（正常，不告警）
EXIT_PARTIAL = 3        # 部分成功（部分 domain 或源失败，推送降级内容）
EXIT_CONFIG_ERROR = 10  # 配置错误（需人工介入）
EXIT_API_ERROR = 11     # API 不可达（自动重试）
EXIT_DB_ERROR = 12      # 数据库损坏（触发自愈）
EXIT_FATAL = 99         # 致命错误（停止管线）
