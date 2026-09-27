# Failure Modes

AWRP is designed around a small set of recurring coordination failures. This
document describes how each failure appears, why it is dangerous, what the
protocol does, and how an operator should recover.

## Wrong-recipient execution

### Symptom

A worker receives or discovers a Task that looks authorized, but the dispatch
was intended for a different endpoint, lane, project, or channel.

### Why it matters

The worker may perform work that is valid for the Task but not assigned to this
session. Two workers can race on the same Run, or a session can operate in the
wrong project boundary.

### Protocol response

- DISPATCH carries an explicit recipient id.
- The worker compares the recipient with its configured endpoint before ACK.
- `inbox` requires an exact channel, endpoint, lane, or Task identity.
- A mismatched recipient cannot be ACKed as that worker.
- A binding that cannot prove exact identity fails closed.

### Recovery

1. Do not ACK or execute.
2. Report the exact Task, recipient, and local endpoint mismatch.
3. Ask the coordinator to publish a correctly addressed Run if work is still
   needed.
4. If the wrong worker already acted, record an incident and do not let the same
   Run execute again.

## Global discovery by recency

### Symptom

A fresh session sees several projects or Tasks and chooses the newest, the most
recently mentioned, or the one whose directory name looks closest.

### Why it matters

Recency is not identity. A worker can bind to the wrong project and receive
credentials or source access outside its intended boundary.

### Protocol response

- Project, Channel, and Task identity are explicit.
- `first-bind` requires exact relay, project, channel, endpoint, and Task id.
- `resume` reads a binding and validates it against canonical state.
- `AMBIGUOUS` is a valid terminal verdict for discovery.

### Recovery

Stop. Request exact identity. Do not broaden the search until something matches.

## Stale expected head

### Symptom

An append is rejected because the Task head changed after the command planned or
composed it.

### Why it matters

Blindly overwriting the newer append would erase a valid fact. Ignoring the
mismatch would create two events at the same sequence.

### Protocol response

Every append names the previous head. The writer re-reads, replays, and composes
against the new head. The losing writer does not mutate the winner's event.

### Recovery

1. Pull fast-forward-only.
2. Validate and replay the Task.
3. Confirm that the semantic operation is still allowed.
4. Recompose a new append against the current head.
5. If the Task changed materially, request a new Run instead of retrying.

## Non-fast-forward publication

### Symptom

A plain push is rejected because the remote branch advanced.

### Why it matters

Force-pushing would hide a competing event, rewrite canonical bytes, and make
delivery history untrustworthy.

### Protocol response

AWRP composes on a captured base and pushes without force. A bounded retry may
recompose byte-identical content after re-sync, but it may not rewrite history.

### Recovery

Pull, replay, validate, recompose, and push again. If the remote chain no longer
matches the expected protocol version, stop.

## Duplicate side effects after delivery failure

### Symptom

Local work succeeds, but HANDOFF publication fails. A retry restarts the whole
implementation instead of reconciling delivery.

### Why it matters

Source pushes, issue comments, PR creation, and other public effects are not
naturally idempotent. Re-running them can duplicate or overwrite work.

### Protocol response

The Run remains the same until HANDOFF is delivered. Recovery paths reconcile
the canonical append and do not authorize the source side effect again.

### Recovery

1. Confirm the source artifact and commit identity.
2. Re-sync the relay.
3. Recompose only the HANDOFF or an audited reconciliation.
4. Deliver and verify it.
5. Do not repeat the implementation.

## Duplicate Run execution after restart

### Symptom

A worker process restarts and cannot see whether it already executed the Run.
It runs the work again.

### Why it matters

The same authorization can then produce two source or public effects.

### Protocol response

- The worker ACKs the exact Run.
- Later events attach to the same Run.
- A duplicate ACK or terminal transition is rejected.
- A retry or revision uses a new Run id.

### Recovery

Replay canonical history. If the Run is terminal, reconcile delivery. If the
Run is still active and the prior worker cannot prove non-execution, stop and
request a new authorized Run.

