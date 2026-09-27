# Schema Reference

The reference implementation publishes machine-readable JSON Schema documents
under `schemas/`. This guide explains the semantic role of each object and the
relationships that the schemas cannot express by themselves.

## Object map

| Schema | Purpose |
|---|---|
| `project.schema.json` | Stable Project identity and channel ownership |
| `context.schema.json` | Semantic grouping that is not routing authority |
| `session.schema.json` | Local compatibility/readiness view |
| `task.schema.json` | Canonical Task manifest |
| `event.schema.json` | Canonical append-only Event |
| `readiness.schema.json` | Machine-readable first-bind/resume verdict |

## Project

A Project is a stable work boundary. It is not inferred from a directory name,
a recent commit, or a chat message.

Representative fields:

```json
{
  "protocol": "awrp/0.1",
  "project_id": "project_alpha",
  "title": "Example Project",
  "channels": ["channel_alpha_contrib"],
  "created_at": "2026-01-01T00:00:00Z"
}
```

Invariants:

- project id is stable;
- a Channel has at most one owning Project;
- attaching the same Channel twice is idempotent only when ownership agrees;
- moving a Channel requires explicit audited intent.

## Context

A Context groups related Tasks semantically. It is not canonical routing and
must not be used to infer ownership.

Representative fields:

```json
{
  "protocol": "awrp/0.1",
  "context_id": "ctx_alpha",
  "title": "Example Project",
  "created_at": "2026-01-01T00:00:00Z",
  "description": ""
}
```

A Task may reference a Context while its actual route lives in Project,
Channel, and worker endpoint fields. This separation allows semantic grouping
without making the group a mailbox.

## Session

The Session schema describes a local compatibility/readiness view. It may
include a local binding, focused Task, Run, and last observed head.

A Session is not canonical. Another machine may have a different Session view
of the same relay. Resolution must go back to Task history.

Use Session data for:

- operator readability;
- fast local focus;
- readiness reporting;
- binding validation input.

Do not use Session data for:

- project selection by recency;
- cross-channel inbox discovery;
- authorization;
- replacing event history.

## Task

The Task manifest is canonical identity and current high-level metadata.

Representative fields:

```json
{
  "protocol": "awrp/0.1",
  "task_id": "task_20260101T000000Z_example01",
  "title": "Verify a guarded dispatch",
  "goal": "Prove exact recipient identity and expected-head CAS.",
  "state": "submitted",
  "phase": "intake",
  "waiting_on": "coordinator_alpha",
  "source_repo": null,
  "source_issue": null,
  "created_by": "coordinator_alpha",
  "integrity": {
    "task_hash": "sha256:..."
  }
}
```

Production tasks also carry Project, Channel, optional lane, worker endpoint,
and side-effect policy. A historical task without that routing must be
explicitly marked legacy at creation; new tasks cannot silently omit it.

The Task manifest may carry a projection of current state, but the event chain
is the authority when they disagree.

## Event

The Event schema is the core of the protocol. Every Event is create-only and
linked to its predecessor.

Representative fields:

```json
{
  "protocol": "awrp/0.1",
  "event_id": "evt_20260101T001000Z_dispatch01",
  "seq": 2,
  "prev_event_id": "evt_20260101T000000Z_created01",
  "prev_event_hash": "sha256:...",
  "type": "DISPATCH",
  "actor": {"role": "coordinator", "id": "coordinator_alpha"},
  "recipient": {"role": "worker", "id": "codex_alpha"},
  "run_id": "run_20260101T001000Z_example01",
  "state": "working",
  "phase": "implementation",
  "waiting_on": "codex_alpha",
  "run_state": "dispatched",
  "summary": "Implement the approved execution pack.",
  "integrity": {"event_hash": "sha256:..."}
}
```

### Identity fields

- `event_id` is globally unique for the Task history.
- `seq` is monotonic and normally contiguous from 1.
- `prev_event_id` names the immediately preceding Event.
- `prev_event_hash` binds the new Event to the exact predecessor bytes.

### Actor and recipient

The actor is the participant that authored the Event. The recipient is the
participant expected to act or observe next.

A worker may append only a DISPATCH whose recipient id matches its configured
endpoint. Recipient identity is not advisory.

### Run identity

Execution-bearing Events name a `run_id`. A Run is created by the first
execution Event for that id, usually DISPATCH. Later Events attach to the same
Run.

A Run cannot execute twice. A retry or revision uses a new Run id.

### State projection

Every Event carries:

- Task `state`;
- `phase`;
- `waiting_on`;
- optional `run_state`;
- `summary`;
- optional details.

