# AWRP bridge requests (ChatGPT coordinator entry point)

This directory is the ONLY supported way for a connector-backed coordinator
(without a repository checkout) to get canonical Task/Event bytes published.
The coordinator writes a constrained, non-canonical intent request; a
GitHub Actions workflow runs the repository's validated composer
(`tools/awrp.py bridge-process`) and publishes with CAS semantics.

## Request file

Path: `bridge/requests/<request_id>.json` (the filename stem MUST equal
`request_id`; charset `[A-Za-z0-9][A-Za-z0-9_-]*`).

```json
{
  "protocol": "awrp/0.1",
  "request_id": "<same as filename>",
  "action": "create-task | dispatch | review | approval | reconcile",
  "idempotency_key": "<opaque, echoed back>",
  "expected_base": "<branch head SHA captured via the branch ref API>",
  "params": {
    "task_id": "<exact>",
    "context_id": "<exact, create-task only>",
    "title": "<exact, create-task only>",
    "goal": "<exact, create-task only>",
    "project_id": "<exact>",
    "channel_id": "<exact>",
    "lane_id": "<exact>",
    "worker_endpoint": "<exact>",
    "run_id": "<exact existing run, appends>",
    "state": "<working|...>",
    "phase": "<exact>",
    "waiting_on": "<exact>",
    "run_state": "<dispatched|...>",
    "summary": "<exact>",
    "recipient_role": "worker",
    "recipient_id": "<exact>",
    "expected_head": "<task head event id>",
    "details": "<markdown string, optional>",
    "created_at": "<fixed timestamp, create-task only, optional>"
  }
}
```

Forbidden anywhere in a request: `event_id`, `seq`, `prev_event_id`,
`prev_event_hash`, `event_hash`, `integrity`, `fencing` objects, actor
identity, and any other canonical-JSON keys. Canonical bytes can never
be supplied — only composed. Actor identity and fencing generation are
derived live from the channel claim by the bridge, never from the request.

## Two-base + semantic-CAS semantics (request commit vs canonical snapshot)

Capture `expected_base` (the branch head SHA) BEFORE creating the request
file. Creating `bridge/requests/<id>.json` itself advances main, so when
the workflow runs, remote main (the transport head) is normally ahead of
`expected_base` (the canonical snapshot). That transport advance is expected
and accepted.

The bridge applies semantic-CAS-first, not path-prefix staleness:

- Exact match or request-only advance (`bridge/requests/*.json`, never
  `*.result.json`): proceed.
- Drift touching the TARGET task (`tasks/<task_id>/`) or the target
  channel's claim files (`channels/<channel_id>/`): reject — the task head,
  active run, or fencing authority moved. Exception: target-task drift is
  accepted when the request explicitly names the resulting head via
  `expected_head` + `expected_hash` (the coordinator's decision is verified
  fresh against latest; recorded as `target-verified`).
- Any other canonical drift (unrelated tasks/channels/projects/contexts,
  result files, docs): proceed ONLY because every semantic invariant is
  re-verified live against post-pull state — expected_head/hash when the
  request carries them, authoritative active run, non-terminal status,
  idempotency/target-path uniqueness, route ownership — before any write.
  The commit then parents the latest transport head with a plain non-force
  push as the final CAS.

If the push loses a transport race but semantic invariants still pass, the
bridge rewinds ONLY its own unpublished outputs (a clean checkout is
required for retry; foreign dirt fails closed) and recomposes from scratch,
bounded to 3 attempts total. Exhaustion leaves zero local trace and raises;
the request stays unresulted so a later trigger reprocesses it. Semantic
rejections are recorded visibly as `rejected` with the reason and never
retried. Direct planning paths (`plan-task-create`, `compose-intent`,
`publish-atomic`, `publish-connector`) stay strict and reject any advance;
only `bridge-process` applies this rule. Creation needs no special case:
task-absence checks already guard uniqueness, so the same rule covers it
without weakening create-task semantics.

## Incident intents

`incident-create` / `incident-update` carry AWRP Incident Registry writes
through the same validated path (params mirror the `incident-create` /
`incident-update` CLI content fields; `reporter_role` must be `coordinator`
on the bridge — workers use the CLI directly). The bridge derives the update
actor as `coordinator/reporter_id`, composes all hashes itself, and records
`published` with `incident_id` (plus `event_id` for updates) or a visible
`rejected` reason. The incident registry grants no execution authority and
takes no fencing: it is operational audit, validated by the same
create-only / append-only / hash-link rules as tasks, in its own
`incidents/` namespace.

## Result polling

After pushing the request, read `bridge/requests/<request_id>.result.json`
(same branch). Statuses:

- `published` — canonical files committed and pushed; contains
  `task_id`, `event_id`, `event_hash`, `written` paths, `published_head`.
- `rejected` — fail-closed with `reason`; nothing canonical was written.
  Fix the cause and send a NEW request (new id, fresh base).
- `skipped` — a result already exists; replays never recompose.

A stale `expected_base`, unknown task, channel/project mismatch, bad
fencing state, or occupied append path all reject before any write.
A losing CAS race rejects the same way: re-read, re-request, never force.

## External-mutation action guard

Coordinator transport intent is a file write (`bridge/requests/*.json`);
a past incident class selected a public-object mutation (`create_issue`)
where the intent was that write, before any repository code could run.
The enforceable boundary is therefore split — this section states both
sides honestly instead of claiming a repository-only fix:

Repo-enforceable (implemented here):

- The transport surface is pinned: `INTENT_ACTIONS` is exactly
  `create-task | dispatch | review | approval | reconcile` (guarded by a
  regression test), and any action or param naming a public-object
  mutation (`create_issue`, `create_pull_request`, issue/PR/comment/label/
  close/merge params, …) is explicitly ineligible — rejected in
  `read_bridge_request` and `compose-intent` before composition, with the
  refusal naming the ineligible class.
