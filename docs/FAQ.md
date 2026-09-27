# Frequently Asked Questions

## What problem does AWRP solve?

Coding agents lose context, run in multiple windows, retry after interruption,
and hand work to reviewers. Chat transcripts help but are not authoritative
execution logs. AWRP provides a small durable protocol for exact identity,
append-only history, guarded dispatch, single execution, deterministic replay,
and fail-closed recovery.

## Is AWRP an agent platform?

No. AWRP v0.1 has no server, database, queue, WebSocket, dashboard, worker
auction, model runtime, or general agent router. It is a protocol plus a
reference CLI and transport boundaries. Host systems provide execution and
tool access.

## Why append-only Events instead of a mutable status field?

Mutable status cannot prove how work became authorized or whether history was
rewritten. Append-only Events preserve the chain of dispatch, ACK, input,
handoff, review, approval, failure, and reconciliation. Replay derives current
state from those facts.

## Why not use a database?

A Git repository is widely available, auditable, branchable, and easy to inspect.
A database can be faster, but it adds infrastructure and a separate backup and
migration surface. AWRP keeps the canonical format transport-neutral so a
database-backed implementation could exist without changing the semantics.

## Is the hash chain a security guarantee?

The hash chain provides byte integrity and predecessor continuity. It does not
by itself prove semantic correctness or prevent an attacker with repository
write access from rewriting the whole history. Semantic validation, scoped
authority, host access control, and Git hosting protections remain necessary.

## Why must a Run id never execute twice?

A retry can arrive after a worker already changed a source repository or a
public object but before HANDOFF delivery. Re-executing the same Run would
repeat effects that are not naturally idempotent. A new Run makes the new
authorization explicit.

## Why ACK before work?

ACK records that the worker validated the exact history head, accepted the Run
identity, and understood the authority. Without ACK, a coordinator cannot tell
whether a worker is idle, still binding, or already executing the same Run.

## Does EXECUTE mean the agent should ignore the human?

No. EXECUTE means the canonical chain authorizes the scoped Run; it removes a
redundant confirmation step for that Run. The worker still requests input for
missing product, security, legal, or policy decisions, and still needs scoped
approval for public or destructive effects.

## Why is project identity explicit?

Recency, directory names, chat context, and name similarity are unreliable
selectors. An explicit Project id prevents work from being routed to the newest
plausible repository or channel. A Context can group work semantically without
becoming authority.

## What is a Context for?

A Context groups related Tasks for human navigation and semantic reference. It
is not a mailbox and does not grant a worker permission to execute. Routing
uses Project, Channel, endpoint, and exact Task identity.

## What is a Channel?

A Channel is the durable coordinator/worker boundary. It owns Tasks for a
cooperating group, has a Project owner, and can be claimed by one logical
coordinator writer. A claim provides mutable writer fencing without rewriting
canonical history.

## What is a Lane?

A Lane is an optional logical session identity inside a Channel. It helps
separate streams. It is not a security boundary and does not replace separate
execution views when local checkout state would otherwise couple parallel Runs.

## Why expected-head CAS?

Optimistic concurrency prevents two writers from composing against the same
stale history. A writer names the exact head, and a mismatch means it must
re-read and recompose. AWRP never resolves the race with force-push because that
would make canonical history non-auditable.

## Why not force-push a lost publication?

A force-push can hide a competing append, rewrite event bytes, or break another
writer's delivery. Re-sync and recomposition preserves both histories and makes
the race visible.

## What does HANDOFF contain?

Outcome, exact changed files or artifacts, verification commands and results,
residual risk, next owner, and the same Run id that was ACKed. The worker must
deliver and verify the HANDOFF before reporting completion.

## Is a local “done” message enough?

No. Local work can be complete while canonical delivery fails. The next action
is to reconcile HANDOFF delivery, not to repeat source or public side effects.

## How are retries different from revisions?

A retry follows a failed or interrupted Run. A revision follows coordinator
review. Both create a new Run id. Neither reopens a terminal Run.

