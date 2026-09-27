# AWRP Glossary

This glossary defines the terms used across the protocol, reference CLI, and
public documentation. Terms are descriptive; the normative rules live in
`protocol/AWRP-0.1.md` and `protocol/WORKER-CONTRACT.md`.

## Actor

The participant that authored an Event. An actor has a role such as
`coordinator` or `worker` and a stable id. Actor identity is part of canonical
history; it is not inferred from the local user who happened to run a command.

## Append-only

A history discipline in which committed canonical Event files are never
modified, deleted, or replaced. Corrections are expressed as new Events or a
new Task/Run, not by rewriting the past.

## Approval

A scoped authorization to perform a later side effect. An approval should bind
the action class, target, exact output identity, and authorized actor. It does
not transfer to changed output or a different target.

## Artifact

A durable output referenced by a Task Event. Large logs, patches, and binaries
belong in artifacts rather than Event JSON. A stable reference is a repository
and commit SHA, a content hash, or another integrity-checked pointer.

## Bridge

A constrained transport path for coordinators without a local checkout. A
coordinator writes a non-canonical intent request; validated repository code
composes and publishes the canonical bytes.

## Canonical

Authoritative for state reconstruction. In AWRP, canonical means the Task
manifest, the complete ordered Event history, and referenced artifact/commit
identities. A projection is not canonical.

## CAS

Compare-and-swap. A mutation names the exact base or head it was composed
against. If the remote value has changed, the mutation fails closed and must be
recomposed. AWRP never resolves a CAS race with force-push.

## Channel

A durable coordinator/worker boundary. A Channel has one owning Project and may
be claimed by one logical coordinator writer at a time. It carries Tasks for a
cooperating group of workers.

## Claim

Mutable coordinator writer authority over a Channel. A claim has an owner and
monotonic generation. Claims may change; canonical Events do not.

## Composition

The validated process of creating canonical Task/Event bytes. Composition
computes sequence, predecessor links, hashes, actor fields, state projection,
and fencing data. Integrations transport composed bytes; they do not reimplement
composition.

## Connector

A host-provided API surface used to read or write a repository. A connector is
transport and persistence, not protocol authority. AWRP can print or execute a
connector plan that uses non-force Git primitives.

## Context

A semantic grouping object for related Tasks. Context is not routing authority
and must not be used for cross-project or cross-channel discovery.

## Coordinator

The participant that plans work, composes canonical Events, reviews results,
and manages scoped authority. A coordinator is not automatically entitled to
public or destructive side effects.

## Create-only

A file-level discipline: a canonical Event path is written once and never
replaced. A failed write is removed or left uncommitted; an already committed
path is not reused for different bytes.

## Dispatch

A DISPATCH Event that authorizes one Run for one recipient. It binds Task,
coordinator, worker endpoint, Run id, state, and expected history head.

## Endpoint

The stable identity of a worker integration. A dispatch intended for one
endpoint is not valid for another, even if both run the same model or operate
in the same repository.

## Event

An append-only fact in a Task's canonical history. Events carry sequence,
predecessor links, actor and recipient, optional Run identity, state
projection, summary, and integrity hash.

## Execution view

A clean, task-run-scoped Git view used to avoid coupling unrelated parallel
Runs through one mutable checkout. The view is acquired from a known relay
head and released only after verified HANDOFF delivery.

## Expected head

The Event id and/or hash that a new append was composed against. It provides
optimistic concurrency inside a Task history. A mismatch means another writer
advanced the chain and the new append must be recomposed.

## Fail closed

Refuse to act when identity, authority, history, or binding is missing,
ambiguous, stale, or invalid. Fail-closed behavior preserves safety at the
cost of requiring human or coordinator resolution.

## Fencing

Monotonic generation attached to coordinator writes. A write is accepted only
when the caller is the current claim owner and presents the current generation.
Fencing prevents an old coordinator from writing after ownership changes.

## First-bind

The safe startup path for a fresh worker window. It requires exact relay,
Project, Channel, endpoint, and Task identity, then validates and replays the
canonical chain before returning an execution verdict.

## HANDOFF

A worker's durable completion claim for a Run. It includes outcome,
verification, artifact references, residual risk, and next owner. Local success
without delivered HANDOFF is incomplete.

