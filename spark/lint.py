
"""SPARK heuristic linter for non-machine-checkable acceptance criteria.
Pure functions, no I/O.
"""

import re
from typing import Dict, List, Optional

VIBE_DENYLIST = [
    'gracefully', 'properly', 'well', 'cleanly', 'robust',
    'nice', 'good', 'appropriate', 'user-friendly', 'seamless',
    'intuitive', 'efficient'
]

CHECKABLE_VERBS = [
    'returns', 'exists', 'passes', 'fails', 'refuses',
    'raises', 'equals', 'imports', 'prints', 'writes', 'matches'
]

WAIVER_SUFFIX = '[waived: promotion-review]'


def check_criterion(text: str) -> List[str]:
    """Flag a criterion that is non-machine-checkable.
    Returns list of flag strings; empty if the criterion looks checkable.
    """
    if text.strip().endswith(WAIVER_SUFFIX):
        return []

    flags = []
    lower = text.lower()

    # 1) Vibe-word check
    for word in VIBE_DENYLIST:
        if word in lower:
            flags.append(f"vibe-word: '{word}'")

    # 2) Structure check: must contain a checkable verb (whole-word)
    if not any(re.search(r'\b' + re.escape(v) + r'\b', lower) for v in CHECKABLE_VERBS):
        flags.append("no checkable structure")

    return flags


def check_item(work_item: dict) -> Dict[str, List[str]]:
    """Aggregate over a work item's acceptance criteria."""
    criteria = work_item.get('acceptance', [])
    if isinstance(criteria, dict):
        criteria = list(criteria.values())  # support dict of criteria
    result = {}
    for i, criterion in enumerate(criteria):
        # key by index if list, or by original if dict handled above
        result[str(i)] = check_criterion(criterion)
    return result
