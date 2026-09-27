# Incident Model

AWRP includes a small incident registry for confirmed failures of the
coordination protocol itself. It is not a second Task system and it does not
replace ordinary source-project issue tracking.

## Purpose

The registry preserves evidence for failures that affect:

- canonical validity;
- project or channel routing;
- worker identity;
- coordinator claim fencing;
- expected-head concurrency;
- transport or connector publication;
- delivery and recovery;
- host-integration assumptions;
- normative documentation.

The goal is to learn from coordination failures without rewriting the history
that exposed them.

## Canonical incident data

An incident has:

- stable incident id;
- discovery record with content hash;
- category;
- severity;
- status;
- append-only update events;
- evidence references;
- root cause when known;
- remediation and verification.

The discovery record and update events are canonical. Human-readable incident
notes and registry indexes are projections and can be rebuilt.

## Incident versus Task

| Concern | Task | Incident |
|---|---|---|
| Purpose | Govern execution of work | Preserve learning from a coordination failure |
| Grants execution authority | Yes, through a Run | No |
| Appears in worker inbox | Yes | No |
| Can block a Run | Through Task state | No direct authority |
| Uses append-only history | Yes | Yes, in its own namespace |
| Has claims/fencing | Yes | No |

An incident never authorizes a worker to execute, migrate a claim, or publish a
public effect.

## When to open an incident

Open one only when there is concrete evidence of a protocol, governance,
routing, fencing, transport, recovery, host-integration, or documentation
failure. Examples:

- validation accepted an illegal transition;
- a worker ACKed a dispatch addressed to another endpoint;
- two coordinator owners both produced accepted writes for one claim
  generation;
- a publication path force-pushed or mutated an Event;
- a delivery retry repeated a non-idempotent side effect;
- first-bind selected a Task without exact identity;
- documentation contradicted the executable contract.

Do not open an incident for:

- a normal source bug;
- an unconfirmed suspicion;
- routine user preference;
- a failed experiment with no protocol impact;
- a message that is merely inconvenient.

## Severity

A practical severity ladder:

| Severity | Meaning | Example |
|---|---|---|
| critical | Widespread authority or history breach | Duplicate execution of the same Run; accepted write outside claim |
| high | Correctness or security boundary fails | Wrong recipient accepted; corrupted chain executed |
| medium | Recoverable coordination failure | Ambiguous binding; lost HANDOFF delivery |
| low | Documentation or diagnostics defect | Contract wording contradicts tests |

Severity describes impact, not blame.

## Containment before recording

When safe:

1. stop the affected action;
2. preserve logs, refs, commits, and Event files;
3. avoid force, delete, merge-away, or rebase-away repairs;
4. contain ambiguous or unsafe state;
5. record the incident with evidence;
6. decide whether recovery needs a new Run or an audited reconciliation.

Record after containment when possible. If immediate containment would destroy
evidence, preserve a copy or ref first.

## Discovery record

The discovery record answers:

- what failed;
- how it was observed;
- what invariant was expected;
- what evidence proves the observation;
- whether any side effect occurred;
- whether the failure is contained.

The discovery record is tamper-evident. Rewriting it to hide the original
observation invalidates the incident.

## Update events

Update events are create-only and hash-linked. Useful update types include:

- evidence added;
- root cause identified;
- remediation applied;
- verification passed;
- impact revised;
- status changed;
- recovery Run linked;
- false-positive determination with reason.

Updates are append-only. A correction is a new update, not an edit to an old
one.

## Recovery

Incident recovery does not grant general execution authority. It usually
produces one of:

1. a new Task for the fix;
2. a new Run under an existing recovery Task;
3. an audited reconciliation Event;
4. a documentation correction;
5. a false-positive closure with retained evidence.

The original incident never becomes a hidden Task channel.

## Verification

A confirmed incident should gain a regression test when it can be reproduced
safely. The test should assert:

- the invalid action is refused;
- the refusal occurs before side effects;
- the failure is explained well enough to diagnose;
- recovery produces a new authorized fact rather than rewriting the old one.

Static review is not sufficient when runtime behavior determines the result.

## Registry projections

Human-readable views may include:

- an incident note;
- a registry index;
- a category summary;
- a rebuildable status table.

Projections are derived from the discovery record and update events. A
projection conflict never overrides canonical incident state.

## Data handling

Incident evidence can contain sensitive operational data. Store only what is
needed to understand and verify the failure. Do not embed credentials, tokens,
private keys, personal data, or customer content.

Prefer references to protected artifacts over copying them. Redact logs before
making them public.

## Public snapshot boundary

The public repository does not ship production incident state. It documents the
model and provides the incident commands in the reference CLI. Public examples
use synthetic identifiers only.

## Review questions

When reviewing an incident update, ask:

- Is the evidence reproducible?
- Did any external side effect occur?
- Was the failure contained before recovery?
- Does the remediation address the root cause or only the symptom?
- Is there a regression test?
- Does the update avoid rewriting history?
- Is any sensitive data unnecessarily exposed?

## Anti-patterns

- treating an incident as a Task and granting it execution authority;
- editing the discovery record;
- closing without verification;
- opening an incident for every source bug;
- deleting an incident because the symptom disappeared;
- using an incident to justify force or history rewrite;
- copying full sensitive logs into the registry.

## Long-term learning

Recurring incidents should influence:

- protocol rules;
- validator checks;
- guarded command preconditions;
- transport restrictions;
- documentation wording;
- regression tests;
- operator training.

Learning is complete only when the failure class is prevented or made safely
diagnosable in the executable system.
