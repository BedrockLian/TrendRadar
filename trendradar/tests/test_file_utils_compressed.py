"""test_file_utils_compressed.py — 验证 zstd 双写修复 (P1-11)"""
import json, sys
from pathlib import Path
from trendradar.scripts.file_utils import write_compressed, read_compressed

# 测试数据
test_data = {
    'items': [{'title': f'新闻{i}', 'url': f'http://x.com/{i}', 'summary': 'x'*100} for i in range(100)],
    'meta': 'test_compressed_v2',
}

# 写到临时文件
test_path = Path('cache/test_compressed')
test_path.parent.mkdir(exist_ok=True)
write_compressed(test_path, test_data)

# 验证两个文件都存在
json_p = test_path.with_suffix('.json')
zst_p = test_path.with_suffix('.json.zst')
print(f'JSON exists: {json_p.exists()} ({json_p.stat().st_size}B)')
print(f'ZST exists:  {zst_p.exists()} ({zst_p.stat().st_size}B)')

# 读回来
got = read_compressed(test_path)
assert got == test_data, f'mismatch: got keys={list(got.keys())}'
print(f'✅ roundtrip ok: {len(got["items"])} items')

# 压缩比
orig = json_p.stat().st_size
zst = zst_p.stat().st_size
print(f'压缩比: {zst/orig*100:.1f}% (省 {(1-zst/orig)*100:.1f}%)')

# 清理
test_path.unlink(missing_ok=True)
json_p.unlink(missing_ok=True)
zst_p.unlink(missing_ok=True)
print('✅ cleanup done')
