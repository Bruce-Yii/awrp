# AWRP Bootstrap

This document is the public snapshot entrypoint for a coding agent or coordinator that wants to use AWRP safely. It describes how to recover context, bind to a project, validate a task, and resume an authorized run without guessing identity.

## 1. Establish the public snapshot

Clone or open the repository and read:

1. `README.md` — product overview and quick start.
2. `protocol/AWRP-0.1.md` — wire semantics.
3. `protocol/WORKER-CONTRACT.md` — execution contract.
4. `docs/decisions/2026-09-27-public-snapshot-boundary.md` — why the repository contains no production relay state.

The public snapshot ships the protocol and reference tooling. It is not itself a production relay and must not be populated with private tasks.

## 2. Create a disposable relay for evaluation

A new user can exercise the protocol in a disposable directory:

```bash
python tools/awrp.py init-context --root .demo \
  --context-id ctx_demo \
  --title "Evaluation"
python tools/awrp.py project-create --root .demo \
  --project-id project_demo \
  --channel channel_demo \
  --title "Evaluation project"
python tools/awrp.py create-task --root .demo \
  --context-id ctx_demo \
  --project-id project_demo \
  --channel-id channel_demo \
  --worker-endpoint codex_demo \
  --title "Evaluate the protocol" \
  --goal "Create, validate, and replay a synthetic task." \
  --worker codex_demo
```

The resulting task directory is canonical for that disposable relay:

```text
.demo/tasks/<task_id>/
├── task.json
├── TASK.md
└── events/
    ├── 000001_...json
    ├── 000002_...json
    └── ...
```

## 3. Restore current state

For a task that already exists:

1. Sync history with a fast-forward-only pull. Never hide divergence with reset, rebase, or force-push.
2. Read `task.json`.
3. Read every event file in sequence order.
4. Run `validate` against the task directory.
5. Run `replay` and derive `state`, `phase`, `waiting_on`, `run_id`, recipient, and authority from the result.

```bash
python tools/awrp.py validate --task-dir <relay>/tasks/<task_id>
python tools/awrp.py replay --task-dir <relay>/tasks/<task_id>
```

If validation fails, stop. A damaged or ambiguous chain is not execution authorization.

## 4. Bind a fresh worker window

A fresh worker must receive an exact project route and task identity. It must not scan all repositories and choose the newest plausible task.

```bash
python tools/awrp.py first-bind \
  --relay <owner/repository> \
  --project-id <exact-project> \
  --channel <exact-channel> \
  --worker-endpoint <exact-endpoint> \
  --task-id <exact-task> \
  --run-id <run-id-when-known>
```

A first-bind result is one of:

- `EXECUTE` — all identity, history, and authority checks pass.
- `NO_TASK` — the bound route has no actionable task.
- `AMBIGUOUS` — more than one target could match; the human must decide.
- `OWNED` — another logical owner currently holds the run.
- `INVALID_CANONICAL` — the chain is corrupt; contain and audit.

Only `EXECUTE` authorizes the ACK for the reported active run.

## 5. ACK before material work

The worker ACKs the exact dispatched `run_id` before performing implementation work:

```bash
python tools/awrp.py emit \
  --task-dir <task-dir> \
  --type ACK \
  --actor-role worker \
  --actor-id <worker-endpoint> \
  --recipient-role coordinator \
  --recipient-id <coordinator> \
  --run-id <run-id> \
  --state working \
  --phase implementation \
  --waiting-on <worker-endpoint> \
  --run-state working \
  --expected-head <reported-head> \
  --summary "Accepted."
```

An ACK is not optional politeness. It records that the worker accepted the authority and history head that it will execute.

## 6. Execute only authorized work

Before each action, check:

- The task is non-terminal.
- The event is a valid `DISPATCH` for this worker.
- The `run_id` has not executed before.
- The side effect is permitted by the task policy.
- Any required human approval matches the exact output.

Local success is not canonical completion. Do not repeat source or public side effects when a delivery step fails; reconcile the handoff instead.

## 7. Deliver a HANDOFF

A successful run ends with a canonical `HANDOFF` that names:

- what changed;
- how it was verified;
- artifact or commit references;
- unresolved risks;
- the exact next owner.

```bash
python tools/awrp.py emit \
  --task-dir <task-dir> \
  --type HANDOFF \
  --actor-role worker \
  --actor-id <worker-endpoint> \
  --recipient-role coordinator \
  --recipient-id <coordinator> \
  --run-id <run-id> \
  --state working \
  --phase review \
  --waiting-on <coordinator> \
  --run-state succeeded \
  --expected-head <current-head> \
  --summary "Implemented and verified."
```

Persist and verify delivery before declaring the run complete.

## 8. Resume after interruption

A later session reads the workspace binding, then resumes:

```bash
python tools/awrp.py resume --root <bound-workspace>
```

The result is derived from canonical events, not from the latest chat message or the newest commit. If the expected history head changed, the tool reports staleness or ambiguity and the worker re-syncs before doing anything else.

## 9. Revision and retry semantics

- A retry after a failed run requires a new `run_id`.
- A revision after review requires a new `run_id`.
- Never execute the same `run_id` twice.
- Never delete or rewrite a canonical event to make a run look successful.
- Use a `RECONCILE` event for audited recovery, not silent mutation.

## 10. Coordinator publication

A coordinator obtains canonical bytes from validated composers such as `plan-task-create`, `dispatch-guarded`, `publish-atomic`, or `publish-connector`. The coordinator must not hand-author event hashes, sequence numbers, fencing generation, or actor identity.

Remote publication is compare-and-swap:

1. capture the remote head;
2. compose against that head;
3. commit on the captured base;
4. push without force;
5. read back and validate.

A non-fast-forward result means another writer won. Re-read, recompose, and publish a new append. Never force-push canonical history.

## 11. Transport boundary

`tools/awrp_transport.py` accepts only a transport-write intent for the configured public snapshot repository and an exact `bridge/requests/<id>.json` path. Issue, pull-request, comment, label, close, merge, release, branch, and upstream mutation parameters are rejected before delegation.

The MCP facade exposes one tool only:

```bash
python tools/awrp_mcp_transport.py --base-dir <relay-checkout>
```

This is an integration boundary, not a replacement for a host application's native connector configuration.

## 12. Incident containment

If validation, routing, delivery, fencing, transport, or recovery fails:

1. stop the affected action;
2. preserve evidence;
3. do not guess a repair;
4. audit the relevant history;
5. record a confirmed protocol/coordination incident;
6. recover through a new authorized run or an audited reconciliation.

Ordinary bugs in a source project are not AWRP incidents.

## 13. Public snapshot boundary

The public repository excludes production state by design. Never add:

- `projects/`
- `channels/`
- `contexts/`
- `incidents/`
- `tasks/`
- `bridge/requests/`
- private project names;
- credentials or runtime tokens;
- personal or customer data.

`tests/test_public_snapshot.py` enforces this boundary.
