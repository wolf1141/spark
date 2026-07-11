# Repo Agent Protocol

## Federal IRON Authority

- IRON vault: `C:\Users\Elijah\Documents\IRON Brain`
- Project page: `Projects/iron-ai-assistant/readme.md`
- Governing decisions: `Projects/iron-ai-assistant/decisions/2026-07-spark-as-planning-stage.md`, `2026-07-spark-intake-and-interaction-contract.md`, `2026-07-spark-bridge-loss-contract.md`
- IRON `Control/` governs identity, values, security/privacy, protected decisions, and Wolf-specific authority.
- This repo governs code, tests, dependencies, architecture, and local workflow.
- If this repo conflicts with IRON `Control/`, IRON `Control/` wins.

## Shared Coding Standard

Keep the surface small, build deep modules, load context just in time, work in vertical slices, verify before claiming done, respect blast radius, and write durable decisions only when they matter.

Full standard: `C:\Users\Elijah\Documents\IRON Brain\Knowledge\Engineering\coding-agent-standards.md`

Load the full standard only when the task is architectural, ambiguous, risky, or explicitly about standards.

## Local Repo Rules

- Stack: Python 3.14; depends on `iron-lib` (editable install from `IRON Workspaces/iron-lib`) plus `PyYAML`. Nothing else.
- Install: `pip install -e .`
- Run: `python -m spark.cli <check|deposit|queue|replan>` — from the vault root (relative `source_issue` paths resolve against cwd).
- Test: `python -m pytest tests/ -q`
- **No model calls, no RLM, no network — ever.** This package is the deterministic shell of a judgment-heavy stage; the judgment lives in the vault's `spark-plan` skill, not here. Adding planning logic here violates a locked decision.
- Tests use temp dirs only. Never touch the vault's live queues (`Working/forge-queue`, `Working/spark-queue`, `Working/spark-drafts`).
- Shared logic (used by ≥2 of `forge`/`spark`/`ore`) moves to `iron-lib`. Never import `forge` or `ore` directly.

## Architecture

- `goal.py` — goal-record parse + queue-item discrimination (goal / bounce / workitem).
- `lint.py` — thin re-export of `ironlib.executability` (keep it thin; the linter itself lives in iron-lib).
- `graph.py` — DAG gate: cycles, dangling deps, rootless sets, duplicate ids.
- `bridge.py` — issue → work-item translation. Carries the issue body minus its frontmatter and the two extracted sections; criteria live only in frontmatter; stamps `source_issue:`.
- `fidelity.py` — independent re-extraction of the source issue's criteria + comparison. **Its parser must never share code with `bridge._extract_list_section`** — the independence is the gate's entire value (a shared bug corrupts both sides identically and the comparison passes; vault issue 036 is the proof). Deduplicating them is not a cleanup, it is a regression.
- `cli.py` — command dispatch and file moves only. `deposit` re-runs the full check and moves only the exact files that parsed and passed; deposit is batch-atomic.
- Invariant: a staged work item is a pure function of its source issue. Fixes go into the issue, then re-bridge. There is no fidelity waiver by design.

## Verification Standard

Full pytest green before claiming done (44 tests as of 2026-07-11). Gate changes need a regression test demonstrating the failure they close — follow the pattern in `tests/test_fidelity.py` (which recreates the 036-class corruption) and the H1–H3/M3 tests in `tests/test_sb4.py`.
