# AWRP v0.1 Worker Contract

Applies equally to Codex, Claude Code, OpenCode, or another coding worker.

Behavioral clarification profile: **v0.1.5 cumulative** (v0.1.1 reviewability, v0.1.2 concurrency, v0.1.3 channel-first, v0.1.4 sessions/claims, plus `NOTE`, dispatch endpoint identity, and bounded publication transports). The wire protocol remains `awrp/0.1`; see `protocol/AWRP-0.1.md` §17 for the core/extension/legacy map.

## Before executing

1. Synchronize relay history without rewriting it.
2. Validate the assigned Task.
3. Replay current state.
4. Confirm Task is not terminal.
5. Confirm the Dispatch recipient id matches your configured worker id.
6. Confirm the `run_id` was not already executed.
7. Confirm requested side effects are permitted.
8. Emit `ACK` for the same run before material work.

If any check fails, stop. Do not repair canonical history by guessing.

### EXECUTE means act (no redundant human confirmation)

ACK is a machine ownership/executor claim, not a second human approval.
When `resume`, `first-bind`, or `focus` returns EXECUTE and all checks under
"Before executing" pass, the worker MUST immediately emit `ACK` for the
exact active `run_id` with the reported expected head, then begin the work
already authorized by the matching `DISPATCH`. The worker MUST NOT ask the
human or coordinator to confirm the ACK or to permit starting: a valid
EXECUTE verdict leaves no undecided authority question.

Human or coordinator input is requested ONLY at a genuine unresolved
authority boundary not already covered by the matching DISPATCH:

- AMBIGUOUS (more than one actionable task: resolve identity explicitly);
- OWNED or interrupted run (recovery decision: re-dispatch, bounded probe,
  or cancel — never silent re-execution);
- recipient/endpoint/channel/lane mismatch with this workspace;
- stale head/hash, terminal Task, or already-executed `run_id`;
- side effects outside the Task authorization (upstream PR/comment/merge,
  destructive operations: explicit scoped human approval required);
- a genuinely missing product/security/maintainer decision (`INPUT_REQUEST`
  and stop before the undecided side effect);
- explicit scope expansion beyond the DISPATCH.

Fail-closed verdicts stop the worker; they never authorize asking the human
to bless an otherwise-valid EXECUTE. Discovery commands only print verdicts
— the CLI never performs ACK or work on its own; the agent performs them.

## While working

Allowed local work may include reading source, reproducing, local editing, tests, local commits, and small relay artifacts.

Do not spam relay events with stdout/progress.

When a missing decision is required from human/coordinator/maintainer/product/security authority, emit `INPUT_REQUEST` and stop.

### Ephemeral execution views (multi-agent default)

Parallel task-runs share no mutable Relay checkout by default. Acquire one
task-run-scoped clean view per session (`execution-view-acquire`, stable
session dir, verified clean/at-tip or fail closed), bind against it with
`first-bind --relay-dir`, and release it only after verified HANDOFF
delivery (`execution-view-release`; uncertain state stays an inert orphan).
Reusing a view after a crash requires positively proven cleanliness,
identity, and freshness — otherwise create a new one. Unpublished commits,
dirty files, or divergence belonging to another window are never stashed,
reset, discarded, published, or waited on: they are foreign bytes. This
changes no freshness, CAS, fencing, routing, or publication authority —
independent Tasks must never acquire a synthetic dependency merely because
their local views collided.

### Proactive incident recording

A worker that confirms an AWRP-system incident during execution records it
in the Incident Registry without waiting to be asked: safety
containment / fail-closed action first when needed, then `incident-create`
(or `incident-update` on the existing open record for a repeated
manifestation). Only confirmed incidents with concrete evidence or a
reproducible coordination failure qualify — suspicion stays local, and
ordinary source-project bugs are never AWRP incidents. Hashes and canonical
bytes are composed by the CLI; the worker supplies only content fields.
Recording grants no execution authority and changes no Task/Run state.

### Post-run durable communication (NOTE)

After HANDOFF clears the active run, execution events can no longer carry
evidence — that rejection is correct and stays. For durable
worker→coordinator (or coordinator→worker) messages, emit `NOTE` instead
of reopening execution:

