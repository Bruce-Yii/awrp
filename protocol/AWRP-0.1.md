# Agent Work Relay Protocol — AWRP v0.1

Status: experimental personal-workflow protocol.

## 1. Purpose

AWRP provides a small durable coordination layer between a human authority, a coordinator/reviewer, and one or more coding workers. It is optimized for low-frequency, high-semantic-value events rather than realtime chat.

## 2. Non-goals

v0.1 does not define a server, realtime streaming, autonomous task auction, leases, cryptographic identities, distributed consensus, database, web UI, or A2A replacement. A single-purpose MCP transport facade may exist as a thin wrapper surface (one tool, transport writes only) — that is an integration adapter, not a protocol replacement, and the native router outside it stays out of scope.

## 3. Objects

### Context
A semantic grouping label for related Tasks, plus a compatibility object
(`contexts/*.json`) that task creation still requires. Context never owns
channels, never routes work, and never selects workers — it is co-equal
with nothing. Project is the stable canonical identity; Context is
grouping plus legacy compatibility.

### Project
The stable canonical identity for a line of work. A Project owns an
exclusive set of channels (`projects/<project_id>.json`), resolves
aliases exactly, and is what agent sessions attach to. One channel belongs
to at most one Project.

### Channel
The durable communication boundary between coordinator-side and
worker-side endpoints. Discovery, claims, and fencing are all
channel-scoped. A worker endpoint binds to exactly one channel by default.

### Lane
An optional session identity INSIDE a channel for concurrent workstreams.
Lanes never replace channel isolation; lane-unset tasks are visible to any
lane of the same channel+endpoint.

### Claim
A mutable per-channel concurrency primitive (`channels/<id>/claim.json`
plus append-only `claim.log.jsonl`) naming the single authoritative
coordinator writer and its monotonic generation. Claims govern mutation
authority only; canonical events stay create-only.

### Session
Workspace-local, never canonical (`.awrp/`): binding (relay/channel/
endpoint/lane), attached projects, and current focus. Sessions participate
in Projects; they never own them.

### Task
A durable goal. A Task can span multiple Runs, and multiple Agent
sessions/windows may serve it behind one logical worker endpoint — but
the endpoint itself is stable: `routing.worker_endpoint` names the single
execution identity for the Task's lifetime, and changing logical worker
endpoint normally becomes a successor Task (no reroute feature exists;
authority transfer would need its own contract). Canonical identity lives
in `task.json`.

### Run
One concrete execution attempt. `DISPATCH` creates a Run. The same `run_id` MUST NOT execute twice.

### Event
An append-only protocol fact represented under `tasks/<task_id>/events/<seq>_<event_id>.json`.

### Artifact
A durable output or pointer, preferably `git_commit`, `relay_file`, or another durable external reference.

## 4. Canonical vs projection

Canonical:
- Context manifest
- Task manifest
- create-only Event files
- referenced Artifact files and Git commit SHAs

Projection only:
- `TASK.md`
- GitHub Issue body
- labels
- comments
- generated snapshots

Projection must never silently override event-derived state.

## 5. Task state

Allowed states:
- `submitted`
- `working`
- `input_required`
- `completed`
- `failed`
- `canceled`
- `rejected`

Use `phase` and `waiting_on` for specific workflow meaning.

Terminal states: `completed`, `failed`, `canceled`, `rejected`.

After terminal state, normal events may not continue the Task. Recovery requires explicit `RECONCILE`.

## 6. Event types

- `TASK_CREATED`
- `DISPATCH`
- `ACK`
- `INPUT_REQUEST`
- `INPUT_PROVIDED`
- `HANDOFF`
- `REVIEW`
- `APPROVAL`
- `CANCEL`
- `ERROR`
- `RECONCILE`
- `NOTE`

No high-frequency `PROGRESS` event exists in v0.1.

`NOTE` is a non-execution communication/evidence primitive: it may
reference a Task and a known historical Run (or neither, with null run),
but it is projection-neutral (state/phase/waiting_on/run-state must repeat
the current head), carries no fencing, opens/claims/closes no Run, and
confers no reviewability or side-effect authorization. Its author is bound
to the referenced run's executor (or dispatch recipient pre-claim), the
task worker identity, or the task coordinator — unattributed evidence is
refused. It exists so post-run evidence survives durably without reopening
execution authority.

## 7. Ordering and integrity

Each Task has a monotonically increasing integer `seq`.

