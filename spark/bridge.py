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


_ISSUE_FM_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n?", re.DOTALL)


def _strip_issue_frontmatter(text: str) -> str:
    """Drop a leading ``---`` YAML frontmatter block if the issue carries one.

    The work item's frontmatter is the contract; re-carrying the issue's raw
    frontmatter into the body would duplicate (and could contradict) it.
    """
    return _ISSUE_FM_RE.sub("", text, count=1)


def _strip_section(text: str, heading: str) -> str:
    """Remove a ``## heading`` section (heading line through next ``## ``/EOF).

    Keeps extracted sections (criteria, blockers) out of the carried body so
    each fact has exactly one source of truth — the frontmatter.
    """
    pat = re.compile(
        rf"^##\s+{re.escape(heading)}\s*\n.*?(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    return pat.sub("", text)


def _carry_body(issue_text: str) -> str:
    """The issue's intent: its text minus frontmatter and extracted sections.

    Everything else — title line, description, implementation notes,
    constraints, any other section — is carried verbatim so the builder sees
    the full intent, not just the machine-checkable criteria.
    """
    carried = _strip_issue_frontmatter(issue_text)
    carried = _strip_section(carried, "Acceptance criteria")
    carried = _strip_section(carried, "Blocked by")
    # Collapse the blank runs left where sections were excised.
    carried = re.sub(r"\n{3,}", "\n\n", carried).strip()
    return carried


def issue_to_workitem(
    issue_text: str,
    item_id: str,
    priority: str = "p2",
    project: str = "iron-ai-assistant",
    work_repo: str = "crucible",
    source_issue: str | None = None,
) -> str:
    """Convert a to-issues issue to FORGE work-item markdown.

    Parses:
      ``## Acceptance criteria`` → ``acceptance:`` list
      ``## Blocked by``        → ``depends_on:`` list

    Emits ``work_repo`` so the FORGE watcher can route the item to the
    correct work repository. Defaults to ``crucible``.

    When ``source_issue`` (vault-relative path to the source ticket) is given
    it is emitted as a frontmatter key so ``spark check``'s fidelity gate can
    independently re-verify the criteria against the issue. When None the key
    is omitted entirely (hand-authored / legacy items).

    The body carries the issue text verbatim MINUS the issue's own
    frontmatter and the ``Acceptance criteria`` / ``Blocked by`` sections:
    frontmatter is the contract, body is the intent, and criteria live ONLY
    in the frontmatter. FORGE's drain pipes ``item.body`` into the build
    prompt, so the carried intent reaches the builder directly.

    Does NOT copy file paths from the issue (they go stale).
    """
    acceptance = _extract_list_section(issue_text, "Acceptance criteria")
    depends_on = _extract_linked_ids(issue_text, "Blocked by")

    frontmatter: dict = {"id": item_id}
    if source_issue is not None:
        frontmatter["source_issue"] = source_issue
    frontmatter.update({
        "priority": priority,
        "project": project,
        "work_repo": work_repo,
        "depends_on": depends_on,
        "acceptance": acceptance,
    })
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

    carried = _carry_body(issue_text)
    if carried:
        work_item_md += f"\n{carried}\n"

    return work_item_md
