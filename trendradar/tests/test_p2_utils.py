"""test_p2_utils.py — 补 0 覆盖核心脚本测试 (Sprint 2 P1-17)

覆盖:
- file_utils: get_data_dir / get_cache_dir / get_config_dir / atomic_write_json
- time_utils: CST / now_cst / parse_iso_cst
- lazy: Lazy 单例/线程安全/reset
- run_id: gen_run_id / parse_run_id / run_id_marker / contextvar
- exit_codes: 7 个常量值
"""
import os
import sys
import json
import tempfile
import threading
from pathlib import Path

import pytest

# 路径设置
TR = Path(r"C:\Users\ASUS\AppData\Local\hermes\trendradar")
sys.path.insert(0, str(TR))
os.environ.setdefault("TRENDRADAR_HOME", str(TR))


# ── time_utils ──────────────────────────────────────────
def test_cst_is_cst8():
    """CST 必须是 UTC+8。"""
    from trendradar.scripts.time_utils import CST
    assert CST.utcoffset(None).total_seconds() == 8 * 3600


def test_now_cst_is_aware():
    """now_cst() 必须返回 aware datetime (CST 时区)。"""
    from trendradar.scripts.time_utils import now_cst, CST
    n = now_cst()
    assert n.tzinfo is not None
    assert n.tzinfo == CST


def test_parse_iso_cst_with_offset():
    """parse_iso_cst 处理带时区字符串。"""
    from trendradar.scripts.time_utils import parse_iso_cst, CST
    dt = parse_iso_cst("2026-06-10T12:00:00+08:00")
    assert dt.tzinfo == CST
    assert dt.hour == 12


def test_parse_iso_cst_without_offset_treats_as_utc():
    """无时区字符串视为 UTC。"""
    from trendradar.scripts.time_utils import parse_iso_cst, CST
    dt = parse_iso_cst("2026-06-10T04:00:00")
    assert dt.tzinfo == CST
    # UTC 04:00 = CST 12:00
    assert dt.hour == 12


# ── lazy ───────────────────────────────────────────────
def test_lazy_caches_value():
    """Lazy.get() 多次调用只触发 factory 一次。"""
    from trendradar.scripts.lazy import Lazy
    calls = [0]
    def factory():
        calls[0] += 1
        return "expensive"
    l = Lazy(factory)
    assert l.get() == "expensive"
    assert l.get() == "expensive"
    assert l.get() == "expensive"
    assert calls[0] == 1, f"factory called {calls[0]} times, expected 1"


def test_lazy_thread_safe():
    """Lazy 在多线程下也只调用 factory 一次。"""
    from trendradar.scripts.lazy import Lazy
    calls = [0]
    lock = threading.Lock()
    def factory():
        with lock:
            calls[0] += 1
        return 42
    l = Lazy(factory)
    results = []
    def worker():
        results.append(l.get())
    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert all(r == 42 for r in results)
    assert calls[0] == 1, f"factory called {calls[0]} times under concurrency"


def test_lazy_reset_clears_cache():
    """reset() 后再次 get() 重新调用 factory。"""
    from trendradar.scripts.lazy import Lazy
    calls = [0]
    l = Lazy(lambda: calls.__setitem__(0, calls[0] + 1) or "v" + str(calls[0]))
    assert l.get() == "v1"
    l.reset()
    assert l.get() == "v2"


# ── run_id ─────────────────────────────────────────────
def test_gen_run_id_with_slot():
    """带 slot 的 run_id 格式: YYYYMMDD_slot_8hex。"""
    from trendradar.scripts.run_id import gen_run_id
    rid = gen_run_id("morning")
    parts = rid.split("_")
    assert len(parts) == 3
    assert parts[0].isdigit() and len(parts[0]) == 8
    assert parts[1] == "morning"
    assert len(parts[2]) == 8 and all(c in "0123456789abcdef" for c in parts[2])


def test_gen_run_id_without_slot():
    """无 slot: YYYYMMDD_8hex。"""
    from trendradar.scripts.run_id import gen_run_id
    rid = gen_run_id()
    parts = rid.split("_")
    assert len(parts) == 2
    assert parts[0].isdigit()