## What is a NOTE event?

NOTE records durable information without authorizing execution. It is useful
for evidence after a delivery incident or for a clarification that does not
belong in the state machine.

## What is RECONCILE?

RECONCILE is an audited recovery or correction record. It does not license
silent mutation of old Events. If canonical history is corrupt, preserve the
evidence and create a new authorized Task or Run rather than pretending the old
chain is valid.

## How are approvals scoped?

An approval should bind the action class, target domain, exact repository,
exact commit or artifact hash, and authorized actor. Changed output or a
different target requires a new approval.

## Does the transport facade block all public GitHub mutations?

The repository facade exposes only a validated relay transport write. Unknown
actions and public-mutation parameters are rejected before delegation. It
cannot reconfigure a host application's native tool router, so host-level tool
visibility is still required.

## Why is the MCP server minimal?

The narrow tool surface is the enforcement point. Exposing one validated
transport operation makes the allowed mutation class inspectable. A broad
GitHub tool surface would move enforcement into host policy and make accidental
public actions easier.

## Can I use a connector instead of Git?

Yes. A connector can create blobs, a tree, a commit, and a non-force ref update
from a plan produced by validated repository code. The connector must not
recompute canonical semantics, and it must read back the result.

## Can a coordinator hand-author event JSON?

No. It may author intent, but canonical bytes must come from a validated
composer. Recomputing a hash over hand-written semantics is not validation.

## How does a fresh worker start safely?

Use `first-bind` with exact relay, Project, Channel, endpoint, and Task
identity. The command syncs, validates, replays, and returns a verdict. Only
EXECUTE authorizes the ACK. Global scanning is not a safe substitute.

## What does AMBIGUOUS mean?

More than one target could match the available identity facts. The worker stops
and asks for exact Project/Task/Run identity. It must not select the newest or
most recently mentioned candidate.

## What does OWNED mean?

Another logical owner currently holds the relevant Run or coordinator claim.
The current window does not execute. Ownership is explicit and generation-
fenced; it is not inferred from which process has the newest file.

## How are coordinator write races handled?

A Channel claim carries an owner and monotonic generation. Routed writes must
match that claim. Expected-head checks serialize Task appends. The winner is
deterministic; the loser re-syncs and recomposes.

## Why use task-scoped execution views?

One mutable checkout couples unrelated parallel Runs through uncommitted files,
branch state, and index state. A clean per-Run view removes that coupling. The
view is released only after verified HANDOFF delivery.

## What happens when validation fails?

Stop. Preserve evidence. Do not execute from partially trusted state, delete
the broken Event, or force history. Identify the first invalid invariant, record
an incident, and recover through a new authorized Run or audited reconciliation.

## Are ordinary source bugs incidents?

No. An AWRP incident is a confirmed protocol, governance, routing, fencing,
transport, recovery, host-integration, or documentation failure. A normal
application bug belongs in the source project's tracker.

## How is protocol compatibility handled?

Additive, backward-compatible behavior may remain on `awrp/0.1` when old
readers fail closed safely. A change that alters canonical meaning requires a
new protocol identifier or a formal migration.

## Why does the public snapshot omit state?

A protocol implementation and a populated production relay have different
security boundaries. Publishing Tasks, Projects, Channels, incidents, or bridge
requests would expose operational history. The public snapshot includes code,
schemas, synthetic examples, and executable boundary tests instead.

## Does “no license granted” mean the code is secret?

No. It means the repository is published for inspection and evaluation, not as
an open-source grant. Anyone can read it on the hosting platform; no permission
to copy, modify, or redistribute is granted by the repository.

## How do I contribute?

Read the protocol and tests first. Add a failing regression test, implement the
smallest correct change, run the focused test and full suite, and update docs.
Do not add production state, credentials, personal data, or internal project
names.

## What makes a good public example?

Use synthetic identities, disposable roots, no credentials, and commands that
actually execute. Examples should fail closed when identity is ambiguous and
should never point at production state.
