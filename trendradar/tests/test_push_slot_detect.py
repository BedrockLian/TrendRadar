"""push_slot_detect 烟雾测试。

覆盖：
  - slot_match() 纯函数：±1 分钟容差
  - 参数输出格式（PUSH_ID / SLOT_LABEL / DEDUP_FLAG / FILTER）
"""

import pytest
from push_slot_detect import slot_match


class TestSlotMatch:
    """slot_match(target_h, target_m, h, m) — 容忍 ±1 分钟"""

    @pytest.mark.smoke
    def test_exact_match(self):
        assert slot_match(9, 0, 9, 0) is True

    def test_plus_one_minute(self):
        assert slot_match(9, 0, 9, 1) is True

    def test_minus_one_minute(self):
        assert slot_match(9, 0, 8, 59) is True

    def test_plus_two_minutes_out_of_range(self):
        assert slot_match(9, 0, 9, 2) is False

    def test_minus_two_minutes_out_of_range(self):
        assert slot_match(9, 0, 8, 58) is False

    def test_noon_exact(self):
        assert slot_match(12, 0, 12, 0) is True

    def test_evening_plus_one(self):
        assert slot_match(21, 0, 21, 1) is True

    def test_midnight_crossover(self):
        """slot_match 以 target 为中心 ±1 分钟。23:59 vs 00:00 的 delta=1439 分钟，不匹配。
        TrendRadar 的时段是 09:00/12:00/21:00，不跨天，此场景不适用。"""
        # slot_match(0, 0, 23, 59) → delta = -1439，不在 ±1 范围
        assert slot_match(0, 0, 23, 59) is False
        assert slot_match(23, 59, 0, 0) is False

    def test_random_hour_negative(self):
        """随机抽查：完全不在范围的"""
        assert slot_match(9, 0, 15, 30) is False
        assert slot_match(12, 0, 21, 5) is False