- `NOTE` is projection-neutral: state/phase/waiting_on must repeat the
  current head, and a referenced run's state must repeat the stored one.
  Only summary/details/artifacts narrative is new.
- It requires an explicit recipient, carries no fencing, opens no run, and
  may reference a known historical run or no run at all. Unknown runs,
  terminal tasks, and state/phase/waiting_on/run-state drift are refused.
- Provenance is bound at append: a run-referenced worker NOTE must come
  from the run's seated executor (or the DISPATCH recipient before any
  claim); a task-level worker NOTE must come from the task routing worker
  identity; a coordinator NOTE must come from the task coordinator.
  Attribution without authority — passing grants no execution right.
- Transport needs lineage, not just a tip: `worker-retry-push` carries a
  NOTE-tipped chain only when the tip NOTE descends directly from the
  requested run's legitimate executor close (consecutive same-run worker
  NOTEs, executor-authored throughout, closed stored state), with no
  intervening governance, superseding dispatch, other-run event, terminal
  state, or route drift. A post-NOTE coordinator tip or a newer run ends
  that run's transport authority.
- It changes no authority: active run, executor ownership, reviewability
  lineage, resume selection, and side-effect authorization are all
  untouched. A NOTE is never a substitute for ACK/HANDOFF/approval.
- Compatibility: readers older than this primitive fail closed on
  NOTE-bearing chains (unknown event type) — the safe direction. Upgrade
  tools before reading such chains; no canonical rewrite is ever needed.

## Completion

Emit `HANDOFF` with:
- concise summary
- verification performed
- remaining risks
- exact branch/commit SHA when code changed
- Artifact references
- any side effects already performed

### v0.1.1 code-reviewability rule

A HANDOFF that asks the coordinator to review code MUST make the exact reviewed bytes durable and remotely readable.

- If the code is committed: reference the exact repository + commit SHA. The commit SHA is the preferred review artifact.
- If any relevant code is uncommitted or untracked: create a **relay patch artifact** before HANDOFF.
- The patch artifact SHOULD be unified diff text and MUST include all relevant tracked and untracked code changes needed for review.
- Recorded `sha256`/`size_bytes` for patch artifacts are computed over LF-canonical bytes (`artifact-hash`); the coordinator MUST verify against LF-canonical bytes, never raw checkout bytes.
- Store it under the Task artifact directory, preferably `tasks/<task_id>/artifacts/<run_id>/working.diff`.
- The HANDOFF Artifact entry MUST include at least `kind=relay_patch`, `path`, `sha256`, and `size_bytes`.
- The patch artifact is a review snapshot only. It does not authorize commit, push, PR creation, merge, or any other publication side effect.
- If a patch cannot be generated completely, emit `INPUT_REQUEST` or `ERROR` rather than claiming the code is reviewable.

A local filesystem path, branch name, file list, or prose summary alone is not sufficient for coordinator code review.

### Completion-delivery invariant

A run MUST NOT be reported as successfully completed to the human until the
canonical HANDOFF has been durably written/pushed to the Relay (where the
Task requires Relay delivery) and delivery has been verified. If delivery
fails, do not redo already-performed source side effects; resume/reconcile
delivery first. Never execute the same `run_id` side effects twice.

A successful worker Run normally leaves the Task at:

```text
state: working
phase: review
waiting_on: chatgpt
run.state: succeeded
```

The coordinator/reviewer decides whether the entire Task is complete.

## Public actions

Do not perform public/upstream actions unless a matching scoped Approval or explicit Dispatch permits them. By default this includes upstream PR creation, upstream issue/PR comments, merge, close, and destructive operations.

### Command/authority matrix (non-host closure)

One table decides every append. `validate` derives per-run `executor`
(first ACK actor) and a task-wide `idempotency` key→event index;
`_prepare_event` enforces this matrix before any write, and any rejection
leaves zero canonical trace (rollback; projections render only after
validation succeeds).

