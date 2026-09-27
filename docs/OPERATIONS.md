# Operations Runbook

This runbook describes how to operate an AWRP relay without turning recovery
into guesswork. It is written for a human authority, a coordinator, and a
worker that share a canonical Task history.

## Operating principles

1. Canonical state is the Task manifest plus complete event history.
2. Every Run id is single-use.
3. Every append names the exact previous head.
4. Every public or destructive effect needs scoped authority.
5. A lost race is recomposed, never forced.
6. A local success without durable HANDOFF is incomplete.
7. Ambiguity stops work.

## Repository layout

A production relay may contain:

```text
projects/       project identity and channel ownership
channels/       durable coordinator/worker boundaries and claims
contexts/       semantic grouping, not routing authority
tasks/          canonical Task manifests and event history
incidents/      confirmed protocol/coordination incidents
bridge/         constrained coordinator transport requests
protocol/       normative contract
schemas/        machine-readable shapes
tools/          reference implementation
```

The public snapshot ships the last four areas plus tests and examples, not the
production state areas.

## Daily start

### Coordinator

1. Fast-forward the relay.
2. Inspect open Tasks and claims.
3. Identify Tasks waiting on the coordinator.
4. Verify that each waiting Task has a valid active Run and a current head.
5. Review pending approvals before authorizing publication.
6. Do not reopen a terminal Task without an audited reconciliation.

### Worker

1. Read the local binding.
2. Fast-forward the relay or refresh the task-scoped execution view.
3. Run `resume` for the bound route.
4. If the verdict is EXECUTE, validate and replay the exact Task.
5. ACK the reported Run before material work.
6. Execute only the authorized scope.
7. Verify and deliver HANDOFF.

## Task intake

A new Task should contain:

- exact Project id;
- Channel id;
- optional lane id;
- worker endpoint;
- title and goal;
- side-effect policy;
- creator and coordinator identity;
- source issue or repository when relevant.

`create-task` refuses an incomplete execution manifest unless the caller
explicitly marks a historical task with `--legacy`. The legacy marker is a
migration tool, not a shortcut for new work.

Before creating a Task, verify that the Project owns the Channel. A Channel
with an existing owner cannot be silently reassigned.

## Dispatch

Use `plan-dispatch` to inspect:

- exact route;
- current Task head;
- binding agreement;
- claim generation;
- planned publication target.

Then use `dispatch-guarded` to recheck the route at composition time.

A raw DISPATCH on an owned channel is rejected unless the caller explicitly
uses the legacy route marker. This prevents a coordinator with a stale or
missing binding from publishing a valid-looking event to the wrong worker.

## Worker execution

Before each material side effect, confirm:

- the Task is non-terminal;
- the latest authoritative Run is the one being executed;
- a DISPATCH exists for this worker endpoint;
- an ACK exists for the same Run;
- the expected head still matches;
- the side effect is permitted;
- any required approval matches the exact output.

If a decision is missing, emit INPUT_REQUEST. Do not invent product, security,
legal, or human-policy decisions.

## Verification

Choose the narrowest meaningful check first, then run the full suite for a
release or protocol change.

A good verification record contains:

```text
Changed: exact behavior or file.
Focused check: command and result.
Full check: command and result.
Build/compile: command and result when applicable.
Artifact: commit SHA or content hash.
Residual risk: what remains outside the verified boundary.
Next owner: coordinator or human authority.
```

Do not report a test that was not run. Do not report a remote object as
published until it is read back.

## HANDOFF

A HANDOFF is the worker's durable completion claim. It should name:

- outcome;
- exact files or artifacts changed;
- verification commands and results;
- known limitations;
- follow-up owner;
- the same Run id that was ACKed.

Persist the HANDOFF with expected-head CAS. If publication races, re-sync and
recompose. Do not repeat the implementation side effect.

## Coordinator review

Review the canonical chain, not only the worker's summary.

1. Validate the Task.
2. Replay the Task.
3. Confirm the Run state and executor.
4. Read the HANDOFF details.
5. Inspect the artifact or commit.
6. Re-run the relevant verification when risk warrants it.
7. Record REVIEW or APPROVAL in canonical history.

A worker claim that a run finished is evidence to verify, not authority to skip
review.

## Approval

Approval is scoped, not general. It should name the exact target class and
output identity. Examples:

- create a public pull request for commit `abc123` in repository `owner/name`;
- publish one release artifact with hash `sha256:...`;
- merge pull request 42 only after CI is green.

Approval expires when the output changes. It does not authorize a different
action class or a broader target.

## Publication

