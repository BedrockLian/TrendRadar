"""
llm_providers.py — Provider-agnostic LLM chat interface for ai_translate.

Unified async interface:
    provider = create_provider(name, model=..., api_key=..., endpoint=...)
    text = await provider.chat(messages=[...], temperature=0.3, max_tokens=4096)

Currently supported (4 protocol families, 7+ services):
- openai_chat (OpenAI-compatible): DeepSeek, OpenAI, Mistral, LocalAI, Qwen, etc.
- anthropic (Anthropic Messages API): Claude 3.5/3.7/4
- google_genai (Google Gemini): Gemini 1.5/2.0
- ollama (local Ollama /api/chat): Llama, Qwen, DeepSeek-r1, etc.

Configuration via env vars (read by create_provider()):
- TRENDRADAR_LLM_PROVIDER    (default: openai_chat)
- TRENDRADAR_LLM_MODEL       (default: deepseek-chat)
- TRENDRADAR_LLM_ENDPOINT    (default: provider-specific)
- TRENDRADAR_LLM_API_KEY     (default: provider-specific)
- TRENDRADAR_LLM_TIMEOUT     (default: 60)

Adding a new provider: extend `_PROVIDER_REGISTRY` + (if non-OpenAI-protocol)
add a new provider class. Most "OpenAI-compatible" services just need the
right endpoint URL configured.
"""
import asyncio
import json
import os
import random
from abc import ABC, abstractmethod
from typing import Any

import aiohttp


# ── Configuration ──────────────────────────────────────────────────────────

DEFAULT_PROVIDER = os.environ.get('TRENDRADAR_LLM_PROVIDER', 'openai_chat')
DEFAULT_MODEL = os.environ.get('TRENDRADAR_LLM_MODEL', 'deepseek-chat')
DEFAULT_TIMEOUT = int(os.environ.get('TRENDRADAR_LLM_TIMEOUT', '60'))


class LLMError(Exception):
    """Base error for all LLM provider issues."""


class LLMAuthError(LLMError):
    """API key invalid / unauthorized — caller should not retry."""


class LLMRateLimit(LLMError):
    """Rate-limited / temporary — caller should back off and retry."""


class LLMResponseError(LLMError):
    """Malformed response from provider."""


# ── Provider base ──────────────────────────────────────────────────────────


class LLMProvider(ABC):
    """Async chat interface — protocol-agnostic.

    Subclasses must implement _do_chat() that returns the assistant text.
    chat() wraps it with exponential backoff retry (shared across all providers).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        endpoint: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL
        self.endpoint = endpoint
        self.timeout = timeout

    @abstractmethod
    async def _do_chat(
        self,
        session: aiohttp.ClientSession,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Provider-specific chat call. Return assistant text or raise LLMError."""

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        max_attempts: int = 5,
        base_delay: float = 2.0,
        max_delay: float = 30.0,
        jitter: float = 0.5,
    ) -> str:
        """Public entrypoint with shared retry/backoff logic.

        Retries on LLMRateLimit and LLMResponseError. Fails fast on LLMAuthError.
        Uses exponential backoff with ±jitter random factor.
        """
        if not messages:
            raise ValueError("messages must be non-empty")

        async with aiohttp.ClientSession() as session:
            last_err: Exception | None = None
            for attempt in range(max_attempts):
                # Increase timeout budget on retries
                per_attempt_timeout = self.timeout + (attempt * 15)
                timeout = aiohttp.ClientTimeout(total=per_attempt_timeout)
                try:
                    return await self._do_chat(
                        session=session,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        # Per-attempt timeout override via wrapper
                    )
                except LLMAuthError:
                    raise  # don't retry auth errors
                except (LLMRateLimit, LLMResponseError) as e:
                    last_err = e
                    if attempt < max_attempts - 1:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        delay += delay * jitter * (random.random() * 2 - 1)
                        await asyncio.sleep(delay)
                    continue
                except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as e:
                    last_err = e
                    if attempt < max_attempts - 1:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        delay += delay * jitter * (random.random() * 2 - 1)
                        await asyncio.sleep(delay)
                    continue

            if last_err is None:
                raise LLMError("chat failed but no error captured")
            raise last_err


# ── OpenAI-compatible (DeepSeek, OpenAI, Mistral, LocalAI, Qwen, Groq, ...) ─


