#!/usr/bin/env python3
from trendradar.scripts.settings import get_logger
log = get_logger('fragment-push')
"""
fragment_push.py — Split rendered briefing markdown into WeCom-compatible fragments.

Reads full markdown from stdin, splits by '### ' section headers,
then further sub-splits any fragment exceeding MAX_BYTES (3800 UTF-8 bytes)
to prevent WeCom silent truncation (4096-byte hard limit).

Outputs a JSON array of fragment strings to stdout.
Logs to stderr.

Usage: $PYTHON scripts/fragment_push.py < rendered_output.txt

Rules:
- Split at each '### ' header (section boundary)
- The title line '### Hermes日报 ...' stays only on the first fragment
- The footer '**📋 共...**' goes only on the last fragment
- Any fragment > MAX_BYTES is further split at paragraph boundaries (\\n\\n)
- If a single paragraph exceeds MAX_BYTES, split at sentence boundaries (。)\\n
- Final fallback: hard cut at MAX_BYTES with '...(续)' / '(接上)...' markers
"""

import json
import re
import sys

# WeCom limit is 4096 bytes. 3800 leaves room for JSON wrapper + metadata.
MAX_BYTES = 3800
# Continuation markers for hard-split fragments
CONT_MARKER = "\n...(续)"
PREV_MARKER = "(接上)...\n"


def _byte_len(text: str) -> int:
    """Accurate UTF-8 byte count."""
    return len(text.encode('utf-8'))


def _split_overlong(fragment: str) -> list[str]:
    """Split an over-long fragment into byte-safe sub-fragments.

    Strategies (tried in order):
    1. Paragraph boundary (\n\n)
    2. Sentence boundary (。\n or 。)
    3. Hard cut at MAX_BYTES with continuation markers
    """
    result = []
    remaining = fragment

    while remaining:
        if _byte_len(remaining) <= MAX_BYTES:
            result.append(remaining)
            break

        # Strategy 1: split at paragraph boundary within MAX_BYTES
        cut = _find_last(remaining, '\n\n', MAX_BYTES)
        if cut is not None:
            result.append(remaining[:cut].rstrip())
            remaining = remaining[cut:].lstrip('\n')
            continue

        # Strategy 2: split at sentence boundary
        for delim in ['。\n', '。']:
            cut = _find_last(remaining, delim, MAX_BYTES)
            if cut is not None:
                result.append(remaining[:cut])
                remaining = remaining[cut:].lstrip('\n')
                break
        else:
            # Strategy 3: hard cut + iterate until all pieces fit
            marker_bytes = _byte_len(CONT_MARKER)
            cut_point = _find_safe_cut(remaining, MAX_BYTES - marker_bytes)
            if cut_point is None or cut_point == 0:
                # Cannot split further — return as-is (shouldn't happen)
                result.append(remaining)
                break
            result.append(remaining[:cut_point] + CONT_MARKER)
            remaining = remaining[cut_point:]

    return result


def _find_last(text: str, delimiter: str, max_bytes: int) -> int | None:
    """Find the last occurrence of delimiter within max_bytes of text.
    
    Returns character offset (not byte offset) of the END of delimiter, or None.
    Uses byte-accurate search: scans backwards from the character that
    corresponds to max_bytes in UTF-8 encoding.
    """
    encoded = text.encode('utf-8')
    if len(encoded) <= max_bytes:
        # Full text fits — search entire text
        idx = text.rfind(delimiter)
        return idx + len(delimiter) if idx != -1 else None

    # Truncate to max_bytes and find the safe char boundary
    truncated = encoded[:max_bytes]
    for trim in range(4):
        try:
            char_limit = len(truncated.decode('utf-8'))
            break
        except UnicodeDecodeError:
            truncated = truncated[:-1]
    else:
        return None

    idx = text.rfind(delimiter, 0, char_limit)
    if idx == -1:
        return None
    return idx + len(delimiter)


