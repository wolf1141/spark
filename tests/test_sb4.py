"""Acceptance tests for SPARK CLI and bridge (SB-4)."""

import io
import os
import sys
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

    def test_check_reports_parse_error_without_crashing(self):
        """038: one malformed frontmatter item is reported; the other is checked."""
        BAD_MD = """---
id: bad
acceptance: ["unclosed quote
---

# bad
"""
        with tempfile.TemporaryDirectory() as drafts:
            _write_md(drafts, "clean.md", CLEAN_MD)
            _write_md(drafts, "bad.md", BAD_MD)
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

    def test_deposit_success_cp1252_safe(self):
        """035: deposit exits 0 even when stdout uses a lossy cp1252 encoding."""
        with tempfile.TemporaryDirectory() as drafts, \
             tempfile.TemporaryDirectory() as queue:
            _write_md(drafts, "clean.md", CLEAN_MD)
            old_stdout = sys.stdout
            # Simulate a cp1252 Windows console that cannot encode every glyph.
            sys.stdout = io.TextIOWrapper(
                io.BytesIO(), encoding="cp1252", errors="strict"
            )
            try:
                exit_code = cli.cmd_deposit("goal-1", drafts, queue)
            finally:
                sys.stdout = old_stdout
            assert exit_code == 0, f"expected 0, got {exit_code}"
            assert (Path(queue) / "clean.md").exists(), "file not in forge-queue"


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

    WRAPPED_ISSUE = """## Acceptance criteria
- Named test `test_window_basic` passes: with `today=2026-02-20` and
  window_days=14 the registry returns the occasion within the window.
- Another criterion.

## Blocked by
- [[SB-1]] continued on the next
  wrapped line
"""

    QUOTED_ISSUE = """## Acceptance criteria
- prints a single "no upcoming occasions" line
- handles empty input
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
        assert "work_repo: crucible" in md

        # Normalise bridge output: strip common leading whitespace so the
        # frontmatter fence starts at column 0 as forge.work_item.parse expects.
        md = textwrap.dedent(md)

        # Write to temp file and parse
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_md(tmp, "bridge_item.md", md)
            item = parse_file(str(path))
            assert item is not None, "parse_file returned None"
            assert item.id == "SB-BRIDGE"
            assert item.work_repo == "crucible"
            err = validate(item)
            assert err is None, f"validate returned error: {err}"

    def test_bridge_work_repo_override(self):
        """issue_to_workitem honours a non-default work_repo."""
        md = issue_to_workitem(
            self.ISSUE_TEXT,
            item_id="SB-ORE",
            priority="p2",
            project="test",
            work_repo="ore",
        )
        assert "work_repo: ore" in md
        md = textwrap.dedent(md)
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_md(tmp, "bridge_item.md", md)
            item = parse_file(str(path))
            assert item is not None
            assert item.work_repo == "ore"

    def test_bridge_keeps_wrapped_bullet_lines(self):
        """036: continuation lines are folded into their parent bullet."""
        md = textwrap.dedent(issue_to_workitem(
            self.WRAPPED_ISSUE,
            item_id="SB-WRAP",
            priority="p2",
            project="test",
        ))
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_md(tmp, "wrap_item.md", md)
            item = parse_file(str(path))
        assert item is not None
        assert len(item.acceptance) == 2
        first = item.acceptance[0]
        assert "window_days=14" in first
        assert "the registry returns" in first
        assert first.startswith("Named test")
        assert item.depends_on == ["SB-1"]

    def test_bridge_quoted_criterion_roundtrips(self):
        """038: criteria containing double quotes produce valid YAML."""
        md = textwrap.dedent(issue_to_workitem(
            self.QUOTED_ISSUE,
            item_id="SB-QUOTE",
            priority="p2",
            project="test",
        ))
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_md(tmp, "quote_item.md", md)
            item = parse_file(str(path))
        assert item is not None
        assert len(item.acceptance) == 2
        assert 'prints a single "no upcoming occasions" line' in item.acceptance


# ── 6. gate-hole regressions (2026-07-10 audit: H1/H2/H3/M3) ─────────────────

EMPTY_ACCEPTANCE_MD = """---
id: SB-EMPTY
priority: p2
project: test
depends_on: []
acceptance: []
---

# SB-EMPTY
"""

NO_ACCEPTANCE_MD = """---
id: SB-NOACC
priority: p2
project: test
depends_on: []
---