- `tools/awrp.py bridge-preflight --root <relay> --request <id>` runs the
  exact composition the workflow would run (envelope, action/params schema,
  target existence, claim ownership, idempotency, semantic-CAS base,
  append-path uniqueness) and prints the planned file writes — with zero
  writes, commits, pushes, or result records. Run it BEFORE delegating any
  external mutation: a wrong action, route, target, or stale base fails
  here, as data, instead of becoming a public object first.
- The workflow (`.github/workflows/awrp-bridge.yml`) and the composers only
  ever write `bridge/requests/*.result.json` plus canonical
  `tasks/<id>/` files and push the relay branch. No code path in this
  repository calls GitHub Issues/PRs/comments/labels/close/merge APIs.

Upstream residual (NOT controllable from this repo):

- If the ChatGPT/GitHub Connector router selects `create_issue` before
  repository code runs, no file in this repo can intercept that API call.
  Do not claim otherwise. The repo-side mitigation narrows the ambiguity
  window (single-purpose surface + machine-checkable preflight + explicit
  ineligibility errors the coordinator loop can match on) but cannot
  substitute for router-level enforcement.

## External integration acceptance plan (connector layer)

For true pre-API fail-closed enforcement, outside this repo, verify:

1. Router allowlist: in the AWRP transport context the only eligible
   external mutation class is the relay file-write path; `create_issue`
   and siblings are ineligible — replay both incident reproductions
   (transport intent → must never yield a public object).
2. Preflight gate: the wrapper runs `bridge-preflight` first and aborts
   the external call on any non-`plannable` outcome; log the refusal.
3. Adversarial matrix: action mismatch, repo/base mismatch, path escape,
   public-object params, duplicate idempotency — each must fail with zero
   public side effects (mirror `tests/test_awrp.py` class `TBX`).
4. Post-publish reconciliation: poll the `.result.json` (`published` vs
   `rejected`) instead of assuming success; a `rejected` result re-requests
   with a fresh base, never retries the same mutation blindly.

## Pre-API transport wrapper (`tools/awrp_transport.py`)

`bridge-preflight` gates a request that already exists. The wrapper moves
the boundary one step earlier: the only mutation operation a coordinator
or plugin exposes is `transport_write`, whose input schema is:

```json
{
  "action_class": "transport_write",
  "repository": "Bruce-Yii/awrp",
  "path": "bridge/requests/<request_id>.json",
  "contents": {
    "protocol": "awrp/0.1",
    "request_id": "<same as path stem>",
  "action": "create-task | dispatch | review | approval | reconcile | incident-create | incident-update",
    "idempotency_key": "<opaque>",
    "expected_base": "<captured remote head>",
    "params": {}
  }
}
```

Semantics: exact four keys, no extras; `action_class`/`repository`/`path`
bound as above (path shape `bridge/requests/<id>.json`, never
`.result.json`); contents mirrors the repository validator (transport
actions only, public-mutation actions/params ineligible). An optional
`preflight(request)` hook (e.g. `bridge-preflight`) must report
`plannable` before delegation. The caller supplies the `delegate`
(`write_file(path, bytes)`): a test fake, an MCP tool, a plugin
connector. The wrapper itself performs no I/O — enforcement lives at the
selection boundary, before delegation, and every mismatch raises with zero
delegated calls (proven by `tests/test_awrp.py` class `TBW` with
`FakeTransport`, including the observed `create_issue` drift shape).

Three states, stated plainly:

1. Machine-enforced by code in this repo: input schema binding,
   ineligibility denylists, preflight composition check, structural
   absence of any public-mutation operation on the wrapper surface.
2. Wirable into an external plugin/tool wrapper: expose ONLY
   `transport_write` with the schema above; run preflight first; poll the
   `.result.json`; never offer issue/PR/comment/label/close/merge tools in
   the AWRP transport context.
3. NOT enforceable from here: the native ChatGPT/GitHub Connector router
   selecting a public mutation before any wrapper code runs. That needs
   platform configuration (router allowlist / tool visibility per context),
   verified by the live E2E procedure: replay the two incident
   reproductions through the wired wrapper and confirm zero public objects
   plus a `published` result. Until then the platform-level risk stays
   open, by name, not by implication.

## MCP facade (`tools/awrp_mcp_transport.py`)

The wiring target for state 2 above, implemented (stdlib only): a stdio
JSON-RPC (MCP-compatible) server exposing exactly one tool,
`awrp_transport_write`, with the input schema from the previous section.
Each call is validated by `awrp_transport` (plus an optional
`--preflight-cmd`, which receives the canonical request JSON on stdin and
must exit 0) and written under the rooted `--base-dir`; anything else —
unknown tool, unknown method, drifted action/repo/path — is a JSON-RPC
error with zero writes. Run:

```sh
python tools/awrp_mcp_transport.py --base-dir <relay-checkout> [--preflight-cmd CMD]
```

Live E2E before platform closure may be claimed: wire this server (not the
native connector) into the host for AWRP transport, replay the observed
drift shapes (`create_issue` selection, unrelated-public-repo target,
repeated attempts after self-correction — see `tests/test_awrp.py` class
`TBM`), and confirm zero public objects plus `published` bridge results.
Machine E2E of the facade→bridge path itself (live server → request file
→ preflight → published event, plus drift zero-write cases) is pinned in
`tests/test_awrp.py` class `TBF` and runs in-suite on every change.
What this facade still cannot do: stop a coordinator that keeps calling
the native connector directly. That half is platform configuration, and
the risk stays open until the E2E above passes on the wired host.
