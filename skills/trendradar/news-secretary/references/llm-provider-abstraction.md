# LLM Provider 解耦（2026-06-01）

## 背景

`ai_translate.py` 此前硬编码 DeepSeek 的 OpenAI 兼容协议——endpoint、headers、retry 策略、JSON response 解析全在脚本里。要切到 Claude / Gemini / 本地 Ollama 必须改 4+ 处。

## 抽象层

新增 `trendradar/scripts/llm_providers.py`：

```
LLMProvider (abstract)
├── OpenAIChatProvider       # DeepSeek/OpenAI/Mistral/Groq/Qwen/OpenRouter/LocalAI/Ollama(OpenAI 模式)
├── AnthropicProvider        # Claude 3.5/3.7/4
├── GoogleGenAIProvider      # Gemini 1.5/2.0
└── OllamaProvider           # 本地 Ollama /api/chat
```

**统一接口**：`await provider.chat(messages, temperature, max_tokens) -> str`

**共享重试**：基类内置指数退避 + ±50% jitter 抖动，max 5 次重试，递增 timeout 预算。子类只关心协议转换。

**错误层级**：
- `LLMError` 基类
  - `LLMAuthError` — 401/403 立刻失败，**不重试**（重试也无效）
  - `LLMRateLimit` — 429/5xx 触发退避重试
  - `LLMResponseError` — JSON 解析失败/字段缺失，触发重试

## 配置驱动切换

4 个环境变量 + 1 个 API key 环境变量即可切换 provider，**零代码改动**：

```bash
# DeepSeek（默认，向后兼容）
TRENDRADAR_LLM_PROVIDER=openai_chat
DEEPSEEK_API_KEY=***

# OpenAI
TRENDRADAR_LLM_PROVIDER=openai_chat
TRENDRADAR_LLM_MODEL=gpt-4o
TRENDRADAR_LLM_ENDPOINT=https://api.openai.com/v1
OPENAI_API_KEY=***

# Claude
TRENDRADAR_LLM_PROVIDER=anthropic
TRENDRADAR_LLM_MODEL=claude-3-5-sonnet-20241022
ANTHROPIC_API_KEY=***

# Gemini
TRENDRADAR_LLM_PROVIDER=google_genai
TRENDRADAR_LLM_MODEL=gemini-1.5-flash
GOOGLE_API_KEY=***

# 本地 Ollama
TRENDRADAR_LLM_PROVIDER=ollama
TRENDRADAR_LLM_MODEL=llama3.1
TRENDRADAR_LLM_ENDPOINT=http://localhost:11434
# 无需 API key
```

**别名**：14 个短别名 → 4 个协议类。例：`deepseek` / `gpt` / `qwen` / `mistral` / `groq` 全部映射到 `OpenAIChatProvider`。

**API key 回退链**：
- `openai_chat` 优先 `DEEPSEEK_API_KEY`，回退 `OPENAI_API_KEY` / `MISTRAL_API_KEY` / `GROQ_API_KEY` / ...
- `anthropic` → `ANTHROPIC_API_KEY`
- `google_genai` → `GOOGLE_API_KEY` / `GEMINI_API_KEY`
- `ollama` 不需要 key

## 4 个协议的协议差异处理

| 协议 | URL | Auth | System msg | 响应 |
|------|-----|------|-----------|------|
| OpenAI 兼容 | `POST {endpoint}/chat/completions` | `Authorization: Bearer KEY` | `messages[0].role=system` | `choices[0].message.content` |
| Anthropic | `POST https://api.anthropic.com/v1/messages` | `x-api-key` + `anthropic-version` | **提到顶层 `system` 字段** | `content[0].text` |
| Gemini | `POST .../models/{model}:generateContent?key=KEY` | URL 参数 | **提到顶层 `systemInstruction`** | `candidates[0].content.parts[0].text` |
| Ollama | `POST {endpoint}/api/chat` | 无 | `messages[0].role=system` | `message.content`（无 choices wrapper） |

**Anthropic 特殊处理**：在 `_split_system()` 中抽取 system message → 顶层；多 system message 用 `\n\n` 拼接。Assistant role 保持不变（`user`/`assistant` → `user`/`assistant`）。

**Gemini 特殊处理**：在 `_convert_messages()` 中转换 — assistant → `model`，所有 content 包成 `parts: [{text: ...}]`。多 system 拼接同上。

## ai_translate.py 改造要点

- `_make_request()` 变成薄 shim：`provider = get_default_provider(); return await provider.chat(messages)`
- `batch_translate()` / `batch_expand()` 接收的响应**直接是 string**（不再 `.json()['choices'][0]`），省去协议相关解析
- `process_curated()` 改为 provider 存在性检查（Ollama 可不设 key）
- 原 `RETRY_MAX_ATTEMPTS/RETRY_BASE_DELAY/...` 5 个常量从 `config/translation.py` 删除——重试逻辑已封装在 provider 内

## 添加新 provider 的清单

1. 决定协议类（OpenAI 兼容 / Anthropic / Gemini / Ollama / 新增）
2. 如新协议：在 `llm_providers.py` 写新类，继承 `LLMProvider`，实现 `_do_chat()`
3. 在 `_PROVIDER_REGISTRY` 注册类+别名
4. 在 `_resolve_api_key_env` 添 API key 回退链
5. 在 `tests/test_llm_providers.py` 加单元测试
6. 在本文件「4 个协议差异」表补一行

## 测试

`trendradar/tests/test_llm_providers.py`（22 测试）覆盖：
- 注册表完整性（4 个协议类 + 14 个别名）
- 工厂函数（env 变量回退、显式参数优先级）
- 消息协议转换（Anthropic system 抽取、Gemini contents/parts）
- 错误层级（4 个 LLMError 子类）
- 集成测试（真实 DeepSeek API）— `@pytest.mark.integration` + `skipif no DEEPSEEK_API_KEY`

## 失败模式参考

**症状：AI 返回 `TITLE: 第一标题` 等前缀** — `_parse_line_pairs()` 第 261 行曾把 `TITLE:`/`SUMMARY:` 开头的整行跳过（视为注释），导致标题/摘要内容完全丢失 → `[扩写失败]`。修复：原代码 strip 前缀后保留内容。详见 news-secretary SKILL 翻译管线第 10 条。

**症状：模型返回原文（title_cn == title）** — `_parse_line_pairs()` 接收的是单行 title+summary 拼成一行输出，AI 误以为是单数。修复：`_EXPAND_TEMPLATE` 改为 "TWO separate sentences, Do NOT merge"。详见 news-secretary SKILL 翻译管线第 6 条。