These fields make replay useful to humans and tools, but they do not replace
transition validation. An Event with a legal-looking hash can still carry an
illegal state transition.

### Integrity

The event hash covers canonical JSON after removing the `event_hash` field.
Canonical JSON means UTF-8, sorted keys, compact separators, and no
platform-dependent line endings.

Validation recomputes the hash and verifies predecessor links. Hash integrity
proves byte continuity; semantic validation proves protocol legality.

## Event types

| Type | Execution-bearing | Meaning |
|---|---:|---|
| `TASK_CREATED` | no | Initial Task fact |
| `DISPATCH` | yes | Authorize one Run for one recipient |
| `ACK` | yes | Worker accepted the Run and head |
| `INPUT_REQUEST` | yes | Worker needs an authorized decision |
| `INPUT_PROVIDED` | yes | Decision recorded for the same Run |
| `HANDOFF` | yes | Worker delivered verified work |
| `REVIEW` | no | Coordinator review or revision request |
| `APPROVAL` | no | Scoped authority for a later effect |
| `CANCEL` | yes | Coordinator stopped the Run |
| `ERROR` | yes | Run failed |
| `RECONCILE` | no | Audited recovery or state correction |
| `NOTE` | no | Durable information without execution authority |

## Task states

```text
submitted → working | input_required | failed | canceled | rejected
working → working | input_required | completed | failed | canceled | rejected
input_required → working | completed | failed | canceled | rejected
```

Terminal states do not accept ordinary execution Events.

## Run states

```text
dispatched → working → succeeded | failed | canceled
```

Only `dispatched` and `working` are active. A Run does not reopen after a
terminal state.

## Readiness

The readiness schema is a verdict, not a state mutation.

Representative fields:

```json
{
  "protocol": "awrp/0.1",
  "status": "EXECUTE",
  "reason": "exact dispatch matches binding and expected head",
  "task_id": "task_20260101T000000Z_example01",
  "run_id": "run_20260101T001000Z_example01",
  "expected_head": "evt_20260101T001000Z_dispatch01"
}
```

Verdicts:

- `EXECUTE` — all identity, history, and authority checks pass;
- `NO_TASK` — no actionable Task in the bound route;
- `AMBIGUOUS` — multiple candidates;
- `OWNED` — another logical owner holds the Run;
- invalid canonical state — chain or binding is untrusted.

A readiness verdict is only actionable when the caller also preserves the
expected head and the same binding assumptions.

## Side-effect policy

A Task may describe allowed side-effect classes. Typical classes:

| Class | Meaning |
|---|---|
| relay read | Read Task/Event/Project state |
| relay write | Append canonical relay history |
| source write | Modify a source repository |
| public write | Create public issues, PRs, comments, releases |
| destructive | Delete, force-push, merge, or mutate production |

Relay reads and canonical appends are ordinary protocol operations. Source,
fork, upstream, public, or destructive effects need explicit authority.

The policy is a bound, not a prompt. A worker that reaches an unlisted class
must request input or approval rather than improvising.

## Artifacts and approvals

Large outputs should not be embedded in Event JSON. Store them in a controlled
location and reference them by:

- repository and commit SHA;
- content hash;
- durable pointer with an integrity check.

Approvals should reference the exact artifact hash they authorize. If the
artifact changes, the approval is stale.

## Schema evolution

Additive changes should:

1. keep the wire protocol identifier when old readers fail closed safely;
2. add optional fields rather than changing existing field meaning;
3. update composer, validator, replay, schemas, docs, and tests together;
4. provide a migration for historical Task manifests that lack the field;
5. never reinterpret an existing field with a new meaning.

A change that alters canonical semantics requires a new protocol identifier or
a formally incompatible migration path.

## Validation order

A robust validator checks:

1. protocol version;
2. required identity fields;
3. manifest hash;
4. event file naming and sequence;
5. predecessor id and hash;
6. recomputed event hash;
7. actor and recipient shape;
8. legal type and state transition;
9. Run state and single-execution rules;
10. routing and fencing requirements;
11. idempotency conflicts.

Fail closed at the first broken invariant. Do not repair a chain silently.

## Schema limitations

JSON Schema validates shape, not every cross-file invariant. The reference
implementation additionally validates:

- Project/Channel ownership;
- Task route completeness;
- expected-head CAS;
- recipient identity;
- claim generation;
- artifact hashes;
- connector repository/path constraints;
- public-transport mutation restrictions.

Consumers should run repository validators instead of relying on schema
validation alone.
