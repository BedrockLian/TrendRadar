# Free-Threaded Python Build

> Debian sid, Python 3.14.4, GCC 15.2.0. 已验证: sqlite3/OpenSSL/pyahocorasick/pytest.

## 编译

```bash
sudo apt-get install -y libsqlite3-dev libssl-dev libbz2-dev liblzma-dev \
  libreadline-dev libncurses-dev libgdbm-dev libdb-dev libffi-dev uuid-dev
cd /tmp && curl -sL https://www.python.org/ftp/python/3.14.4/Python-3.14.4.tar.xz | tar xJ
cd Python-3.14.4
./configure --prefix=/opt/python3.14t --disable-gil --enable-optimizations
make -j$(nproc) && sudo make install
sudo ln -sf /opt/python3.14t/bin/python3.14t /usr/local/bin/python3.14t
```

PGO 超时则去掉 `--enable-optimizations`。

## 依赖

```bash
python3.14t -m pip install setuptools wheel
python3.14t -m pip install pyahocorasick --no-build-isolation
python3.14t -m pip install feedparser zstandard
```

`zstandard` 替代 stdlib 缺失的 `_zstd` C 扩展（`cpython-314t` ABI 不兼容 `cpython-314`）。settings.py 内置三级 fallback：`compression.zstd → zstandard → 普通 JSON`。

## 使用

```
export PYTHON=/usr/local/bin/python3.14t
export PYTHONPATH=/home/asus/.hermes   # 必须 — from trendradar.scripts.common 等导入
export PYTHON_GIL=0                     # 必须 — 否则 C 扩展自动恢复 GIL
$PYTHON scripts/push_prepare.py --push-id morning
```