| actor | event type | terminal task state? | rule |
|---|---|---|---|
| coordinator | TASK_CREATED | n/a (submitted) | valid context/project/channel ownership |
| coordinator | DISPATCH | never terminal | claim owner + fencing when the channel is claimed; no active run; routing/recipient identity: registered routing.worker_endpoint must equal recipient id, and worker waiting_on must equal recipient id (legacy tasks without a registered endpoint take documented compatibility, never guessed) |
| worker (executor) | ACK | never | first ACK wins; a second session stops as owned |
| worker, actor == executor | HANDOFF / INPUT_REQUEST / INPUT_PROVIDED / ERROR | never | worker completion (run.state) never equals Task acceptance |
| worker or coordinator | NOTE | never (terminal tasks refuse NOTE) | projection-neutral directed message; no authority change (see below) |
| coordinator | REVIEW / APPROVAL / CANCEL / RECONCILE | only a coordinator may set terminal states | claim owner + fencing when the channel is claimed |
| anyone | any append + idempotency_key | — | duplicate key refused, naming the recorded outcome event |

- RECONCILE is coordinator-only governance; workers report, never govern.
- REVIEW/APPROVAL attribute results, they do not execute: besides the active
  run they may reference the latest dispatched run ONLY when it is a
  legitimately closed reviewable succeeded result with valid HANDOFF
  lineage (normal post-HANDOFF acceptance); a latest failed/canceled/
  non-HANDOFF run does not qualify, older runs refuse as stale lineage,
  unknown runs refuse outright.
- A replacement worker needs CANCEL/RECONCILE plus a new DISPATCH (a new
  ACK seats a new executor); hijacking another executor's run is refused.
- `replay` exposes the idempotency index: an unknown key is a lookup miss,
  not an error; resubmission with a known key is refused with the outcome
  pointer, so duplicate/unknown command outcomes always recover explicitly.

## Idempotency

The same `run_id` MUST NOT execute twice. Seeing an old Dispatch again after restart is not authorization to redo it. A revision requires a new Run.

### Session resume ownership (v0.1.4 clarification, no wire change)

- A workspace binds once (`bind` writes `.awrp/binding.json`: relay,
  channel, worker endpoint, optional lane). Binding survives fresh sessions;
  it never lives in chat history, newest commit, mtime, or TASK.md.
- Fresh wake runs `resume`: sync ff-only, channel+endpoint (+lane) inbox,
  validate/replay each candidate, then exactly one of: NO_TASK (nothing
  actionable, no ACK), EXECUTE (exactly one unACKed task → ACK with the
  reported expected head, then work), AMBIGUOUS (>1 → stop, resolve
  explicitly, never silent FIFO), OWNED (active run already ACKed without
  HANDOFF → do not redo work, surface recovery).
- ACK is the machine claim: one ACK per run, enforced at append; a second
  session racing the same run loses deterministically and must stop as
  owned/interrupted. An optional `claimant` session id makes ownership
  auditable.
- Pushed canonical events are immutable. `audit-history` fails closed on
  modified/deleted/renamed event files versus the pushed ref; on remote
  advance, resync and append the next legal seq only — never delete, rename,
  replace, or re-emit a pushed event.

### Coordinator claims (v0.1.4 clarification, no wire change)

- One authoritative coordinator writer per channel: a mutable
  `channels/<id>/claim.json` carries a monotonic `generation`, acquired with
  CAS (`acquire-claim --expected-generation`); concurrent winners are
  impossible from the same prior generation.
- Coordinator canonical writes may pin `--fencing-generation`; stale fencing
  rejects the append before event creation. Legacy tasks have no claim
  domain and reject fencing.
- Takeover is explicit, human-authorized, and recorded (`takeover: true`,
  generation still increments, previous owner preserved). Read-only windows
  inspect via `read-claim` without owning.
- Claim files are mutable concurrency primitives; canonical events stay
  create-only. Claim operations MUST NOT alter existing event bytes
  (verifiable: re-validate + re-hash after every claim transition).
- Authority binding: on a channel with a live claim, routed coordinator
  mutations (DISPATCH/RECONCILE/REVIEW/APPROVAL/CANCEL, via `emit`,
  `publish-atomic`, or `publish-connector`) require `actor.role ==
  coordinator` AND `actor.id == <claim owner>`; anything else fails closed
  before any write. A worker event must never carry another owner's fencing
  identity (seq17-class bypass).
