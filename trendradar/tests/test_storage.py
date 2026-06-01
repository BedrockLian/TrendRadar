"""Tests for storage.py — Storage class (SQLite + file I/O)."""

import pytest
import sqlite3
import json
from unittest.mock import patch


# ── Tests ───────────────────────────────────────────────────────────────


class TestStorageInit:
    """Tests for Storage initialization."""

    @pytest.mark.smoke
    def test_init_creates_base_dir(self, tmp_path):
        """Storage() creates the base directory if it doesn't exist."""
        from trendradar.scripts.storage import Storage

        base = tmp_path / 'trendradar_data'
        assert not base.exists()

        store = Storage(base)
        assert base.exists()
        assert base.is_dir()

    def test_init_accepts_string_path(self, tmp_path):
        """Storage() accepts a string path."""
        from trendradar.scripts.storage import Storage

        base = tmp_path / 'string_data'
        store = Storage(str(base))
        assert store.base_dir == base
        assert base.exists()

    def test_init_sets_internal_state(self, tmp_path):
        """Storage() initializes empty connection dict and lock."""
        from trendradar.scripts.storage import Storage

        store = Storage(tmp_path / 'data')
        assert store._db_connections == {}
        assert store._db_lock is not None


class TestStorageDatabase:
    """Tests for database methods."""

    def test_db_creates_connection(self, tmp_path):
        """db() creates a new sqlite3.Connection with correct PRAGMAs."""
        from trendradar.scripts.storage import Storage

        store = Storage(tmp_path / 'db_test')
        conn = store.db('test.db')

        assert isinstance(conn, sqlite3.Connection)

        # Verify WAL mode is active
        cur = conn.execute("PRAGMA journal_mode")
        mode = cur.fetchone()[0]
        assert mode.upper() == 'WAL'

        # Verify busy_timeout
        cur = conn.execute("PRAGMA busy_timeout")
        timeout = cur.fetchone()[0]
        assert timeout >= 1000

    def test_db_reuses_connection(self, tmp_path):
        """db() reuses an existing connection for the same file."""
        from trendradar.scripts.storage import Storage

        store = Storage(tmp_path / 'reuse_test')
        conn1 = store.db('reuse.db')
        conn2 = store.db('reuse.db')

        assert conn1 is conn2

    def test_db_can_create_table_and_write(self, tmp_path):
        """db() connection supports table creation and data insertion."""
        from trendradar.scripts.storage import Storage

        store = Storage(tmp_path / 'write_test')
        conn = store.db('write_test.db')

        conn.execute('CREATE TABLE IF NOT EXISTS test_data (id INTEGER PRIMARY KEY, name TEXT)')
        conn.execute("INSERT INTO test_data (name) VALUES (?)", ("hello",))
        conn.commit()

        cur = conn.execute("SELECT name FROM test_data WHERE id = 1")
        assert cur.fetchone()[0] == "hello"

    def test_close_db_closes_single_connection(self, tmp_path):
        """close_db() closes a specific connection and removes from cache."""
        from trendradar.scripts.storage import Storage

        store = Storage(tmp_path / 'close_test')
        conn = store.db('close.db')
        db_path = str(store._r('close.db'))

        assert db_path in store._db_connections

        store.close_db('close.db')

        assert db_path not in store._db_connections
        # Connection should be closed
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_close_db_all_closes_everything(self, tmp_path):
        """close_db() with no args closes all connections."""
        from trendradar.scripts.storage import Storage

        store = Storage(tmp_path / 'close_all_test')
        store.db('a.db')
        store.db('b.db')
        store.db('c.db')

        assert len(store._db_connections) == 3

        store.close_db()

        assert len(store._db_connections) == 0


class TestStorageFileIO:
    """Tests for file I/O methods."""

    def test_read_write_json(self, tmp_path):
        """read_json() and write_json() round-trip data."""
        from trendradar.scripts.storage import Storage

        store = Storage(tmp_path / 'json_test')
        data = {'key': 'value', 'nested': {'a': 1, 'b': [2, 3]}}

        store.write_json('data.json', data)
        result = store.read_json('data.json')

        assert result == data

    def test_read_json_default_on_missing(self, tmp_path):
        """read_json() returns default when file doesn't exist."""
        from trendradar.scripts.storage import Storage

        store = Storage(tmp_path / 'missing_test')
        result = store.read_json('nonexistent.json', default={'fallback': True})

        assert result == {'fallback': True}

    def test_exists(self, tmp_path):
        """exists() correctly reports file presence."""
        from trendradar.scripts.storage import Storage

        store = Storage(tmp_path / 'exists_test')
        assert store.exists('foo.txt') is False

        store.write_text('foo.txt', 'hello')
        assert store.exists('foo.txt') is True

    def test_delete(self, tmp_path):
        """delete() removes a file and returns True/False."""
        from trendradar.scripts.storage import Storage

        store = Storage(tmp_path / 'delete_test')
        store.write_text('del.txt', 'delete me')
        assert store.exists('del.txt')

        removed = store.delete('del.txt')
        assert removed is True
        assert store.exists('del.txt') is False

        # Deleting non-existent returns False
        removed2 = store.delete('del.txt')
        assert removed2 is False
