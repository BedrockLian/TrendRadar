"""Apply a Codex-generated translation response to a curated JSON file.

The pipeline creates a source-backed queue when no external LLM provider is
available. Codex can translate those entries directly, save a response JSON,
and invoke this command to apply only URL-matched translations.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from trendradar.runtime.common import CST, find_curated_file
from trendradar.runtime.file_utils import atomic_write_json, get_data_dir
from trendradar.runtime.output_protocol import configure_utf8_stdio
from trendradar.config.domains import DOMAINS

_INVALID_MARKERS = ('[未翻译]', '[翻译失败]', '[扩写失败]')


def _response_items(response: object) -> list[dict]:
    if isinstance(response, dict):
        response = response.get('items', [])
    if not isinstance(response, list):
        raise ValueError('Codex response must be a JSON list or an object with an items list')
    items = []
    for index, entry in enumerate(response):
        if not isinstance(entry, dict) or not str(entry.get('url', '')).strip():
            raise ValueError(f'Codex response item {index} is missing url')
        items.append(entry)
    return items


def apply_response(curated_path: Path, response_path: Path) -> dict:
    """Apply validated URL-keyed translations and return an audit summary."""
    data = json.loads(curated_path.read_text(encoding='utf-8'))
    response = _response_items(json.loads(response_path.read_text(encoding='utf-8')))
    by_url = {}
    for domain in DOMAINS:
        for item in data.get(domain, []):
            url = str(item.get('url', '')).strip()
            if url:
                by_url[url] = item

    applied = 0
    unmatched = []
    for entry in response:
        url = str(entry['url']).strip()
        item = by_url.get(url)
        if item is None:
            unmatched.append(url)
            continue
        changed = False
        for field in ('title_cn', 'summary_cn'):
            value = str(entry.get(field, '') or '').strip()
            if value.startswith(_INVALID_MARKERS):
                raise ValueError(f'Codex response contains a placeholder in {field}: {url}')
            source_field = 'title' if field == 'title_cn' else 'summary'
            source_value = str(item.get(source_field, '') or '').strip()
            if value and value == source_value:
                raise ValueError(f'Codex response copied the source into {field}: {url}')
            if value and value != str(item.get('title' if field == 'title_cn' else 'summary', '')).strip():
                item[field] = value
                changed = True
        if changed:
            applied += 1

    if applied:
        stats = data.get('_llm_stats')
        if isinstance(stats, dict):
            stats.update({
                'provider': 'codex_direct',
                'status': 'translated' if not unmatched else 'needs_codex',
                'translated_count': applied,
                'untranslated_count': len(unmatched),
            })
        atomic_write_json(curated_path, data, indent=2)
        generic_path = get_data_dir() / f'curated_{data.get("push_id", "")}.json'
        if generic_path.name != curated_path.name and generic_path.exists():
            atomic_write_json(generic_path, data, indent=2)

    return {
        'status': 'ok' if not unmatched else 'partial',
        'curated_path': str(curated_path),
        'response_path': str(response_path),
        'requested': len(response),
        'applied': applied,
        'unmatched': unmatched,
    }


def main() -> None:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description='Apply Codex direct translations to curated data')
    parser.add_argument('--push-id', required=True, choices=['morning', 'noon', 'evening'])
    parser.add_argument('--response', required=True, type=Path)
    args = parser.parse_args()

    today = datetime.now(CST).strftime('%Y%m%d')
    curated_path = find_curated_file(today, args.push_id)
    if curated_path is None:
        raise SystemExit(f'curated file not found for {args.push_id}')
    result = apply_response(curated_path, args.response)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
