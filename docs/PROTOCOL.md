# Protocol Walkthroughs

This document demonstrates the protocol through small, synthetic examples. All identifiers are fictional. The examples are intentionally verbose so a reader can trace identity, history, and authority without access to production state.

## 1. Task creation

A Task starts in `submitted` / `intake`. The creator supplies a goal and the coordinator derives canonical bytes:

```json
{
  "protocol": "awrp/0.1",
  "task_id": "task_20260101T000000Z_example01",
  "title": "Verify a guarded dispatch",
  "goal": "Prove that the worker ACKs the exact dispatched run before work.",
  "state": "submitted",
  "phase": "intake",
  "waiting_on": "coordinator_alpha",
  "source_repo": null,
  "source_issue": null,
  "created_by": "coordinator_alpha",
  "integrity": {
    "task_hash": "sha256:computed-by-validated-composer"
  }
}
```

The first Event is always `TASK_CREATED`. A creator cannot select a ready execution state or bypass event composition.

## 2. Guarded dispatch

The coordinator knows:

```text
project_id   = project_alpha
channel_id   = channel_alpha_review
endpoint     = codex_alpha
task_id      = task_20260101T000000Z_example01
run_id       = run_20260101T001000Z_example01
expected_head= evt_task_created
```

`plan-dispatch` proves that the route and binding agree. `dispatch-guarded` recomputes the route and expected head immediately before composing the Event.

```json
{
  "protocol": "awrp/0.1",
  "event_id": "evt_20260101T001000Z_dispatch01",
  "seq": 2,
  "prev_event_id": "evt_task_created",
  "prev_event_hash": "sha256:...",
  "type": "DISPATCH",
  "actor": {"role": "coordinator", "id": "coordinator_alpha"},
  "recipient": {"role": "worker", "id": "codex_alpha"},
  "run_id": "run_20260101T001000Z_example01",
  "state": "working",
  "phase": "implementation",
  "waiting_on": "codex_alpha",
  "run_state": "dispatched",
  "summary": "Implement and verify the approved change.",
  "integrity": {"event_hash": "sha256:computed-by-validated-composer"}
}
```

The worker endpoint is part of identity. A dispatch intended for `codex_alpha` is not valid for `codex_beta`.

## 3. Worker discovery

Discovery is channel- and endpoint-scoped:

```bash
python tools/awrp.py inbox \
  --root <relay> \
  --channel channel_alpha_review \
  --worker-endpoint codex_alpha
```

The result may include multiple tasks. A lane can narrow the view, but it does not replace the channel/endpoint checks. The worker still validates the full event chain for the exact task it intends to execute.

## 4. Expected-head CAS

Before ACK, the worker captures the current Task head:

```json
{
  "task_id": "task_20260101T000000Z_example01",
  "head_event_id": "evt_20260101T001000Z_dispatch01",
  "head_event_hash": "sha256:...",
  "head_seq": 2
}
```

The ACK names that exact head. If another valid append lands first, the ACK fails closed. The worker re-reads and revalidates instead of overwriting the newer history.

## 5. ACK

```json
{
  "type": "ACK",
  "actor": {"role": "worker", "id": "codex_alpha"},
  "recipient": {"role": "coordinator", "id": "coordinator_alpha"},
  "run_id": "run_20260101T001000Z_example01",
  "state": "working",
  "phase": "implementation",
  "waiting_on": "codex_alpha",
  "run_state": "working",
  "summary": "Accepted."
}
```

The ACK proves acceptance of the history head and authority. It does not mean the work is complete.

## 6. Input request

Suppose implementation reveals a product decision that the Task policy does not authorize the worker to make. The worker emits `INPUT_REQUEST`:

```json
{
  "type": "INPUT_REQUEST",
  "run_id": "run_20260101T001000Z_example01",
  "state": "input_required",
  "phase": "clarification",
  "waiting_on": "coordinator_alpha",
  "run_state": "working",
  "summary": "Choose between the two compatible storage layouts."
}
```

The worker must not invent the product/security decision. The coordinator records the decision in a new Event; the worker then resumes the same Run only if the current contract permits it and the expected head matches.

## 7. Input provided

```json
{
  "type": "INPUT_PROVIDED",
  "run_id": "run_20260101T001000Z_example01",
  "state": "working",
  "phase": "implementation",
  "waiting_on": "codex_alpha",
  "run_state": "working",
  "summary": "Use option B; the decision is recorded in the task policy."
}
```

The input response does not create a new Run. It advances the same authorized attempt after a blocking question.

## 8. HANDOFF

The worker verifies the change and emits a canonical HANDOFF:

