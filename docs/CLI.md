# CLI Reference

The reference CLI is `tools/awrp.py`. It uses only the Python standard library and exposes protocol operations through explicit arguments.

## Command groups

### Context and task intake

- `init-context` — create a semantic grouping context.
- `create-task` — create a Task and its initial `TASK_CREATED` event.
- `recover-task` — derive recovery guidance for an existing Task.
- `plan-task-create` — compose a new Task without writing it.
- `inbox` — list actionable tasks for an exact channel/endpoint or Task.

### Validation and replay

- `validate` — verify manifest, sequence, hash links, and state projection.
- `replay` — derive Task state, phase, waiting-on, active Run, and idempotency facts.
- `render-card` — render a human-readable Task projection.
- `doctor` — diagnose a relay or workspace.
- `audit-chain` — inspect canonical event history.
- `audit-history` — compare committed history with append-only expectations.
- `audit-fencing` — inspect claim generation and coordinator write fencing.
- `audit-dispatch-identity` — verify recipient and endpoint identity across dispatches.

### Event composition

- `emit` — append a validated event with expected-head CAS.
- `compose-intent` — compose canonical bytes from a constrained envelope.
- `bridge-preflight` — validate a bridge request and print planned writes without side effects.
- `bridge-process` — process pending bridge requests through validated composers.
- `render-bootstrap` — generate an exact first-bind instruction from canonical state.

### Publication

- `publish-preflight` — prove publication preconditions and planned refs.
- `publish-atomic` — commit and push canonical bytes on a captured head.
- `publish-connector` — print or execute a connector publication plan.
- `worker-retry-push` — bounded retry after losing an append race.
- `publish-ephemeral` — publish from a disposable clean clone when the primary checkout is coupled.
- `artifact-hash` — compute the stable hash of a review artifact.

### Project routing

- `project-create` — create a Project and Channel route.
- `project-assign-channel` — attach a Channel to a Project with validation.
- `resolve-project` — resolve exact identity from an explicit hint.
- `project-snapshot` — render a project's current route and tasks.
- `audit-projects` — check project/channel consistency.
- `migration-associate` — associate a legacy Task with an exact Project.
- `probe-project` — report `PROJECT_BIND_REQUIRED`, `AMBIGUOUS`, or an exact route.

### Worker binding and focus

- `bind` — write a local workspace binding after validating the route.
- `first-bind` — sync, bind or verify, validate, replay, and report a safe verdict.
- `resume` — derive the current actionable Run for a bound workspace.
- `attach` — record exact Project interest without changing focus.
- `switch` — switch focus to an exact Project/Task/Run.
- `focus` — resolve the current focus against canonical state.
- `check-lineage` — verify pasted Task/Run history.

### Coordinator writes

- `plan-dispatch` — derive route, heads, fingerprint, and planned publication.
- `dispatch-guarded` — recheck the route and atomically compose a dispatch.
- `acquire-claim` — acquire or migrate a channel coordinator claim.
- `read-claim` — read current claim owner and fencing generation.
- `migrate-claim` — perform an explicit claim-generation transition.
- `repair-claim` — audit and repair only the allowed claim projection.

### Execution views

- `execution-view-acquire` — create or verify a clean task-scoped Git view.
- `execution-view-release` — remove a verified view only after HANDOFF delivery.

### Incident registry

- `incident-create` — create a confirmed protocol/coordination incident.
- `incident-update` — append evidence, remediation, or resolution to an incident.
- `incident-show` — render one incident.
- `incident-list` — filter incidents by status, severity, or category.
- `incident-audit` — validate incident discovery and event chains.
- `incident-rebuild` — rebuild derived incident projections.

## Common patterns

### Inspect a Task

```bash
python tools/awrp.py validate --task-dir tasks/<task_id>
python tools/awrp.py replay --task-dir tasks/<task_id>
python tools/awrp.py render-card --task-dir tasks/<task_id>
```

### Plan before publishing

```bash
python tools/awrp.py plan-dispatch \
  --binding-root <workspace> \
  --task-id <task_id>
```

Review the plan. Then publish through the guarded path rather than hand-authoring an Event.

### Bind a fresh worker

```bash
python tools/awrp.py first-bind \
  --relay <owner/repository> \
  --project-id <project_id> \
  --channel <channel_id> \
  --worker-endpoint <endpoint> \
  --task-id <task_id>
```

### Resume a bound session

```bash
python tools/awrp.py resume --root <workspace>
```

### Append an event safely

```bash
python tools/awrp.py emit \
  --task-dir <task-dir> \
  --type NOTE \
  --actor-role worker \
  --actor-id <endpoint> \
  --recipient-role coordinator \
  --recipient-id <coordinator> \
  --state working \
  --phase review \
  --waiting-on <coordinator> \
  --summary "Evidence recorded without re-executing the run." \
  --expected-head <current-head>
```

## Exit behavior

The CLI fails closed on invalid history, missing identity, stale expected heads, unauthorized side effects, ambiguous routes, and publication races. A non-zero exit is a safety signal; do not work around it by editing canonical files.

## Composition versus projection

Commands that create or append canonical bytes use validated composers. Commands that render cards, indexes, or instructions are projections and do not grant authority.

## Public snapshot limitation

The public snapshot does not contain production `projects/`, `channels/`, `contexts/`, `incidents/`, `tasks/`, or `bridge/requests/` state. Use a disposable root to evaluate the CLI.
