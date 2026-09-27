# ChatGPT / Coordinator Adapter Notes

AWRP v0.1 does not assume one specific ChatGPT connector.

A coordinator only needs to:
1. read Context and Task manifests
2. enumerate/fetch Event files
3. validate/replay state
4. obtain the next canonical bytes from a validated composer
   (`plan-task-create` for a new Task, `publish-connector --print-plan`
   or `dispatch-guarded` for appends) — never hand-author them
5. publish those exact bytes through the connector transport
6. optionally update human projections such as `TASK.md` or a GitHub Issue

Correctness must not depend on Issue-comment write support. The canonical operation is create-new-file at a new event path with composer-produced bytes.

## Connector composition contract (normative)

1. Connectors (GitHub API, file creation, `git`, `gh api`) are
   transport/persistence only. They carry bytes; they do not author
   canonical Task/Event semantics.
2. A conforming coordinator MUST NOT hand-author canonical Task/Event
   semantic JSON. Canonical bytes must come from AWRP's validated
   composer path: `create-task` / `emit` / `dispatch-guarded` /
   `publish-atomic` / `publish-connector` locally, or `plan-task-create`
   / `publish-connector --print-plan` output executed verbatim through
   the connector.
3. Merely recomputing `integrity.event_hash` is not semantic validation
   (the historical `state = ready` incident had a hand-computed hash on
   illegal semantics and still failed canonical validation).
4. If a coordinator environment cannot invoke a validated
   composer/planner, it must fail closed rather than publish a
   hand-written canonical Event.
5. Three categories, never confused: (a) conforming coordinator
   publication (composer bytes + CAS rules); (b) out-of-band repository
   corruption or non-conforming writes (arbitrary writers cannot be
   technically prevented from pushing garbage — detect via validate /
   audit, never execute from it); (c) worker/discovery fail-closed
   containment (invalid chains stay invisible and un-ACKable).

For a GitHub-backed relay, a ChatGPT connector uses repository file
creation strictly as the transport for composer-produced bytes; a
computer-side worker can use `git` or `gh api` the same way.

## Connector end-to-end runbook (no user transport)

This is the supported machine path from a coordinator decision to a
bound worker discovering the run, with no human carrying payloads.
(The Agent window may still need a wake/resume action where the
runtime does not poll; waking is not carrying.)

New Task, connector-executed (GitHub Git-Database API names):

1. read relay state: get the task dir listing (must 404 for a new
   task), `projects/<id>.json`, and the branch head SHA (this is the
   captured base; pass it as `--expected-base`).
2. obtain exact bytes: `compose-intent --root <relay> --intent-file
   <intent.json> --actor-role coordinator --actor-id <claim-owner>
   --expected-base <base>` where the intent file carries ONLY a
   constrained envelope — `{"action": "create-task"|"dispatch"|"review"|
   "approval"|"reconcile", "idempotency_key": "<opaque>", "params":
   {exact content/reference fields}}`. Run the repository's
   `tools/awrp.py` (stdlib only, importable anywhere) — independently
   reimplementing the output contract is NOT a supported path, even
   byte-exactly, because only the validated composer enforces state,
   ownership, fencing, chain, and CAS rules. Initial state is always
   `submitted`/`intake`; the envelope has no knob for anything else,
   and unknown envelope keys are rejected.
3. publish: `create-blob` ×3 (task.json, event JSON, TASK.md
   projection) → `create-tree` with `base_tree` from the captured
   base → `create-commit` with `parents=[base]` → `update-ref
   refs/heads/<branch>` with `force:false`. A 422/non-fast-forward
   means another writer won: re-read, re-plan, recompose — never
   force.
4. read back: fetch the event file, recompute `event_hash` (hash
   recomputation here is verification of fetched bytes, never authorship
   of new semantics), run the equivalent of `validate`, and only then
   treat the message as sent. A follow-up DISPATCH for the first run
   uses the same blob/tree/commit/ref pattern with a `compose-intent`
   `dispatch` envelope plus `dispatch-guarded` semantics (route proof +
   expected head + fencing where claimed).

The standing capability rule: safety hardening must keep this path
end-to-end usable. It is guarded in-suite by a connector-style
plan→transport→discovery fixture; any change that breaks that fixture
is a P0 regression regardless of which gate it came from.

## Remote bridge: request file plus Actions-executed composer

When the coordinator runtime has connector writes but no repository
checkout, the supported path is NOT reimplementation — it is a
constrained intent request plus a repository workflow that runs the
real validated composer:

- The coordinator writes ONLY `bridge/requests/<request_id>.json`
  (filename stem equals `request_id`): `{protocol, request_id,
  action, idempotency_key, expected_base, params}` with the same
  per-action exact params as `compose-intent`. Forbidden anywhere in
  the request: `event_id`, `seq`, prev link/hash, `event_hash`,
  `integrity`, fencing objects, actor identity, and any other
  canonical-JSON keys. Actor identity and fencing generation are
  derived live from the channel claim by the bridge, never supplied.
- `.github/workflows/awrp-bridge.yml` (triggered only by request
  paths, never by result files or canonical task paths) checks out the
  repo and runs `tools/awrp.py bridge-process` per unresulted request.
  The workflow file contains no canonical semantics — only file
  iteration and CLI invocation (statically guarded in-suite).
- `bridge-process` validates the request, composes through the shared
  validated paths (`_plan_new_task` / `_prepare_event`), materializes
  plan bytes verbatim (round-trip hash re-verified, tasks/-confined,
  create/append-only with the TASK.md projection exception),
  validates, then commits request result plus canonical files and
  pushes non-force with post-verification. Every failure mode records
  a `rejected` result that is itself committed and pushed, so the
  coordinator can poll `bridge/requests/<id>.result.json`
  (`published` / `rejected` / `skipped` for idempotent replay).
- Recursion is impossible by construction: result commits match the
  trigger exclusion, canonical commits match no trigger path, and
  replays short-circuit on the recorded result.
- Required token scope is `contents: write` on the relay repo; branch
  protection requiring reviews would fail the push closed (documented
  limitation, never worked around with force).

## Coordinator publication integrity gate

A coordinator MUST NOT hand-author canonical semantics, and MUST NOT
hand-enter an `integrity.event_hash` and then treat the Event as
dispatched without verification. New Tasks start exclusively through
`create-task` or `plan-task-create` (initial state is fixed to
`submitted`; there is no supported knob for anything else).

Before announcing or relying on a newly published Event, the coordinator MUST:

1. compute the Event hash with `tools/awrp.py` canonicalization (`ensure_ascii=false`, sorted keys, compact separators, UTF-8, `integrity.event_hash` removed before SHA-256), or a byte-equivalent implementation;
2. write the Event to the Relay;
3. fetch/read the stored Event back from the Relay;
4. recompute and verify its `event_hash`, `prev_event_id`, `prev_event_hash`, and `seq` against the actual preceding Event;
5. when practical, run the equivalent of `tools/awrp.py validate` / replay before telling a worker to execute.

Semantic fields MUST NOT be edited after the hash is calculated without recomputing the hash before publication.

If post-write validation fails, the Event is not execution authorization and the worker must not proceed from it.

## Canonical connector publication (publish-connector)

Reference implementation: `tools/awrp.py publish-connector` (no working-tree
mutation; `--print-plan` dry-runs the whole gate sequence and prints the
plan below without touching the repo or the remote).

Preconditions (all fail closed before any publication):
1. captured remote head (`git ls-remote <remote> <branch>`) equals the
   `--expected-base` the event was composed against;
2. current `channels/<id>/claim.json` exists; `actor.role == coordinator`
   and `actor.id == <claim owner>`; `--fencing-generation` equals the live
   claim generation;
3. `--expected-head` / `--expected-hash` equal the live task chain head;
4. the new event path `tasks/<task_id>/events/<seq>_<event_id>.json` does not
   yet exist at the captured base (append-only).

GitHub Git-Database-API equivalent (same guarantees, no clone needed):
1. create-blob: the canonical event JSON (`ensure_ascii=false`, indent 2,
   trailing newline; `integrity.event_hash` over the canonical form);
2. create-blob: the rendered `TASK.md` projection for the new head;
3. create-tree with `base_tree` = the captured head commit's tree and the two
   blobs at their task paths;
4. create-commit with `message`, `tree`, `parents` = [captured head SHA];
5. update-ref `refs/heads/<branch>` to the new commit SHA with `force: false`
   — a 422 / non-fast-forward means another writer won: stop, re-read,
   recompose, never force.

## Invalid pre-canonical Event repair boundary

Create-only Events remain the normal rule. An integrity repair is an exceptional recovery path, not normal mutation.

If an Event has **never passed canonical validation** and the assigned worker confirms that it performed **no task side effects and no ACK** from that invalid Event, the coordinator may repair only integrity metadata required to make the already-written semantics validate. Any dependent downstream integrity links/hashes may be recomputed without changing semantic fields. The repair must then be recorded by a new `RECONCILE` Event.

If semantic fields are disputed, or any worker/source/public side effect already occurred from the invalid Event, do not rewrite history under this exception; stop and recover through a new explicit Task/Run or other audited recovery path.

Suggested new-window command:

> Restore AWRP context `<context_id>` from `<owner>/<relay-repo>` and continue from canonical state.

## Project trigger vs Agent bootstrap (first window)