## Handoff delivery

The verified act of publishing the HANDOFF Event into canonical relay history.
Delivery may use a plain push, connector plan, bridge request, or bounded
recompute-and-push retry. Delivery does not authorize re-running the work.

## Idempotency key

An opaque identifier for a logical mutation. Retrying the same request with the
same key must not create a second canonical effect. A new key must not be used
to bypass a CAS race for the same semantic mutation.

## Input request

An execution-bearing Event that asks the coordinator or human authority for a
decision the worker is not authorized to make. The worker pauses the same Run
rather than inventing a product, security, legal, or policy decision.

## Lane

An optional logical session identity inside a Channel. A lane helps separate
independent streams but does not by itself provide operating-system isolation.

## Manifest

The canonical Task JSON file. It records stable Task identity and high-level
metadata. Event history remains authoritative if a projection in the manifest
is stale.

## NOTE

A non-execution Event that records durable, review-relevant information. It is
useful after a delivery problem because it can preserve evidence without
claiming that the original side effect happened twice.

## Projection

A human-readable or tool-friendly view derived from canonical state, such as a
Task card, README, issue body, index, or chat summary. A projection may be
stale and never overrides canonical history.

## Protocol

The `awrp/0.1` wire and semantic contract. Behavior-profile additions must be
backward-compatible; a semantic change that older readers could misinterpret
requires a new protocol identifier or migration.

## Public snapshot

This repository's deliberately limited distribution: protocol, schemas,
reference implementation, synthetic examples, tests, and documentation. It
contains no production Task, Project, Channel, incident, or bridge-request
state.

## Recipient

The participant expected to act or observe next. A worker accepts a DISPATCH
only when the recipient id matches its configured endpoint.

## Reconcile

A non-execution Event used for audited recovery or correction when ordinary
Run semantics cannot describe the situation. Reconciliation does not license
silent history rewriting.

## Recovery

Returning to a safe, validated state after interruption, conflict, corruption,
or delivery failure. Recovery distinguishes canonical delivery problems from
source-work problems so completed side effects are not repeated.

## Relay

The repository or durable store that contains canonical AWRP state. A relay
holds Projects, Channels, Tasks, Events, Artifacts, and incidents. The public
snapshot is a protocol product, not a populated production relay.

## Resume

Deriving the current actionable Run for a bound worker session. Resume validates
the binding and canonical chain; it does not infer authority from the newest
chat, commit, or directory.

## Review

A coordinator's canonical assessment of a worker's HANDOFF. A review may accept
the Run, request a revision, or record a blocking finding. A revision uses a
new Run.

## Role

The coarse participant class of an actor or recipient: coordinator or worker in
the core protocol. Roles organize authority; stable ids identify the actual
participant.

## Run

One execution attempt for a Task. A Run id is single-use. Retry and revision
create new Runs. Run state is `dispatched`, `working`, `succeeded`, `failed`, or
`canceled`.

## Schema

A machine-readable JSON description of object shape. Schema validation is
necessary but not sufficient; AWRP also validates cross-file identity,
ordering, authority, and fencing invariants.

## Side-effect policy

A Task-bound classification of permitted actions. Relay reads and canonical
appends are ordinary; source, fork, upstream, public, or destructive actions
need explicit authority.

## Single execution

The invariant that one Run id cannot authorize the same side effect twice.
Process restart, delivery retry, or a new chat message does not create a new
authorization.

## Task

The canonical unit of governed work. A Task records goal, route, state,
side-effect policy, authority, and the Event history that proves how work was
dispatched and completed.

## Terminal state

A Task state that does not accept ordinary execution Events: `completed`,
`failed`, `canceled`, or `rejected`. Terminal does not mean permanently
unchangeable; audited reconciliation or a new Task governs any later work.

## Transport

The mechanism that carries canonical bytes: Git, a connector, a bridge request,
or the MCP facade. Transport success proves delivery, not semantic authority.

## Worker

The participant that validates a DISPATCH, ACKs the Run, performs authorized
work, verifies it, and delivers HANDOFF. A worker does not invent missing
decisions or execute a Run twice.

## Wire version

The `awrp/0.1` protocol identifier stored in canonical objects. Readers fail
closed on unsupported versions instead of reinterpreting unknown fields.