Normal append publication:

1. capture the remote head;
2. compose canonical bytes against that head;
3. write create-only files;
4. commit;
5. push without force;
6. read back the ref and canonical files;
7. validate again.

A non-fast-forward result is a normal race outcome. Re-sync, replay, and
recompose. Never force-push, merge away, or rebase away canonical history.

## Recovery matrix

| Symptom | Likely cause | Safe action |
|---|---|---|
| `stale expected head` | Another valid append landed | Re-read, replay, recompose |
| `non-fast-forward` | Remote ref advanced | Re-sync and recompose |
| `ambiguous route` | Multiple project/task candidates | Stop; request exact identity |
| `wrong recipient` | Dispatch endpoint mismatch | Do not ACK; report mismatch |
| `task already has ACK` | Duplicate or concurrent worker | Do not execute again |
| `invalid canonical chain` | History corruption or tampering | Contain and audit |
| `binding relay missing` | Local pointer is stale | Stop; refresh exact binding |
| `claim owner mismatch` | Wrong coordinator writer | Acquire/migrate claim explicitly |
| `HANDOFF delivery failed` | Local work complete, canonical append missing | Reconcile delivery only |
| `bridge rejected` | Invalid request or stale base | Inspect result; fix and resubmit |

## Claim and fencing operations

A channel claim has an owner and monotonic generation. Coordinators acquire the
claim before routed writes and pass the generation to write paths.

If a coordinator window dies:

1. verify the current claim owner and generation;
2. determine whether the old owner can resume;
3. migrate the claim explicitly if needed;
4. replay the Task;
5. recompose the next append.

Do not repair claim projection by editing a live claim file without the
protocol's audited repair command.

## Bridge operations

A bridge request is pending when it has no result file. Process pending
requests in a bounded sweep. Each request must be:

- shape-valid;
- action-allowlisted;
- bound to the configured repository and exact path;
- free of canonical event internals;
- based on a reachable expected base.

Result states:

- `published` — canonical bytes were written and verified;
- `rejected` — nothing canonical was written;
- `skipped` — a result already exists.

A repeated request must not create a second event.

## Incident handling

An incident is a confirmed protocol, governance, routing, fencing, transport,
recovery, host-integration, or documentation failure. Suspicion is not an
incident. Ordinary source-project bugs are not AWRP incidents.

Containment first:

1. stop the affected action;
2. preserve logs, refs, and canonical files;
3. do not rewrite history;
4. identify the first invalid link or failed invariant;
5. record the incident with append-only evidence;
6. add a regression test;
7. recover with a new authorized Run or audited reconciliation.

## Recovery after a corrupt chain

If validation fails:

- do not execute from partially trusted state;
- do not delete the bad Event to make replay pass;
- identify the earliest invalid sequence or hash;
- determine whether a later valid chain exists on another ref;
- if not, create a new Task or Run with an explicit reconciliation record;
- retain the corrupt evidence for audit.

## Backup and restore

Git history is the durable store. A restore should:

1. clone or fetch the canonical repository;
2. verify the ref and commit identity;
3. validate each in-flight Task;
4. replay before resuming;
5. compare local bindings with canonical identity;
6. re-point execution views only after validation.

Do not treat a chat transcript or a copied file as a backup unless its commit
and canonical chain are verified.

## Monitoring

Useful operational signals:

- Tasks waiting on a coordinator for longer than the agreed window;
- active Runs with no ACK;
- HANDOFF delivery failures;
- repeated CAS races on one Task;
- ambiguous bindings;
- claim generation churn;
- bridge rejection rates;
- invalid canonical chains.

Metrics should be derived from canonical history, not mutable projections.

## Maintenance

Before changing protocol code:

1. write or identify a failing regression test;
2. run the focused test and observe the expected failure;
3. implement the smallest correct change;
4. run the focused test;
5. run the complete suite;
6. update protocol, schema, README, and adapter docs together;
7. verify no public-boundary test was weakened.

Protocol changes that alter canonical semantics require a compatibility plan.
Purely additive fields may remain on the same wire version when old readers fail
closed safely.

## Public release checklist

- no production state directories;
- no credentials or private bindings;
- no personal or customer data;
- no internal project names in examples;
- full test suite green;
- public-boundary tests green;
- CI green on the public repository;
- README commands execute;
- license/provenance statement is accurate;
- repository description is truthful;
- expected ghfind quality inputs are recomputed from current source.

## Human decisions

The human authority decides product scope, security tolerance, public
exposure, destructive actions, and acceptance. The protocol records those
decisions; it does not make them.
