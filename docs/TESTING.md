# Testing and Verification

AWRP treats verification as part of the protocol, not as an optional final step. A Run is not complete because local work looks finished; it is complete only after verified evidence and canonical HANDOFF delivery.

## Test layers

### Public snapshot boundary

`tests/test_public_snapshot.py` protects the publication boundary:

- top-level allowlist;
- private relay path denylist;
- high-confidence secret patterns;
- personal/customer data markers;
- internal project-name markers;
- substantive README requirements;
- natural source-size expectation.

Run it alone during public-tree edits:

```bash
python -m unittest tests/test_public_snapshot.py -v
```

### Protocol and runtime

`tests/test_awrp.py` exercises the reference implementation and protocol invariants:

- append-only event chains;
- canonical hashing;
- Task and Run state transitions;
- recipient and endpoint identity;
- project/channel routing;
- first-bind and resume safety;
- claims and fencing generations;
- expected-head compare-and-swap;
- connector publication;
- transport-intent restrictions;
- public-mutation rejection;
- incident registry rules;
- artifact stability.

Run the complete suite:

```bash
python -m pytest -q
```

### Compile check

The reference implementation is standard-library Python. Byte-compile it before publication:

```bash
python -m compileall -q tools tests examples
```

### End-to-end demo

The disposable demo creates, validates, and replays a synthetic Task:

```bash
python examples/demo_flow.py
```

Expected properties:

- one Task ID;
- four canonical Events;
- a non-empty head hash;
- replay reaches `phase = review`;
- the Run reaches `succeeded` with no active Run.

The demo writes under `.demo/`, which is ignored. Remove the directory after inspection.

## Verification evidence

A useful HANDOFF names:

1. the exact production change;
2. the narrowest relevant test;
3. the full suite result;
4. build or compile result when applicable;
5. artifact or commit identity;
6. remaining risk;
7. the next owner.

Example:

```text
Changed: exact recipient validation in dispatch composition.
Verified: python -m pytest -q → 412 passed.
Verified: python -m compileall -q tools tests examples → exit 0.
Artifact: commit <sha>.
Risk: host-native connector routing remains outside repository enforcement.
Next: coordinator review.
```

## Regression discipline

A regression test is valid only if it fails on the pre-fix behavior for the expected reason. A test that passes before the fix does not prove the fix.

For a bug fix:

1. reproduce the bug;
2. write the smallest failing test;
3. watch it fail;
4. implement the minimal correction;
5. watch the focused test pass;
6. run the full suite;
7. record both commands and results.

## Test fixtures

Fixtures must be synthetic. Do not copy:

- real project or customer names;
- private Task/Run identifiers;
- production event payloads;
- personal data;
- tokens or environment files;
- private repository bindings.

Use names such as `project_alpha`, `channel_beta`, and `task_example` so a test failure cannot disclose production routing.

## Network and external effects

The reference test suite should not require network access or mutate public objects. Tests that model publication use temporary Git repositories, fake transports, or dry-run planners.

If a test needs a real external service, gate it explicitly and keep the default suite deterministic.

## Publication verification

Before creating a public repository:

```text
[ ] boundary tests pass
[ ] full suite passes
[ ] compile check passes
[ ] demo runs and disposable output is removed
[ ] secret scan is clean
[ ] privacy scan is clean
[ ] license/provenance statement is present
[ ] README and repository description are truthful
[ ] repository size and primary language are verified from GitHub metadata
[ ] exact quality inputs are recomputed from current ghfind source
```

After publication:

```text
[ ] unauthenticated repository page is reachable
[ ] unauthenticated raw README is reachable
[ ] no private state paths exist
[ ] CI passes on the public repository
[ ] ghfind rescan/refresh is attempted through an authorized route
[ ] expected score is labeled as a simulation until a fresh snapshot exists
```

## What counts as proof

- Static reading is not runtime proof.
- A subagent's `VERIFIED` label is not a substitute for local command output.
- A passing focused test is not a green suite.
- A successful local command is not proof of remote delivery.
- A non-fast-forward push is not fixed by force.
- A cached ghfind API response is not proof of a fresh scan.

## Incident tests

A confirmed protocol/coordination incident should gain a deterministic regression test when the failure can be reproduced safely. The test should assert the fail-closed behavior and zero unintended side effects.

Examples:

- wrong recipient cannot ACK;
- stale expected head cannot append;
- missing binding cannot execute;
- shared-route dispatch is rejected by default;
- HANDOFF without ACK is rejected;
- public-mutation transport intent is rejected before delegation;
- a corrupted chain is not executable.

## Performance and long-running work

Performance optimizations require before/after measurements under a pinned input. Do not weaken validation or determinism for speed. If an optimization changes recovery semantics, it is not complete until the full correctness suite passes.

## Test data hygiene

A test may assert that a forbidden identifier is rejected; the test source may therefore contain a generic forbidden example. Keep such examples obviously synthetic and avoid real customer or personal identifiers.
