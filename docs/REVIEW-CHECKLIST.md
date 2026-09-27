# Review Checklist

Use this checklist when reviewing a protocol change, a worker HANDOFF, a
coordinator publication, or a public snapshot.

## Task identity

- [ ] The Task id is exact and stable.
- [ ] Project, Channel, and worker endpoint are explicit.
- [ ] Context is used only as semantic grouping.
- [ ] The current state came from replay, not a stale projection.
- [ ] The Task is not terminal unless the reviewer is auditing recovery.

## Dispatch authority

- [ ] The latest active Run is identified.
- [ ] DISPATCH recipient matches the worker endpoint.
- [ ] The Run id has never executed before.
- [ ] The coordinator holds the current Channel claim generation.
- [ ] Side effects are inside the Task policy.
- [ ] Route-sensitive publication used the guarded path.
- [ ] No global cross-project discovery was used to select the Task.

## Worker execution

- [ ] ACK exists for the same Run.
- [ ] ACK names the expected history head.
- [ ] The worker revalidated the chain before material work.
- [ ] No missing product, security, legal, or policy decision was invented.
- [ ] INPUT_REQUEST was used when a decision was required.
- [ ] The same Run's side effects were not repeated after a delivery failure.

## Verification

- [ ] The focused regression test was run and its result recorded.
- [ ] The full relevant suite was run.
- [ ] Build or compile checks ran when applicable.
- [ ] Static review was not treated as runtime proof.
- [ ] Remote objects were read back after publication.
- [ ] A non-fast-forward result was not hidden with force.

## HANDOFF

- [ ] HANDOFF names the same Run that was ACKed.
- [ ] Outcome and changed artifacts are exact.
- [ ] Verification commands and results are included.
- [ ] Residual risk is stated.
- [ ] The next owner is explicit.
- [ ] HANDOFF delivery is durable and verified before completion is reported.

## Review and approval

- [ ] The coordinator reviewed canonical history, not only the summary.
- [ ] Findings are recorded in canonical history.
- [ ] A revision uses a new Run.
- [ ] Approval binds the exact commit or artifact hash.
- [ ] Changed output is not published under a stale approval.
- [ ] Public, upstream, and destructive effects are separately authorized.

## Protocol change

- [ ] The change is covered by a test that failed before the fix.
- [ ] Canonical hash and predecessor semantics remain intentional.
- [ ] Event types and state transitions are validated.
- [ ] Composer, validator, replay, schemas, and docs agree.
- [ ] Old-reader behavior is defined and tested.
- [ ] Incompatible semantics use a new protocol or migration.
- [ ] Additive fields fail closed when unknown readers cannot interpret them.

## Transport and publication

- [ ] The integration transports bytes instead of authoring semantics.
- [ ] Expected base or head was captured immediately before publication.
- [ ] The ref update is non-force.
- [ ] A lost race triggers re-sync and recomposition.
- [ ] Bridge requests omit canonical internals.
- [ ] Idempotency keys are stable for the logical mutation.
- [ ] MCP transport rejects unknown or public mutation actions.
- [ ] Connector plans are read back and validated after execution.

## Concurrency

- [ ] Channel claim owner and generation are current.
- [ ] Parallel Runs do not share a mutable checkout by default.
- [ ] Execution views are released only after HANDOFF delivery.
- [ ] Foreign worktree or checkout bytes were not discarded.
- [ ] Ambiguous ownership stops execution.

## Security and privacy

- [ ] No credentials, tokens, cookies, or private keys are present.
- [ ] No personal, customer, or resume data is present.
- [ ] No internal project names appear in public examples.
- [ ] No production Project, Channel, Task, incident, or bridge-request state is
      included.
- [ ] Logs and artifacts are redacted before publication.
- [ ] Host-level tool restrictions are described honestly.
- [ ] Residual platform risk is not presented as solved.

## Public snapshot

- [ ] The repository is original and not a fork.
- [ ] The description is truthful and specific.
- [ ] The README quick start executes.
- [ ] Documentation links resolve inside the repository.
- [ ] License or provenance wording is accurate.
- [ ] `python -m pytest -q` is green.
- [ ] `python -m unittest tests/test_public_snapshot.py -v` is green.
- [ ] CI is green on the public repository.
- [ ] Unauthenticated repository metadata is verified after publication.
- [ ] Expected quality metrics are labeled as simulations until a fresh
      third-party scan exists.

## Incident handling

- [ ] The failure has concrete evidence.
- [ ] Unsafe effects were contained first.
- [ ] History was preserved rather than rewritten.
- [ ] The incident grants no execution authority by itself.
- [ ] A regression test captures the failure class.
- [ ] Recovery uses a new Task, new Run, or audited reconciliation.

## Review outcome

Record one of:

- accepted;
- revision required;
- blocked on missing authority;
- blocked on invalid canonical state;
- incident required;
- false positive with retained evidence.

Do not accept a Run merely because the local work looks finished. Acceptance
requires canonical history, verification, and the correct next owner.
