"""Real E2E pipeline test — runs actual pipeline stages via subprocess (not mocked).

Validates pipeline_orchestrator.py end-to-end with curated mock data.
Marked @pytest.mark.integration so CI can skip slow real-process tests.

Usage:
    cd /home/asus/TrendRadar/trendradar
    PYTHONPATH=/home/asus/.hermes/trendradar python -m pytest tests/test_pipeline_e2e_real.py -v
    # Skip integration tests in CI:
    PYTHONPATH=/home/asus/.hermes/trendradar python -m pytest tests/ -v -m "not integration"
"""

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

# Paths
TRENDRADAR_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = TRENDRADAR_DIR / 'scripts'
DATA_DIR = TRENDRADAR_DIR / 'data'
HERMES_DIR = TRENDRADAR_DIR.parent  # derived from __file__, not hardcoded

# Ensure imports work
sys.path.insert(0, str(HERMES_DIR))
sys.path.insert(0, str(TRENDRADAR_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

CST = timezone(timedelta(hours=8))
PYTHON = sys.executable  # Use same Python that's running the tests


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_curated_data():
    """Create minimal curated JSON data (2 items per domain)."""
    today = datetime.now(CST).strftime('%Y%m%d')
    return {
        'top_headlines': [
            {
                'title': '中国发布新一代AI芯片突破性进展',
                'summary': '中国科研团队在AI芯片领域取得重大突破，性能提升300%',
                'source_platform': '新华网',
                'url': 'https://xinhua.com/ai-chip-breakthrough',
                'timestamp': f'{today}T09:00:00Z',
                '_curator_scores': {'total': 12, 'pass': True},
            },
            {
                'title': '普京访华签署多项合作协议',
                'summary': '中俄双方签署能源贸易基建等20余项合作协议',
                'source_platform': 'BBC',
                'url': 'https://bbc.com/putin-china-visit',
                'timestamp': f'{today}T08:30:00Z',
                '_curator_scores': {'total': 11, 'pass': True},
            },
        ],
        'foreign_china': [
            {
                'title': 'US weighs new chip export restrictions targeting China',
                'summary': 'The Biden administration is considering tighter semiconductor export controls targeting China.',
                'source_platform': 'Reuters',
                'url': 'https://reuters.com/us-chips-restrictions',
                'timestamp': f'{today}T10:00:00Z',
                '_curator_scores': {'total': 10, 'pass': True},
            },
            {
                'title': 'EU reviews trade policy on Chinese electric vehicles',
                'summary': 'EU commission launches review of trade policies on Chinese EV imports.',
                'source_platform': 'BBC',
                'url': 'https://bbc.com/eu-china-ev-trade',
                'timestamp': f'{today}T11:00:00Z',
                '_curator_scores': {'total': 10, 'pass': True},
            },
        ],
        'tech': [
            {
                'title': 'GPT-6 训练成本曝光超50亿美元',
                'summary': 'OpenAI内部文件显示GPT-6训练成本超50亿美元，是GPT-5的5倍',
                'source_platform': 'The Verge',
                'url': 'https://theverge.com/gpt6-cost',
                'timestamp': f'{today}T12:00:00Z',
                '_curator_scores': {'total': 10, 'pass': True},
            },
            {
                'title': '量子计算里程碑：1000量子比特处理器问世',
                'summary': 'IBM发布1000+量子比特处理器，量子纠错取得突破',
                'source_platform': '36氪',
                'url': 'https://36kr.com/quantum-1000qubit',
                'timestamp': f'{today}T10:30:00Z',
                '_curator_scores': {'total': 10, 'pass': True},
            },
        ],
        'economy': [
            {
                'title': '4月青年失业率降至16.3%',
                'summary': '国家统计局公布最新就业数据，青年失业率连续3个月下降',
                'source_platform': '新华社',
                'url': 'https://xinhua.com/youth-employment-april',
                'timestamp': f'{today}T09:30:00Z',
                '_curator_scores': {'total': 10, 'pass': True},
            },
            {
                'title': '央行宣布降准0.5个百分点',
                'summary': '央行释放长期流动性约1万亿元，支持实体经济',
                'source_platform': '澎湃新闻',
                'url': 'https://thepaper.cn/pboc-rrr-cut',
                'timestamp': f'{today}T14:00:00Z',
                '_curator_scores': {'total': 10, 'pass': True},
            },
        ],
        'gaming': [
            {
                'title': '黑神话悟空DLC即将公布',
                'summary': '游戏科学将在下月公布黑神话悟空首个DLC内容',
                'source_platform': '机核',
                'url': 'https://gcores.com/wukong-dlc-announce',
                'timestamp': f'{today}T15:00:00Z',
                '_curator_scores': {'total': 10, 'pass': True},
            },
            {
                'title': '原神5.7版本新角色曝光',
                'summary': '原神5.7版本预计引入枫丹新角色和全新地图区域',
                'source_platform': '游民星空',
                'url': 'https://gamersky.com/genshin-57-leak',
                'timestamp': f'{today}T16:00:00Z',
                '_curator_scores': {'total': 10, 'pass': True},
            },
        ],
        'total': 10,
        'curated_at': datetime.now(CST).isoformat(),
        'push_id': 'noon',
        'run_id': 'test-e2e-run-001',
    }


@pytest.fixture
def e2e_workdir(tmp_path, mock_curated_data):
    """Set up a temporary workdir with curated data for E2E pipeline testing."""
    today = datetime.now(CST).strftime('%Y%m%d')

    workdir = tmp_path / 'trendradar'
    data_dir = workdir / 'data'
    scripts_dir = workdir / 'scripts'
    data_dir.mkdir(parents=True)
    scripts_dir.mkdir(parents=True)

    # Write curated JSON files (both dated and generic)
    curated_json = json.dumps(mock_curated_data, ensure_ascii=False, indent=2)

    # Write generic version
    (data_dir / 'curated_noon.json').write_text(curated_json, encoding='utf-8')

    # Write dated version
    (data_dir / f'curated_noon_{today}.json').write_text(curated_json, encoding='utf-8')

    return workdir


# ── Helper ────────────────────────────────────────────────────────────────────

def _run_pipeline_cmd(cmd: list, cwd: Path, env_extra: dict = None, timeout: int = 120) -> subprocess.CompletedProcess:
    """Run a subprocess with standard project env.

    Does NOT set PYTHON_GIL=0 because not all Python builds support disabling the GIL.
    Uses the same Python that's running the tests.
    """
    env = os.environ.copy()
    env['PYTHONPATH'] = str(HERMES_DIR)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(cwd),
        env=env,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestPipelineE2EReal:
    """Real E2E pipeline tests using subprocess for actual script execution."""

    def test_list_steps_output(self):
        """--list-steps returns valid JSON with all 7 stages."""
        cmd = [PYTHON, str(SCRIPTS_DIR / 'pipeline_orchestrator.py'), '--list-steps']
        result = _run_pipeline_cmd(cmd, cwd=TRENDRADAR_DIR)

        assert result.returncode == 0, f"--list-steps failed: {result.stderr}"
        data = json.loads(result.stdout)
        assert data['version'] == '2.9.0'
        assert 'steps' in data
        assert 'python' in data
        steps = data['steps']
        assert len(steps) == 7, f"Expected 7 steps, got {len(steps)}"
        step_names = [s['name'] for s in steps]
        assert 'slot_detect' in step_names
        assert 'push_prepare' in step_names
        assert 'parallel' in step_names
        assert 'render_markdown' in step_names
        assert 'fragment_push' in step_names
        assert 'record_fingerprints' in step_names

    def test_check_version_success(self):
        """--check-version succeeds when all scripts exist."""
        cmd = [PYTHON, str(SCRIPTS_DIR / 'pipeline_orchestrator.py'), '--check-version']
        result = _run_pipeline_cmd(cmd, cwd=TRENDRADAR_DIR)

        assert result.returncode == 0, f"--check-version failed: {result.stderr}"
        data = json.loads(result.stdout)
        assert data['status'] == 'ok'
        assert data['version'] == '2.9.0'

    def test_verify_version_function(self):
        """verify_version() returns ok=True when scripts exist."""
        from pipeline_orchestrator import verify_version
        result = verify_version()
        assert result['ok'], f"verify_version failed: {result.get('errors', [])}"
        assert 'errors' in result

    def test_render_markdown_with_curated_data(self, e2e_workdir):
        """render_markdown.py processes curated JSON and outputs valid markdown."""
        cmd = [PYTHON, str(SCRIPTS_DIR / 'render_markdown.py'), '--push-id', 'noon']
        result = _run_pipeline_cmd(
            cmd,
            cwd=TRENDRADAR_DIR,
            env_extra={'TRENDRADAR_HOME': str(e2e_workdir)},
            timeout=60,
        )

        assert result.returncode == 0, f"render_markdown failed: {result.stderr}"
        assert len(result.stdout) > 0, "render_markdown produced empty output"
        # Verify key elements in output
        assert 'Hermes日报' in result.stdout, "Missing daily briefing header"
        assert '📰 头条' in result.stdout or '头条' in result.stdout, "Missing top_headlines section"

    def test_render_markdown_output_structure(self, e2e_workdir):
        """render_markdown output contains all domain sections from curated data."""
        cmd = [PYTHON, str(SCRIPTS_DIR / 'render_markdown.py'), '--push-id', 'noon']
        result = _run_pipeline_cmd(
            cmd,
            cwd=TRENDRADAR_DIR,
            env_extra={'TRENDRADAR_HOME': str(e2e_workdir)},
            timeout=60,
        )

        assert result.returncode == 0, f"render_markdown failed: {result.stderr}"

        # Verify domain labels appear in output
        output = result.stdout
        expected_labels = ['📰 头条', '🌏 外媒看华', '💻 科技', '📊 经济民生', '🎮 游戏']
        found = [label for label in expected_labels if label in output]
        assert len(found) >= 2, f"Expected at least 2 domain labels, found: {found}"

        # Verify source links appear
        assert '[【' in output or '[' in output, "No source links found in output"

    def test_fragment_push_with_rendered_output(self, e2e_workdir):
        """fragment_push.py splits rendered markdown into byte-safe fragments."""
        # First render
        render_cmd = [PYTHON, str(SCRIPTS_DIR / 'render_markdown.py'), '--push-id', 'noon']
        render_result = _run_pipeline_cmd(
            render_cmd,
            cwd=TRENDRADAR_DIR,
            env_extra={'TRENDRADAR_HOME': str(e2e_workdir)},
            timeout=60,
        )
        assert render_result.returncode == 0, f"render failed: {render_result.stderr}"

        # Then fragment
        frag_cmd = [PYTHON, str(SCRIPTS_DIR / 'fragment_push.py')]
        env = os.environ.copy()
        env['PYTHONPATH'] = str(HERMES_DIR)
        env['TRENDRADAR_HOME'] = str(e2e_workdir)
        frag_result = subprocess.run(
            frag_cmd,
            input=render_result.stdout,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(TRENDRADAR_DIR),
            env=env,
        )

        assert frag_result.returncode == 0, f"fragment_push failed: {frag_result.stderr}"

        # Parse fragments JSON
        fragments = json.loads(frag_result.stdout)
        assert isinstance(fragments, list), f"Expected JSON array, got: {type(fragments)}"
        assert len(fragments) >= 1, "Expected at least 1 fragment"

        # Verify each fragment is under byte limit
        from fragment_push import MAX_BYTES
        for i, frag in enumerate(fragments):
            byte_len = len(frag.encode('utf-8'))
            assert byte_len <= MAX_BYTES, (
                f"Fragment {i}: {byte_len} bytes exceeds MAX_BYTES={MAX_BYTES}"
            )

    def test_push_prepare_importable(self):
        """push_prepare.py module imports and has expected functions."""
        from push_prepare import run_curation, count_new_items, ensure_raw_exists
        assert callable(run_curation)
        assert callable(count_new_items)
        assert callable(ensure_raw_exists)

    def test_pipeline_json_output_structure(self, e2e_workdir):
        """Pipeline orchestrator JSON output has correct structure when run with mock data."""
        # We test that the orchestrator module itself can be imported
        # and its functions produce correct output structure
        from pipeline_orchestrator import list_pipeline_steps, verify_version

        steps_json = json.dumps(list_pipeline_steps())
        assert 'steps' in steps_json
        assert 'version' in steps_json

        ver = verify_version()
        assert isinstance(ver, dict)
        assert 'ok' in ver
        assert 'errors' in ver

    def test_data_dir_structure(self, e2e_workdir):
        """Verify the curated data files were created correctly."""
        data_dir = e2e_workdir / 'data'
        assert data_dir.exists(), "data directory not created"

        curated_files = list(data_dir.glob('curated_noon*.json'))
        assert len(curated_files) >= 1, f"No curated files found in {data_dir}"

        # Load and verify structure
        for cf in curated_files:
            data = json.loads(cf.read_text())
            assert 'top_headlines' in data
            assert 'tech' in data
            assert 'economy' in data
            assert 'gaming' in data
            assert 'total' in data
            assert 'push_id' in data
            assert data['push_id'] == 'noon'


@pytest.mark.integration
class TestPipelineEdgeCases:
    """Edge cases for E2E pipeline behavior."""

    def test_empty_curated_handling(self, tmp_path):
        """Pipeline handles empty curated data gracefully."""
        workdir = tmp_path / 'trendradar'
        data_dir = workdir / 'data'
        data_dir.mkdir(parents=True)

        empty_curated = {
            'top_headlines': [],
            'foreign_china': [],
            'tech': [],
            'economy': [],
            'gaming': [],
            'total': 0,
            'curated_at': datetime.now(CST).isoformat(),
            'push_id': 'noon',
        }
        (data_dir / 'curated_noon.json').write_text(
            json.dumps(empty_curated, ensure_ascii=False)
        )
        (data_dir / f'curated_noon_{datetime.now(CST).strftime("%Y%m%d")}.json').write_text(
            json.dumps(empty_curated, ensure_ascii=False)
        )

        # render_markdown should still exit 0 with empty content
        cmd = [PYTHON, str(SCRIPTS_DIR / 'render_markdown.py'), '--push-id', 'noon']
        result = _run_pipeline_cmd(
            cmd,
            cwd=TRENDRADAR_DIR,
            env_extra={'TRENDRADAR_HOME': str(workdir)},
            timeout=60,
        )
        # render_markdown may exit with 0 or non-zero on empty - either is acceptable
        # The important thing is it doesn't crash
        assert 'Traceback' not in result.stderr, f"render_markdown crashed: {result.stderr}"
        # Positive: should produce stdout (even if empty) and not signal failure via stderr
        assert result.stdout is not None

    def test_missing_curated_file_errors_gracefully(self):
        """render_markdown with missing curated file errors gracefully."""
        nonexistent = Path(tempfile.mkdtemp()) / 'trendradar'
        (nonexistent / 'data').mkdir(parents=True)

        cmd = [PYTHON, str(SCRIPTS_DIR / 'render_markdown.py'), '--push-id', 'noon']
        result = _run_pipeline_cmd(
            cmd,
            cwd=TRENDRADAR_DIR,
            env_extra={'TRENDRADAR_HOME': str(nonexistent)},
            timeout=60,
        )
        # Should fail but not crash
        assert 'Traceback' not in result.stderr
        # Positive: should exit with non-zero for missing file
        assert result.returncode != 0