```json
{
  "type": "HANDOFF",
  "run_id": "run_20260101T001000Z_example01",
  "state": "working",
  "phase": "review",
  "waiting_on": "coordinator_alpha",
  "run_state": "succeeded",
  "summary": "Implemented, tested, and documented the change.",
  "details": "Verification: 42 tests passed. Artifact: commit abc123."
}
```

A HANDOFF without a preceding ACK for the same Run is rejected. Local completion does not substitute for canonical delivery.

## 9. Review

The coordinator replays the chain, checks the artifact, and emits `REVIEW`:

```json
{
  "type": "REVIEW",
  "run_id": "run_20260101T001000Z_example01",
  "state": "working",
  "phase": "revision",
  "waiting_on": "codex_alpha",
  "run_state": "succeeded",
  "summary": "One compatibility case is missing; revision required."
}
```

A revision does not reopen the succeeded Run. The coordinator creates a new Run with a new ID and a new expected head.

## 10. Approval

Approvals bind to exact output. If the worker changes the output after approval, the old approval no longer authorizes the new bytes.

```json
{
  "type": "APPROVAL",
  "state": "working",
  "phase": "publication",
  "waiting_on": "coordinator_alpha",
  "summary": "Approved public PR creation for commit abc123 only."
}
```

The approval records the target class and exact output identity. A later commit is not covered.

## 11. Completion

After review and required approvals, the coordinator emits `RECONCILE` or the contract's completion transition to `completed`. Terminal state is a projection over the event chain, not a mutable flag that can be edited independently.

## 12. Failure and retry

A failed Run records the failure reason and terminal Run state:

```json
{
  "type": "ERROR",
  "run_id": "run_20260101T001000Z_example01",
  "state": "working",
  "phase": "implementation",
  "waiting_on": "codex_alpha",
  "run_state": "failed",
  "summary": "Verification failed; no public side effect occurred."
}
```

Retry uses a new Run:

```text
run_20260101T001000Z_example01  failed
run_20260101T020000Z_example02  dispatched
```

The same Run never changes from failed back to working.

## 13. Cancellation

Cancellation is an explicit coordinator decision:

```json
{
  "type": "CANCEL",
  "state": "canceled",
  "phase": "closed",
  "waiting_on": "coordinator_alpha",
  "run_state": "canceled",
  "summary": "Requirement withdrawn; no further execution authorized."
}
```

Workers do not infer cancellation from silence or a newer unrelated task.

## 14. NOTE

NOTE carries durable, review-relevant information without authorizing execution:

```json
{
  "type": "NOTE",
  "state": "working",
  "phase": "review",
  "waiting_on": "coordinator_alpha",
  "summary": "Verification evidence is stored at the referenced commit; the same Run was not re-executed."
}
```

This is useful after a delivery problem: it records evidence without pretending that the original side effect happened twice.

## 15. Append-only violation examples

The following are invalid:

- changing the `seq` of an existing Event;
- replacing an Event to change its summary;
- recomputing a later hash to hide an earlier edit;
- deleting a HANDOFF and appending a replacement at the same sequence;
- accepting a branch that rewrites canonical history.

The validator reports the first broken link. Recovery uses a new audited event or a new Run; it does not mutate the old chain.

## 16. Hash canonicalization

The event hash is computed over canonical JSON after excluding the `integrity.event_hash` field itself:

```text
UTF-8
ensure_ascii = false
sorted keys
compact separators
```

The exact byte recipe is part of the protocol contract. Pretty-printed display files and projections are not hashed as canonical event bytes unless the contract explicitly says so.

## 17. Idempotency

A bridge request carries an opaque `idempotency_key`. Replaying the same request does not create a second event. The result file distinguishes:

- `published` — canonical bytes were written;
- `rejected` — nothing canonical was written;
- `skipped` — a result already exists.

A coordinator that sees `rejected` fixes the cause and submits a new request with a fresh base. It does not blindly retry the same mutation.

## 18. Multiple projects

A worker window may attach to more than one project, but focus is explicit. `switch` changes the current project/task/run focus; it does not infer identity from a directory name or the most recent chat.

`check-lineage` verifies pasted history. A claim that a run finished is evidence to verify, not authority to skip directly to completion.

## 19. Public/private boundary

The public reference snapshot contains protocol code and synthetic examples only. Production relay directories and private identifiers are intentionally absent. This prevents a documentation example from becoming an accidental state export.

## 20. Minimal operator checklist

Before approving a public effect, confirm:

- Task is non-terminal.
- Run is active and matches the worker endpoint.
- ACK exists for the same Run.
- HANDOFF names exact output and verification.
- Approval matches the current commit SHA.
- Remote head has not advanced unexpectedly.
- Publication path is the approved target class.
- The resulting external object is read back and verified.
