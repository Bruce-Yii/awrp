# Public Snapshot Policy

This repository is a public release of the AWRP protocol and reference
implementation. It is intentionally separate from any populated production
relay. This document explains the boundary, why it exists, and how maintainers
verify it.

## Release goal

The public snapshot should let a reader:

- understand the protocol without access to private operations;
- run the reference implementation locally;
- execute synthetic examples and tests;
- review the security and recovery model;
- verify that no production state was exported.

## Release contents

Published content includes:

- `protocol/` — normative protocol and worker/coordinator contracts;
- `schemas/` — machine-readable object shapes;
- `tools/` — standard-library reference CLI and transport facades;
- `examples/` — synthetic, disposable flows;
- `tests/` — protocol tests and public-boundary checks;
- `templates/` — thin agent instruction adapters;
- `docs/` — architecture, operations, integration, security, compatibility,
  glossary, FAQ, failure modes, and review guidance;
- GitHub Actions workflows for tests and the optional bridge contract.

## Excluded content

The release excludes:

- production `projects/`, `channels/`, `contexts/`, `incidents/`, and `tasks/`;
- `bridge/requests/` and result files;
- local `.awrp/` bindings and session state;
- credentials, tokens, cookies, private keys, or environment files;
- personal, resume, customer, or candidate data;
- internal project names used by real operations;
- private repository bindings;
- workspace-only project manifests and execution ledgers.

Text may mention a path such as `tasks/<task_id>/` when documenting protocol
semantics. The boundary applies to published files, not to protocol vocabulary.

## Why not publish the implementation repository directly?

A populated relay and a protocol implementation have different lifecycles.
The implementation is a product; the relay is operational state. Publishing
the repository that contains both would expose history that cannot be removed
by a later file deletion.

A fresh snapshot gives the public repository a clean history from its first
commit.

## Originality and provenance

The public repository is an original implementation, not a fork and not a
mirror of an upstream project. The protocol documents, reference tools,
schemas, examples, and tests in this snapshot are the release artifact.

The repository does not claim an open-source license. It is published for
inspection and evaluation. Do not add a permissive license without an explicit
owner decision.

## Redaction rules

Use synthetic identifiers in examples and tests:

```text
project_alpha
channel_alpha_contrib
codex_alpha
task_example
run_example
ctx_alpha
```

Do not copy:

- real repository or channel names;
- real Task, Run, Event, or incident ids;
- real worker or coordinator identities;
- local filesystem paths;
- private deployment or infrastructure details;
- logs that contain personal or customer information.

If a real identifier is required to explain a protocol invariant, describe the
shape generically and construct a synthetic fixture.

## Verification before publication

Run:

```bash
python -m compileall -q tools tests examples
python -m pytest -q
python -m unittest tests/test_public_snapshot.py -v
python examples/demo_flow.py
```

Then inspect the publishable file list:

```bash
git ls-files
git grep -n -I -E "AKIA|gh[pousr]_|github_pat_|sk-[A-Za-z0-9_-]{20,}|BEGIN .*PRIVATE KEY"
```

The first command must contain no production state directory. The second must
return no credential-shaped match. A human must also read the diff, because a
secret scanner cannot decide whether a synthetic name is actually private.

## Post-publication verification

Check the following without authentication:

- repository page is reachable;
- README is visible;
- source and protocol files are visible;
- no private state path exists;
- CI has completed successfully;
- description and language metadata are accurate.

A fresh public repository may need a short period before third-party quality
indexes rescan it. Report any expected score as a simulation until a fresh
index response exists.

## Adding a new file

Before adding a file, ask:

1. Does it describe the protocol or a public-safe example?
2. Does it contain real operational identity or data?
3. Is it a durable product document, or local workspace bookkeeping?
4. Does it increase understanding rather than repository size alone?
5. Does the public-boundary test still pass?

Keep local project metadata out of the public tree. The executable boundary is
`tests/test_public_snapshot.py`.

## Release notes

When changing the public snapshot, record:

- protocol or implementation change;
- compatibility impact;
- verification commands and results;
- public-boundary impact;
- whether any new runtime or dependency was introduced.

Do not publish internal run ids, task ids, incident markers, or private
coordination metadata in release notes.

## Manual review prompts

Automated checks cover known credential shapes, forbidden path names, and a
small set of internal identifiers. A reviewer still reads the content and asks
whether the public release would reveal operational behavior even when no
pattern matched.

### Identity review

- Do example ids reveal a real Project, Channel, Task, Run, or worker?
- Does a commit reference in documentation point to a private relay branch?
- Does a protocol example reproduce a real event sequence that could be used to
  infer private work?

### Narrative review

- Do headings or summaries describe a private incident in recognizable detail?
- Does a failure-mode example combine facts that uniquely identify an internal
  project even after names are replaced?
- Does a screenshot, log excerpt, or sample payload contain customer context?

### Provenance review

- Is any file copied from an external project without a recorded license or
  permission?
- Does the wording imply an upstream affiliation that does not exist?
- Does a no-license statement conflict with a copied asset that requires
  different treatment?

### Quality review

- Does the README claim a command or feature that is not in this snapshot?
- Does a document describe production state as if it were shipped here?
- Are generated reports or temporary verification output accidentally tracked?
- Is the public tree substantive because it documents the product, not because
  it contains repeated filler?

If any answer is uncertain, stop publication and resolve the uncertainty with
the repository owner.

## Change ownership

Protocol semantics are owned by the Worker Contract and protocol documents.
Reference behavior is owned by the tools and tests. Public-boundary rules are
owned by the public snapshot test. Release metadata must not silently override
those sources.

A change that spans several areas should update them together:

| Change | Required areas |
|---|---|
| New Event type | protocol, schemas, composer, validator, replay, tests, docs |
| New command | parser, implementation, tests, CLI docs |
| New state | state machine, validator, replay, templates, operations docs |
| New transport restriction | facade, schema, tests, integration and security docs |
| New public file | public-boundary test and snapshot policy review |

## Safe rollback

Before the first public commit, rollback is a local branch or index change.
After publication, rollback means a new commit that removes or corrects the
offending content. Do not rewrite shared public history to hide a leak; make
the correction visible and, if necessary, rotate exposed credentials through
their owner.

A security incident that exposes a credential is not a documentation rollback.
Revoke and rotate the credential first, then remove the exposed text, then
record the incident outside the public snapshot.

## Review ownership

The repository owner decides every public release. Automated checks provide
evidence; they do not replace owner review of provenance, privacy, and
truthful metadata.
