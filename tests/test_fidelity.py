"""Bridge body-carry + fidelity gate tests (2026-07-10 audit finding C / 036).

All paths are tmp dirs; the vault's live queues are never touched.
"""

import textwrap
import tempfile
from pathlib import Path

import spark.cli as cli
from spark.bridge import issue_to_workitem
from ironlib.work_item import parse_file, validate


ISSUE_TEXT = """---
type: project
status: active
project: iron-ai-assistant
---

# 099 — TF-1: Test fixture issue

## What to build

The fixture package's data layer: a parser so a human-editable file
becomes typed records.

## Acceptance criteria

- Named test `test_window_basic` passes: with `today=2026-02-20` and
  window_days=14 the registry returns the occasion within the window.
- `parse_registry` raises `RegistryError` on an entry with `month: 13`

## Blocked by

- None — can start immediately.

## Implementation notes

Use tempfile for isolation. Keep the parser pure.
"""


def _write(dir_path, filename: str, content: str) -> Path:
    path = Path(dir_path) / filename
    path.write_text(content, encoding="utf-8")
    return path


def _bridge(issue_text: str, item_id: str = "TF-1", **kwargs) -> str:
    return textwrap.dedent(issue_to_workitem(
        issue_text, item_id=item_id, priority="p2", project="test", **kwargs
    ))


# -- Part A: body carry ------------------------------------------------------

class TestBodyCarry:
    def test_body_carries_intent_minus_extracted_sections(self):
        md = _bridge(ISSUE_TEXT)
        # Intent text is carried
        assert "## What to build" in md
        assert "becomes typed records" in md
        assert "## Implementation notes" in md
        assert "Keep the parser pure" in md
        assert "# 099" in md  # title line carried
        # Extracted sections and issue frontmatter are NOT in the body
        assert "## Acceptance criteria" not in md
        assert "## Blocked by" not in md
        assert "can start immediately" not in md
        assert "type: project" not in md
        assert "status: active" not in md

    def test_body_roundtrips_with_hr_and_backticks(self):
        issue = ISSUE_TEXT + """
## Constraints

Some prose above a horizontal rule.

---

Code fence below:

```python
x = "---"
```
"""
        md = _bridge(issue, item_id="TF-HR")
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "hr_item.md", md)
            item = parse_file(str(path))
        assert item is not None and item.parse_error is None
        assert item.id == "TF-HR"
        assert len(item.acceptance) == 2
        assert validate(item) is None
        assert "---" in item.body
        assert 'x = "---"' in item.body
        assert "Some prose above a horizontal rule." in item.body

    def test_source_issue_emitted_when_passed(self):
        md = _bridge(ISSUE_TEXT, source_issue="Projects/x/dev/issues/099-tf-1.md")
        assert "source_issue: Projects/x/dev/issues/099-tf-1.md" in md
        # still parses; ironlib ignores the unknown key
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "si_item.md", md)
            item = parse_file(str(path))
        assert item is not None and validate(item) is None

    def test_source_issue_absent_when_not_passed(self):
        md = _bridge(ISSUE_TEXT)
        assert "source_issue" not in md


# -- Part B: fidelity gate ---------------------------------------------------

def _stage(tmp_path, issue_text: str, staged_md: str | None = None,
           issue_name: str = "issue.md"):
    """Write issue + staged item under tmp_path; return (drafts, issue_path)."""
    issue_path = _write(tmp_path, issue_name, issue_text)
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    if staged_md is None:
        staged_md = _bridge(issue_text, source_issue=issue_name)
    _write(drafts, "item.md", staged_md)
    return drafts, issue_path


class TestFidelityGate:
    def test_fidelity_pass_with_wrapped_criteria(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        drafts, _ = _stage(tmp_path, ISSUE_TEXT)
        assert cli.cmd_check(str(drafts)) == 0

    def test_fidelity_catches_staged_side_corruption(self, tmp_path,
                                                     monkeypatch, capsys):
        # 036-class regression: bridge a DOCTORED issue (wrapped continuation
        # dropped, as the old bug did) but point source_issue at the REAL
        # issue file — the staged item differs from its source exactly as a
        # bridge bug would produce.
        monkeypatch.chdir(tmp_path)
        doctored = ISSUE_TEXT.replace(
            "- Named test `test_window_basic` passes: with `today=2026-02-20` and\n"
            "  window_days=14 the registry returns the occasion within the window.",
            "- Named test `test_window_basic` passes: with `today=2026-02-20` and",
        )
        staged_md = _bridge(doctored, source_issue="issue.md")
        drafts, _ = _stage(tmp_path, ISSUE_TEXT, staged_md=staged_md)
        assert cli.cmd_check(str(drafts)) != 0
        out = capsys.readouterr().out
        assert "TF-1 fidelity: criterion 1 differs" in out
        assert "test_window_basic" in out

    def test_fidelity_catches_issue_side_drift(self, tmp_path,
                                               monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        drafts, issue_path = _stage(tmp_path, ISSUE_TEXT)
        # Edit the issue's criteria AFTER bridging
        drifted = ISSUE_TEXT.replace("month: 13", "month: 14")
        issue_path.write_text(drifted, encoding="utf-8")
        assert cli.cmd_check(str(drafts)) != 0
        out = capsys.readouterr().out
        assert "TF-1 fidelity: criterion 2 differs" in out

    def test_fidelity_catches_count_mismatch(self, tmp_path,
                                             monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        drafts, issue_path = _stage(tmp_path, ISSUE_TEXT)
        drifted = ISSUE_TEXT.replace(
            "## Blocked by",
            "- A brand-new third criterion `t()` passes\n\n## Blocked by",
        )
        issue_path.write_text(drifted, encoding="utf-8")
        assert cli.cmd_check(str(drafts)) != 0
        out = capsys.readouterr().out
        assert "TF-1 fidelity: criterion count mismatch: staged 2 vs source 3" in out

    def test_missing_source_issue_file_fails(self, tmp_path,
                                             monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        staged_md = _bridge(ISSUE_TEXT, source_issue="gone/issue.md")
        drafts = tmp_path / "drafts"
        drafts.mkdir()
        _write(drafts, "item.md", staged_md)
        assert cli.cmd_check(str(drafts)) != 0
        out = capsys.readouterr().out
        assert "TF-1: source issue not found: gone/issue.md" in out

    def test_no_source_issue_key_skips_fidelity(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        staged_md = _bridge(ISSUE_TEXT)  # no source_issue
        drafts = tmp_path / "drafts"
        drafts.mkdir()
        _write(drafts, "item.md", staged_md)
        assert cli.cmd_check(str(drafts)) == 0

    def test_deposit_refuses_on_fidelity_failure(self, tmp_path,
                                                 monkeypatch):
        monkeypatch.chdir(tmp_path)
        staged_md = _bridge(ISSUE_TEXT, source_issue="gone/issue.md")
        drafts = tmp_path / "drafts"
        drafts.mkdir()
        _write(drafts, "item.md", staged_md)
        queue = tmp_path / "queue"
        queue.mkdir()
        assert cli.cmd_deposit("goal-1", str(drafts), str(queue)) != 0
        assert not list(queue.glob("*.md"))
        assert (drafts / "item.md").exists()
