"""SPARK's acceptance-executability linter.

Relocated into ironlib (2026-07-08, OB-1) and consolidated with forge's
independently-hardened copy — the two had drifted (forge's stripped
backtick/quoted spans before vibe-checking and dropped 'correct'/'clean' from
the denylist; this copy had neither). One implementation now, in
``ironlib.executability``; this module re-exports it under SPARK's existing
names so ``spark/cli.py`` and ``tests/test_sb2.py`` needed no changes.
"""

from ironlib.executability import check_criterion, check_item

__all__ = ["check_criterion", "check_item"]
