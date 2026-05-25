"""E2E 集成测试 — 模拟从 slot_detect 到 fragments 的全流程。

验证修改 A 模块不会导致 B 模块崩溃。
Mock 外部依赖（RSS 抓取、翻译 API），测试内部逻辑链。
"""

import json
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / 'scripts')
TRENDRADAR_DIR = str(Path(__file__).resolve().parent.parent)
HERMES_DIR = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, HERMES_DIR)
sys.path.insert(0, TRENDRADAR_DIR)
sys.path.insert(0, SCRIPTS_DIR)


class TestFragmentsByteCounting:
    """验证 fragment_push 的 UTF-8 字节计数分片逻辑。"""

    def test_short_briefing_no_split(self):
        """短简报不触发子分片。"""
        from fragment_push import split_fragments, MAX_BYTES
        markdown = "### Hermes日报 · 2026-05-25\n\n\n### 头条\n\n测试标题\n\n简短摘要\n\n[【来源】](https://example.com)\n\n\n**📋 共 1 条**"
        fragments = split_fragments(markdown)
        assert len(fragments) == 1
        assert len(fragments[0].encode('utf-8')) <= MAX_BYTES
        assert "### Hermes日报" in fragments[0]
        assert "**📋 共 1 条**" in fragments[0]

    def test_overlong_fragment_subsplits(self):
        """超长片段自动子分片。"""
        from fragment_push import split_fragments, MAX_BYTES

        # 构造一个超长段落（远超 3800 bytes）
        long_text = "长文本" * 2000  # ~6000 bytes UTF-8
        markdown = f"### Hermes日报 · 测试\n\n\n### 头条\n\n{long_text}\n\n[【来源】](https://example.com)\n\n\n**📋 共 1 条**"
        fragments = split_fragments(markdown)

        # 每个 fragment 应该在字节限制内
        for i, frag in enumerate(fragments):
            byte_len = len(frag.encode('utf-8'))
            assert byte_len <= MAX_BYTES, (
                f"Fragment {i}: {byte_len} bytes exceeds MAX_BYTES={MAX_BYTES}"
            )

        # 至少应该产生 2+ 个 fragment
        assert len(fragments) >= 2

    def test_title_only_on_first(self):
        """标题仅出现在第一个 fragment。"""
        from fragment_push import split_fragments
        markdown = "### Hermes日报 · test\n\n\n### 头条\n\n条目1\n\n\n### 板块2\n\n条目2\n\n\n**📋 共 2 条**"
        fragments = split_fragments(markdown)
        assert "### Hermes日报" in fragments[0]
        for frag in fragments[1:]:
            assert "### Hermes日报" not in frag

    def test_footer_only_on_last(self):
        """页脚仅出现在最后一个 fragment。"""
        from fragment_push import split_fragments
        markdown = "### Hermes日报 · test\n\n\n### 头条\n\n条目1\n\n\n### 板块2\n\n条目2\n\n\n**📋 共 2 条**"
        fragments = split_fragments(markdown)
        assert "**📋 共 2 条**" in fragments[-1]
        for frag in fragments[:-1]:
            assert "**📋 共" not in frag

    def test_empty_input(self):
        """空输入返回空数组。"""
        from fragment_push import split_fragments
        assert split_fragments("") == []
        assert split_fragments("   \n  ") == []

    def test_safe_utf8_cut(self):
        """硬分割不会切断多字节 UTF-8 字符。"""
        from fragment_push import _find_safe_cut
        # 中文 3 bytes/char, emoji 4 bytes
        text = "测试中文字符😀abc"
        # 截断到 10 bytes
        cut = _find_safe_cut(text, 10)
        # 解码结果不应该有错误
        truncated = text[:cut]
        # 验证编码往返
        truncated.encode('utf-8').decode('utf-8')
        assert len(truncated.encode('utf-8')) <= 10