- Claim-history durability: every `acquire-claim` transition is appended to
  `channels/<id>/claim.log.jsonl`; commit and push `claim.json` AND
  `claim.log.jsonl` together. The log is the trust anchor for
  `audit-fencing` generation/owner checks — a clone without it silently
  degrades to compat-pass, so the history must travel with the claim.

### Multi-agent concurrency model (v0.1.2 clarification, no wire change)

- Parallel work across distinct Tasks/subtasks is supported.
- Concurrent execution or event appends for the same Task/run are not
  supported: one Task's canonical event chain is a single-writer serialized
  log. Races fail closed; never auto-merge, rebase, or force-push canonical
  history.
- A Task has at most one side-effect-authorized active Run at a time. A valid
  `DISPATCH` establishes it; `ACK`/`HANDOFF`/other execution events must
  belong to it (the CLI derives and enforces `active_run_id`; `REVIEW` /
  `APPROVAL` / `CANCEL` / `RECONCILE` stay coordinator-governed). A stale
  worker resuming from an old view must stop and re-sync/replay.
- Same `run_id` side effects execute at most once, even across workers.
- No leases, no expiry, no work stealing in v0.1.
- Coordinators fan out as Parent Task → independent subtasks per worker →
  integration/review, instead of assigning several workers to mutate one Task
  chain simultaneously.

### Channel-first routing (v0.1.3 clarification, no wire change)

- `channel_id` is the durable communication boundary between coordinator-side
  and worker-side endpoints (for example one channel per project workflow).
  `context_id` stays semantic grouping; `task_id` stays work identity; the
  coarse worker product id stays capability identity only.
- A logical worker endpoint (for example one per project chat/session) binds
  to exactly one channel by default; the same product in two projects MUST
  use distinct endpoint ids. Cross-channel execution fails closed even when
  the coarse recipient id matches.
- An optional lane/session identity may exist INSIDE a channel for concurrent
  workstreams, but MUST NOT replace channel isolation.
- Discovery is channel-scoped: `inbox --channel <id>
  [--worker-endpoint <id>]` scans canonical manifests/events (never TASK.md,
  mtime, chat history, or newest commit) and returns only valid, nonterminal,
  active-run tasks in that channel, FIFO by dispatch order. Exact
  `--task-id` is the unambiguous escape hatch; `--legacy` explicitly opts
  into unscoped legacy tasks. Bare global discovery is rejected.
- Never infer the intended channel from context_id, newest Relay commit,
  TASK.md, or chat history.

### Current execution context (sessions)

A Project is the stable canonical identity; GPT/Agent sessions are
dynamic participants that attach to one or more Projects without owning
them. Workspace-local session state lives in `.awrp/session.json`
(attached projects + current project/task/run focus) and never in
canonical history:

- `attach --root <ws> --project-id <id>` records read interest after
  verifying the project exists; attaching never takes over a coordinator
  claim and never selects work.
- `switch --root <ws> --project-id <id> [--task-id <t> [--run-id <r>]]`
  moves focus explicitly; the target must be attached, the task must
  belong to the project (intrinsic id or valid migration), and a named
  run must be the authoritative active run. A switch that would persist
  an actionable Task/Run focus proves Relay freshness first (stale view
  fails before any session mutation); project-only and run-less task
  focus are non-executing and stay lightweight.
- `focus --root <ws>` resolves the current focus against canonical state
  (`FOCUS_EXECUTE` with expected head/hash, `FOCUS_OWNED`, `FOCUS_STALE`,
  `FOCUS_NONE`, `FOCUS_PROJECT`) without scanning. `FOCUS_EXECUTE`
  additionally requires proven Relay freshness (`FOCUS_NOT_FRESH`
  otherwise); the other verdicts are non-execute and stay safe.
- Session writes are serialized with an exclusive lock file plus atomic
  replacement and a monotonic generation counter; a held lock fails the
  second writer instead of silently overwriting, stale locks are
  stealable, and corrupt pre-existing state fails closed with bytes
  preserved (only a truly absent file bootstraps).
