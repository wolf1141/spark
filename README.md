# spark

The deterministic shell of **SPARK**, IRON's planning stage — the pipeline step upstream of FORGE that turns a researched goal into build-ready work items. This package is deliberately **not** the planner: it holds only the mechanical residue — gates, file moves, and the format bridge. All planning judgment lives in the IRON vault's `spark-plan` skill, run by an agent with Wolf in the loop. If you find yourself adding planning logic, decomposition heuristics, or model calls here, stop — that is out of scope by locked decision.

## IRON Context

This repository is part of the IRON ecosystem. Strategy, vocabulary, and durable decisions live in Wolf's private IRON Brain vault:

- Project home: `Projects/iron-ai-assistant/readme.md`
- What SPARK is (form/identity): `Projects/iron-ai-assistant/decisions/2026-07-spark-as-planning-stage.md`
- Intake + interaction contract: `Projects/iron-ai-assistant/decisions/2026-07-spark-intake-and-interaction-contract.md`
- Bridge loss contract + fidelity gate: `Projects/iron-ai-assistant/decisions/2026-07-spark-bridge-loss-contract.md`
- Build plan: `Projects/iron-ai-assistant/dev/prds/spark-bootstrap.md` (SB-1…SB-6)
- First-principles audit (why the gates look the way they do): `Projects/iron-ai-assistant/dev/audits/2026-07-10-spark-first-principles-audit.md`
- Vocabulary (goal record, bounce, work item, human gate, replan budget): `Projects/iron-ai-assistant/CONTEXT.md`
- The judgment layer: `.claude/skills/spark-plan/SKILL.md` (in the vault)

This repo exists (rather than the shell living in the vault) for a tooling reason only: FORGE's builder refuses vault paths, so the shell had to be FORGE-buildable in its own repo.

## What's here

- `spark.goal` — goal-record parsing (`parse_goal`) and queue-item discrimination (`classify`: goal / bounce / workitem).
- `spark.lint` — re-export of `ironlib.executability`, the acceptance-criterion executability linter (vibe-word denylist + checkable-verb/anchor gates).
- `spark.graph` — dependency-graph gate: cycles, dangling `depends_on`, rootless sets, duplicate ids.
- `spark.bridge` — the format bridge: a `to-tickets` prose issue → a FORGE work-item `.md`. Carries the issue body (minus its frontmatter and the extracted `## Acceptance criteria` / `## Blocked by` sections) so FORGE's builder sees planner intent; criteria live **only** in frontmatter; stamps `source_issue:` for the fidelity gate.
- `spark.fidelity` — the independent fidelity gate: re-extracts the source issue's criteria with a **deliberately separate parser** and requires count + normalized-text equality against the staged item. Do not "dedupe" this with `bridge._extract_list_section` — implementation independence is load-bearing (a shared extractor bug would corrupt both sides identically; that is exactly how vault issue 036 escaped every gate).
- `spark.cli` — `check` / `deposit` / `queue` / `replan`; pure mechanism, no judgment.

## CLI

Run from the **vault root** (relative `source_issue` paths resolve against cwd):

```
python -m spark.cli check   <draft-dir>                      # all gates; exit 0 iff clean
python -m spark.cli deposit <goal-id> <drafts-dir> <queue>   # re-check, then move only gated files
python -m spark.cli queue   <spark-queue-dir>                # list Goals / Bounces / Escalated
python -m spark.cli replan  <item.md>                        # replan budget; escalates at count >= 2
```

`check` failure classes: linter flags, schema errors (missing/empty `acceptance`, bad `priority`), unparseable `.md` files, duplicate ids, graph errors, and fidelity mismatches (`<id> fidelity: …`, `<id>: source issue not found: …`).

Contract points enforced here, decided in the vault records above: staged work items are a pure function of their source issue (fix the issue and re-bridge — never hand-edit a staged file; the fidelity gate has no waiver), deposit is batch-atomic, and the human gate happens before `deposit` (the skill presents items one at a time for per-item verdicts).

## Development

- Install: `pip install -e .` (depends on `iron-lib`, installed editable from `IRON Workspaces/iron-lib`)
- Test: `python -m pytest tests/ -q` — all tests use temp dirs; never point them at the vault's live queues (`Working/forge-queue`, `Working/spark-queue`).
- No network, no model calls, no RLM — ever, by decision. Pure deterministic Python.
- Logic needed by more than one of `forge`/`spark`/`ore` belongs in `iron-lib`, not here; never import another tool package directly.