def test_parse_run_id_roundtrip():
    """parse_run_id 是 gen_run_id 的逆操作。"""
    from trendradar.scripts.run_id import gen_run_id, parse_run_id
    for slot in ("morning", "noon", "evening", ""):
        rid = gen_run_id(slot)
        parsed = parse_run_id(rid)
        assert parsed["date"] == rid.split("_")[0]
        if slot:
            assert parsed["slot"] == slot
        assert parsed["uid"] == rid.split("_")[-1]


def test_run_id_marker_contains_rid():
    """run_id_marker 包含 rid 字符串 (供 grep 追踪)。"""
    from trendradar.scripts.run_id import run_id_marker
    m = run_id_marker("20260610_morning_a1b2c3d4")
    assert "[rid:20260610_morning_a1b2c3d4]" in m


def test_run_id_contextvar():
    """set_run_id_ctx / get_run_id_ctx 双向工作。"""
    from trendradar.scripts.run_id import set_run_id_ctx, get_run_id_ctx, current_run_id
    token = current_run_id.set("test_rid_123")
    try:
        assert get_run_id_ctx() == "test_rid_123"
    finally:
        current_run_id.reset(token)
    assert get_run_id_ctx() == ""


# ── exit_codes ─────────────────────────────────────────
def test_exit_codes_values():
    """7 个退出码值固定, 防止误改。"""
    from trendradar.scripts.exit_codes import (
        EXIT_SUCCESS, EXIT_NO_CONTENT, EXIT_PARTIAL,
        EXIT_CONFIG_ERROR, EXIT_API_ERROR, EXIT_DB_ERROR, EXIT_FATAL,
    )
    assert EXIT_SUCCESS == 0
    assert EXIT_NO_CONTENT == 2
    assert EXIT_PARTIAL == 3
    assert EXIT_CONFIG_ERROR == 10
    assert EXIT_API_ERROR == 11
    assert EXIT_DB_ERROR == 12
    assert EXIT_FATAL == 99


# ── file_utils (Sprint 2 P1-15 改的 3 个 Lazy 函数) ────
def test_get_data_dir_cached():
    """get_data_dir() 多次调用返回同一对象 (Lazy 缓存生效)。"""
    from trendradar.scripts.file_utils import get_data_dir
    d1 = get_data_dir()
    d2 = get_data_dir()
    assert d1 is d2  # 必须是同一对象 (cache hit)


def test_get_cache_dir_cached():
    from trendradar.scripts.file_utils import get_cache_dir
    assert get_cache_dir() is get_cache_dir()


def test_get_config_dir_cached():
    from trendradar.scripts.file_utils import get_config_dir
    assert get_config_dir() is get_config_dir()


def test_atomic_write_json_creates_file():
    """atomic_write_json 创建新文件 + 内容正确。"""
    from trendradar.scripts.file_utils import atomic_write_json
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "test.json"
        atomic_write_json(p, {"hello": "world", "items": [1, 2, 3]})
        assert p.exists()
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data == {"hello": "world", "items": [1, 2, 3]}


def test_atomic_write_json_overwrites_atomically():
    """atomic_write_json 覆盖已有文件, 无 .tmp 残留。"""
    from trendradar.scripts.file_utils import atomic_write_json
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "test.json"
        atomic_write_json(p, {"v": 1})
        atomic_write_json(p, {"v": 2})
        # 读回来是最新
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data == {"v": 2}
        # 目录里没有 .tmp_ 残留
        tmp_files = list(Path(tmp).iterdir())
        assert all(not f.name.startswith(".tmp_") for f in tmp_files)


def test_atomic_write_json_handles_chinese():
    """atomic_write_json 中文不 escape (ensure_ascii=False)。"""
    from trendradar.scripts.file_utils import atomic_write_json
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "test.json"
        atomic_write_json(p, {"title": "测试中文"})
        content = p.read_text(encoding="utf-8")
        assert "测试中文" in content  # 不应是 \uXXXX


def test_atomic_write_json_does_not_create_parent_dirs():
    """atomic_write_json 行为: 不自动建父目录 (这是预期, 不是 bug)。

    Sprint 2 P1-17: 锁定现有行为, 防止将来悄悄改了。
    父目录创建是 caller 的责任 (P0-8 修复时 PUSH_LOG 写入前用 .parent.mkdir)。
    """
    from trendradar.scripts.file_utils import atomic_write_json
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "subdir" / "deeper" / "test.json"
        with pytest.raises(FileNotFoundError):
            atomic_write_json(p, {"ok": True})


