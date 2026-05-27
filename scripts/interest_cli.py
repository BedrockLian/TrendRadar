#!/usr/bin/env python3
"""兴趣配置管理 CLI — ai_interests.yaml 的增删查改。"""
import sys, os
from pathlib import Path

TR = Path(os.environ.get('TRENDRADAR_HOME', Path.home() / '.hermes' / 'trendradar'))
CONFIG = TR / 'config' / 'ai_interests.yaml'


def load():
    import yaml
    if CONFIG.exists():
        return yaml.safe_load(CONFIG.read_text(encoding='utf-8')) or {'positive': [], 'negative': []}
    return {'positive': [], 'negative': []}


def save(data):
    import yaml
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding='utf-8'
    )
    print(f'[OK] 已写入 {CONFIG}')


def cmd_list(args):
    data = load()
    print(f'正面兴趣 ({len(data["positive"])} 条):')
    for i, item in enumerate(data['positive'], 1):
        print(f'  {i}. {item}')
    print()
    print(f'排除项 ({len(data["negative"])} 条):')
    for i, item in enumerate(data['negative'], 1):
        print(f'  {i}. {item}')


def cmd_add(args):
    if not args:
        print('用法: interest add "关注方向"', file=sys.stderr)
        sys.exit(1)
    data = load()
    text = ' '.join(args)
    if text in data['positive'] or text in data['negative']:
        print(f'[WARN] 已存在: {text}', file=sys.stderr)
        return
    data['positive'].append(text)
    save(data)
    print(f'[OK] 已添加正面兴趣: {text}')


def cmd_remove(args):
    if not args:
        print('用法: interest remove "关键词/编号"', file=sys.stderr)
        sys.exit(1)
    data = load()
    query = ' '.join(args)
    removed = False
    for key in ('positive', 'negative'):
        # Try numeric index
        try:
            idx = int(query) - 1
            if 0 <= idx < len(data[key]):
                item = data[key].pop(idx)
                print(f'[OK] 已从 {key} 删除: {item}')
                removed = True
        except ValueError:
            pass
        # Try text match
        for item in data[key][:]:
            if query in item:
                data[key].remove(item)
                print(f'[OK] 已从 {key} 删除: {item}')
                removed = True
    if not removed:
        print(f'[WARN] 未找到: {query}', file=sys.stderr)
    if removed:
        save(data)


def cmd_exclude(args):
    if not args:
        print('用法: interest exclude "不想看的内容"', file=sys.stderr)
        sys.exit(1)
    data = load()
    text = ' '.join(args)
    if text in data['negative'] or text in data['positive']:
        print(f'[WARN] 已存在: {text}', file=sys.stderr)
        return
    data['negative'].append(text)
    save(data)
    print(f'[OK] 已添加排除项: {text}')


if __name__ == '__main__':
    cmds = {
        'list': cmd_list, 'ls': cmd_list,
        'add': cmd_add,
        'remove': cmd_remove, 'rm': cmd_remove, 'delete': cmd_remove,
        'exclude': cmd_exclude, 'block': cmd_exclude,
    }
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(f'用法: interest <命令> [参数...]')
        print(f'命令: list, add <文本>, remove <文本/编号>, exclude <文本>')
        sys.exit(1)
    cmds[sys.argv[1]](sys.argv[2:])