## Corrupted event chain

### Symptom

Sequence, predecessor id, predecessor hash, or recomputed event hash does not
validate.

### Why it matters

A partially trusted chain can authorize the wrong work or hide a prior edit.

### Protocol response

The validator reports the first broken invariant. Replay refuses to treat the
Task as canonical.

### Recovery

1. Stop execution.
2. Preserve refs, commits, and files.
3. Identify the earliest broken link.
4. Do not delete or replace the bad event.
5. Record an incident.
6. Create a new Task or audited reconciliation.

## Hand-computed event with illegal semantics

### Symptom

An integration recomputes a valid-looking event hash over a hand-authored event
whose state transition or route is illegal.

### Why it matters

A hash proves byte integrity, not semantic correctness. A plausible hash can
make an illegal event look authentic.

### Protocol response

Canonical bytes must come from validated composers. Semantic validation checks
transitions, recipient identity, route, and fencing after hash validation.

### Recovery

Reject the hand-authored event, preserve it as evidence, and republish through
the composer if the operation is still authorized.

## Two coordinators write one channel

### Symptom

Two coordinator windows believe they own the same Channel and both prepare
valid-looking writes.

### Why it matters

Without fencing, the last writer could silently replace the other writer's
intent.

### Protocol response

The claim has an owner and monotonic generation. Routed writes must match the
current claim. Expected-head checks serialize Task appends.

### Recovery

Determine the canonical claim owner from history. Migrate the claim explicitly
if needed. The old owner re-syncs and recomposes; it does not force.

## Two workers share one mutable checkout

### Symptom

Parallel Runs use one checkout. One Run's uncommitted files, branch, or index
state contaminates another.

### Why it matters

Workers can test the wrong code, publish the wrong diff, or block each other
during synchronization.

### Protocol response

Task-run-scoped execution views are the default for parallel work. A view is
acquired from a known head and released only after HANDOFF delivery.

### Recovery

Stop both runs before external effects. Preserve artifacts. Recreate clean
views from canonical heads. Do not discard foreign bytes without identifying
their owner.

## Worker receives an ACK for a Run it never ACKed

### Symptom

Replay shows an ACK event for the worker endpoint, but the current process has
no memory of the earlier session.

### Why it matters

The Run may already be executing or finished. Re-executing it is unsafe.

### Protocol response

Canonical history, not process memory, decides. An active Run with ACK is not a
new authorization.

### Recovery

Read the latest events and artifacts. If terminal, reconcile. If active, contact
the owner or coordinator before doing anything.

## Public-object mutation through a relay tool

### Symptom

An integration passes issue, PR, comment, label, merge, release, branch, or
upstream fields to a transport-write tool.

### Why it matters

A relay-write boundary is often assumed to be a full GitHub policy boundary.
Passing public mutation parameters can turn a narrow connector into a broad one.

### Protocol response

The transport facade rejects unknown action classes and mutation parameters
before delegation. It exposes only a validated relay write.

### Recovery

Reject the request, audit the integration, and keep the host's native public
tools outside the relay transport. A repository facade cannot reconfigure a host
router that runs before repository code.

## Bridge request requests canonical internals

### Symptom

A connector submits `seq`, `event_hash`, `prev_event_id`, fencing generation,
actor identity, or other canonical fields.

### Why it matters

The connector would be authoring semantics, not intent. Malformed or forged
canonical bytes could reach publication.

### Protocol response

The bridge schema forbids canonical internals. The repository composer derives
them from current state.

### Recovery

Reject the request, fix the connector, and submit a new request with a fresh
expected base. Do not copy rejected bytes into a hand-authored event.

## Bridge request replays

### Symptom

A network retry sends the same bridge request again.

### Why it matters

A duplicate DISPATCH, HANDOFF, or approval can corrupt the intended sequence.

### Protocol response

The request id and idempotency key are stable. A result file records published,
rejected, or skipped. A repeated request does not create a second event.