- Sessions pin their Relay: the resolved Relay dir (and name when known)
  is stored at establishment, and later attach/switch/focus/lineage
  against another Relay dir is rejected — the same project_id on another
  clone is never reinterpreted. Pre-identity files migrate only via an
  explicit `--relay-dir`.
- `inbox --project <id>` lists actionable tasks carrying exactly that
  project id; `check-lineage` verifies a pasted
  project/task/run lineage against current focus and canonical state
  (intrinsic id, else exact valid migration — never channel membership
  alone) and fails closed or re-routes on conflict instead of
  reinterpreting it.
- Coordinator claims stay mutation authority only: attaching/reading
  never requires a claim, and only the fenced owner mutates protected
  Task/Run/channel state. Short commands like “继续” inherit the resolved
  focus; they never trigger global rediscovery.
- Lane pins are strict: a binding that pins a lane sees tasks carrying that
  lane plus lane-unset tasks of the same channel+endpoint (the coordinator
  cannot know a worker window's lane pin, so unset means any lane — the same
  wildcard the route-compat, first-bind visibility, and plan-dispatch checks
  already apply); lane-set tasks stay exclusive across lanes, and an unpinned
  binding that sees more than one actionable task
  reports AMBIGUOUS, never FIFO. `first-bind` requires an exact
  `--project-id`, refuses a requested lane crossing a pinned one, and
  returns EXECUTE only when the identical selection ordinary `resume`
  would make (single source of truth: `select_for_resume`). Bound-workspace
  DISPATCH has one normal path: generic `emit` / `publish-atomic` /
  `publish-connector` DISPATCH on a project-owned channel is rejected
  unless explicitly marked `--legacy-route` (legacy/internal only, never
  the coordinator's normal path). Coordinators plan with `plan-dispatch`
  (exact route + plan fingerprint, no run required) and publish with
  `dispatch-guarded` (revalidates route, fingerprint, and heads; `--publish`
  commits on the captured base and pushes non-force, so staleness fails
  before anything canonical). Fresh workspaces without a binding use the
  explicit `--no-binding` mode with a fully named route — never a silent
  fallback. Connector runtimes without a checkout publish exclusively
  through `bridge/requests/` intent files executed by the
  `awrp-bridge` workflow (`bridge-process`: shared validated composers,
  single CAS commit, recorded result, no recursion). New Tasks for connector publication start exclusively from
  `create-task` or `plan-task-create` (fixed `submitted` state, exact
  ownership-checked parameters, deterministic bytes plus an atomic API
  plan) — hand-authored creation is non-conforming. Coordinator intent
  flows through `compose-intent` (strict envelope, unknown keys
  rejected, same validated composers underneath) — never around it. Safety hardening
  must keep this end-to-end coordinator path usable; the in-suite
  connector-style fixture guards it as a standing P0 rule.

### Publication workflow (optimistic append)

1. `git pull --ff-only` (stop on failure).
2. Validate + replay; note the active run and the canonical task head
   (`head_event_id` / head hash, also shown as `active_run_id` by replay).
3. Append with `emit --expected-head <head_event_id>` (and/or
   `--expected-hash`); a stale head rejects the append before publication.
4. Commit the append (one Task dir per commit keeps history reviewable).
5. Run `publish-preflight` (checks local base vs remote branch head with
   plain `git ls-remote`; any advancement fails the preflight).
6. Plain `git push`; a non-fast-forward rejection is the final safety net.
7. On any race: stop, re-sync/replay, discard/recompose the unpublished event
   as a new append attempt. Never force-push, merge, or rebase canonical
   event files.

### Ephemeral canonical publication (stateless transport)

When the execution checkout itself is contaminated (unrelated local
commits, dirty state, untracked files) or long-lived while origin/main
moves, repairing that clone must never become a publication prerequisite.
`tools/awrp.py publish-ephemeral` decouples the two: the worker composes
events locally with `emit` (validating there), then publishes by importing
ONLY explicitly listed event/artifact bytes into a fresh disposable clone
of the current remote head:

- The execution workspace is only ever READ. No pull, rebase, merge,
  clean, or reset there — ever.
- Fresh-clone validation is authoritative: the first listed event must link
  onto the fresh remote head (same-task drift fails closed), already-present
  identical bytes are skipped idempotently, differing bytes collide and
  refuse, and `_worker_semantic_check` (recipient/route/active/lineage)
  re-proves authority in the scratch state.
- The scratch commit contains exactly the listed paths plus the rendered
  `TASK.md` (asserted before commit); unrelated local commits can never
  hitchhike. Push is plain non-force with bounded retries; each retry
  discards the scratch and re-clones. Scratch is always deleted.
- Compatibility with `worker-retry-push`: unchanged. Use retry-push for
  clean checkouts (in-place recompose); use publish-ephemeral when the
  execution clone is dirty, has unrelated local commits, or must stay
  untouched. Both enforce the same semantic checks; neither force-pushes,
  merges, rewrites canonical bytes, or transports unlisted history.

### Worker transport retry on unrelated-main drift (bounded)

When a plain push loses a race to an unrelated advance of origin/main, the
worker MAY use `tools/awrp.py worker-retry-push` instead of manual recovery,
and only for the safe case below. Repo-head drift is transport drift, not
semantic staleness — but only while every invariant in this section holds:

- The worker captured `--expected-base` (the remote head) before building its
  unpublished commits, and both local HEAD and the latest remote head still
  contain it. Anything else is rewritten/diverged history: stop.
- The worktree is clean (only committed work is transported) and the
  unpublished range changes no canonical byte: any modify/delete/rename of
  `tasks/*/task.json` or `tasks/*/events/*` refuses the retry. New event
  files (append-only adds) and mutable projections (`TASK.md`) are the only
  canonical-tree writes allowed.
- After fetching, the remote gap (`expected_base..remote_head`) MUST NOT
  touch `tasks/<task_id>/` (same-task advance is semantic staleness — there
  is no target-verified exception on the worker path), MUST NOT touch
  `channels/<channel_id>/` claim state (fencing authority moved), and MUST
  NOT overlap the unpublished file set (real contention, including shared
  tooling files).
- Before every recompose the helper re-verifies live authority: expected
  head/hash still the latest, non-terminal Task, unchanged DISPATCH
  recipient and route, plus narrow transport authority for the run itself:
  either the authoritative active run, or — when no run is active — exactly
  the run the current validated tip proves just closed through its closing
  worker HANDOFF (same run_id, worker actor, closed run state). Older,
  superseded, or otherwise non-tip runs never transport, even while the Task
  stays non-terminal; a later coordinator tip (e.g. REVIEW) removes a closed
  run's transport authority. Any move fails closed. (Liveness was enforced at
  append time; an unchanged tip proves no same-task advance since. There is
  no separate worker failure-closing event — failed closes travel as
  HANDOFF/failed under the same tip rule.)
