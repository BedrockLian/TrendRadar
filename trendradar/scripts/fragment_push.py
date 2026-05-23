#!/usr/bin/env python3
from settings import get_logger
log = get_logger('fragment-push')
"""
fragment_push.py — Split rendered briefing markdown into WeCom-compatible fragments.

Reads full markdown from stdin, splits by '### ' section headers,
ensures the footer (tail note) only appears on the last fragment.

Outputs a JSON array of fragment strings to stdout.
Logs to stderr.

Usage: $PYTHON scripts/fragment_push.py < rendered_output.txt

Supports the first line being the title line (### Hermes日报 · ...):
it is re-attached to the first fragment only.
"""

import json
import re
import sys


def split_fragments(markdown: str) -> list[str]:
    """Split rendered markdown into fragments split at '### ' section headers.

    Rules:
    - Split at each '### ' header (section boundary)
    - The title line '### Hermes日报 ...' stays only on the first fragment
    - The footer '**📋 共...**' goes only on the last fragment
    - Empty fragments are dropped
    """
    if not markdown or not markdown.strip():
        return []

    lines = markdown.split('\n')

    # Extract the title line (first line starting with ### Hermes日报)
    title_line = ''
    non_title_lines = []
    for i, line in enumerate(lines):
        if line.startswith('### Hermes日报'):
            title_line = line
        else:
            non_title_lines.append(line)

    body = '\n'.join(non_title_lines)

    # Split body by '### ' section headers
    # Each section starts with '### ' and includes everything until the next '### ' or end
    sections_raw = re.split(r'\n(?=### )', body)

    sections = [s.strip() for s in sections_raw if s.strip()]

    if not sections:
        return [markdown]  # single fragment, no splitting

    # Detect footer: the last line starting with **📋 共
    footer = ''
    last_section = sections[-1]
    last_section_lines = last_section.split('\n')
    for i in range(len(last_section_lines) - 1, -1, -1):
        if last_section_lines[i].strip().startswith('**📋 共'):
            footer = last_section_lines.pop(i).strip()
            sections[-1] = '\n'.join(last_section_lines).strip()
            break

    # Build fragments
    fragments = []
    for i, section in enumerate(sections):
        if not section:
            continue
        if i == 0 and title_line:
            frag = f"{title_line}\n\n\n{section}"
        else:
            frag = section

        if i == len([s for s in sections if s]) - 1 and footer:
            frag = f"{frag}\n\n\n{footer}"

        fragments.append(frag)

    return fragments


def main():
    markdown = sys.stdin.read()
    fragments = split_fragments(markdown)
    print(json.dumps(fragments, ensure_ascii=False))
    print(
        f"[FRAGMENT] Split into {len(fragments)} fragments",
        file=sys.stderr,
    )
    for i, f in enumerate(fragments):
        log.info(f"  Fragment {i+1}: {len(f)} chars")


if __name__ == '__main__':
    main()
