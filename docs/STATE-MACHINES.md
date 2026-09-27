# State Machines

AWRP separates four state machines. Confusing them is a common source of
recovery bugs, so the reference implementation validates each one explicitly.

## Task state machine

The Task state describes the governed unit of work.

```text
                    ┌───────────────┐
                    │   submitted   │
                    └───────┬───────┘
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
          ▼                 ▼                 ▼
    ┌───────────┐     ┌────────────┐    ┌───────────┐
    │  working  │     │input_required│   │  failed   │
    └─────┬─────┘     └──────┬──────┘    └───────────┘
          │                  │
          ├──────────────────┤
          │                  │
          ▼                  ▼
    ┌───────────┐       ┌───────────┐
    │ completed │       │ completed │
    └───────────┘       └───────────┘
```

Every state can also move to `canceled` or `rejected` when the contract permits
that transition.

### Task transitions

| From | Event | To | Notes |
|---|---|---|---|
| submitted | DISPATCH | working | Creates the first Run |
| submitted | INPUT_REQUEST | input_required | No active execution without dispatch |
| submitted | ERROR | failed | Terminal failure |
| submitted | CANCEL | canceled | Coordinator authority |
| submitted | RECONCILE | submitted or other legal state | Audited recovery only |
| working | ACK | working | Same Run becomes active execution |
| working | INPUT_REQUEST | input_required | Worker needs a decision |
| working | INPUT_PROVIDED | working | Same Run resumes |
| working | HANDOFF | working | Run becomes succeeded; Task awaits review |
| working | REVIEW | working | Review or revision request |
| working | APPROVAL | working | Scoped authority recorded |
| working | ERROR | working | Run becomes failed; Task remains workable |
| working | CANCEL | canceled | Terminal Task state |
| working | RECONCILE | legal state | Recovery with evidence |
| input_required | INPUT_PROVIDED | working | Same Run continues after decision |
| input_required | CANCEL | canceled | Coordinator withdraws work |
| input_required | RECONCILE | legal state | Audited recovery |
| completed | ordinary execution | rejected | Terminal Task |
| failed | ordinary execution | rejected | Terminal Task |
| canceled | ordinary execution | rejected | Terminal Task |
| rejected | ordinary execution | rejected | Terminal Task |

### Task terminal states

Terminal states are:

- `completed`;
- `failed`;
- `canceled`;
- `rejected`.

A terminal Task does not accept ordinary execution Events. Later work uses a new
Task or a formally audited reconciliation that the contract permits.

## Run state machine

A Run is one execution attempt.

```text
   dispatch
      │
      ▼
 ┌────────────┐   ACK / execution
 │ dispatched │
 └─────┬──────┘
       │
       ▼
 ┌──────────┐
 │ working  │
 └─┬────┬──┘
   │    │
   │    └──────────► canceled
   │
   ├───────────────► succeeded
   └───────────────► failed
```

### Run transitions

| From | Event | To | Actor |
|---|---|---|---|
| absent | DISPATCH | dispatched | coordinator |
| dispatched | ACK | working | addressed worker |
| dispatched | ERROR | failed | addressed worker or coordinator |
| dispatched | CANCEL | canceled | coordinator |
| working | HANDOFF | succeeded | same worker |
| working | ERROR | failed | same worker |
| working | CANCEL | canceled | coordinator |
| succeeded | ordinary execution | rejected | any |
| failed | ordinary execution | rejected | any |
| canceled | ordinary execution | rejected | any |

### Run identity rules

- DISPATCH creates the Run id.
- Later execution Events reference the same id.
- A second DISPATCH for the same id is rejected.
- A second ACK for the same id is rejected.
- A Run cannot move from terminal back to active.
- Retry and revision create a new Run id.
- HANDOFF from a different worker does not close the Run.

## Coordinator claim state machine

A Channel claim is mutable coordinator writer authority.

```text
   unclaimed
      │ acquire
      ▼
   owner A, generation 1
      │ migrate / takeover with authority
      ▼
   owner B, generation 2
      │ migrate
      ▼
   owner C, generation 3
```

### Claim rules

- A claim has one owner and a monotonic generation.
- A routed write must match the current owner and generation.
- Migration creates a new generation; it does not rewrite Events.
- Process restart does not imply ownership.
- Directory ownership does not imply claim ownership.
- A stale coordinator write is fenced out.
- Repair of a claim projection must not silently change canonical Event
  semantics.

## Execution-view state machine

An execution view is a clean, task-run-scoped Git checkout.

```text
   absent
     │ acquire
     ▼
  acquired ───── dirty/foreign bytes ───► refused
     │
     │ work + HANDOFF delivery
     ▼
  releasable
     │ release
     ▼
  released
```

### Acquire

Acquisition proves:

- the requested repository is the expected relay;
- the remote ref is reachable;
- the local session path is stable;
- the view is absent or already clean at the expected head.

