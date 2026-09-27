# AWRP — Agent Work Relay Protocol

AWRP is a small, auditable coordination protocol for a human authority, a coordinator/reviewer, and coding agents such as Codex, Claude Code, and OpenCode. It coordinates low-frequency, high-semantic-value work through append-only events, guarded dispatch, deterministic replay, and fail-closed recovery.

This repository is the public-safe reference snapshot: protocol, schemas, standard-library implementation, examples, and tests. It contains no production relay state, task history, credentials, or private project records.

## Why another coordination layer?

Coding agents need durable state that survives context loss, multiple windows, retries, and reviewer handoffs. A chat transcript is useful context, but it is not an authoritative execution log. AWRP keeps the protocol small enough to inspect and strict enough to fail closed when identity, authority, or history is ambiguous.

## Features

- **Append-only canonical events** with sequence and hash-chain validation.
- **Project → Channel → Task → Run → Event → Artifact** identity model.
- **Guarded dispatch** that binds coordinator, worker, repository, branch, and side-effect policy.
- **Deterministic replay** to recover state without re-running side effects.
- **Compare-and-swap delivery** for remote publication and handoffs.
- **Single-purpose transport facade** for relay writes; public-object mutations are structurally rejected.
- **Standard library only** for the reference CLI and transport modules.

## Architecture

```text
Project
  └─ Channel
      └─ Lane (optional session identity)
          └─ Claim (mutable coordinator writer authority)
              └─ Task
                  └─ Run (single execution attempt)
                      └─ Event (create-only, hash-linked)
                          └─ Artifact (durable output or pointer)
```

Canonical truth is the Task manifest plus its complete ordered event history. README files, issues, labels, comments, and chat summaries are projections; they must never override event-derived state.

The public snapshot intentionally omits production `projects/`, `channels/`, `contexts/`, `incidents/`, `tasks/`, and `bridge/requests/` state.

## Quick start

Requirements: Python 3.11+.

```bash
git clone https://github.com/Bruce-Yii/awrp.git
cd awrp
python tools/awrp.py --help
python examples/demo_flow.py
```

Create a disposable project and task in a temporary directory:

```bash
python tools/awrp.py init-context --root .demo --context-id ctx_alpha --title "Example Project"
python tools/awrp.py project-create --root .demo \
  --project-id project_alpha \
  --channel channel_alpha_contrib \
  --title "Example Project"
python tools/awrp.py create-task --root .demo \
  --context-id ctx_alpha \
  --project-id project_alpha \
  --channel-id channel_alpha_contrib \
  --worker-endpoint codex_alpha \
  --title "Fix example issue" \
  --goal "Reproduce, fix, and verify a synthetic issue." \
  --worker codex_alpha
```

Dispatch the exact route instead of hand-authoring an event:

```bash
python tools/awrp.py dispatch-guarded \
  --no-binding \
  --project-id project_alpha \
  --channel channel_alpha_contrib \
  --worker-endpoint codex_alpha \
  --repo .demo \
  --task-id <task_id> \
  --run-id run_01 \
  --actor-role coordinator \
  --actor-id coordinator_alpha \
  --recipient-role worker \
  --recipient-id codex_alpha \
  --state working \
  --phase implementation \
  --waiting-on codex_alpha \
  --run-state dispatched \
  --summary "Implement the approved execution pack."
```

Historical tasks that genuinely predate project/channel routing can be created with the explicit `--legacy` marker. New tasks must not use it.

Use the generated `tasks/<task_id>/` path to validate or replay it:

```bash
python tools/awrp.py validate --task-dir .demo/tasks/<task_id>
python tools/awrp.py replay --task-dir .demo/tasks/<task_id>
```

The demo state is disposable. Never point a public demonstration at production relay state.

## Core workflow

1. A coordinator creates or resolves an exact Project/Channel/Worker route.
2. A Task records the goal, side-effect policy, and authority.
3. The coordinator dispatches one Run with an explicit recipient and expected history head.
4. The worker ACKs the same Run before material work.
5. The worker performs only authorized work and emits a HANDOFF.
6. The coordinator validates and replays the event chain, then reviews the result.
7. A retry or revision uses a new Run; the same Run never executes twice.

Unknown identity, missing history, stale expected head, or ambiguous authority fails closed. The tool does not guess a project from recency, a local binding, or a pasted summary.

## Transport boundary

`tools/awrp_transport.py` exposes one mutation shape: a validated transport-write request for a relay checkout. `tools/awrp_mcp_transport.py` wraps that boundary in a minimal MCP stdio server.

This facade does not replace or reconfigure a host application's native connector. Callers must wire this server explicitly when they want the transport restriction to apply.

## Tests

Run the complete suite:

```bash
python -m pytest -q
```

Or run the public-snapshot boundary checks alone:

```bash
python -m unittest tests/test_public_snapshot.py -v
```

The suite covers protocol/runtime invariants, transport restrictions, publication checks, replay, routing, and public-snapshot privacy boundaries.

## Documentation

- `protocol/AWRP-0.1.md` — protocol rules and compatibility map
- `protocol/AWRP-0.1.1-ERRATA.md` — backward-compatible clarification
- `protocol/WORKER-CONTRACT.md` — worker rules
- `protocol/CHATGPT-ADAPTER.md` — coordinator integration notes
- `schemas/` — machine-readable event, task, project, context, session, and readiness shapes
- `bridge/README.md` — transport request contract
- `AWRP-BOOTSTRAP.md` and `docs/BOOTSTRAP.md` — fresh-session recovery flow
- `docs/ARCHITECTURE.md` — identity, state, and recovery model
- `docs/OPERATIONS.md` — coordinator and worker runbook
- `docs/INTEGRATION.md` — Git, connector, bridge, and MCP transports
- `docs/SECURITY.md` — protected properties and trust boundaries
- `docs/FAILURE-MODES.md` — concrete coordination failures and recovery
- `docs/COMPATIBILITY.md` — additive and incompatible protocol changes
- `docs/PUBLIC-SNAPSHOT.md` — publication boundary and provenance policy
- `docs/decisions/2026-09-27-public-snapshot-boundary.md` — why this is a fresh public snapshot

## Security model

- Append-only history is validated before replay or resume.
- Worker identity and authority must match exactly.
- `run_id` is single-use; revisions create a new Run.
- Public/upstream side effects are not implied by successful local work.
- Transport requests are schema-validated before delegation.
- Unknown or drifted public-object mutations are rejected before any write.
- Secrets and production relay state are outside this repository's boundary.

## License

No license is granted. The public snapshot is provided for inspection and evaluation only; no permission is granted to copy, modify, or redistribute it.