- Recompose is a content-identical replay of the unpublished commits onto the
  latest transport head (conflict aborts with zero trace). Commit objects gain
  a new parent; canonical event file bytes MUST be LF-canonical-byte-identical
  afterwards (line-ending renormalization ignored, same doctrine as
  `artifact-hash`; any content change refuses publication). This is transport
  recomposition,
  not history rewriting: the target chain was never touched remotely, and no
  canonical byte ever changes — that is why the "never rebase" rule above
  still stands for everything except this verified byte-identical case.
- After each recompose the helper re-runs validate/replay plus every
  `--verify-cmd` before pushing; a failing check blocks publication with the
  work preserved locally. Retries are bounded (`--max-attempts`, default 3,
  hard range 1..5); exhaustion raises with the work intact. The helper never
  force-pushes, never merges, never `reset --hard`, and never transports
  uncommitted files.

### Coordinator remote publication (CAS, no local race arbiter)

- A local `claim.json` write is NOT the race arbiter across independent
  clones/windows. Authority on the remote branch comes from compare-and-swap
  at publication: build the commit on a captured remote head, then plain
  (non-force) push. A concurrent winner makes the loser fail; the loser
  re-syncs and recomposes — never force-pushes, merges, or rebases canonical
  event files.
- Connector writers without a local clone use Git object/ref primitives with
  the same guarantee: create blobs/tree/commit via the Git Database API,
   then update the branch ref with `force: false` against the captured head
   SHA. A 422 / non-fast-forward response means another writer won: stop,
   re-read, recompose. Never retry with force.
