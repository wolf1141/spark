"""Goal-record parsing and queue-item discrimination.

Parses goal markdown files with YAML frontmatter and body sections
(Intent, Context, Constraints). Provides classify() to distinguish
goal records, bounce reports, and work items.
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class Goal:
    type: str = ""
    id: str = ""
    title: str = ""
    project: str = ""
    objective: str = ""
    status: str = ""
    created: str = ""
    intent: str = ""
    context: str = ""
    constraints: str = ""


def parse_goal(text: str, source_path: str = "") -> Optional[Goal]:
    """Parse a goal record from a markdown string with YAML frontmatter."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
    if not m:
        return None
    yaml_block = m.group(1)
    body = m.group(2).strip()
    lines = yaml_block.splitlines()
    fields: dict[str, str] = {}
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        kv = re.match(r"^([\w_-]+)\s*:\s*(.*)", ln)
        if kv:
            k = kv.group(1)
            v = kv.group(2).strip().strip('"').strip("'")
            fields[k] = v

    # Extract body sections: Intent, Context, Constraints
    sections = {"intent": "", "context": "", "constraints": ""}
    pat = re.compile(
        r"^##\s+(Intent|Context|Constraints)\s*\n(.*?)(?=^##\s+(?:Intent|Context|Constraints)\s*\n|\Z)",
        re.DOTALL | re.MULTILINE,
    )
    for match in pat.finditer(body):
        heading = match.group(1).lower()
        content = match.group(2).strip()
        sections[heading] = content

    return Goal(
        type=fields.get("type", ""),
        id=fields.get("id", ""),
        title=fields.get("title", ""),
        project=fields.get("project", ""),
        objective=fields.get("objective", ""),
        status=fields.get("status", ""),
        created=fields.get("created", ""),
        intent=sections.get("intent", ""),
        context=sections.get("context", ""),
        constraints=sections.get("constraints", ""),
    )


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
