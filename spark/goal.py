"""Goal-record parsing and queue-item discrimination.

Parses goal markdown files with YAML frontmatter and body sections
(Intent, Context, Constraints). Provides classify() to distinguish
goal records, bounce reports, and work items.
"""

import re

from ironlib.goal import Goal, parse_goal


def classify(text: str) -> str:
    """Classify a markdown text as 'goal', 'bounce', or 'workitem'.

    Rules:
    - Contains ``<!-- BLOCKER REPORT`` → 'bounce'
    - Frontmatter with ``type: goal`` → 'goal'
    - Frontmatter with ``acceptance`` → 'workitem'
    """
    if "<!-- BLOCKER REPORT" in text:
        return "bounce"
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if m:
        yaml_block = m.group(1)
        if re.search(r"^type\s*:\s*goal\s*$", yaml_block, re.MULTILINE):
            return "goal"
        if re.search(r"^acceptance\s*:", yaml_block, re.MULTILINE):
            return "workitem"
    # If no frontmatter or no matching key, default to workitem (as acceptance is common)
    return "workitem"