### Recovery

Read the result. If skipped, no new action is needed. If rejected, fix the
protocol or base before submitting a new request.

## Project and Channel ownership conflict

### Symptom

A Channel is attached to a second Project, or a coordinator writes through a
Channel owned by another Project.

### Why it matters

Ownership drift makes routing ambiguous and can expose one project's Task to
another coordinator.

### Protocol response

`project-create`, `project-assign-channel`, and routing validators check
ownership. A conflicting assignment fails closed.

### Recovery

Audit the Project registry and Channel owner. Migrate explicitly. Do not delete
one side of the conflict to make validation pass.

## Context mistaken for routing authority

### Symptom

A worker scans Contexts or uses a Context title to find actionable work.

### Why it matters

A semantic group can contain Tasks from different projects or channels. Context
membership does not grant execution authority.

### Protocol response

Inbox and binding use Project, Channel, endpoint, lane, or exact Task identity.
Context is descriptive.

### Recovery

Resolve the exact route from canonical Task data, then bind or act on that
route.

## Local binding points at the wrong checkout

### Symptom

`.awrp/binding.json` names a relay directory or repository that no longer
matches the current Task.

### Why it matters

Resume could validate a different history and present it as the current work.

### Protocol response

Binding validation checks the relay and Task route. A dangling or mismatched
binding fails closed.

### Recovery

Obtain the exact relay, Project, Channel, endpoint, and Task id, then rebind.

## Terminal state is edited directly

### Symptom

An operator edits `task.json` to change `completed` to `working`, or replaces a
terminal Event.

### Why it matters

The manifest and history now disagree. The edit hides what actually happened.

### Protocol response

Audit and validation detect the mismatch. Ordinary execution Events cannot
append to a terminal Task.

### Recovery

Restore evidence, record an incident, and use a new Task or audited
reconciliation. Do not keep the direct edit.

## Approval is reused for changed output

### Symptom

A human approved commit A, the worker produced commit B, and the coordinator
publishes B under the old approval.

### Why it matters

Approval is intended to bind human review to exact output.

### Protocol response

Approval references should include the output identity. The publication path
must compare the approved artifact with the current one.

### Recovery

Pause publication, obtain approval for B if appropriate, and record the new
scope.

## Large payload in Event history

### Symptom

Logs, patches, screenshots, or binaries are embedded in Event details.

### Why it matters

History becomes hard to read, replay, and validate. Large payloads also create
merge and transport pressure.

### Protocol response

Events carry concise semantic facts and artifact references. Artifact hashes
provide integrity.

### Recovery

Store the payload as an artifact, reference it by commit or hash, and append a
NOTE describing the evidence.

## Private state copied into a public example

### Symptom

A documentation example includes real Project, Task, Run, or bridge-request
identifiers.

### Why it matters

Even without credentials, operational history can expose private work, routing,
and people.

### Protocol response

The public snapshot uses synthetic identifiers and excludes production state
directories. A boundary test scans the publishable tree.

### Recovery

Remove the private content before publication, replace it with synthetic data,
and add a regression test for the marker class.

## Failure-handling summary

| Failure | Automatic response | Operator action |
|---|---|---|
| Wrong recipient | ACK refused | Report mismatch |
| Ambiguous identity | Bind/inbox refused | Request exact route |
| Stale head | Append refused | Re-sync and recompose |
| Non-fast-forward | Push refused | Re-sync and recompose |
| Duplicate Run | Transition refused | Reconcile or new Run |
| Corrupt chain | Replay refused | Preserve and audit |
| Claim mismatch | Routed write refused | Acquire or migrate claim |
| Delivery failure | Canonical state unchanged | Reconcile HANDOFF only |
| Bridge replay | Idempotent skip | Read result |
| Terminal edit | Validation failure | Incident and new Task |

The common rule is simple: preserve history, stop unsafe work, and create a new
authorized fact instead of rewriting an old one.
