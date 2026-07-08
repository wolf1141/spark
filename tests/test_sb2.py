
"""Tests for spark.lint - SB-2 acceptance-executability linter."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from spark.lint import check_criterion, check_item


def test_vibe_word_flag():
    """Acceptance criterion 1: vibe-word triggers flag."""
    flags = check_criterion('handles errors gracefully')
    assert len(flags) > 0, "Expected non-empty flag list for vibe-word criterion"
    assert any('vibe' in f for f in flags), f"Flags should cite vibe-word: {flags}"


def test_clean_pass():
    """Acceptance criterion 2: checkable criterion returns empty flags."""
    flags = check_criterion("hello() returns 'hi'")
    assert flags == [], f"Expected empty flags for checkable criterion, got: {flags}"


def test_waiver_honored():
    """Acceptance criterion 3: waiver escapes flags."""
    flags = check_criterion('subjective copy reads naturally [waived: promotion-review]')
    assert flags == [], f"Expected empty flags for waived criterion, got: {flags}"


def test_structure_miss():
    """Additional: structure miss (no checkable verb) triggers flag."""
    flags = check_criterion('the system should behave well')
    # This should have both vibe-word ('well') and no checkable verb
    assert len(flags) > 0, "Expected non-empty flags for structure miss"
    assert any('no checkable verb' in f for f in flags), f"Should flag structure miss: {flags}"
