"""Fidelity gate: staged acceptance criteria must match the source issue.

Audit finding C (2026-07-10): the bridge used to drop the issue body and every
gate inspected only post-bridge artifacts, so bridge corruption (issue 036)
was invisible to all gates. This gate closes that hole by re-reading the
SOURCE issue and comparing its ``## Acceptance criteria`` against the staged
item's frontmatter.

Deliberately independent implementation: this module must NOT import or copy
``bridge._extract_list_section``. If the gate shared the bridge's extraction
code, a shared bug would corrupt both sides identically and the comparison
would pass — exactly how 036 escaped. The strategy here is different by
design: split the document on ``^## `` headings, take the section's block,
then accumulate entries line by line.
"""

from __future__ import annotations

import re
from pathlib import Path

_SOURCE_ISSUE_RE = re.compile(
    r"^source_issue\s*:\s*(.+?)\s*$", re.MULTILINE
)
_STAGED_FM_RE = re.compile(r"\A---\s*\n(.*?)\n---", re.DOTALL)

_TRUNCATE = 120


def read_source_issue_key(staged_path: str) -> str | None:
    """Read the raw ``source_issue`` frontmatter key from a staged item file.

    ``ironlib.work_item.parse`` ignores unknown keys, so the key is read
    directly from the file's frontmatter block. Returns None when the key is
    absent (hand-authored / legacy items — fidelity is skipped for those).
    """
    text = Path(staged_path).read_text(encoding="utf-8")
    fm = _STAGED_FM_RE.match(text)
    if not fm:
        return None
    m = _SOURCE_ISSUE_RE.search(fm.group(1))
    if not m:
        return None
    return m.group(1).strip().strip('"').strip("'") or None


def extract_criteria(issue_text: str) -> list[str]:
    """Extract ``## Acceptance criteria`` entries — independent of bridge.py.

    Split the document on ``^## `` headings, take the matching section's
    block, then accumulate entries: a line starting ``- `` opens an entry;
    subsequent non-blank, non-heading lines append to it.
    """
    # Split into (heading, block) chunks on H2 headings.
    parts = re.split(r"^(## .*)$", issue_text, flags=re.MULTILINE)
    block: str | None = None
    for i in range(1, len(parts), 2):
        heading = parts[i][3:].strip()
        if heading.lower() == "acceptance criteria":
            block = parts[i + 1] if i + 1 < len(parts) else ""
            break
    if block is None:
        return []

    entries: list[str] = []
    for line in block.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            entries.append(stripped[2:])
        elif entries:
            entries[-1] = f"{entries[-1]} {stripped}"
        # Non-bullet lines before the first entry are ignored.
    return entries


def _normalize(text: str) -> str:
    """Collapse internal whitespace runs and strip, for comparison."""
    return re.sub(r"\s+", " ", text).strip()


def _clip(text: str) -> str:
    """Truncate to ~120 chars for flag messages (ASCII-only output)."""
    return text if len(text) <= _TRUNCATE else text[:_TRUNCATE] + "..."


def check_fidelity(item_id: str, staged_path: str,
                   staged_acceptance: list[str]) -> list[str]:
    """Compare staged acceptance against the source issue's criteria.

    Returns a list of flag strings (empty means pass or no ``source_issue``
    key). Resolves a relative ``source_issue`` path against the current
    working directory — the SKILL runs ``spark check`` from the vault root.
    """
    source_issue = read_source_issue_key(staged_path)
    if source_issue is None:
        return []

    issue_path = Path(source_issue)
    try:
        issue_text = issue_path.read_text(encoding="utf-8")
    except OSError:
        return [f"{item_id}: source issue not found: {source_issue}"]

    expected = [_normalize(c) for c in extract_criteria(issue_text)]
    staged = [_normalize(c) for c in staged_acceptance]

    flags: list[str] = []
    if len(staged) != len(expected):
        flags.append(
            f"{item_id} fidelity: criterion count mismatch: "
            f"staged {len(staged)} vs source {len(expected)} ({source_issue})"
        )
    for i, (s, e) in enumerate(zip(staged, expected)):
        if s != e:
            flags.append(
                f"{item_id} fidelity: criterion {i + 1} differs: "
                f"staged '{_clip(s)}' vs source '{_clip(e)}'"
            )
    return flags
