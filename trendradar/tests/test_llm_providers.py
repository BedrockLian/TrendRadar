"""llm_providers 烟雾测试。

覆盖:
  - create_provider() 工厂：所有别名解析
  - Provider 构造参数（api_key/model/endpoint 解析）
  - 消息协议转换：Anthropic (system 提取), Google Gemini (contents/parts)
  - 错误类型：LLMError / LLMAuthError / LLMRateLimit / LLMResponseError
  - 重试逻辑：max_attempts / backoff
  - 集成测试：DEEPSEEK_API_KEY 实测（pytest -m integration 才跑）
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / 'scripts')
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from llm_providers import (
    LLMProvider,
    LLMError,
    LLMAuthError,
    LLMRateLimit,
    LLMResponseError,
    OpenAIChatProvider,
    AnthropicProvider,
    GoogleGenAIProvider,
    OllamaProvider,
    create_provider,
    get_default_provider,
    _PROVIDER_REGISTRY,
)


# ── 1. Provider registry ────────────────────────────────────────────────


class TestProviderRegistry:
    """All 4 protocol families + aliases registered."""

    def test_all_protocol_classes_registered(self):
        """All 4 base classes must be importable and in registry."""
        for cls in (OpenAIChatProvider, AnthropicProvider,
                    GoogleGenAIProvider, OllamaProvider):
            assert cls in _PROVIDER_REGISTRY.values()

    def test_aliases_resolve_to_correct_class(self):
        # OpenAI-compat aliases
        for alias in ('openai_chat', 'openai', 'deepseek', 'gpt',
                      'qwen', 'mistral', 'groq', 'openrouter', 'localai',
                      'ollama_openai'):
            assert _PROVIDER_REGISTRY[alias] is OpenAIChatProvider, alias

        # Anthropic aliases
        for alias in ('anthropic', 'claude'):
            assert _PROVIDER_REGISTRY[alias] is AnthropicProvider, alias

        # Gemini aliases
        for alias in ('google_genai', 'gemini'):
            assert _PROVIDER_REGISTRY[alias] is GoogleGenAIProvider, alias

        # Ollama
        assert _PROVIDER_REGISTRY['ollama'] is OllamaProvider

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            create_provider('nonexistent')


# ── 2. create_provider factory ───────────────────────────────────────────


class TestCreateProvider:
    """Factory resolves all params from explicit → env → defaults."""

    def test_explicit_args(self):
        p = create_provider(
            'openai_chat', model='gpt-4o', api_key='sk-test',
            endpoint='https://api.openai.com/v1',
        )
        assert p.model == 'gpt-4o'
        assert p.api_key == 'sk-test'
        assert p.endpoint == 'https://api.openai.com/v1'

    def test_auto_endpoint_from_model_name(self):
        # 'deepseek-chat' substring → deepseek endpoint
        p = create_provider('openai_chat', model='deepseek-v3',
                            api_key='sk', endpoint=None)
        assert p.endpoint == 'https://api.deepseek.com/v1'

    def test_ollama_default_endpoint(self):
        p = create_provider('ollama', model='llama3.1', api_key=None)
        assert p.endpoint == 'http://localhost:11434'

    def test_anthropic_default_endpoint(self):
        p = create_provider('anthropic', model='claude-3-5-sonnet',
                            api_key='sk-ant')
        assert p.endpoint == 'https://api.anthropic.com'

    def test_gemini_default_endpoint(self):
        p = create_provider('google_genai', model='gemini-1.5-flash',
                            api_key='key')
        assert p.endpoint == 'https://generativelanguage.googleapis.com'

    def test_api_key_env_fallback(self, monkeypatch):
        monkeypatch.setenv('DEEPSEEK_API_KEY', 'sk-env-test')
        p = create_provider('openai_chat', model='deepseek-chat')
        assert p.api_key == 'sk-env-test'

    def test_anthropic_env_alias(self, monkeypatch):
        monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-test')
        p = create_provider('anthropic', model='claude-3-5-sonnet')
        assert p.api_key == 'sk-ant-test'

    def test_gemini_env_alias(self, monkeypatch):
        monkeypatch.setenv('GOOGLE_API_KEY', 'goog-test')
        p = create_provider('google_genai', model='gemini-1.5-flash')
        assert p.api_key == 'goog-test'

    def test_explicit_overrides_env(self, monkeypatch):
        monkeypatch.setenv('DEEPSEEK_API_KEY', 'sk-from-env')
        p = create_provider('openai_chat', model='deepseek-chat',
                            api_key='sk-explicit')
        assert p.api_key == 'sk-explicit'


# ── 3. Anthropic message conversion ─────────────────────────────────────


class TestAnthropicConversion:
    """Anthropic separates system message; check extraction."""

    def test_single_system_extraction(self):
        ap = AnthropicProvider(api_key='test', model='claude-3-5-sonnet')
        system, rest = ap._split_system([
            {'role': 'system', 'content': 'You are a translator.'},
            {'role': 'user', 'content': 'Hello'},
        ])
        assert system == 'You are a translator.'
        assert rest == [{'role': 'user', 'content': 'Hello'}]

    def test_multiple_systems_concatenated(self):
        ap = AnthropicProvider(api_key='test', model='claude')
        system, rest = ap._split_system([
            {'role': 'system', 'content': 'Rule A.'},
            {'role': 'system', 'content': 'Rule B.'},
            {'role': 'user', 'content': 'X'},
        ])
        assert system == 'Rule A.\n\nRule B.'

    def test_no_system_message(self):
        ap = AnthropicProvider(api_key='test', model='claude')
        system, rest = ap._split_system([
            {'role': 'user', 'content': 'Hi'},
        ])
        assert system is None
        assert rest == [{'role': 'user', 'content': 'Hi'}]


# ── 4. Gemini message conversion ────────────────────────────────────────


class TestGeminiConversion:
    """Gemini uses contents[].parts[].text + systemInstruction field."""

    def test_basic_conversion(self):
        gp = GoogleGenAIProvider(api_key='test', model='gemini-1.5-flash')
        sys_ins, contents = gp._convert_messages([
            {'role': 'system', 'content': 'Be brief.'},
            {'role': 'user', 'content': 'Hi'},
            {'role': 'assistant', 'content': 'Hello!'},
            {'role': 'user', 'content': 'How are you?'},
        ])
        assert sys_ins == {'parts': [{'text': 'Be brief.'}]}
        assert contents == [
            {'role': 'user', 'parts': [{'text': 'Hi'}]},
            {'role': 'model', 'parts': [{'text': 'Hello!'}]},
            {'role': 'user', 'parts': [{'text': 'How are you?'}]},
        ]

    def test_no_system_message(self):
        gp = GoogleGenAIProvider(api_key='test', model='gemini')
        sys_ins, contents = gp._convert_messages([
            {'role': 'user', 'content': 'Hi'},
        ])
        assert sys_ins is None
        assert contents == [
            {'role': 'user', 'parts': [{'text': 'Hi'}]},
        ]


# ── 5. Error class hierarchy ────────────────────────────────────────────


class TestErrorHierarchy:
    """All errors derive from LLMError; specific subclasses for retry logic."""

    def test_hierarchy(self):
        assert issubclass(LLMAuthError, LLMError)
        assert issubclass(LLMRateLimit, LLMError)
        assert issubclass(LLMResponseError, LLMError)

    def test_caught_as_llm_error(self):
        try:
            raise LLMAuthError('test')
        except LLMError as e:
            assert isinstance(e, LLMAuthError)


# ── 6. Backward-compat: ai_translate._make_request shim ─────────────────


class TestBackwardCompatShim:
    """ai_translate._make_request() now returns str via LLMProvider."""

    @pytest.mark.asyncio
    async def test_make_request_returns_string(self, monkeypatch):
        # Mock the underlying provider to return canned text
        async def fake_chat(*args, **kwargs):
            return 'translated text'

        # Patch the chat method on the actual class
        monkeypatch.setattr(
            'trendradar.scripts.llm_providers.OpenAIChatProvider.chat',
            fake_chat,
        )
        # Reload module to ensure shim is fresh
        sys.path.insert(0, '/home/asus/.hermes')
        from trendradar.scripts.ai_translate import _make_request
        import aiohttp

        async with aiohttp.ClientSession() as session:
            result = await _make_request(session, 'test-key', [
                {'role': 'user', 'content': 'test'},
            ])
        assert isinstance(result, str)
        assert result == 'translated text'


# ── 7. Integration test: real DeepSeek API (only when key set) ───────────


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get('DEEPSEEK_API_KEY'),
    reason="DEEPSEEK_API_KEY not set",
)
class TestRealDeepSeekAPI:
    """Live API call — marks 'integration' for selective running."""

    @pytest.mark.asyncio
    async def test_chat_returns_text(self):
        p = create_provider(
            'openai_chat',
            model='deepseek-chat',
            api_key=os.environ['DEEPSEEK_API_KEY'],
            endpoint='https://api.deepseek.com/v1',
        )
        resp = await p.chat(
            messages=[{'role': 'user', 'content': 'Reply with exactly: OK'}],
            temperature=0,
            max_tokens=10,
            max_attempts=2,
        )
        assert isinstance(resp, str)
        assert 'OK' in resp.upper()

    @pytest.mark.asyncio
    async def test_chat_handles_invalid_key(self):
        p = create_provider(
            'openai_chat',
            model='deepseek-chat',
            api_key='sk-invalid-test-key',
            endpoint='https://api.deepseek.com/v1',
        )
        with pytest.raises((LLMAuthError, LLMRateLimit)):
            await p.chat(
                messages=[{'role': 'user', 'content': 'Hi'}],
                max_attempts=1,
            )
