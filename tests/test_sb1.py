"""Tests for SB-1: spark package scaffold and goal parsing."""
import pytest
import spark
import spark.goal
from spark.goal import parse_goal, classify, Goal


def test_import():
    """Acceptance 1: import spark and its dependency.

    Originally checked ``import forge`` (SPARK's declared dependency at SB-1
    time). After OB-1's iron-lib migration, spark no longer imports forge for
    anything — its actual dependency is iron-lib, so that's what this checks
    now. The intent (SPARK's declared dependency actually resolves) is
    unchanged.
    """
    assert spark is not None
    import ironlib
    assert ironlib is not None


SAMPLE_GOAL = """---
type: goal
id: G1
title: "Make it work"
project: iron-ai-assistant
objective: "Build spark package"
status: proposed
created: 2025-01-15
---

## Intent
Make the assistant useful.

## Context
The forge factory builds work items.

## Constraints
Must not break forge.
"""


def test_parse_goal():
    """Acceptance 2: parse a goal record correctly."""
    goal = parse_goal(SAMPLE_GOAL)
    assert goal is not None
    assert goal.type == "goal"
    assert goal.id == "G1"
    assert goal.title == "Make it work"
    assert goal.project == "iron-ai-assistant"
    assert goal.objective == "Build spark package"
    assert goal.status == "proposed"
    assert goal.created == "2025-01-15"
    assert goal.intent.strip() == "Make the assistant useful."
    assert goal.context.strip() == "The forge factory builds work items."
    assert goal.constraints.strip() == "Must not break forge."


WORK_ITEM = """---
id: WI-1
priority: p1
project: test
acceptance:
  - "import spark works"
---

# Work item
"""

BLOCKER = """---
id: B-1
priority: p1
project: test
---
<!-- BLOCKER REPORT
Something went wrong
-->
"""


def test_classify_goal():
    """Acceptance 3a: classify returns 'goal' for type: goal."""
    assert classify(SAMPLE_GOAL) == "goal"


def test_classify_bounce():
    """Acceptance 3b: classify returns 'bounce' for blocker."""
    assert classify(BLOCKER) == "bounce"


def test_classify_workitem():
    """Acceptance 3c: classify returns 'workitem' for work item with acceptance."""
    assert classify(WORK_ITEM) == "workitem"
