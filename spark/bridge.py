"""Format bridge: convert a to-issues issue to a FORGE work-item .md."""

from __future__ import annotations

import re
from datetime import datetime

import yaml


def _extract_list_section(body: str, heading: str) -> list[str]:
    """Extract bullet items from `## heading` section.

    Wraps continuation lines (indented non-bullet lines following a ``- ``
    line) into their parent bullet so decisive detail is never dropped.
    """
    pat = re.compile(
        rf"^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pat.search(body)
    if not m:
        return []
    items: list[str] = []
    current: str | None = None
    for raw_line in m.group(1).split("\n"):
        stripped = raw_line.strip()
        if not stripped:
            # Blank line terminates the current bullet.
            if current is not None:
                items.append(current)
                current = None
            continue
        if stripped.startswith("- "):
            if current is not None:
                items.append(current)
            current = stripped[2:].strip()
        elif current is not None:
            # Continuation line: collapse whitespace and append.
            current = f"{current} {stripped}"
        # Lines before any bullet are ignored.
    if current is not None:
        items.append(current)
    return items


def _extract_linked_ids(body: str, heading: str) -> list[str]:
    """Extract `[[id]]` references from `## heading` section."""
    items = _extract_list_section(body, heading)
    ids: list[str] = []
    for item in items:
        for m in re.finditer(r"\[\[([^]]+)\]\]", item):
            ids.append(m.group(1))
    return ids


def issue_to_workitem(
    issue_text: str,
    item_id: str,
    priority: str = "p2",
    project: str = "iron-ai-assistant",
    work_repo: str = "crucible",
) -> str:
    """Convert a to-issues issue to FORGE work-item markdown.

    Parses:
      ``## Acceptance criteria`` → ``acceptance:`` list
      ``## Blocked by``        → ``depends_on:`` list

    Emits ``work_repo`` so the FORGE watcher can route the item to the
    correct work repository. Defaults to ``crucible``.

    Does NOT copy file paths from the issue (they go stale).
    """
    acceptance = _extract_list_section(issue_text, "Acceptance criteria")
    depends_on = _extract_linked_ids(issue_text, "Blocked by")

    frontmatter = {
        "id": item_id,
        "priority": priority,
        "project": project,
        "work_repo": work_repo,
        "depends_on": depends_on,
        "acceptance": acceptance,
    }
    fm_yaml = yaml.safe_dump(
        frontmatter,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    ).rstrip("\n")

    work_item_md = f"""---
{fm_yaml}
---

# {item_id}

Converted from to-issues issue by spark.bridge on {datetime.now().strftime('%Y-%m-%d')}.
"""

    return work_item_md