Acquisition refuses to delete or repair foreign bytes. A dirty view fails
closed.

### Use

While acquired:

- one Run owns the view;
- the worker binds exact Task and endpoint identity;
- unrelated Runs use different views;
- a stale view is not repaired by discarding unknown changes;
- HANDOFF must be delivered before release.

### Release

Release requires:

- the Run is terminal in canonical history;
- HANDOFF for that Run is published;
- the view has no uncommitted bytes that the owner intends to keep.

If publication failed, release refuses. The worker reconciles delivery; it does
not abandon the Run.

## Bridge request state machine

A bridge request has its own small lifecycle.

```text
   absent
     │ coordinator writes intent
     ▼
  pending
     │ bridge-process
     ├──► published
     ├──► rejected
     └──► skipped (result already exists)
```

### Request rules

- A request is a non-canonical intent, not an Event.
- The filename and request id must match.
- The repository and path are exact.
- Canonical internals are forbidden.
- The action class is allowlisted.
- The expected base must be reachable.
- The idempotency key belongs to the logical mutation.
- A published request is not executed again.
- A rejected request writes no canonical bytes.

## Event replay machine

Replay is read-only. It walks Events in sequence order and folds them into
current state.

```text
   TASK_CREATED
        │
        ▼
   validate predecessor
        │
        ▼
   apply transition
        │
        ├── invalid ──► stop with first error
        │
        ▼
   next event
        │
        ▼
   current Task/Run projection
```

### Replay rules

- Sequence must be contiguous.
- Predecessor id and hash must match.
- Event hash is recomputed.
- Task transition must be legal.
- Run transition must be legal.
- DISPATCH must be first for its Run.
- ACK must follow the same Run.
- HANDOFF must be authored by the Run's executor.
- Terminal Runs do not reopen.
- Idempotency conflicts are reported.
- Replay never executes a side effect.

## Expected-head state machine

Expected-head CAS protects one Task chain.

```text
   head H
     │ compose
     ▼
   append C(H)
     │
     ├── remote still H ──► publish C(H)
     │
     └── remote advanced to H2
             │
             ▼
        reject C(H)
             │
             ▼
        replay H2 and recompose C2(H2)
```

### CAS rules

- Capture the base or head immediately before composition.
- The ref update is non-force.
- A mismatch never overwrites the remote value.
- The same semantic mutation is recomposed, not retried with a new
  idempotency key.
- If the newer state makes the mutation illegal, request a new Run.

## Input-request state machine

A worker can pause the same Run for a missing decision.

```text
   working
      │ INPUT_REQUEST
      ▼
   input_required
      │
      ├── INPUT_PROVIDED ──► working
      ├── CANCEL ───────────► canceled
      └── timeout/recovery ─► audited reconciliation or failure
```

INPUT_REQUEST does not create a new Run. INPUT_PROVIDED continues the same Run
only when the current contract and expected head allow it.

## Review and revision state machine

```text
   HANDOFF / run succeeded
        │
        ▼
      REVIEW
        │
        ├── accept ────────► complete Task
        ├── revision ─────► new Run
        ├── approval ─────► scoped side effect
        └── block ─────────► input_required or new Task
```

A revision never reopens the succeeded Run. A new Run references the review or
causation that required it.

## Reconciliation state machine

RECONCILE is not a normal execution state transition. It records audited
recovery when the ordinary Run model cannot describe the situation.

```text
   detected inconsistency
        │ contain
        ▼
   preserve evidence
        │ audit
        ▼
   RECONCILE or new Task
        │
        ▼
   regression test
```

Reconciliation must not:

- rewrite an old Event;
- change an artifact hash;
- impersonate a worker;
- grant public authority;
- hide a failed publication.

## State precedence

When fields disagree, use this precedence:

1. canonical Event history;
2. Task manifest plus referenced artifacts;
3. repository validation and replay result;
4. workspace binding;
5. issue or task-card projection;
6. chat summary;
7. newest commit or recency heuristic.

A lower layer never overrides a higher layer.

## Combined execution example

```text
Task:   submitted → working → working → working → working → completed
Run:    absent    → dispatched → working → input_required → working → succeeded
Events: CREATE     DISPATCH    ACK         INPUT_REQUEST     INPUT_PROVIDED  HANDOFF/REVIEW
```

The Task does not become completed merely because the Run succeeded. Coordinator
review and any required approval still have to be canonical facts.

## Validation checklist

For every new Event, ask:

- Is the Task transition legal?
- Does a DISPATCH create a new Run?
- Does a non-DISPATCH Event reference an existing Run?
- Is the Run transition legal?
- Is the actor the Run executor where required?
- Is the recipient the addressed worker?
- Is expected head current?
- Is the claim owner/generation valid for a routed write?
- Is the Task terminal?
- Does the idempotency key conflict?

If any answer is unknown, the Event is refused.