# SB-NOACC
"""

JUNK_MD = """this file has no frontmatter fence at all
just some prose that will never parse into a work item
"""


class TestH1AcceptancePresence:
    """H1: empty/absent acceptance must fail `spark check`."""

    def test_empty_acceptance_list_fails_check(self):
        with tempfile.TemporaryDirectory() as drafts:
            _write_md(drafts, "empty.md", EMPTY_ACCEPTANCE_MD)
            assert cli.cmd_check(drafts) != 0

    def test_missing_acceptance_key_fails_check(self):
        with tempfile.TemporaryDirectory() as drafts:
            _write_md(drafts, "noacc.md", NO_ACCEPTANCE_MD)
            assert cli.cmd_check(drafts) != 0


class TestH2DepositOnlyGatedFiles:
    """H2: deposit must never move a file the gate could not inspect."""

    def test_junk_alone_fails_check_and_deposit_naming_it(self, capsys):
        with tempfile.TemporaryDirectory() as drafts, \
             tempfile.TemporaryDirectory() as queue:
            _write_md(drafts, "junk.md", JUNK_MD)

            assert cli.cmd_check(drafts) != 0
            assert "junk.md" in capsys.readouterr().out

            assert cli.cmd_deposit("goal-1", drafts, queue) != 0
            assert "junk.md" in capsys.readouterr().out
            # nothing moved
            assert not list(Path(queue).glob("*.md"))
            assert (Path(drafts) / "junk.md").exists()

    def test_mixed_batch_refuses_and_moves_nothing(self):
        with tempfile.TemporaryDirectory() as drafts, \
             tempfile.TemporaryDirectory() as queue:
            _write_md(drafts, "clean.md", CLEAN_MD)
            _write_md(drafts, "junk.md", JUNK_MD)

            assert cli.cmd_deposit("goal-1", drafts, queue) != 0
            # nothing moved — the valid item must not ride the batch through
            assert not list(Path(queue).glob("*.md"))
            assert (Path(drafts) / "clean.md").exists()
            assert (Path(drafts) / "junk.md").exists()


class TestH3ReplanEscalationAlwaysWrites:
    """H3: escalation must actually write status when the item has none."""

    NO_STATUS_REPLAN_2_MD = """---
id: RN-NS
replan_count: 2
---

# RN-NS

Some body text here.
replan_count: 99
"""

    def test_escalate_inserts_status_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_md(tmp, "rnns.md", self.NO_STATUS_REPLAN_2_MD)
            exit_code = cli.cmd_replan(str(path))
            assert exit_code == 0
            text = path.read_text(encoding="utf-8")
            assert "status: escalated" in text, f"status not inserted:\n{text}"

    BODY_ONLY_REPLAN_MD = """---
id: RN-BODY
status: active
---

# RN-BODY

Some prose.
replan_count: 5
"""

    def test_body_replan_count_line_ignored(self):
        # frontmatter has NO replan_count; a stray `replan_count: 5` sits in the
        # body. Scoped correctly, the frontmatter count reads 0 → increment to 1
        # (NOT escalate off the body's 5), and the body line is left untouched.
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_md(tmp, "rnbody.md", self.BODY_ONLY_REPLAN_MD)
            exit_code = cli.cmd_replan(str(path))
            assert exit_code == 0
            text = path.read_text(encoding="utf-8")
            assert "replan_count: 1" in text, f"frontmatter not incremented:\n{text}"
            assert "status: escalated" not in text, "body line wrongly triggered escalation"
            # the stray body line is untouched, not incremented/consumed
            assert "replan_count: 5" in text


class TestM3DuplicateIds:
    """M3: duplicate item ids must be caught, not set-collapsed."""

    DUP_A = """---
id: SB-DUP
priority: p2
project: test
depends_on: []
acceptance:
  - "`f()` returns 0"
---

# first
"""

    DUP_B = """---
id: SB-DUP
priority: p2
project: test
depends_on: []
acceptance:
  - "`g()` returns 1"
---

# second
"""

    def test_duplicate_ids_fail_check(self, capsys):
        with tempfile.TemporaryDirectory() as drafts:
            _write_md(drafts, "a.md", self.DUP_A)
            _write_md(drafts, "b.md", self.DUP_B)
            assert cli.cmd_check(drafts) != 0
            out = capsys.readouterr().out
            assert "SB-DUP" in out
            assert "Duplicate" in out
