# AWRP Architecture

## Design goals

AWRP optimizes for four properties:

1. **Recoverability** — a new process can reconstruct state from durable facts.
2. **Bounded authority** — a Run names exactly who may act and what may change.
3. **Single execution** — a `run_id` cannot be executed twice.
4. **Fail-closed recovery** — ambiguity stops work instead of selecting a plausible target.

It deliberately does not optimize for realtime messaging, dashboards, autonomous bidding, or a general agent platform.

## Identity graph

```text
Project
  └─ Channel
      └─ Lane
          └─ Claim
              └─ Task
                  └─ Run
                      └─ Event
                          └─ Artifact
```

### Project

A stable work boundary that owns one or more channels. Project identity is explicit; recency and naming similarity never select a project.

### Channel

A durable coordinator/worker boundary. A channel may be claimed by one coordinator writer at a time. Claim state is mutable and generation-fenced; canonical events are append-only.

### Lane

An optional logical session identity inside a channel. A lane does not by itself isolate operating-system processes or agent windows; the execution-view rules cover that boundary.

### Task

The unit of governed work. A Task records its goal, state, phase, side-effect policy, participants, and the history needed to prove how work was authorized.

### Run

One execution attempt. A retry or revision creates a new Run. The same Run must never execute twice, even after a process restart.

### Event

An append-only fact in the Task's canonical history. Events carry sequence, previous-event links, a content hash, actor and recipient identity, Run identity, state projection, and details.

### Artifact

A durable output referenced by repository and commit SHA, a content-addressed blob, or another stable pointer. Large logs and binaries do not belong in the event history.

## Canonical state and projections

Canonical state is:

- the Task manifest;
- the complete ordered Event history;
- referenced artifacts and commit identities.

Everything else is a projection:

- human-readable task cards;
- README files;
- issue bodies and comments;
- labels;
- chat summaries;
- generated indexes.

Projections may be stale. A projection must never override event-derived state.

## Event chain

Each event records at least:

- monotonic `seq`;
- unique `event_id`;
- `prev_event_id`;
- `prev_event_hash`;
- its own canonical `event_hash`;
- event type;
- actor and recipient roles/ids;
- optional `run_id`;
- state, phase, waiting-on, and run-state projection;
- summary and optional details.

A validator recomputes the canonical hash and checks sequence continuity. A missing or modified predecessor makes the chain invalid from that point forward.

## State machines

### Task state

```text
submitted
  ├─→ working
  ├─→ input_required
  ├─→ failed
  ├─→ canceled
  └─→ rejected

working
  ├─→ working
  ├─→ input_required
  ├─→ completed
  ├─→ failed
  ├─→ canceled
  └─→ rejected

input_required
  ├─→ working
  ├─→ completed
  ├─→ failed
  ├─→ canceled
  └─→ rejected
```

Terminal states do not accept ordinary execution events. Recovery requires an explicit audited transition or reconciliation.

### Run state

```text
dispatched → working → succeeded
                   ├─→ failed
                   └─→ canceled
```

Only `dispatched` and `working` are active. A Run reaches a terminal state once and does not reopen.

## Dispatch lifecycle

```text
coordinator plan
    ↓
route/fingerprint/head checks
    ↓
DISPATCH composed
    ↓
expected-head CAS
    ↓
worker discovery
    ↓
worker identity and authority checks
    ↓
ACK
    ↓
authorized work
    ↓
HANDOFF composed
    ↓
delivery verified
    ↓
coordinator review
```

A coordinator plans before publishing because route mistakes are cheaper to prevent than to reconcile. The worker validates the received chain before acting because a correctly composed message can still be delivered to the wrong endpoint.

## Coordinator writer fencing

A channel claim carries:

- owner identity;
- monotonic generation;
- acquisition and transition facts.

A coordinator write must match the current claim owner and generation. Claim migration is explicit; a process does not infer ownership from recency.

This prevents two coordinator windows from composing valid-looking writes against the same channel without a deterministic winner.

## Execution views

A single mutable checkout couples unrelated parallel work through uncommitted bytes and branch divergence. The default execution model is one clean, task-scoped view per worker session.

An execution view is:

- acquired from a known relay head;
- verified clean and at tip before reuse;
- released only after canonical HANDOFF delivery;
- never repaired by discarding foreign bytes.

This reduces synthetic waits and prevents one task from blocking another through local dirt.

## Publication and CAS

Local append flow:

1. pull fast-forward-only;
2. validate and replay;
3. compose bytes through validated code;
4. capture the current expected event head;
5. write new files only;
6. commit;
7. push without force;
8. verify the remote result.

A push race is not repaired with force. The writer re-syncs, replays, and recomposes.

Connector publication follows the same rule with Git database primitives: blobs, tree, commit, and a non-force ref update.

## Bridge transport

A connector without a checkout can write a constrained intent file. The bridge workflow runs the real validated composer; the connector never supplies canonical event bytes.

The pre-API wrapper narrows the mutation surface to one transport-write class. Unknown actions, repository drift, path drift, and public-mutation parameters fail before delegation.

The wrapper cannot reconfigure a host application's native tool router. That residual is explicit: platform-level enforcement requires host configuration and live acceptance testing.

## Recovery classes

### Stale expected head

Another writer appended after composition. Re-read, replay, and recompose a new append.

### Lost publication race

The remote advanced. Do not force. Re-sync and recompose if semantic invariants still hold; otherwise reject and request a new Run.

### Missing binding

A fresh window cannot prove exact Project/Channel/Task identity. Generate a first-bind instruction with exact values; never scan globally.

### Ambiguous binding

Multiple candidates match. Stop and ask the authority to choose.

### Corrupt chain

Validation fails. Contain, audit, and record an incident. Do not execute from partially trusted state.

### Delivery failure after local success

Do not repeat source or public side effects. Reconcile HANDOFF delivery first.

## Trust boundaries

- Human approval is required for scoped public or destructive effects.
- A local binding is a convenience pointer, not canonical authority.
- Chat summaries are context, not authorization.
- A connector carries bytes; repository code composes semantics.
- Git transport proves delivery; it does not grant permission.
- A projection never outranks the canonical chain.

## Compatibility

The wire protocol remains `awrp/0.1` across additive behavior-profile steps. New fields must be backward-compatible. Older readers fail closed on unknown protocol versions rather than reinterpreting history.

A behavior change that alters canonical semantics requires a new protocol identifier or a formally incompatible migration path.

## Implementation map

- `tools/awrp.py` — reference CLI and validation/composition logic
- `tools/awrp_transport.py` — pure transport-intent validation
- `tools/awrp_mcp_transport.py` — minimal MCP stdio facade
- `schemas/` — machine-readable shapes
- `protocol/` — normative protocol and contracts
- `tests/test_awrp.py` — executable protocol/runtime suite
- `tests/test_public_snapshot.py` — public-boundary guard
