# Script Rendering Architecture

## Why Script Rendering

LLM-based rendering (`render_briefing.py`) was replaced with pure-script rendering because:

| Dimension | LLM Rendering | Script Rendering |
|-----------|--------------|-----------------|
| Speed | ~9s (5× parallel API) | ~0s |
| Token cost | API cost per run | Zero |
| Format consistency | Dependent on LLM prompt adherence | Hardcoded, 100% reliable |
| User complaints | Frequent (empty line issues) | None |

## Scripts

### `render_markdown.py`
Reads curated JSON → directly formats markdown per render-format.md spec.

- No API calls, zero token cost
- Summaries truncated at 150 chars with sentence-boundary-aware cutoff
- Empty line rules hardcoded (no LLM drift)
- Output compatible with `fragment_push.py`

### `render_deep_analysis.py`
Reads Pro subagent output from stdin → formats for WeCom mobile.

- Strips tables/code blocks/horizontal rules (unsupported by WeCom)
- Detects section headings by keyword → adds emoji (📈🎯📌⚡)
- Auto-truncates at 1600 chars (WeCom single-message limit)
- Preserves natural paragraph breaks

## When to Use

| Scenario | Renderer |
|----------|----------|
| Daily briefing (morning/noon/evening) | `render_markdown.py` (always) |
| Deep analysis (evening Pro agents) | `render_deep_analysis.py` (always) |
| LLM-based fallback | Not needed — script covers all cases |

## Adding a New Renderer

1. Create `scripts/render_*.py` that reads from stdin or a file
2. Output clean markdown to stdout
3. Reference it in `news-secretary` SKILL.md pipeline section
4. Add to the pipeline diagram
