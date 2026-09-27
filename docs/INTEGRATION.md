# Integration Guide

AWRP can be integrated through a local Git checkout, a connector that writes
validated intents, or the minimal MCP transport facade. All three modes keep
protocol semantics in repository code; integrations only carry bytes.

## Integration goals

A correct integration should make these properties obvious:

1. Canonical bytes are composed by AWRP, not by an integration adapter.
2. Identity is explicit: Project, Channel, Task, Run, actor, and recipient.
3. Publication is compare-and-swap against a captured remote head.
4. A lost race causes recomposition, never force-push.
5. A repeated request is idempotent.
6. A local success is not reported as canonical completion before HANDOFF
   delivery is verified.

## Choose a transport

### Local Git checkout

Use the local transport when the coordinator or worker already has a checkout
of the relay repository.

Recommended flow:

```bash
git pull --ff-only
python tools/awrp.py validate --task-dir tasks/<task_id>
python tools/awrp.py plan-dispatch --task-dir tasks/<task_id> --channel <channel_id> --worker-endpoint <endpoint>
python tools/awrp.py dispatch-guarded --task-dir tasks/<task_id> ...
git push origin <branch>
```

Use plain pushes. Do not use force, merge, or rebase to publish a canonical
append.

### Connector transport

A connector without a checkout can compose a connector publication plan:

```bash
python tools/awrp.py publish-connector \
  --task-dir <task-dir> \
  --print-plan \
  --remote <owner/repository> \
  --branch <branch>
```

The plan contains the exact tree, commit, and non-force ref update. The
connector may create the referenced blobs, tree, and commit, but it must not
recompute protocol semantics or force the ref.

After the connector writes, read the remote ref and canonical files back. A
successful API response alone is not proof that the intended chain is now the
branch head.

### Bridge transport

The bridge is for constrained, repository-backed coordinator writes that do not
have a local checkout. The coordinator writes a request under:

```text
bridge/requests/<request_id>.json
```

The request carries intent, idempotency key, expected base, and typed
parameters. It must not carry canonical event internals such as
`event_hash`, `seq`, `prev_event_id`, fencing generation, or actor identity.

The GitHub Actions workflow runs:

```bash
python tools/awrp.py bridge-process --root . --all-pending --remote origin --branch main
```

The workflow uses the validated composer, commits the canonical bytes, and
pushes without force. A result file records whether the request published,
rejected, or was skipped.

The public snapshot intentionally contains the workflow contract but no
production request directory.

### MCP stdio facade

The MCP facade exposes one tool, `awrp_transport_write`. Start it explicitly:

```bash
python tools/awrp_mcp_transport.py --base-dir <relay-checkout>
```

The tool accepts only a transport-write intent for the configured repository
and an exact bridge request path. Unknown actions, path drift, repository
drift, and public-mutation parameters are rejected before a delegate is
invoked.

The facade does not reconfigure a host application's native tool router. Host
configuration must expose only the intended MCP server if the restriction is
to apply to the whole session.

## Worker integration

A worker session should persist a small local binding. The binding is a
convenience pointer, never canonical authority. It records the relay
repository, local relay directory, Project, Channel, endpoint, optional lane,
Task id, and optional Run id.

On a fresh wake:

1. read the binding;
2. ensure the relay checkout is fast-forwarded;
3. run `resume`;
4. obey the verdict;
5. validate and replay the exact Task before material work.

Verdicts:

| Verdict | Meaning | Action |
|---|---|---|
| `EXECUTE` | Exact route and authority are proven | ACK the reported Run immediately |
| `NO_TASK` | Bound route has no actionable Task | Do nothing and report idle |
| `AMBIGUOUS` | More than one target could match | Stop; request exact identity |
| `OWNED` | Another logical owner holds the Run | Do not execute |
| invalid canonical | Chain or binding cannot be trusted | Contain and audit |

## Coordinator integration

A coordinator should separate planning from publication:

1. resolve exact Project and Channel identity;
2. acquire or verify the channel claim;
3. read the current Task state and head;
4. plan the dispatch route;
5. recompute the guard immediately before composing;
6. publish on the captured head;
7. read back and validate.

