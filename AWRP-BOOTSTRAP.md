# AWRP Bootstrap

This is the public snapshot entrypoint for a fresh coding-agent or coordinator
session. For the full walkthrough, read `docs/BOOTSTRAP.md`, then
`protocol/WORKER-CONTRACT.md`.

## 1. Read before acting

1. `README.md` — product overview and runnable quick start.
2. `protocol/AWRP-0.1.md` — protocol and compatibility rules.
3. `protocol/WORKER-CONTRACT.md` — canonical execution contract.
4. `docs/ARCHITECTURE.md` — identity, state, and recovery model.
5. `docs/SECURITY.md` — protected properties and trust boundaries.

The public repository contains protocol code and synthetic examples, not
production relay state.

## 2. Evaluate in a disposable root

```bash
python tools/awrp.py init-context --root .demo --context-id ctx_demo --title "Evaluation"
python tools/awrp.py project-create --root .demo --project-id project_alpha --channel channel_alpha --title "Evaluation project"
python tools/awrp.py create-task --root .demo --context-id ctx_demo --project-id project_alpha --channel-id channel_alpha --worker-endpoint codex_demo --title "Evaluate" --goal "Create, validate, and replay a synthetic task." --worker codex_demo
python examples/demo_flow.py
```

Never point a public demonstration at production state.

## 3. Restore existing work

1. Sync with `git pull --ff-only`; stop on failure.
2. Read `tasks/<task_id>/task.json` and every file under `events/` in `seq` order.
3. Run `validate` and then `replay` for that exact Task.
4. Derive state, phase, waiting-on, Run id, recipient, and authority from the
   replay result. Projections, chat summaries, and commit recency are not
   authority.

```bash
python tools/awrp.py validate --task-dir <relay>/tasks/<task_id>
python tools/awrp.py replay --task-dir <relay>/tasks/<task_id>
```

## 4. First-bind a fresh worker

```bash
python tools/awrp.py first-bind --relay <owner/repository> --project-id <exact> --channel <exact> --worker-endpoint <exact> --task-id <exact>
```

Obey the reported verdict. Only EXECUTE authorizes work. NO_TASK means no
current dispatch; AMBIGUOUS returns authority to the human; OWNED means another
logical owner holds the run; invalid canonical state must be contained and
audited.

## 5. ACK before material work

On EXECUTE, emit ACK for the exact reported `run_id` and expected head
immediately, and never ask the human to confirm the ACK. The ACK records accepted
authority and history; it does not mean the work is finished.

## 6. Execute and hand off

Perform only work permitted by the Task and the current authority. Never run
the same `run_id` twice. A retry or revision creates a new Run.

Before declaring completion:

1. verify the change with the narrowest relevant checks and the full suite;
2. reference exact commit or artifact identity;
3. emit a canonical HANDOFF for the same Run;
4. deliver and verify that HANDOFF;
5. report remaining risk and the next owner.

A local success message without a durable HANDOFF is incomplete.

## 7. Recover safely

- Lost publication race: re-sync, replay, recompose, append again; never force.
- Stale expected head: re-read and recompose; never overwrite.
- Missing or ambiguous binding: stop and request exact identity.
- Corrupt chain: contain, preserve evidence, audit, and record an incident.
- Delivery failure after local work: reconcile HANDOFF delivery; do not repeat
  the source or public side effect.

## 8. Public snapshot boundary

Do not add production `projects/`, `channels/`, `contexts/`, `incidents/`,
`tasks/`, or `bridge/requests/` state to this repository. Do not add private
project names, credentials, personal data, or customer data. The executable
boundary is `tests/test_public_snapshot.py`.