“这个项目使用 AWRP” is a ChatGPT-side trigger, not an Agent-side bootstrap
phrase. On the first window for a project, ChatGPT MUST:

1. resolve the project route: read `projects/<project_id>.json`, confirm the
   channel belongs to that project, create the project route first if it
   does not exist — never let the user invent channel/run/claim ids;
2. dispatch the exact task/run to the project's worker endpoint;
3. generate one strong Agent first-bind instruction naming relay,
   project_id, channel_id, worker_endpoint, and the exact task_id (plus
   run_id when a single run is authoritative).

The Agent then runs `tools/awrp.py first-bind` with exactly those values:
sync ff-only, bind-or-verify the workspace, validate/replay the exact
target, and report EXECUTE / NO_TASK / OWNED. The Agent ACKs only the
matching active run with the reported expected head, and never scans
globally or across projects. After durable binding, normal same-workspace
interaction may reduce to “继续”.

Normative: the bare phrase with the same meaning is explicitly INVALID as a
fresh Agent instruction — it carries no project/channel/endpoint/task
identity and MUST NOT be acted on. A fresh window without an exact
project/task instruction must stop (`probe-project` reports
`PROJECT_BIND_REQUIRED` / `AMBIGUOUS` and never selects).

Deterministic instruction generation: `tools/awrp.py render-bootstrap
--root <relay> --project-id <project> --task-id <task> [--run-id <run>]`
validates project ownership and the exact task route from canonical state
and prints the exact `first-bind` parameters plus the ready command. It
takes exact ids only and never scans for a likely project; use its output
verbatim as the Agent's first-bind instruction.

## Notion AWRP Identity block (coordinator-facing)

Relay worker code never calls Notion. Resolution is split: the
coordinator resolves human references (name/alias/semantic pointer)
against the canonical Notion project page, then the Relay layer works
only from the resolved exact `project_id` (`resolve-project`,
`project-snapshot`, `attach`/`switch`). Every governed Notion project
page carries an AWRP Identity block with exactly:

- Canonical Project Name
- Project ID (stable; equals Relay `project_id`)
- Aliases (exact strings; Relay matches them exactly, duplicates across
  projects are ambiguous, never first-match). Matching is per-field and
  deterministic: an alias equal to another project's title still resolves
  in alias-space only — cross-field meaning is a coordinator-side
  judgment, never Relay inference.
- Relay Repository
- Canonical Notion Page ID (self identity; Relay stores it opaquely as
  `notion_page_id`, legacy `notion` URL stays readable for compat)
- Project Boundary
- Known Routing (hints only — never execution authority)
- Status

Two Relay Projects claiming one canonical Notion page ID is an
integrity error (`audit-projects` detects it). A Project pointing at a
noncanonical/parallel page is detectable exactly when the pointed ID
differs from the page's self identity — compare, never guess. Note:
older Second Brain text may still contain channel-first sections
followed by a Project-first correction; only the Project-first
semantics are canonical for new behavior.

## Human phrasebook (route IDs stay internal)

The human speaks project/task semantics; the coordinator translates to
exact Relay identity before the Agent ever sees route internals:

- “this project uses AWRP” → trigger only. Resolve the canonical
  project (Notion page → exact `project_id` via `resolve-project`),
  dispatch or locate the exact task/run, then hand the Agent one exact
  instruction (`first-bind` / `attach`+`switch` with relay, project,
  channel, endpoint, task, run). Never forward the bare phrase.
- “continue the current project” → continue the bound workspace's resolved
  focus (`resume`/`focus`); if focus is missing or stale, re-resolve
  explicitly instead of guessing newest.
- “switch to project B” → coordinator resolves the human label to one exact
  `project_id` first (AMBIGUOUS stays with the human); only then
  `switch` the session. Never switch on name similarity.
- “that task finished” → the worker records HANDOFF on the
  exact run; anyone else treats the claim as lineage to verify
  (`check-lineage`), not as fact.

Channel/lane/run/claim ids surface to the human only on ambiguity or
failure. No UI, dashboard, or server is involved — this is wording
discipline plus the existing exact-identity commands.

Coordinator responsibilities:
- proactively record confirmed AWRP-system incidents (`incident-create` /
  `incident-update` where a checkout exists, `incident-create` /
  `incident-update` bridge intents otherwise; reporter_role coordinator) —
  containment first when needed, recording without a human asking, evidence
  required, source-project bugs excluded (see `incidents/README.md`)
- research/pre-flight before coding dispatch
- choose worker explicitly
- create each new Run
- review HANDOFF artifacts
- request revisions via a new Run
- record scoped human approvals
- reject stale approval when output changed
- expose conflicts instead of silently resolving them
- verify Relay Event integrity after publication before authorizing execution