def _find_safe_cut(text: str, max_bytes: int) -> int | None:
    """Find a safe character boundary for hard cut at max_bytes.
    Avoid splitting mid-multi-byte UTF-8 character."""
    encoded = text.encode('utf-8')
    if len(encoded) <= max_bytes:
        return len(text)

    # Truncate and decode back to find safe boundary
    truncated = encoded[:max_bytes]
    # Try to decode; if it fails, trim one byte at a time
    for trim in range(4):  # max 4 bytes for a single UTF-8 char
        try:
            return len(truncated.decode('utf-8'))
        except UnicodeDecodeError:
            truncated = truncated[:-1]
    return max_bytes  # fallback (should never reach here)


def split_fragments(markdown: str) -> list[str]:
    """Split rendered markdown into WeCom-safe fragments.

    Rules:
    - Split at each '### ' header (section boundary)
    - The title line '### Hermes日报 ...' stays only on the first fragment
    - The footer '**📋 共...**' goes only on the last fragment
    - Any fragment > MAX_BYTES is further sub-split at safe boundaries
    - Empty fragments are dropped
    """
    if not markdown or not markdown.strip():
        return []

    lines = markdown.split('\n')

    # Extract the title line (first line starting with ### Hermes日报)
    title_line = ''
    non_title_lines = []
    for line in lines:
        if line.startswith('### Hermes日报'):
            title_line = line
        else:
            non_title_lines.append(line)

    body = '\n'.join(non_title_lines)

    # Split body by '### ' section headers
    sections_raw = re.split(r'\n(?=### )', body)

    sections = [s.strip() for s in sections_raw if s.strip()]

    if not sections:
        return [markdown]  # single fragment, no splitting

    # Detect footer: any line starting with '📌 *共' or '**📋 共'
    footer = ''
    last_section = sections[-1]
    last_section_lines = last_section.split('\n')
    for i in range(len(last_section_lines) - 1, -1, -1):
        stripped = last_section_lines[i].strip()
        if stripped.startswith(('📌 *共', '**📋 共', '📌 *共', '📋 共')):
            footer = last_section_lines.pop(i).strip()
            sections[-1] = '\n'.join(last_section_lines).strip()
            break

    # Build initial fragments by section
    raw_fragments = []
    non_empty = [s for s in sections if s]
    for i, section in enumerate(sections):
        if not section:
            continue
        if i == 0 and title_line:
            frag = f"{title_line}\n\n\n{section}"
        else:
            frag = section

        if i == len(non_empty) - 1 and footer:
            frag = f"{frag}\n\n\n{footer}"

        raw_fragments.append(frag)

    # Byte-count check + sub-splitting
    final_fragments = []
    for frag in raw_fragments:
        if _byte_len(frag) <= MAX_BYTES:
            final_fragments.append(frag)
        else:
            sub_frags = _split_overlong(frag)
            final_fragments.extend(sub_frags)

    return final_fragments


def main():
    markdown = sys.stdin.read()
    fragments = split_fragments(markdown)
    # Only JSON on stdout — orchestrator parses this
    print(json.dumps(fragments, ensure_ascii=False))
    # All diagnostics go to stderr
    print(
        f"[FRAGMENT] Split into {len(fragments)} fragments",
        file=sys.stderr,
    )
    over_limit = False
    for i, f in enumerate(fragments):
        byte_count = len(f.encode('utf-8'))
        char_count = len(f)
        print(f"  Fragment {i+1}: {char_count} chars / {byte_count} bytes", file=sys.stderr)
        if byte_count > MAX_BYTES:
            over_limit = True
            print(
                f"  ⚠️  Fragment {i+1}: {byte_count} bytes exceeds MAX_BYTES={MAX_BYTES} — "
                f"WeCom may silently truncate",
                file=sys.stderr,
            )
    if over_limit:
        # Signal to orchestrator that fragments are unsafe
        print("", file=sys.stderr)
        print("[FRAGMENT] ⚠️  WARNING: one or more fragments exceed byte limit", file=sys.stderr)


if __name__ == '__main__':
    main()
