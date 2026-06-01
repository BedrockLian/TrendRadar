#!/usr/bin/env python3
"""下载 Clash/Mihomo 订阅 → 匹配并更新现有配置中的代理（按 server:port 匹配，保留名称）

用法:
  python3 mihomo-update.py
  或直接运行 ~/.local/bin/mihomo-update

配置订阅 URL 在脚本顶部的 SUB_URL 变量中。运行前自动备份原配置到 config.yaml.bak，
验证通过后重启 mihomo。失败自动回滚。

工作方式:
  1. 下载 base64 编码的订阅（anytls://, trojan:// 等 URI）
  2. 解析新旧配置中每个代理的 server:port 作为匹配键
  3. 匹配到的更新密码/参数/SNI，保留原名称（保持 proxy-groups 引用有效）
  4. 未匹配的旧代理保留原样，新订阅中的新代理追加
  5. 处理同名冲突（追加 #N 后缀）
  6. 验证 + 重启 mihomo
"""

import base64, subprocess, sys, urllib.parse, urllib.request, os, time, re
from pathlib import Path

SUB_URL = os.environ.get('MIHOMO_SUB_URL', '')
CONFIG = Path.home() / '.config' / 'mihomo' / 'config.yaml'
BACKUP = CONFIG.with_suffix('.yaml.bak')


def download_sub(url):
    """下载并解码订阅，返回代理 URI 列表"""
    proxy = os.environ.get('HTTP_PROXY') or 'http://127.0.0.1:7890'
    handler = urllib.request.ProxyHandler({'http': proxy, 'https': proxy})
    opener = urllib.request.build_opener(handler)
    req = urllib.request.Request(url)
    with opener.open(req, timeout=30) as r:
        raw = r.read()
    try:
        text = base64.b64decode(raw).decode('utf-8')
    except Exception:
        text = raw.decode('utf-8')
    uris = [l.strip() for l in text.split('\n')
            if l.strip() and not l.startswith('#') and not l.startswith('STATUS') and '://' in l]
    return uris


def parse_proxy(uri):
    """解析 anytls:// 或 trojan:// URI 为代理字典，返回 (server:port) 作为匹配键"""
    parsed = urllib.parse.urlparse(uri)
    host = parsed.hostname
    port = parsed.port or 443
    qs = dict(urllib.parse.parse_qsl(parsed.query))
    frag = urllib.parse.unquote(parsed.fragment or '')
    pw_value = parsed.username or parsed.password or ''
    if uri.startswith('anytls://'):
        return {'type': 'anytls', 'server': host, 'port': port, 'password': pw_value,
                'sni': qs.get('sni', host), 'udp': True,
                'skip-cert-verify': qs.get('insecure', '0') == '1',
                'fingerprint': qs.get('fp', 'chrome'), 'name': frag,
                '_key': f'{host}:{port}'}
    elif uri.startswith('trojan://'):
        return {'type': 'trojan', 'server': host, 'port': port, 'password': pw_value,
                'sni': qs.get('sni', host), 'udp': True,
                'skip-cert-verify': qs.get('allowInsecure', '0') in ('1', 'true'),
                'name': frag, '_key': f'{host}:{port}'}
    return None


def proxy_to_yaml_lines(proxy):
    """代理字典 → YAML 行列表"""
    lines = ['  - name: "' + proxy['name'] + '"']
    lines.append('    type: ' + proxy['type'])
    lines.append('    server: ' + proxy['server'])
    lines.append('    port: ' + str(proxy['port']))
    if proxy.get('password'):
        lines.append('    password: ' + proxy['password'])
    if proxy.get('sni'):
        lines.append('    sni: ' + proxy['sni'])
    lines.append('    udp: true')
    if proxy.get('skip-cert-verify'):
        lines.append('    skip-cert-verify: true')
    if proxy.get('type') == 'anytls':
        lines.append('    fingerprint: ' + proxy.get('fingerprint', 'chrome'))
    return lines


def parse_old_proxies(lines, proxy_start, proxy_end):
    """解析旧配置中的代理条目列表"""
    old_entries = []
    current_name = None
    current_lines = []
    for i in range(proxy_start + 1, proxy_end):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith('- name:'):
            if current_lines:
                old_entries.append({'name': current_name, 'lines': current_lines})
            current_name = stripped.split('"')[1] if '"' in stripped else stripped.split(': ', 1)[1]
            current_lines = [line]
        elif current_lines:
            current_lines.append(line)
    if current_lines:
        old_entries.append({'name': current_name, 'lines': current_lines})
    return old_entries


