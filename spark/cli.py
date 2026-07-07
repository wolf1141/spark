"""SPARK CLI — the deterministic shell for check, deposit, and queue.

Commands:
    spark check <draft-dir>       — lint + graph-gate a batch
    spark deposit <goal-id>       — check → move to forge-queue
    spark queue <spark-queue-dir> — list items grouped by type
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from spark.goal import classify
from spark.lint import check_item
from spark.graph import validate as graph_validate
from forge.work_item import load_all


def _exit_err(*args) -> None:
    print(*args, file=sys.stderr)
    raise SystemExit(1)


def cmd_check(draft_dir: str, forge_queue: str | None = None) -> int:
    """Parse batch, run linter + graph gate. Exit 0 iff clean.

    ``forge_queue`` is unused but accepted for interface compatibility.
    """
    items = load_all(draft_dir)
    if not items:
        print("SKIP: no items in", draft_dir)
        return 0

    errors: list[str] = []

    # Lint each item's acceptance criteria
    for item in items:
        flags = check_item({"acceptance": item.acceptance})
        for idx_str, flag_list in flags.items():
            for flag in flag_list:
                errors.append(f"{item.id} criterion {int(idx_str) + 1}: {flag}")

    # Graph validation
    graph_errors = graph_validate(items)
    for ge in graph_errors:
        errors.append(ge)

    if errors:
        for e in errors:
            print(e)
        return 1
    return 0


def cmd_deposit(goal_id: str, drafts_dir: str, forge_queue: str) -> int:
    """Check drafts_dir, then move .md files to forge_queue if clean."""
    # Run check first
    exit_code = cmd_check(drafts_dir, forge_queue)
    if exit_code != 0:
        print("deposit refused: check failed", file=sys.stderr)
        return 1

    draft_path = Path(drafts_dir)
    queue_path = Path(forge_queue)
    queue_path.mkdir(parents=True, exist_ok=True)

    md_files = list(draft_path.glob("*.md"))
    if not md_files:
        print("nothing to deposit", file=sys.stderr)
        return 1

    for src in md_files:
        dst = queue_path / src.name
        src.rename(dst)

    # Remove empty drafts dir
    try:
        remaining = list(draft_path.iterdir())
        if not remaining:
            draft_path.rmdir()
    except OSError:
        pass

    print(f"deposited {len(md_files)} item(s) from {goal_id} → forge-queue")
    return 0


def _parse_yaml_field(text: str, field: str) -> str | None:
    """Quick YAML frontmatter field extraction."""
    import re
    m = re.search(rf"^{re.escape(field)}\s*:\s*(.+?)\s*$", text, re.MULTILINE)
    return m.group(1).strip().strip('"').strip("'") if m else None


def cmd_queue(spark_queue_dir: str) -> int:
    """List spark-queue items grouped: Goals / Bounces / Escalated."""
    qpath = Path(spark_queue_dir)
    if not qpath.is_dir():
        print("spark-queue is empty")
        return 0

    goals: list[str] = []
    bounces: list[str] = []
    escalated: list[str] = []

    for md_file in sorted(qpath.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        kind = classify(text)
        status = _parse_yaml_field(text, "status") or ""
        name = md_file.name

        if status == "escalated":
            escalated.append(name)
        elif kind == "goal":
            goals.append(name)
        elif kind == "bounce":
            # Check replan count for escalation boundary
            replan_str = _parse_yaml_field(text, "replan_count")
            replan = int(replan_str) if replan_str else 0
            if replan >= 2:
                escalated.append(name)
            else:
                bounces.append(name)
        else:
            bounces.append(name)

    if goals:
        print("Goals:")
        for g in goals:
            print(f"  {g}")
    if bounces:
        print("Bounces:")
        for b in bounces:
            print(f"  {b}")
    if escalated:
        print("Escalated:")
        for e in escalated:
            print(f"  {e}")
    if not goals and not bounces and not escalated:
        print("spark-queue is empty")

    return 0


def cmd_replan(md_path: str) -> int:
    """Handle a bounced item: increment replan_count or escalate at limit."""
    import re

    path = Path(md_path)
    if not path.is_file():
        _exit_err(f"not found: {md_path}")

    text = path.read_text(encoding="utf-8")

    # Read current replan_count
    m = re.search(r"^replan_count\s*:\s*(\d+)", text, re.MULTILINE)
    current = int(m.group(1)) if m else 0

    if current >= 2:
        # Escalate: set status and leave in queue (no forge-queue write)
        if "status: escalated" not in text:
            text = re.sub(
                r"(^status\s*:\s*)(\S+)",
                r"\1escalated",
                text,
                count=1,
                flags=re.MULTILINE,
            )
            path.write_text(text, encoding="utf-8")
        print(f"escalated: {path.name} (replan_count={current}) — needs Wolf")
        return 0

    # Increment replan_count
    new_count = current + 1
    if m:
        text = re.sub(
            rf"^replan_count\s*:\s*{current}",
            f"replan_count: {new_count}",
            text,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        # Insert after the first frontmatter field
        text = re.sub(
            r"(^---\s*\n)",
            f"\\1replan_count: {new_count}\n",
            text,
            count=1,
        )
    path.write_text(text, encoding="utf-8")
    print(f"replan_count: {current} → {new_count} ({path.name})")
    return 0


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        print("usage: spark <check|deposit|queue|replan> [args...]", file=sys.stderr)
        return 2

    cmd = argv[0]
    args = argv[1:]

    if cmd == "check":
        if len(args) < 1:
            _exit_err("usage: spark check <draft-dir>")
        return cmd_check(args[0])

    if cmd == "deposit":
        if len(args) < 3:
            _exit_err("usage: spark deposit <goal-id> <drafts-dir> <forge-queue>")
        return cmd_deposit(args[0], args[1], args[2])

    if cmd == "queue":
        if len(args) < 1:
            _exit_err("usage: spark queue <spark-queue-dir>")
        return cmd_queue(args[0])

    if cmd == "replan":
        if len(args) < 1:
            _exit_err("usage: spark replan <item.md>")
        return cmd_replan(args[0])

    _exit_err(f"unknown command: {cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