Route planning prevents a common failure: a semantically valid DISPATCH
delivered to the wrong worker, lane, or project. The guard is intentionally
close to composition so a binding change between planning and publication is
detected.

## Approval integration

Public or destructive effects should be represented as approvals that bind to:

- action class;
- target domain;
- exact repository;
- exact commit or artifact hash;
- authorized actor;
- single-use or expiry semantics when appropriate.

Approval does not transfer to a new commit, another repository, another action
class, or a broader target set.

A common safe pattern is:

```text
worker HANDOFF(commit A)
coordinator review(commit A)
human approval(public PR for commit A)
coordinator publication(commit A)
```

If the worker changes the output to commit B, repeat review and approval.

## Idempotency

Every externally retried mutation needs an idempotency key. The key identifies
the logical operation, not the transport attempt.

A repeated bridge request with the same key returns the existing result or a
skipped status; it does not create a second event. A repeated worker retry
recomposes byte-identical canonical content and fails closed if the current
remote state no longer matches.

Do not use a new idempotency key to retry the same semantic mutation after a
CAS race. Re-sync, replay, and recompose against the new head first.

## Expected-head compare-and-swap

Compare-and-swap has three parts:

1. capture `expected_base` or `expected_head`;
2. compose canonical bytes against that exact value;
3. update the ref without force.

If the ref advanced, the mutation lost the race. Re-read the new canonical
state and decide whether the operation is still semantically valid. If yes,
compose a new append. If no, reject and request a new authorized Run.

Never resolve a race by force-pushing the losing history.

## Multi-window behavior

Two coordinator windows writing the same channel are serialized by claim
generation and expected-head checks. Two worker windows attempting the same
Run are exposed by recipient identity, ACK state, and single-execution rules.

If local checkouts would couple unrelated parallel Runs, acquire a clean
execution view per Run:

```bash
python tools/awrp.py execution-view-acquire --root <session-dir> --relay <owner/repository> --task-id <task_id> --run-id <run_id>
python tools/awrp.py first-bind --relay-dir <view> --project-id <exact> --channel <exact> --worker-endpoint <exact> --task-id <exact>
```

Release the view only after HANDOFF delivery is verified:

```bash
python tools/awrp.py execution-view-release --root <session-dir>
```

## Host boundaries

Repository code cannot prevent a host from invoking a different tool, changing
model output, or exposing credentials. Host controls remain responsible for:

- tool visibility and routing;
- secret storage and injection;
- network and process isolation;
- user confirmation for sensitive actions;
- model and dependency trust.

AWRP narrows protocol authority and canonical mutation. It does not replace
host security.

## Error handling

Integration code should map errors into three classes:

| Class | Examples | Response |
|---|---|---|
| Retryable transport | timeout, temporary 5xx | Retry the same idempotent request |
| CAS conflict | non-fast-forward, stale head | Re-sync and recompose; do not force |
| Protocol denial | wrong recipient, invalid state, ambiguous route | Stop and report; do not retry blindly |

A protocol denial is not a transient network error. Retrying the same request
without changing the protocol facts only creates noise.

## Integration test checklist

- Wrong worker endpoint cannot ACK.
- Wrong project or channel cannot claim a Task.
- Stale expected head cannot append.
- A repeated bridge request does not duplicate an Event.
- A connector plan uses a non-force ref update.
- MCP rejects unknown action classes and public mutation parameters.
- HANDOFF without ACK is rejected.
- A failed publication race does not mutate canonical history.
- A fresh binding is validated against the relay before resume.
- A synthetic public snapshot contains no production state.

## Minimal host configuration

A host that wants AWRP enforcement should:

1. run the reference tools from a pinned checkout;
2. expose only the AWRP MCP server for relay writes;
3. keep other GitHub or issue tools disabled or separately approved;
4. inject secrets outside the repository;
5. log tool inputs without secret values;
6. preserve canonical task directories outside temporary workspaces;
7. run `tests/test_awrp.py` before upgrading the pinned revision.

This configuration is stricter than the protocol alone. The protocol states
what is authorized; the host configuration decides which tools can be reached.
