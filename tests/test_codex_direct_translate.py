import json


def test_apply_response_matches_items_by_url(tmp_path):
    from trendradar.cli.codex_direct_translate import apply_response

    curated_path = tmp_path / 'curated_noon.json'
    response_path = tmp_path / 'response.json'
    curated_path.write_text(json.dumps({
        'push_id': 'noon',
        'top_headlines': [{
            'title': 'Original title',
            'summary': 'Original summary',
            'url': 'https://example.com/item',
        }],
    }, ensure_ascii=False), encoding='utf-8')
    response_path.write_text(json.dumps({
        'items': [{
            'url': 'https://example.com/item',
            'title_cn': '中文标题',
            'summary_cn': '中文摘要。',
        }],
    }, ensure_ascii=False), encoding='utf-8')

    result = apply_response(curated_path, response_path)
    data = json.loads(curated_path.read_text(encoding='utf-8'))

    assert result['status'] == 'ok'
    assert result['applied'] == 1
    assert data['top_headlines'][0]['title_cn'] == '中文标题'
    assert data['top_headlines'][0]['summary_cn'] == '中文摘要。'


def test_apply_response_reports_unmatched_url(tmp_path):
    from trendradar.cli.codex_direct_translate import apply_response

    curated_path = tmp_path / 'curated_noon.json'
    response_path = tmp_path / 'response.json'
    curated_path.write_text(json.dumps({'top_headlines': []}), encoding='utf-8')
    response_path.write_text(json.dumps([{
        'url': 'https://example.com/missing',
        'title_cn': '中文标题',
        'summary_cn': '中文摘要。',
    }], ensure_ascii=False), encoding='utf-8')

    result = apply_response(curated_path, response_path)

    assert result['status'] == 'partial'
    assert result['applied'] == 0
    assert result['unmatched'] == ['https://example.com/missing']
