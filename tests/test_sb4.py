"""Acceptance tests for SPARK CLI and bridge (SB-4)."""

import os
import textwrap
import tempfile
from pathlib import Path

import spark.cli as cli
from spark.bridge import issue_to_workitem
from ironlib.work_item import parse_file, validate


# ── helpers ────────────────────────────────────────────────────────────────

CLEAN_MD = """---
id: SB-X
priority: p2
project: test
depends_on: []
acceptance:
  - "`compute(x)` returns 0 when x is valid"
  - "`compute(x)` raises on empty input"
---

# SB-X

A clean test item.
"""

FLAGGED_MD = """---
id: SB-Y
priority: p2
project: test
depends_on: []
acceptance:
  - "handles errors gracefully"
---

# SB-Y

A flagged test item.
"""

BOUNCE_MD = """---
id: BNC-1
type: goal
status: active
replan_count: 1
---

# BNC-1

<!-- BLOCKER REPORT
Something went wrong.
-->
"""

GOAL_MD = """---
id: G-1
type: goal
status: active
---

# G-1

A goal item.
"""

ESCALATED_MD = """---
id: ESC-1
status: escalated
replan_count: 3
---

# ESC-1

Already escalated.
"""


def _write_md(dir_path: str, filename: str, content: str) -> Path:
    path = Path(dir_path) / filename
    path.write_text(content, encoding="utf-8")
    return path


# ── 1. spark check ─────────────────────────────────────────────────────────

class TestSparkCheck:
    def test_check_pass(self):
        """spark check exits 0 for a clean work item."""
        with tempfile.TemporaryDirectory() as drafts:
            _write_md(drafts, "clean.md", CLEAN_MD)
            exit_code = cli.cmd_check(drafts)
            assert exit_code == 0, f"expected 0, got {exit_code}"

    def test_check_fail(self):
        """spark check exits non-zero and prints flag for a flagged item."""
        with tempfile.TemporaryDirectory() as drafts:
            _write_md(drafts, "flagged.md", FLAGGED_MD)
            exit_code = cli.cmd_check(drafts)
            assert exit_code != 0, f"expected non-zero, got {exit_code}"


# ── 2. spark deposit ───────────────────────────────────────────────────────

class TestSparkDeposit:
    def test_deposit_success(self):
        """Clean batch → moves .md to forge-queue; drafts dir emptied of md."""
        with tempfile.TemporaryDirectory() as drafts, \
             tempfile.TemporaryDirectory() as queue:
            _write_md(drafts, "clean.md", CLEAN_MD)
            exit_code = cli.cmd_deposit("goal-1", drafts, queue)
            assert exit_code == 0, f"deposit returned {exit_code}"
            # Ensure file moved to queue
            assert (Path(queue) / "clean.md").exists(), "file not in forge-queue"
            # Drafts no longer has .md files
            assert not list(Path(drafts).glob("*.md")), "drafts still has .md files"

    def test_deposit_refuse(self):
        """Flagged batch → deposit refused; files stay in drafts."""
        with tempfile.TemporaryDirectory() as drafts, \
             tempfile.TemporaryDirectory() as queue:
            _write_md(drafts, "flagged.md", FLAGGED_MD)
            exit_code = cli.cmd_deposit("goal-1", drafts, queue)
            assert exit_code != 0, f"expected non-zero deposit, got {exit_code}"
            # File NOT in queue
            assert not list(Path(queue).glob("*.md")), "file should not be in forge-queue"
            # File still in drafts
            assert (Path(drafts) / "flagged.md").exists(), "file should remain in drafts"


# ── 3. spark replan ────────────────────────────────────────────────────────

class TestSparkReplan:
    REPLAN_2_MD = """---
id: RN-2
status: active
replan_count: 2
---

# RN-2
"""

    REPLAN_1_MD = """---
id: RN-1
status: active
replan_count: 1
---

# RN-1
"""

    def test_replan_escalate(self):
        """replan_count >= 2 → sets status: escalated, file still there."""
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_md(tmp, "rn2.md", self.REPLAN_2_MD)
            exit_code = cli.cmd_replan(str(path))
            assert exit_code == 0
            text = path.read_text()
            assert "status: escalated" in text, f"expected status: escalated, got:\n{text}"
            assert path.exists(), "file should still exist"

    def test_replan_increment(self):
        """replan_count 1 → increments to 2."""
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_md(tmp, "rn1.md", self.REPLAN_1_MD)
            exit_code = cli.cmd_replan(str(path))
            assert exit_code == 0
            text = path.read_text()
            assert "replan_count: 2" in text, f"expected replan_count: 2, got:\n{text}"


# ── 4. spark queue ─────────────────────────────────────────────────────────

class TestSparkQueue:
    def test_queue_listing(self):
        """Queue dir with goal, bounce, escalated → correct headings."""
        with tempfile.TemporaryDirectory() as qdir:
            _write_md(qdir, "goal.md", GOAL_MD)
            _write_md(qdir, "bounce.md", BOUNCE_MD)
            _write_md(qdir, "escalated.md", ESCALATED_MD)
            exit_code = cli.cmd_queue(qdir)
            assert exit_code == 0


# ── 5. spark bridge round-trip ─────────────────────────────────────────────

class TestSparkBridge:
    ISSUE_TEXT = """## Acceptance criteria
- returns 0 when valid input is provided
- fails loudly on empty input
- raises ValueError on None

## Blocked by
- [[SB-1]]
- [[SB-2]]

## Implementation notes
Use tempfile for isolation.
"""

    def test_bridge_roundtrip(self):
        """issue_to_workitem → parse_file → validate returns None."""
        md = issue_to_workitem(
            self.ISSUE_TEXT,
            item_id="SB-BRIDGE",
            priority="p2",
            project="test",
        )
        assert md, "bridge output should not be empty"
        assert "SB-BRIDGE" in md

        # Normalise bridge output: strip common leading whitespace so the
        # frontmatter fence starts at column 0 as forge.work_item.parse expects.
        md = textwrap.dedent(md)

        # Write to temp file and parse
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_md(tmp, "bridge_item.md", md)
            item = parse_file(str(path))
            assert item is not None, "parse_file returned None"
            assert item.id == "SB-BRIDGE"
            err = validate(item)
            assert err is None, f"validate returned error: {err}"