def main():
    if not SUB_URL:
        print("⚠️  MIHOMO_SUB_URL 环境变量未设置，请设置后重试", flush=True)
        sys.exit(0)
    print("📥 下载新订阅...", flush=True)
    uris = download_sub(SUB_URL)
    print(f"   {len(uris)} 条代理", flush=True)

    new_proxies = {}
    for uri in uris:
        try:
            p = parse_proxy(uri)
            if p:
                new_proxies[p['_key']] = p
        except Exception:
            pass
    print(f"  有效: {len(new_proxies)} 个", flush=True)
    if len(new_proxies) < 3:
        print("❌ 有效代理太少", flush=True)
        sys.exit(1)

    # 读取当前配置
    orig = CONFIG.read_text(encoding='utf-8')
    lines = orig.split('\n')

    # 定位 proxies: 段边界
    proxy_start = proxy_end = None
    for i, line in enumerate(lines):
        if line.strip() == 'proxies:' and proxy_start is None:
            proxy_start = i
        elif proxy_start is not None and proxy_end is None:
            if line and not line[0].isspace() and line.strip() != '':
                proxy_end = i
                break

    if proxy_start is None or proxy_end is None:
        print("❌ 找不到 proxies 段边界", flush=True)
        sys.exit(1)

    old_entries = parse_old_proxies(lines, proxy_start, proxy_end)

    # 构建新 proxies 输出
    new_output = ['proxies:']
    used_names = {}
    used_keys = set()
    updated = kept = added = 0

    for entry in old_entries:
        name = entry['name']
        blk_text = '\n'.join(entry['lines'])
        sv = re.search(r'    server: (.+)', blk_text)
        pt = re.search(r'    port: (\d+)', blk_text)
        key = f'{sv.group(1)}:{pt.group(1)}' if sv and pt else None

        if key and key in new_proxies:
            np = new_proxies[key]
            np['name'] = name
            new_lines = proxy_to_yaml_lines(np)
            if name in used_names:
                new_lines[0] = '  - name: "' + name + ' #' + str(used_names[name]) + '"'
                used_names[name] += 1
            else:
                used_names[name] = 1
            new_output.extend(new_lines)
            used_keys.add(key)
            updated += 1
        else:
            if name in used_names:
                entry['lines'][0] = '  - name: "' + name + ' #' + str(used_names[name]) + '"'
                used_names[name] += 1
            else:
                used_names[name] = 1
            new_output.extend(entry['lines'])
            kept += 1

    for key, np in new_proxies.items():
        if key not in used_keys:
            new_lines = proxy_to_yaml_lines(np)
            if np['name'] in used_names:
                new_lines[0] = '  - name: "' + np['name'] + ' #' + str(used_names[np['name']]) + '"'
                used_names[np['name']] += 1
            else:
                used_names[np['name']] = 1
            new_output.extend(new_lines)
            added += 1

    new_content = '\n'.join(lines[:proxy_start] + new_output + lines[proxy_end:])

    BACKUP.write_text(orig, encoding='utf-8')
    CONFIG.write_text(new_content, encoding='utf-8')

    print("🔍 验证配置...", flush=True)
    r = subprocess.run(['mihomo', '-t', '-d', str(CONFIG.parent)],
                       capture_output=True, text=True, timeout=15)
    if r.returncode != 0:
        err = (r.stdout + r.stderr)[:500]
        print(f"❌ 验证失败: {err}", flush=True)
        CONFIG.write_text(orig, encoding='utf-8')
        print("↩️ 已回滚", flush=True)
        sys.exit(1)
    print("  ✅ 验证通过", flush=True)

    print("🔄 重启 mihomo...", flush=True)
    r = subprocess.run(['systemctl', '--user', 'restart', 'mihomo'],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        print(f"❌ 重启失败: {r.stderr}", flush=True)
        CONFIG.write_text(orig, encoding='utf-8')
        print("↩️ 已回滚", flush=True)
        sys.exit(1)

    time.sleep(3)
    r = subprocess.run(['systemctl', '--user', 'status', 'mihomo'],
                       capture_output=True, text=True, timeout=10)
    if 'active (running)' in r.stdout:
        print("  ✅ mihomo 运行中", flush=True)
    else:
        print(f"⚠️ 状态: {r.stdout[:200]}", flush=True)

    print(f"\n✅ 完成: {updated} 更新 + {kept} 保留 + {added} 新增 = {updated+kept+added} 代理", flush=True)


if __name__ == '__main__':
    main()
