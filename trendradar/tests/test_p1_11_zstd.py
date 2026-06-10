"""test_p1_11_zstd.py — 验证 zstd 双写修复"""
import sys
from pathlib import Path
HERE = Path(__file__).parent.parent  # trendradar/
sys.path.insert(0, str(HERE))

from trendradar.scripts.file_utils import write_compressed, read_compressed

# 测试数据
test_data = {
    'items': [{'title': f'news_{i}', 'summary': 'x'*100} for i in range(100)],
    'meta': 'v2_double_write',
}

# 写到 cache/ 临时
test_path = HERE / 'cache' / 'test_compressed_p1_11'
test_path.parent.mkdir(exist_ok=True)
write_compressed(test_path, test_data)

# 验证两个文件都存在
json_p = test_path.with_suffix('.json')
zst_p = test_path.with_suffix('.json.zst')
print(f'JSON exists: {json_p.exists()} ({json_p.stat().st_size}B)')
print(f'ZST exists:  {zst_p.exists()} ({zst_p.stat().st_size}B)')

# 读回来
got = read_compressed(test_path)
assert got == test_data, f'mismatch: keys {list(got.keys())}'
print(f'✅ roundtrip ok: {len(got["items"])} items')

# 压缩比
orig = json_p.stat().st_size
zst = zst_p.stat().st_size
ratio = zst / orig * 100
saved = (1 - zst/orig) * 100
print(f'✅ compression: {ratio:.1f}% (saved {saved:.1f}%)')

# 清理
json_p.unlink()
zst_p.unlink()
print('✅ cleanup done')