Each Event carries:
- `integrity.prev_event_id`
- `integrity.prev_event_hash`
- `integrity.event_hash`

The first Event uses null previous values.

v0.1 canonical event hashing uses UTF-8 JSON with keys sorted, no insignificant whitespace, `ensure_ascii=false`, and no floating-point values in canonical machine fields. `integrity.event_hash` is removed before hashing.

`event_hash = SHA256(canonical_event_without_event_hash)`

This detects silent modification/deletion/chain breaks; it does not authenticate the actor.

## 8. Fork rule

If validation cannot produce one unique chain, automatic work stops. The coordinator exposes the conflict and performs explicit recovery. Do not choose a branch only by wall-clock timestamp.

## 9. Run semantics

Recommended Run states:
- `dispatched`
- `working`
- `succeeded`
- `failed`
- `canceled`

Typical flow:

```text
DISPATCH(run_01)
  → ACK(run_01)
  → HANDOFF(run_01)
  → REVIEW
      accepted → APPROVAL / completion
      revision → DISPATCH(run_02)
```

Agent success does not imply Task completion.

## 10. Recipient/idempotency rule

A worker executes a Dispatch only if:
- recipient role is `worker`
- recipient id matches its configured worker id
- for Project-first Tasks (registered `routing.worker_endpoint`), recipient
  id equals that endpoint and worker `waiting_on` equals recipient id
  (fail-closed identity invariant; legacy tasks without a registered
  endpoint take documented compatibility and never guess)
- `run_id` was not already executed
- chain validation passes
- Task is not terminal
- requested side effects are permitted

## 11. Decision boundary

If execution requires a product/security/compatibility/maintainer/human decision that is not already authorized, emit `INPUT_REQUEST`, set `state=input_required`, set `waiting_on`, and stop before the undecided side effect.

## 12. Approval

Approval must be scoped and bound to exact outputs. For code publication, bind to exact commit SHA. A later commit is not automatically covered by an older Approval.

## 13. Side-effect policy

Recommended levels:
- P0 read-only repo/issue/web — allow
- P1 local edits/tests/local commit — allow
- P2 private relay write — allow
- P3 push user fork/branch — dispatch-specific
- P4 upstream PR/comment — human approval
- P5 merge/destructive operation — explicit human approval

## 14. Identity/threat model

`actor.id` is a logical identity. Multiple workers may share one GitHub account/token in v0.1. The threat model is honest agents, accidental error, and state drift — not malicious participants.

## 15. GitHub transport

Recommended: private repository, one Task directory per Task, optional one Issue per Task for human UI, low-frequency comments only, preserved Git history.

## 16. Recovery

A new coordinator window should resolve the Project first, then recover
from canonical state (Context is grouping/compatibility only — never the
recovery root):
1. resolve the exact `project_id` (never infer it from channels/recency)
2. enumerate that Project's Tasks
3. read Task manifests
4. load Events
5. validate sequence + hashes
6. replay state
7. identify `state`, `phase`, `waiting_on`, latest Run, latest Artifacts
8. fetch only the Artifacts needed for the next decision

The target is Current State, not a conversation summary.

## 17. Compatibility map

Wire protocol core (`awrp/0.1`, frozen): Context/Task/Run/Event/Artifact
shapes, `seq` + hash-chain integrity, task states and terminal set, run
states, recipient/idempotency rules, create-only event files. Old readers
fail closed (never silently reinterpret) on anything newer.

First-stage control-plane extensions (cumulative behavior profiles
v0.1.1–v0.1.5, backward-compatible): reviewable patch artifacts (v0.1.1),
single-writer concurrency model (v0.1.2), channel-first routing (v0.1.3),
sessions/claims/fencing (v0.1.4), `NOTE` communication primitive,
dispatch endpoint identity, bounded transport helpers
(`worker-retry-push`, `publish-ephemeral`), bridge/connector publication,
project registry and migrations. Extensions add rules and tools; they
never weaken core authority semantics.

Local-only state (never canonical, never pushed as truth): `.awrp/`
binding/session/focus, worktree checkouts, CLI output formatting.

Projection-only state (derived, never authoritative): `TASK.md`,
GitHub Issue bodies/labels/comments, snapshots, audit reports.

Legacy compatibility (explicit, never guessed): tasks without
routing/channel claims predate Project-first routing and take the compat
path (unfenced, unscoped discovery via `--legacy`, endpoint never
inferred). Migration associations move legacy tasks under Projects
explicitly; history is never rewritten to look Project-first.
