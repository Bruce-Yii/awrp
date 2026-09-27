# AWRP v0.1.1 Errata — Reviewable Code Artifacts

Status: backward-compatible behavioral clarification for wire protocol `awrp/0.1`.

## Why this exists

The first real AWRP Pilot successfully transported task state, ACK, HANDOFF, tests, risks, and upstream status. It also exposed one reviewability gap: the worker's implementation was still uncommitted in a machine-local worktree, so the coordinator could read the summary but could not inspect the exact changed bytes remotely.

## Rule

When a HANDOFF expects remote code review, the exact reviewed code state MUST be available as a durable artifact.

### Committed code

Prefer an immutable pointer:

```text
repository + commit SHA
```

### Uncommitted or untracked code

The worker MUST create a relay patch artifact before HANDOFF.

Preferred path:

```text
tasks/<task_id>/artifacts/<run_id>/working.diff
```

The HANDOFF artifact metadata MUST include:

```json
{
  "kind": "relay_patch",
  "path": "tasks/<task_id>/artifacts/<run_id>/working.diff",
  "sha256": "sha256:<hex>",
  "size_bytes": 1234
}
```

The patch SHOULD be standard unified diff text and MUST contain every tracked and untracked code change required for the requested review. For untracked files, the worker must include their full diff representation rather than only listing file names.

## Integrity

The coordinator SHOULD recompute SHA-256 after fetching the patch and compare it with the HANDOFF metadata before reviewing.

For canonical Event publication, the coordinator MUST additionally use the canonical serializer/hash rule from `tools/awrp.py` (or a byte-equivalent implementation), write the Event, fetch it back, and verify the stored `event_hash` and chain link before treating that Event as execution authorization. Hand-entering an Event hash without read-back validation is not sufficient.

If the worker encounters an Event hash mismatch, sequence gap, or chain-link mismatch, it MUST stop before ACK or task side effects and report the integrity blocker.

### Invalid pre-canonical Event repair

Create-only Event history remains the default. A later Event cannot make an earlier hash-invalid Event pass validation because validation fails at the bad Event first.

A narrow integrity-only repair is allowed only when all of the following are true:

1. the Event has never passed canonical validation;
2. the worker confirms it performed no ACK and no task/source/public side effects from that invalid Event;
3. the semantic fields are not disputed;
4. the repair changes only `integrity.event_hash` and any mechanically dependent downstream `prev_event_hash` / `event_hash` values;
5. the corrected chain is independently revalidated;
6. a new `RECONCILE` Event records the old/new hash facts and the reason for the repair.

If semantics are disputed or side effects already occurred, do not use this exception to rewrite history. Stop and recover through a new audited Task/Run or another explicit recovery path.

## Authority

A relay patch is a review snapshot only. Creating or reviewing it does not authorize source-repository publication.

By default, review-artifact Tasks must distinguish side effects by target domain instead of using an unqualified verb such as `push`:

- `relay_repo`: private AWRP transport/store. P2 relay writes, commits, and pushes are allowed when the Task requires ACK/Event/Artifact delivery.
- `source_repo`: the local/source working repository being reviewed. Local reads/tests may be allowed; source commits or pushes require explicit Task authority.
- `user_fork`: a user-owned fork/branch of the source project. Push is dispatch-specific.
- `upstream`: third-party/public project. Issue comments, PR creation, merge, and other public side effects require scoped human approval unless explicitly authorized.

Therefore a statement such as `do not push` is invalidly ambiguous in AWRP coordination. It MUST identify the target domain, for example:

```text
Do not push to source_repo, user_fork, or upstream.
Relay writes/commits/pushes to relay_repo are allowed and required for protocol delivery.
```

Creating or reviewing a relay patch does not by itself authorize:

- source-repository commit
- source-repository push
- user-fork publication
- upstream Issue/PR comment
- upstream PR creation
- merge
- destructive actions

Those actions remain governed by the Task side-effect policy and scoped Approval.

## Recovery clarification

If a worker has already completed local computation but withheld Relay delivery because an earlier instruction ambiguously prohibited `push`, the coordinator SHOULD append a canonical `RECONCILE` clarification rather than silently rewriting prior Events or creating a duplicate Run.

The RECONCILE should state that:

1. the same `run_id` remains authoritative;
2. already-completed source-side work must not be repeated;
3. only missing Relay delivery should be completed when the local artifact already exists;
4. `relay_repo` write/commit/push is distinct from prohibited source/upstream publication.

This ordinary RECONCILE path applies to valid prior Events. It does not repair a hash-invalid Event; use the narrow invalid pre-canonical repair rule above when its prerequisites hold.

## Failure behavior

If the worker cannot produce a complete remotely readable patch, it must not claim the implementation is ready for code review. Emit `INPUT_REQUEST` or `ERROR` and stop at the missing boundary.

## Compatibility

This errata does not alter Event field names, task states, run states, hash-chain rules, or `protocol: awrp/0.1`. Existing valid v0.1 history remains valid. The rule applies prospectively to review-oriented HANDOFFs using the v0.1.1 behavior profile.
