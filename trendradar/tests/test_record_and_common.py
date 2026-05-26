"""record_fingerprints + common 烟雾测试。

覆盖：
  - record(): 插入 DB、计数正确、幂等
  - gen_run_id() / parse_run_id() / run_id_marker()
"""
import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from common import gen_run_id, parse_run_id, run_id_marker
from record_fingerprints import record as record_fp

from settings import get_data_dir
DATA_DIR = get_data_dir()
CST = timezone(timedelta(hours=8))
TEST_DATE = datetime.now(CST).strftime('%Y%m%d')


# ── common.py ────────────────────────────────────────────────────────────────

class TestGenRunId:
    def test_with_slot(self):
        rid = gen_run_id('evening')
        # 格式: YYYYMMDD_evening_xxxxxxxx
        assert rid.startswith(TEST_DATE)
        assert '_evening_' in rid
        assert len(rid.split('_')[-1]) == 8  # 8-char UUID hex

    def test_without_slot(self):
        rid = gen_run_id()
        assert rid.startswith(TEST_DATE)
        assert '_' in rid
        assert len(rid.split('_')[-1]) == 8

    def test_uniqueness(self):
        rids = {gen_run_id() for _ in range(100)}
        assert len(rids) == 100  # 全唯一


class TestParseRunId:
    def test_full_format(self):
        result = parse_run_id('20260521_evening_abc12345')
        assert result['date'] == '20260521'
        assert result['slot'] == 'evening'
        assert result['uid'] == 'abc12345'

    def test_no_slot(self):
        result = parse_run_id('20260521_abc12345')
        assert result['date'] == '20260521'
        assert result['slot'] == ''
        assert result['uid'] == 'abc12345'

    def test_short_string(self):
        result = parse_run_id('20260521')
        assert result['date'] == '20260521'
        assert result['slot'] == ''
        assert result['uid'] == ''


class TestRunIdMarker:
    def test_normal(self):
        marker = run_id_marker('20260521_evening_test9999')
        assert 'rid:20260521_evening_test9999' in marker

    def test_empty_run_id(self):
        marker = run_id_marker('')
        assert 'rid:' in marker


# ── record_fingerprints ──────────────────────────────────────────────────────

def _mock_store(monkeypatch, rf, conn):
    """替换 rf._store，使其 .db() 返回测试连接。"""
    mock_store = MagicMock()
    mock_store.db.return_value = conn
    monkeypatch.setattr(rf, '_store', mock_store)


class TestRecordFingerprints:
    def test_insert_includes_run_id(self, tmp_db, sample_curated, monkeypatch):
        """新记录应包含 run_id 字段"""
        conn, db_path = tmp_db
        tmp_data = Path(tempfile.mkdtemp())

        # 注入 run_id 到 curated
        curated_with_rid = {**sample_curated, 'run_id': '20260521_evening_test1234'}
        curated_file = tmp_data / f'curated_evening_{TEST_DATE}.json'
        curated_file.write_text(json.dumps(curated_with_rid, ensure_ascii=False))

        import record_fingerprints as rf
        monkeypatch.setattr(rf, 'DATA_DIR', tmp_data)
        _mock_store(monkeypatch, rf, conn)

        record_fp('evening')
        rows = conn.execute("SELECT run_id FROM fingerprints LIMIT 1").fetchall()
        assert rows[0][0] == '20260521_evening_test1234'

    def test_insert_new_items(self, tmp_db, sample_curated, monkeypatch):
        """插入新条目，计数增加"""
        conn, db_path = tmp_db

        # 把 curated 写入临时文件并用 monkeypatch 劫持 DATA_DIR
        tmp_data = Path(tempfile.mkdtemp())
        curated_file = tmp_data / f'curated_evening_{TEST_DATE}.json'
        curated_file.write_text(json.dumps(sample_curated, ensure_ascii=False))

        import record_fingerprints as rf
        monkeypatch.setattr(rf, 'DATA_DIR', tmp_data)
        _mock_store(monkeypatch, rf, conn)

        before = conn.execute("SELECT COUNT(*) FROM fingerprints").fetchone()[0]
        record_fp('evening')
        after = conn.execute("SELECT COUNT(*) FROM fingerprints").fetchone()[0]

        assert after > before
        assert after == before + sum(len(v) for v in sample_curated.values())

    def test_idempotent(self, tmp_db, sample_curated, monkeypatch):
        """INSERT OR IGNORE：重复插入应不改变计数"""
        conn, db_path = tmp_db

        tmp_data = Path(tempfile.mkdtemp())
        curated_file = tmp_data / f'curated_evening_{TEST_DATE}.json'
        curated_file.write_text(json.dumps(sample_curated, ensure_ascii=False))

        import record_fingerprints as rf
        monkeypatch.setattr(rf, 'DATA_DIR', tmp_data)
        _mock_store(monkeypatch, rf, conn)

        record_fp('evening')
        count1 = conn.execute("SELECT COUNT(*) FROM fingerprints").fetchone()[0]
        record_fp('evening')
        count2 = conn.execute("SELECT COUNT(*) FROM fingerprints").fetchone()[0]

        assert count1 == count2

    def test_missing_curated_file(self, monkeypatch, tmp_db):
        """curated 文件不存在时，record 应优雅返回不崩溃"""
        conn, db_path = tmp_db
        tmp_data = Path(tempfile.mkdtemp())  # 空目录，无 curated 文件

        import record_fingerprints as rf
        monkeypatch.setattr(rf, 'DATA_DIR', tmp_data)
        _mock_store(monkeypatch, rf, conn)

        # 不应抛出异常
        record_fp('morning')
        count = conn.execute("SELECT COUNT(*) FROM fingerprints").fetchone()[0]
        assert count == 0

    def test_empty_title_skipped(self, tmp_db, monkeypatch):
        """title 为空的条目跳过"""
        conn, db_path = tmp_db
        tmp_data = Path(tempfile.mkdtemp())

        curated = {
            'tech': [
                {'title': '', 'summary': 'no title', 'source_platform': 'X',
                 'url': 'https://x.com/1'},
                {'title': 'Valid Title', 'summary': 'valid', 'source_platform': 'Y',
                 'url': 'https://y.com/1'},
            ],
        }
        (tmp_data / f'curated_evening_{TEST_DATE}.json').write_text(
            json.dumps(curated, ensure_ascii=False))

        import record_fingerprints as rf
        monkeypatch.setattr(rf, 'DATA_DIR', tmp_data)
        _mock_store(monkeypatch, rf, conn)

        record_fp('evening')
        count = conn.execute("SELECT COUNT(*) FROM fingerprints").fetchone()[0]
        assert count == 1  # 只有 Valid Title
