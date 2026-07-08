"""Acceptance tests for spark.graph.validate()."""

from spark.graph import validate
from ironlib.work_item import WorkItem


def make_item(id: str, depends_on: list[str] | None = None) -> WorkItem:
    """Helper to create a WorkItem with minimal fields needed for validation."""
    if depends_on is None:
        depends_on = []
    return WorkItem(
        id=id,
        title=id,
        priority="p2",
        project="test",
        depends_on=depends_on,
    )


class TestAcceptance:
    """Inline test data — no vault reads."""

    def test_cycle(self):
        """AC 1: returns error for a cyclic set."""
        items = [
            make_item("x", depends_on=["y"]),
            make_item("y", depends_on=["x"]),
        ]
        errors = validate(items)
        assert errors, "expected at least one error for a cycle"
        assert any("cycle" in e.lower() for e in errors), "cycle error not found"

    def test_dangling(self):
        """AC 2: returns error for dangling reference."""
        items = [
            make_item("a", depends_on=["b"]),
        ]
        errors = validate(items)
        assert errors
        assert any("dangling" in e.lower() for e in errors)

    def test_rootless(self):
        """AC 3: returns error for a rootless set."""
        items = [
            make_item("a", depends_on=["b"]),
            make_item("b", depends_on=["a"]),
        ]
        errors = validate(items)
        assert errors
        assert any("rootless" in e.lower() for e in errors)

    def test_fb_graph(self):
        """AC 4: no error for FB-1..FB-5 dependency shape."""
        items = [
            make_item("FB-1", depends_on=[]),
            make_item("FB-2", depends_on=[]),
            make_item("FB-3", depends_on=["FB-1"]),
            make_item("FB-4", depends_on=["FB-1", "FB-2", "FB-3"]),
            make_item("FB-5", depends_on=["FB-3", "FB-4"]),
        ]
        errors = validate(items)
        assert not errors, f"FB graph should be valid but got errors: {errors}"