# ── write_compressed / read_compressed (Sprint 1 P1-11 改的) ─
def test_write_read_compressed_roundtrip_json():
    """write_compressed 期望 path 是完整 (无后缀) 文件名, 写 .json + .zst。

    Sprint 1 P1-11 修复: 双写策略。
    write_compressed('test_data', data) → 写 test_data.json + test_data.json.zst
    read_compressed('test_data') → 读 .zst 优先, fallback .json
    """
    from trendradar.scripts.file_utils import write_compressed, read_compressed
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "test_data"
        data = {"items": [{"id": 1, "name": "test"}, {"id": 2, "name": "test2"}]}
        write_compressed(p, data)
        # .json 一定存在 (P1-11 双写)
        assert p.with_suffix(".json").exists()
        # 读回一致 (fallback .json)
        got = read_compressed(p)
        assert got == data


# ── common.py shim 兼容性 (P1-14 拆分后) ───────────────
def test_common_re_exports_all_symbols():
    """common.py 仍然 re-export 所有原符号 (向后兼容)。"""
    from trendradar.scripts import common
    expected = [
        "CST", "Lazy",
        "gen_run_id", "parse_run_id", "run_id_marker",
        "set_run_id_ctx", "get_run_id_ctx", "current_run_id",
        "EXIT_SUCCESS", "EXIT_NO_CONTENT", "EXIT_PARTIAL",
        "EXIT_CONFIG_ERROR", "EXIT_API_ERROR", "EXIT_DB_ERROR", "EXIT_FATAL",
        "STOP_WORDS", "list_curated_files", "find_curated_file",
        "get_data_dir_for_common", "_parse_line_pairs",
    ]
    for name in expected:
        assert hasattr(common, name), f"common.{name} missing"


def test_common_lazy_is_same_as_lazy_module():
    """common.Lazy 应该就是 trendradar.scripts.lazy.Lazy。"""
    from trendradar.scripts.common import Lazy as CommonLazy
    from trendradar.scripts.lazy import Lazy as DirectLazy
    assert CommonLazy is DirectLazy


def test_common_cst_is_same_as_time_utils_cst():
    from trendradar.scripts.common import CST as CommonCST
    from trendradar.scripts.time_utils import CST as DirectCST
    assert CommonCST is DirectCST


# ── curated_paths (P1-14 拆出) ─────────────────────────
def test_find_curated_file_three_levels(tmp_path):
    """find_curated_file 3 级 fallback (dated → latest dated → generic)。

    关键: 必须先重置 _data_dir_cache 再 monkeypatch, 因为 Lazy 缓存
    之前进程已 init 时 (TRENDRADAR_HOME=运行时) 缓存了。
    """
    from trendradar.scripts import curated_paths
    curated_paths._data_dir_cache = None
    # 现在 init 走 tmp_path
    (tmp_path / "data").mkdir()
    curated_paths._data_dir_cache = tmp_path / "data"

    from trendradar.scripts.curated_paths import find_curated_file

    # Level 3: generic
    generic = tmp_path / "data" / "curated_morning.json"
    generic.write_text("{}")
    assert find_curated_file("20260610", "morning") == generic

    # Level 2: latest dated
    dated = tmp_path / "data" / "curated_morning_20260609.json"
    dated.write_text("{}")
    assert find_curated_file("20260610", "morning") == dated

    # Level 1: exact date wins
    exact = tmp_path / "data" / "curated_morning_20260610.json"
    exact.write_text("{}")
    assert find_curated_file("20260610", "morning") == exact

    # 清理缓存供下一个 test
    curated_paths._data_dir_cache = None


def test_list_curated_files_respects_days(tmp_path):
    """list_curated_files 只返回 N 天内的文件。"""
    from trendradar.scripts import curated_paths
    curated_paths._data_dir_cache = None
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    curated_paths._data_dir_cache = data_dir

    (data_dir / "curated_old.json").write_text("{}")
    (data_dir / "curated_new.json").write_text("{}")
    # 把 old 的 mtime 改到 10 天前
    import time
    old_time = time.time() - 10 * 86400
    os.utime(data_dir / "curated_old.json", (old_time, old_time))

    from trendradar.scripts.curated_paths import list_curated_files
    files = list_curated_files(days=5)
    assert len(files) == 1
    assert "curated_new.json" in files[0]
    curated_paths._data_dir_cache = None
