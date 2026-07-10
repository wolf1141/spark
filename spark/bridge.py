"""Format bridge: convert a to-issues issue to a FORGE work-item .md."""

from __future__ import annotations

import re
from datetime import datetime


def _extract_list_section(body: str, heading: str) -> list[str]:
    """Extract bullet items from `## heading` section."""
    pat = re.compile(
        rf"^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pat.search(body)
    if not m:
        return []
    items: list[str] = []
    for line in m.group(1).split("\n"):
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
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

    # Build YAML list lines at 2-space indent under their parent key.
    if depends_on:
        dep_lines = "\n".join(f"  - {d}" for d in depends_on)
    else:
        dep_lines = "  []"

    ac_lines = "\n".join(f'  - "{c}"' for c in acceptance)

    work_item_md = f"""---
id: {item_id}
priority: {priority}
project: {project}
work_repo: {work_repo}
depends_on:
{dep_lines}
acceptance:
{ac_lines}
---

# {item_id}

Converted from to-issues issue by spark.bridge on {datetime.now().strftime('%Y-%m-%d')}.
"""

    return work_item_md