class OpenAIChatProvider(LLMProvider):
    """POST {endpoint}/chat/completions

    Used by: DeepSeek, OpenAI, Mistral, LocalAI, Qwen (DashScope compat),
    Groq, Together, Anyscale, OpenRouter (openai mode), etc.

    Default endpoint: https://api.deepseek.com/v1
    """

    DEFAULT_BASE_URLS = {
        'deepseek': 'https://api.deepseek.com/v1',
        'openai': 'https://api.openai.com/v1',
        'mistral': 'https://api.mistral.ai/v1',
        'groq': 'https://api.groq.com/openai/v1',
        'qwen': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        'openrouter': 'https://openrouter.ai/api/v1',
        'localai': 'http://localhost:8080/v1',
        'ollama_openai': 'http://localhost:11434/v1',
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.endpoint:
            # Auto-detect from model name
            model_lower = (self.model or '').lower()
            for prefix, url in self.DEFAULT_BASE_URLS.items():
                if prefix in model_lower:
                    self.endpoint = url
                    break
            if not self.endpoint:
                self.endpoint = self.DEFAULT_BASE_URLS['deepseek']

    async def _do_chat(
        self,
        session: aiohttp.ClientSession,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> str:
        url = f"{self.endpoint.rstrip('/')}/chat/completions"
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'

        payload = {
            'model': self.model,
            'messages': messages,
            'temperature': temperature,
            'max_tokens': max_tokens,
        }

        async with session.post(url, json=payload, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
            if resp.status == 401 or resp.status == 403:
                raise LLMAuthError(f"Auth failed: {resp.status} {await resp.text()}")
            if resp.status == 429 or resp.status == 529:
                raise LLMRateLimit(f"Rate limited: {resp.status}")
            if resp.status >= 500:
                raise LLMRateLimit(f"Server error: {resp.status}")
            data = await resp.json()

        if 'choices' not in data or not data['choices']:
            err = data.get('error', {}).get('message', 'no choices')
            raise LLMResponseError(f"Bad response: {err}")

        try:
            return data['choices'][0]['message']['content'].strip()
        except (KeyError, IndexError, TypeError) as e:
            raise LLMResponseError(f"Malformed choices: {e}")


# ── Anthropic (Claude 3.5/3.7/4) ──────────────────────────────────────────


class AnthropicProvider(LLMProvider):
    """POST https://api.anthropic.com/v1/messages

    Used by: Claude 3 Haiku/Sonnet/Opus, Claude 3.5/3.7/4.

    Differences from OpenAI:
    - system message is a top-level field, not in messages array
    - auth via x-api-key header (not Authorization: Bearer)
    - required header: anthropic-version
    - max_tokens required (no upper default like 4096)
    - response: content[0].text (content is array of {type, text} blocks)
    """

    DEFAULT_BASE_URL = 'https://api.anthropic.com'
    DEFAULT_MODEL = 'claude-3-5-sonnet-20241022'
    API_VERSION = '2023-06-01'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.endpoint:
            self.endpoint = self.DEFAULT_BASE_URL

    def _split_system(self, messages: list[dict]) -> tuple[str | None, list[dict]]:
        """Extract system message from messages array; return (system, rest)."""
        system = None
        rest = []
        for m in messages:
            if m.get('role') == 'system':
                if system is None:
                    system = m['content']
                else:
                    # Concatenate multiple system messages
                    system = f"{system}\n\n{m['content']}"
            else:
                rest.append(m)
        return system, rest

    async def _do_chat(
        self,
        session: aiohttp.ClientSession,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> str:
        url = f"{self.endpoint.rstrip('/')}/v1/messages"
        headers = {
            'Content-Type': 'application/json',
            'anthropic-version': self.API_VERSION,
        }
        if self.api_key:
            headers['x-api-key'] = self.api_key

        system, user_messages = self._split_system(messages)
        payload: dict[str, Any] = {
            'model': self.model,
            'messages': user_messages,
            'max_tokens': max_tokens,
            'temperature': temperature,
        }
        if system:
            payload['system'] = system

        async with session.post(url, json=payload, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
            if resp.status == 401:
                raise LLMAuthError(f"Auth failed: {resp.status} {await resp.text()}")
            if resp.status == 429 or resp.status == 529:
                raise LLMRateLimit(f"Rate limited: {resp.status}")
            if resp.status >= 500:
                raise LLMRateLimit(f"Server error: {resp.status}")
            data = await resp.json()

        if 'error' in data:
            err_type = data['error'].get('type', '')
            if err_type in ('authentication_error', 'permission_error'):
                raise LLMAuthError(f"Anthropic auth error: {data['error']}")
            raise LLMResponseError(f"Anthropic API error: {data['error']}")

        try:
            content = data['content']
            if not content or content[0].get('type') != 'text':
                raise LLMResponseError(f"Unexpected content shape: {content}")
            return content[0]['text'].strip()
        except (KeyError, IndexError, TypeError) as e:
            raise LLMResponseError(f"Malformed response: {e}")


# ── Google Gemini (generateContent) ────────────────────────────────────────


class GoogleGenAIProvider(LLMProvider):
    """POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key=...

    Used by: Gemini 1.5 Pro/Flash, Gemini 2.0 Flash, Gemma.

    Differences from OpenAI:
    - Auth via ?key=... query param (or Bearer header)
    - contents[].parts[].text (role + parts, not message dicts)
    - systemInstruction is a top-level field (optional)
    - response: candidates[0].content.parts[0].text
    - generationConfig: {temperature, maxOutputTokens}
    """

    DEFAULT_BASE_URL = 'https://generativelanguage.googleapis.com'
    DEFAULT_MODEL = 'gemini-1.5-flash'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.endpoint:
            self.endpoint = self.DEFAULT_BASE_URL

    def _convert_messages(self, messages: list[dict]) -> tuple[dict | None, list[dict]]:
        """Convert {role, content} messages → (systemInstruction, contents).

        Gemini only has user/model roles. System prompt goes into systemInstruction.
        """
        system_instruction = None
        contents = []
        for m in messages:
            role = m.get('role')
            text = m.get('content', '')
            if role == 'system':
                if system_instruction is None:
                    system_instruction = {'parts': [{'text': text}]}
                else:
                    # Concat
                    system_instruction['parts'][0]['text'] += f"\n\n{text}"
            elif role == 'user':
                contents.append({'role': 'user', 'parts': [{'text': text}]})
            elif role == 'assistant':
                contents.append({'role': 'model', 'parts': [{'text': text}]})
        return system_instruction, contents

    async def _do_chat(
        self,
        session: aiohttp.ClientSession,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> str:
        url = (
            f"{self.endpoint.rstrip('/')}/v1beta/models/{self.model}"
            f":generateContent"
        )
        if self.api_key:
            url += f"?key={self.api_key}"
        headers = {'Content-Type': 'application/json'}

        system_instruction, contents = self._convert_messages(messages)
        payload: dict[str, Any] = {
            'contents': contents,
            'generationConfig': {
                'temperature': temperature,
                'maxOutputTokens': max_tokens,
            },
        }
        if system_instruction:
            payload['systemInstruction'] = system_instruction

        async with session.post(url, json=payload, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
            if resp.status == 401 or resp.status == 403:
                raise LLMAuthError(f"Auth failed: {resp.status} {await resp.text()}")
            if resp.status == 429:
                raise LLMRateLimit(f"Rate limited: {resp.status}")
            if resp.status >= 500:
                raise LLMRateLimit(f"Server error: {resp.status}")
            data = await resp.json()

        if 'error' in data:
            err = data['error']
            if err.get('status') in ('UNAUTHENTICATED', 'PERMISSION_DENIED'):
                raise LLMAuthError(f"Gemini auth error: {err}")
            raise LLMResponseError(f"Gemini error: {err}")

        try:
            candidate = data['candidates'][0]
            parts = candidate['content']['parts']
            if not parts or 'text' not in parts[0]:
                raise LLMResponseError(f"No text in parts: {parts}")
            return parts[0]['text'].strip()
        except (KeyError, IndexError, TypeError) as e:
            raise LLMResponseError(f"Malformed response: {e}")


# ── Ollama (local /api/chat) ───────────────────────────────────────────────


class OllamaProvider(LLMProvider):
    """POST {endpoint}/api/chat

    Used by: local Ollama server (llama, qwen, deepseek-r1, mistral, etc.)

    Differences from OpenAI:
    - endpoint: http://localhost:11434 by default
    - No auth header required
    - Optional stream: false (default)
    - response: message.content (no 'choices' wrapper)
    """

    DEFAULT_BASE_URL = 'http://localhost:11434'
    DEFAULT_MODEL = 'llama3.1'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.endpoint:
            self.endpoint = self.DEFAULT_BASE_URL

    async def _do_chat(
        self,
        session: aiohttp.ClientSession,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> str:
        url = f"{self.endpoint.rstrip('/')}/api/chat"
        headers = {'Content-Type': 'application/json'}

        payload = {
            'model': self.model,
            'messages': messages,
            'stream': False,
            'options': {
                'temperature': temperature,
                'num_predict': max_tokens,
            },
        }

        async with session.post(url, json=payload, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
            if resp.status == 401:
                raise LLMAuthError(f"Ollama auth (set OLLAMA_AUTH): {resp.status}")
            if resp.status == 404:
                raise LLMResponseError(f"Model not found: {self.model}")
            if resp.status >= 500:
                raise LLMRateLimit(f"Ollama server error: {resp.status}")
            data = await resp.json()

        try:
            return data['message']['content'].strip()
        except (KeyError, TypeError) as e:
            raise LLMResponseError(f"Malformed Ollama response: {e}")


# ── Registry & Factory ──────────────────────────────────────────────────────


_PROVIDER_REGISTRY: dict[str, type[LLMProvider]] = {
    'openai_chat': OpenAIChatProvider,
    'openai': OpenAIChatProvider,  # alias
    'deepseek': OpenAIChatProvider,  # alias
    'gpt': OpenAIChatProvider,
    'qwen': OpenAIChatProvider,
    'mistral': OpenAIChatProvider,
    'groq': OpenAIChatProvider,
    'openrouter': OpenAIChatProvider,
    'localai': OpenAIChatProvider,
    'anthropic': AnthropicProvider,
    'claude': AnthropicProvider,  # alias
    'google_genai': GoogleGenAIProvider,
    'gemini': GoogleGenAIProvider,  # alias
    'ollama': OllamaProvider,
    'ollama_openai': OpenAIChatProvider,  # Ollama's /v1/chat/completions compat
}


def _resolve_api_key_env(provider_name: str) -> str | None:
    """Provider-specific env var lookup with chain fallback."""
    # Try provider-specific env first, then generic, then settings fallback
    env_chains = {
        'openai_chat': ['DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'MISTRAL_API_KEY',
                        'GROQ_API_KEY', 'QWEN_API_KEY', 'OPENROUTER_API_KEY',
                        'TRENDRADAR_LLM_API_KEY'],
        'anthropic': ['ANTHROPIC_API_KEY', 'TRENDRADAR_LLM_API_KEY'],
        'google_genai': ['GOOGLE_API_KEY', 'GEMINI_API_KEY', 'TRENDRADAR_LLM_API_KEY'],
        'ollama': ['TRENDRADAR_LLM_API_KEY'],  # usually None
    }
    # Resolve alias → canonical
    canonical = {
        'openai': 'openai_chat', 'deepseek': 'openai_chat', 'gpt': 'openai_chat',
        'qwen': 'openai_chat', 'mistral': 'openai_chat', 'groq': 'openai_chat',
        'openrouter': 'openai_chat', 'localai': 'openai_chat',
        'ollama_openai': 'openai_chat',
        'claude': 'anthropic', 'gemini': 'google_genai',
    }.get(provider_name, provider_name)
    for env_name in env_chains.get(canonical, []):
        val = os.environ.get(env_name)
        if val:
            return val
    # 链全部 miss 后 fallback 到 settings.get_api_key()（支持 .env 文件）
    # Bug 修复 (2026-06-02 22:11): 21:00 evening ai_translate 401 假阳性根因 —
    # _resolve_api_key_env 只查 os.environ，cron agent env 没注入 DEEPSEEK_API_KEY，
    # 但 settings.get_api_key() 有 TRENDRADAR_HOME/.env + ~/.hermes/.env 双重 fallback。
    try:
        from trendradar.scripts.settings import get_api_key as _gk
        fallback = _gk()
        if fallback:
            return fallback
    except Exception:
        pass
    return None


def create_provider(
    provider_name: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    endpoint: str | None = None,
    timeout: int | None = None,
) -> LLMProvider:
    """Factory: build a provider instance by name.

    Resolution order:
    1. Explicit arg if provided
    2. TRENDRADAR_LLM_* env var
    3. Provider-specific env fallback chain (DEEPSEEK_API_KEY, OPENAI_API_KEY, etc.)
    4. Built-in defaults

    Examples:
        # Auto-detect from env
        create_provider()

        # Force DeepSeek via OpenAI compat
        create_provider('openai_chat', model='deepseek-chat',
                        api_key='sk-...', endpoint='https://api.deepseek.com/v1')

        # Switch to Claude
        create_provider('anthropic', model='claude-3-5-sonnet-20241022',
                        api_key='sk-ant-...')

        # Local Ollama
        create_provider('ollama', model='llama3.1',
                        endpoint='http://localhost:11434')
    """
    name = (provider_name or DEFAULT_PROVIDER).lower().strip()
    if name not in _PROVIDER_REGISTRY:
        raise ValueError(
            f"Unknown provider: '{name}'. "
            f"Available providers: {', '.join(sorted(_PROVIDER_REGISTRY.keys()))} "
        )

    cls = _PROVIDER_REGISTRY[name]
    resolved_key = api_key or _resolve_api_key_env(name)
    resolved_model = model or os.environ.get('TRENDRADAR_LLM_MODEL') or DEFAULT_MODEL
    resolved_endpoint = endpoint or os.environ.get('TRENDRADAR_LLM_ENDPOINT')
    resolved_timeout = timeout or int(os.environ.get('TRENDRADAR_LLM_TIMEOUT', DEFAULT_TIMEOUT))

    return cls(
        api_key=resolved_key,
        model=resolved_model,
        endpoint=resolved_endpoint,
        timeout=resolved_timeout,
    )


# ── Backward-compat: drop-in replacement for the old _make_request() ──────


def get_default_provider() -> LLMProvider:
    """Singleton getter for ai_translate.py integration.

    Reads env vars. Returns the same provider across calls.
    """
    global _default_provider
    if _default_provider is None:
        _default_provider = create_provider()
    return _default_provider


_default_provider: LLMProvider | None = None