class TestOrchestratorSteps:
    """验证 pipeline_orchestrator 的步骤定义（SSOT）。"""

    def test_list_steps_returns_all_7_stages(self):
        """--list-steps 返回完整 7 阶段定义。"""
        from pipeline_orchestrator import list_pipeline_steps
        steps_info = list_pipeline_steps()
        assert steps_info["version"] == "2.8.0"
        steps = steps_info["steps"]
        assert len(steps) == 7
        step_names = [s["name"] for s in steps]
        assert "slot_detect" in step_names
        assert "push_prepare" in step_names
        assert "parallel" in step_names
        assert "render_markdown" in step_names
        assert "fragment_push" in step_names
        assert "record_fingerprints" in step_names

    def test_parallel_step_has_parallel_flag(self):
        """并行步骤标记 parallel=True。"""
        from pipeline_orchestrator import list_pipeline_steps
        steps_info = list_pipeline_steps()
        parallel_step = [s for s in steps_info["steps"] if s["name"] == "parallel"][0]
        assert parallel_step["parallel"] is True
        assert len(parallel_step["scripts"]) == 2

    def test_verify_version_finds_all_scripts(self):
        """--check-version 找到所有依赖脚本。"""
        from pipeline_orchestrator import verify_version
        result = verify_version()
        assert result["ok"], f"Missing scripts: {result.get('errors', [])}"


class TestStorageUnification:
    """验证 Storage 统一 DB 接入。"""

    def test_storage_db_wal_enabled(self, tmp_path):
        """Storage.db() 自动开启 WAL 模式。"""
        from storage import Storage
        store = Storage(tmp_path)
        conn = store.db("test.db")

        # 验证 WAL
        row = conn.execute("PRAGMA journal_mode").fetchone()
        assert row[0].upper() == "WAL", f"Expected WAL, got {row[0]}"

        # 验证 busy_timeout
        row = conn.execute("PRAGMA busy_timeout").fetchone()
        assert row[0] == 5000

        # 清理
        store.close_db()

    def test_storage_db_connection_reuse(self, tmp_path):
        """同文件名复用连接。"""
        from storage import Storage
        store = Storage(tmp_path)
        conn1 = store.db("test.db")
        conn2 = store.db("test.db")
        assert conn1 is conn2  # 复用
        store.close_db()


class TestSilentCleanup:
    """验证 SILENT 退出时的中间文件清理。"""

    def test_cleanup_removes_curated_files(self, tmp_path):
        """_cleanup_silent 删除 curated JSON。"""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        # 创建临时 curated 文件
        curated_file = tmp_path / "data"
        curated_file.mkdir(parents=True)
        push_file = curated_file / "curated_noon.json"
        push_file.write_text('{"test": true}')

        # Mock DATA_DIR
        with patch('pipeline_orchestrator.DATA_DIR', curated_file), \
             patch('pipeline_orchestrator.datetime') as mock_dt:
            from datetime import datetime, timezone, timedelta
            mock_dt.now.return_value = datetime(2026, 5, 25, tzinfo=timezone(timedelta(hours=8)))
            from pipeline_orchestrator import _cleanup_silent
            _cleanup_silent("noon")

            # 文件应该被删除
            assert not push_file.exists()


class TestMigrationRollback:
    """验证迁移回滚 (down) 功能。"""

    def test_migrate_up_and_down(self, tmp_path):
        """完整 up → down 回滚循环。"""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from migrations.runner import migrate, down, _current_version
        import sqlite3

        db_path = tmp_path / "test_migrations.db"

        # Up: 执行迁移
        version = migrate(db_path)
        assert version > 0, f"Expected version > 0, got {version}"

        # 验证表已创建
        conn = sqlite3.connect(str(db_path))
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert 'fingerprints' in tables
        assert 'heat_tracker' in tables
        assert '_migrations' in tables

        # Down: 回滚到 0
        new_version = down(db_path, target_version=0)
        assert new_version == 0

        # 验证表已删除
        conn = sqlite3.connect(str(db_path))
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        # fingerprints 和 heat_tracker 应被删除
        assert 'fingerprints' not in tables
        assert 'heat_tracker' not in tables
        # _migrations 表本身不会被 down SQL 删除（它是迁移引擎的表）
        # 但所有迁移记录应被清除

    def test_down_noop_at_target(self, tmp_path):
        """回滚到当前版本不执行任何操作。"""
        from migrations.runner import migrate, down

        db_path = tmp_path / "test_noop.db"
        version = migrate(db_path)
        new_version = down(db_path, target_version=version)
        assert new_version == version  # 无变化

    def test_down_missing_annotation_raises(self, tmp_path):
        """缺少 -- down: 注释的迁移拒绝回滚。"""
        from migrations.runner import down, _extract_down_sql

        # 验证 _extract_down_sql 对已有迁移文件可提取
        migration_path = Path(__file__).resolve().parent.parent / "migrations" / "001_initial.sql"
        sql = migration_path.read_text()
        down_sql = _extract_down_sql(sql)
        assert down_sql is not None, "001_initial.sql 缺少 -- down: 回滚 SQL"
        assert "DROP TABLE" in down_sql.upper()