- Implemented canonical adapter: `tools/awrp.py publish-connector` performs
  the above with local Git plumbing (captured head → blob the event +
  rendered projection → tree built on the captured head tree in a temporary
  index → commit with parent = captured head → `push
  <commit>:refs/heads/<branch>` with no force) without touching the working
  tree; `--print-plan` emits the equivalent GitHub Git-Database-API call plan
  (create-blob ×2 → create-tree on the base tree → create-commit with
  parents=[base] → update-ref with force=false) for connector writers.
- For channel-bound tasks on a channel with a live coordinator claim,
  coordinator mutation events (DISPATCH/RECONCILE/REVIEW/APPROVAL/CANCEL)
  MUST carry `--fencing-generation` matching the current claim; the matching
  `{channel_id, generation, owner}` is stamped into the event for durable
  audit (`audit-fencing`). Histories from before claim adoption stay valid;
  legacy unrouted tasks stay unfenced.

## Conflict/corruption

If hash validation fails, sequence duplicates, the chain forks, Git cannot fast-forward, Task state conflicts with requested action, or Approval does not match the current output, stop and surface the condition. Never force-push relay history merely to hide conflict.

### Corruption diagnostics and recovery (audit-only)

`tools/awrp.py audit-chain --task-dir <dir> [--repo <checkout>]`
classifies per-event integrity evidence (required keys, seq continuity,
prev-link, hash recomputation) and attributes each file to its introducing
commit where git history is available — distinguishing hand-composed
producer failures (hash mismatch, intact links, often a single-file
non-composer commit) from link breaks and gaps. It repairs nothing.

Corrupted tasks stay preserved audit-only; history is never rewritten to
hide them. Recovery, if the coordinator orders it, goes through a new
explicit Task/Run or the `RECONCILE` repair boundary — never through
editing canonical files. All canonical writes travel validated composer
paths (`emit`, `dispatch-guarded`, `publish-atomic`, `publish-connector`,
`bridge-process`); direct git commits of hand-written event JSON are
out-of-band writes, detected by validate/audit after the fact, never
prevented beforehand.

### Producer-integrity revision (P0 follow-up)

- Activation reports three distinct machine verdicts: `NO_TASK` (true
  empty), `INVALID_CANONICAL` (corrupt chains present, with task/path,
  bad seq+event, recorded vs recomputed hash, and the last-valid prefix
  from `audit_chain()` attached), plus `AMBIGUOUS`/`OWNED`/`EXECUTE` as
  before. `INVALID_CANONICAL` never ACKs or executes; `first-bind` treats
  it as fail-closed (refuses like any non-EXECUTE).
- Native recovery: `recover-task` mints a new Task from a corrupted
  predecessor's provenance (last-valid prefix + bad-event summary +
  approval digest/contract + stored approval bytes). It refuses clean
  predecessors, missing approvals, and duplicate target ids; it never
  copies predecessor events and never touches predecessor history. With
  `--run-id` it completes the workflow in the same invocation by appending
  a seq2 DISPATCH through the normal validated composer: recipient from
  the new task's registered endpoint (identity gate applies), artifacts
  carrying approval + provenance refs, stable `recovery-dispatch-*`
  idempotency (duplicates refuse), `--expected-head` CAS,
  `--fencing-generation`/`--legacy-route` passthrough.
- Post-push integrity: every canonical publication path
  (`publish-atomic`, `publish-connector`, `dispatch-guarded --publish`,
  bridge, `worker-retry-push`, `publish-ephemeral`) runs
  `post_push_verify()` — fetch, tip equality, remote read-back, hash
  recompute, chain validate — before reporting success.
- Intent-only composition: intent files, bridge requests, and CLI surface
  reject caller-supplied `event_id`/`seq`/prev-link/`event_hash`/actor/
  fencing material. Residual: `created_at` stays caller-supplied (bridge
  determinism needs it); semantics after it are fully composed.
