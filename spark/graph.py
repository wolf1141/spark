"""Graph validation for dependency graphs."""

from ironlib.work_item import WorkItem
from ironlib.scheduler import detect_cycles


def validate(items: list[WorkItem]) -> list[str]:
    """Validate dependency graph of a batch of WorkItems.

    Returns a list of error strings. An empty list means the graph is valid.
    """
    errors: list[str] = []

    # Duplicate ids — a set would silently collapse them, aliasing completions
    # and the cycle map. Flag each colliding id once.
    seen: set[str] = set()
    reported: set[str] = set()
    for item in items:
        if item.id in seen and item.id not in reported:
            errors.append(f"Duplicate id: '{item.id}' appears more than once in the batch.")
            reported.add(item.id)
        seen.add(item.id)
    ids = seen

    # Dangling dependencies
    for item in items:
        for dep in item.depends_on:
            if dep not in ids:
                errors.append(
                    f"Dangling dependency: '{item.id}' depends on '{dep}'"
                    " which is not in the batch."
                )

    # Cycle detection (reuse ironlib.scheduler.detect_cycles)
    cycles = detect_cycles(items)
    for cycle in cycles:
        errors.append(f"Cycle detected: {cycle}")

    # Rootless graph (every item has at least one dependency)
    if items and all(len(item.depends_on) > 0 for item in items):
        errors.append(
            "Rootless graph: every item has at least one dependency (no root)."
        )

    return errors
