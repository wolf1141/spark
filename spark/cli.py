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
from ironlib.work_item import load_all, validate as validate_item


def _exit_err(*args) -> None:
    print(*args, file=sys.stderr)
    raise SystemExit(1)


def _norm(p) -> str:
    """Normalized absolute path for cross-referencing globbed vs parsed files."""
    return os.path.normcase(os.path.abspath(str(p)))


def cmd_check(draft_dir: str, forge_queue: str | None = None) -> int:
    """Parse batch, run schema + linter + graph gate. Exit 0 iff clean.

    ``forge_queue`` is unused but accepted for interface compatibility.
    """
    items = load_all(draft_dir)
    md_files = sorted(Path(draft_dir).glob("*.md"))
    if not items and not md_files:
        print("SKIP: no items in", draft_dir)
        return 0

    errors: list[str] = []

    # Any .md file that load_all could not turn into a work item (no
    # frontmatter fence at all) is silently dropped by the parser — flag it
    # here so it can never ride a clean batch into forge-queue via deposit.
    parsed_paths = {_norm(it.source_path) for it in items if it.source_path}
    for md in md_files:
        if _norm(md) not in parsed_paths:
            errors.append(f"{md.name}: cannot parse frontmatter (no work item)")

    # Schema + lint each parsed item
    for item in items:
        if item.parse_error:
            errors.append(item.parse_error)
            continue
        # Schema gate: id present, acceptance non-empty, priority known.
        # This is the only check that catches empty/absent acceptance.
        schema_err = validate_item(item)
        if schema_err:
            errors.append(schema_err)
            continue
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
    """Check drafts_dir, then move ONLY the gated work-item files to forge_queue.

    ``cmd_check`` fails the whole batch if any ``.md`` in the dir failed to parse
    or failed a gate, so a clean check means every parsed item's file is safe to
    move — deposit moves exactly that set, never a raw glob.
    """
    # Run check first
    exit_code = cmd_check(drafts_dir, forge_queue)
    if exit_code != 0:
        print("deposit refused: check failed", file=sys.stderr)
        return 1

    draft_path = Path(drafts_dir)
    queue_path = Path(forge_queue)

    # Move only the exact files that parsed and passed check.
    items = load_all(drafts_dir)
    src_files = [Path(it.source_path) for it in items if it.source_path]
    if not src_files:
        print("nothing to deposit", file=sys.stderr)
        return 1

    queue_path.mkdir(parents=True, exist_ok=True)
    for src in src_files:
        dst = queue_path / src.name
        src.rename(dst)

    # Remove empty drafts dir
    try:
        remaining = list(draft_path.iterdir())
        if not remaining:
            draft_path.rmdir()
    except OSError:
        pass

    print(f"deposited {len(src_files)} item(s) from {goal_id} to forge-queue")
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

    # Isolate the frontmatter block so replan_count/status only ever match the
    # fenced YAML, never a stray line in the body (L4).
    fm = re.match(r"(?s)\A(---\s*\n)(.*?\n)(---\s*\n?)", text)
    if fm:
        head, block, fence = fm.group(1), fm.group(2), fm.group(3)
        tail = text[fm.end():]
    else:
        head, block, fence, tail = "", "", "", text

    # Read current replan_count from the frontmatter only
    m = re.search(r"^replan_count\s*:\s*(\d+)", block, re.MULTILINE)
    current = int(m.group(1)) if m else 0

    if current >= 2:
        # Escalate: set status and leave in queue (no forge-queue write).
        sm = re.search(r"^status\s*:\s*(\S+)", block, re.MULTILINE)
        wrote = False
        if sm:
            if sm.group(1) != "escalated":
                block = re.sub(
                    r"^(status\s*:\s*)\S+",
                    r"\1escalated",
                    block,
                    count=1,
                    flags=re.MULTILINE,
                )
                wrote = True
        else:
            # No status field — insert one (mirror the replan_count insert below)
            block = f"status: escalated\n{block}"
            wrote = True

        if wrote:
            path.write_text(head + block + fence + tail, encoding="utf-8")
            print(f"escalated: {path.name} (replan_count={current}) — needs Wolf")
        else:
            print(f"already escalated: {path.name} (replan_count={current}) — needs Wolf")
        return 0

    # Increment replan_count
    new_count = current + 1
    if m:
        block = re.sub(
            rf"^replan_count\s*:\s*{current}",
            f"replan_count: {new_count}",
            block,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        # Insert as the first frontmatter field
        block = f"replan_count: {new_count}\n{block}"
    path.write_text(head + block + fence + tail, encoding="utf-8")
    print(f"replan_count: {current} -> {new_count} ({path.name})")
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
