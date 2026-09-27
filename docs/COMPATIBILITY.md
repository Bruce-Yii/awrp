# Compatibility

AWRP separates the wire protocol identifier from additive behavior changes.
This document explains what may change without a new protocol, what requires
a migration, and how readers should handle unknown versions.

## Compatibility goals

A compatible change should:

- preserve the meaning of existing canonical fields;
- allow old readers to fail closed rather than misinterpret history;
- keep validators, replay, composers, schemas, and documentation aligned;
- preserve hash and event-chain interpretation;
- avoid forcing a rewrite of existing Tasks;
- make the migration boundary visible in tests.

## Wire version

Canonical objects carry:

```json
{"protocol": "awrp/0.1"}
```

The wire version describes the meaning of existing fields and canonical
history. A reader must reject an unsupported version instead of guessing.

## Additive changes

The following can remain backward-compatible on `awrp/0.1` when old readers
fail closed safely:

- adding a new optional Event field that validators may ignore;
- adding a new optional Task manifest field;
- adding a new command or diagnostic;
- adding a new schema property with an explicit default;
- adding a new evidence or artifact reference;
- adding stricter validation that rejects previously invalid action shapes;
- adding a transport restriction that blocks actions not required by the
  protocol.

The important question is not whether old binaries still start. It is whether
an old reader can misinterpret a valid new history. If yes, the change is not
backward-compatible.

## Incompatible changes

The following require a new protocol identifier or a formal migration:

- changing the meaning of an existing field;
- changing canonical hash canonicalization;
- changing event sequence or predecessor semantics;
- allowing a state transition that was previously forbidden;
- changing recipient identity rules;
- allowing one Run id to execute twice;
- changing the binding between Task, Project, Channel, and endpoint;
- changing approval scope semantics;
- making a projection authoritative over canonical history;
- changing the public-mutation denylist into an allowlist with different
  scope.

An incompatible change must not be hidden behind a flag that silently changes
existing history.

## Reader behavior

A reader must:

1. read the protocol identifier first;
2. reject unsupported major wire versions;
3. tolerate documented additive optional fields;
4. fail closed when a required invariant cannot be evaluated;
5. never reinterpret an old field with a new meaning;
6. report the exact unknown field or version that blocked progress.

Unknown data is not permission to proceed.

## Composer behavior

A composer must:

1. produce the current wire version;
2. include every field required by that version;
3. compute hashes over the current canonical byte recipe;
4. include provenance or migration fields when the contract requires them;
5. refuse to write an Event into a chain of an incompatible version.

A composer must not write a new-version Event into an old-version Task merely
because the fields look similar.

## Validator behavior

A validator should distinguish:

| Condition | Result |
|---|---|
| Unknown optional field | accept or report, according to contract |
| Unknown required field | fail closed |
| Unsupported wire version | fail closed |
| Illegal transition | fail closed |
| Missing routing identity on a new Task | fail closed |
| Historical legacy shape with explicit marker | validate under legacy rules |
| Hash recipe mismatch | fail closed |

Validators should report the first broken invariant and enough context to
diagnose it without exposing secrets.

## Replay behavior

Replay derives state from Events. A new field that is not part of the state
machine should not change historical state. If it would, the change is
semantic and needs a migration.

A replay implementation may expose additional diagnostic data for newer
versions, but it must not present that data as canonical state for an older
wire version.

## Schema versioning

Schemas describe shape, not the entire protocol. Update them with the
composer and validator in the same change. Prefer explicit descriptions for
new optional properties:

```json
{
  "type": "object",
  "properties": {
    "new_optional_field": {
      "type": "string",
      "description": "Optional diagnostic added in behavior profile 0.1.x."
    }
  }
}
```

Do not reuse an old property name for a new meaning. Do not make a new
required field optional in schema while keeping it required in code.

## Migration strategy

A migration should be:

1. explicit about source and target versions;
2. idempotent or safely detectable;
3. append-only where canonical history is involved;
4. able to report partial or ambiguous state;
5. covered by synthetic fixtures;
6. reversible or explicitly one-way with recorded consequences.

For a history-level change, prefer a new Task or a reconciled Event over
rewriting old Events.

## Version negotiation

A coordinator and worker do not need a long-lived version negotiation protocol
if the wire version is stored in every canonical object. They should instead:

1. read the version;
2. compare it with their supported set;
3. stop on an unsupported version;
4. report the exact version and object;
5. wait for an explicit migration decision.

## Testing compatibility

Compatibility tests should include:

- an old reader fixture with a newer additive field;
- an unsupported version fixture;
- a changed-hash-recipe fixture;
- a migration fixture with ambiguous data;
- a legacy Task fixture;
- a new Task missing routing identity;
- a reader that must not treat a projection as canonical;
- a run with a duplicate `run_id` that must be rejected.

Compatibility is proven by executing old and new readers against the same
synthetic fixtures, not by reading a version string.

## Deprecation

Deprecate a field or command only after:

1. a replacement is documented;
2. old history remains readable;
3. the validator emits a precise diagnostic;
4. tests cover both paths;
5. the removal timeline is explicit.

A deprecation warning must not be the only protection against silently writing
incompatible bytes.

## Public documentation rule

Public documentation must state the current wire version, the supported
behavior profile, and the fail-closed rule. It should not claim compatibility
with an unreleased or untested revision.

## Practical review questions

- Can an old reader misinterpret this new history?
- Does the change alter a field's meaning or only add an optional field?
- Does the composer and validator agree on the same version?
- Are hash and predecessor rules unchanged?
- Does replay produce the same state for old fixtures?
- Is there a synthetic test for the new reader and an old reader?
- Is the migration append-only and idempotent?
- Is any new field documented in the schema and protocol text?
