# pytest 测试夹具模式

最后更新: 2026-05-30

## tmp_db 夹具：DB 与 monkeypatch 路径对齐

**陷阱**：`tmp_db` 创建 DB 在随机路径（如 `/tmp/tmpXXXX`），但测试 monkeypatch
`_store.base_dir` 指向另一个临时目录 → `_store.db('fingerprints.db')` 连接到空文件。

**正确模式** (2026-05-30 修复):

```python
@pytest.fixture
def tmp_db():
    """创建临时目录，内含 fingerprints.db（含完整表结构），返回 (conn, tmp_dir)。"""
    import shutil
    tmp_dir = Path(tempfile.mkdtemp())
    db_path = tmp_dir / 'fingerprints.db'
    conn = sqlite3.connect(str(db_path))
    conn.execute('''CREATE TABLE IF NOT EXISTS fingerprints (...))''')
    conn.commit()
    yield conn, tmp_dir
    conn.close()
    shutil.rmtree(tmp_dir, ignore_errors=True)
```

测试中使用：
```python
def test_insert(self, tmp_db, monkeypatch):
    conn, tmp_dir = tmp_db
    # 把 curated 文件也写进 tmp_dir
    (tmp_dir / f'curated_evening_{TEST_DATE}.json').write_text(json.dumps(data))
    # DATA_DIR 和 _store.base_dir 都指向 tmp_dir
    monkeypatch.setattr(rf, 'DATA_DIR', tmp_dir)
    monkeypatch.setattr(rf._store, 'base_dir', tmp_dir)
    record_fp('evening')
```

## pytest-asyncio 安装

Python 3.14t free-threaded 环境：
```bash
python3.14t -m pip install --break-system-packages -i https://pypi.org/simple/ pytest-asyncio
```

aliyun 镜像缺此包，需走 PyPI 直连。

## 当前测试状态

```
cd trendradar && python3 -m pytest tests/ -q
177 passed in 0.47s
```
