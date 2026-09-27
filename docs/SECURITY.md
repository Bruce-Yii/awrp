# Security Model

AWRP is a coordination protocol, not a sandbox. Its security model limits how execution authority is represented, validated, and delivered. Host, operating-system, and platform controls remain necessary.

## Protected properties

1. **Single execution** — a `run_id` cannot authorize the same side effect twice.
2. **Exact identity** — a worker executes only a dispatch addressed to its endpoint.
3. **Append-only history** — committed canonical Events are not silently rewritten.
4. **Bounded side effects** — public or destructive actions require scoped approval.
5. **Fail-closed ambiguity** — missing or conflicting identity stops work.
6. **Verified delivery** — local success is not canonical completion.

## Trust boundaries

### Human authority

The human approves public, destructive, or otherwise scoped effects. Approval binds to the exact output identity. If output changes, approval must be reacquired.

### Coordinator

The coordinator composes canonical intent but does not hand-author hashes, sequence numbers, actor identity, or fencing generation. Repository code derives those values and validates state.

### Worker

The worker trusts canonical history only after validation and replay. It does not trust a chat message, directory name, newest commit, or issue comment as execution authority.

### Transport

Git, GitHub connectors, and MCP carry bytes. They do not define protocol semantics. A transport success does not prove that the bytes were authorized.

### Host integration

Repository code cannot intercept a native tool call that the host router selects before repository code runs. Platform-level allowlists and tool visibility are separate controls.

## Credential handling

- Credentials do not belong in Task or Event payloads.
- Secrets belong in the host's secret store or environment injection mechanism.
- Public snapshot fixtures use synthetic values only.
- Artifacts should reference commit SHA or content hashes rather than embed tokens.
- Logs and projections must redact credential-shaped values.

## Path safety

Canonical writes are confined to validated task paths. Transport requests match an exact repository and `bridge/requests/<id>.json` shape. MCP writes resolve under a rooted base directory and reject path escape.

## Command execution

The reference CLI composes files and Git operations; it is not a general shell surface. If a host exposes arbitrary shell execution beside AWRP, that host surface must apply its own allowlist and approval policy.

The optional MCP preflight hook is executed only after transport validation. A nonzero hook result aborts with zero delegated writes.

## Public-object mutation guard

The transport facade has no create-issue, create-PR, comment, label, close, merge, release, branch-deletion, or upstream-push operation. Drifted action names and mutation-shaped parameters are rejected before the delegate runs.

This is defense in depth, not a claim that a host's native router is under repository control.

## Canonical integrity

Event hashes cover canonical JSON with the event hash field removed. Validation recomputes:

- sequence continuity;
- previous-event ID and hash;
- current content hash;
- state projection consistency;
- recipient and actor fields;
- Run identity where present.

A hash proves byte integrity, not semantic correctness by itself. Semantic validation checks legal transitions and authority.

## Replay safety

Replay is read-only. It derives state from history and never executes a side effect. A worker uses replay to decide what the canonical chain authorizes, not to trigger the action itself.

## Resume safety

A local binding points to a relay directory but is not canonical. Resume verifies the relay, task, channel, endpoint, and expected head. A stale or ambiguous binding fails closed.

## Approval scope

An approval should bind:

- target class (for example, public PR creation);
- exact repository;
- exact commit or artifact hash;
- authorized actor;
- expiration or single-use semantics where appropriate.

Approval does not transfer to a new commit, another repository, another action class, or a broader target set.

## Replay and retry attacks

- A repeated bridge request is idempotent.
- A repeated Run is invalid.
- A replayed connector publication is validated against the current remote head.
- A lost CAS race causes recomposition, not force-push.
- A HANDOFF delivery failure does not authorize re-running source effects.

## Denial of service

Large generated logs, binaries, and unbounded payloads do not belong in Events. Request and event schemas bound the shapes that the reference implementation accepts. Host-level rate limits and size limits still apply.

## Multi-window attacks

Two coordinator windows may attempt to write the same channel. Claim generation and expected-head checks force one deterministic winner. Two worker windows may attempt the same Run; recipient identity, ACK state, and single-execution rules expose the conflict.

## Filesystem attacks

- Task paths are derived from validated identifiers.
- Canonical files are create-only.
- Transport paths are exact-match and root-confined.
- Symlink behavior must be considered on the host filesystem; the reference snapshot should be used inside a controlled checkout.

## Supply-chain boundary

Pinned actions and dependencies should be reviewed before use. The reference implementation minimizes dependencies, but the host can still compromise Python, Git, the operating system, or the model/tool runtime.

## Incident response

When a confirmed protocol or coordination incident occurs:

1. stop the affected action;
2. preserve evidence;
3. validate the full chain;
4. contain ambiguous or unsafe state;
5. do not rewrite history to hide the incident;
6. record an incident with append-only evidence;
7. add a regression test;
8. recover through a new authorized Run or audited reconciliation.

## Residual risks

The public snapshot cannot guarantee:

- host tool-router restrictions;
- operating-system isolation;
- model correctness;
- credential-manager correctness;
- network or endpoint security;
- human approval quality;
- protection of secrets already leaked elsewhere.

These are explicit integration boundaries, not hidden claims of coverage.

## Publication checklist

Before public release:

- scan every tracked text file for high-confidence secret patterns;
- scan for personal/customer data and internal project names;
- verify no private relay state directories exist;
- verify the license/provenance statement is accurate;
- confirm README does not claim features the snapshot does not contain;
- run the complete test suite and public-boundary tests;
- verify CI on the public repository.

## Security contact

This snapshot has no private security contact. Do not include personal email addresses in the public repository. Use the hosting platform's private vulnerability reporting mechanism for the public repository.
