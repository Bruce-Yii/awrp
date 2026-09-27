"""Single-purpose pre-API AWRP transport wrapper boundary.

A coordinator that wants to publish through the AWRP bridge calls exactly
one mutation operation: transport_write. Everything else — issue, PR,
comment, label, close, merge, release, branch, or any other public-object
mutation — is structurally unavailable (no such function exists here) and,
when presented anyway, rejected before any delegate is invoked.

The wrapper binds three invariants before delegation:

  action_class == 'transport_write'
  repository   == 'Bruce-Yii/awrp'
  path         == 'bridge/requests/<request_id>.json' (exact shape)

plus a contents schema mirroring the repository validator
(action allowlist, public-mutation denylist, required envelope keys), and
an optional preflight hook (e.g. the read-only ``bridge-preflight`` gate)
that must report plannable first.

Wiring: the caller supplies the ``delegate`` that performs the actual file
write (a test fake, an MCP tool, a plugin connector). The wrapper never
touches the network or the filesystem itself — enforcement lives at the
selection boundary, before delegation. A plugin/tool layer exposes ONLY
``transport_write`` with the schema in bridge/README.md; the native
ChatGPT/GitHub Connector router cannot be replaced from here, which is an
explicitly documented residual (see README), not a claimed fix.
"""

import hashlib
import json
import re

TRANSPORT_ACTION_CLASS = 'transport_write'
TRANSPORT_REPOSITORY = 'Bruce-Yii/awrp'
TRANSPORT_PATH_RE = re.compile(r'^bridge/requests/[A-Za-z0-9][A-Za-z0-9_-]*\.json$')
TRANSPORT_REQUEST_KEYS = frozenset({'action_class', 'repository', 'path', 'contents'})
TRANSPORT_ACTIONS = frozenset({'create-task', 'dispatch', 'review', 'approval', 'reconcile', 'incident-create', 'incident-update'})
# Mirrors tools/awrp.py PUBLIC_MUTATION_ACTIONS / PUBLIC_MUTATION_PARAMS;
# tests/test_awrp.py pins the equality so the two cannot drift apart.
PUBLIC_MUTATION_ACTIONS = frozenset({'create_issue', 'create_pull_request', 'comment_issue', 'comment_pull_request', 'close_issue', 'close_pull_request', 'reopen_issue', 'merge_pull_request', 'add_label', 'remove_label', 'assign_issue', 'set_milestone', 'create_release', 'delete_branch', 'push_upstream'})
PUBLIC_MUTATION_PARAMS = frozenset({'issue_number', 'issue_id', 'pull_number', 'comment_id', 'comment_body', 'labels', 'assignees', 'milestone_number', 'merge_method', 'close_reason', 'pr_head', 'pr_base', 'release_tag'})
CONTENTS_REQUIRED_KEYS = frozenset({'protocol', 'request_id', 'action', 'idempotency_key', 'expected_base', 'params'})


class IneligibleMutation(RuntimeError):
    """Raised before delegation whenever the intent is not a transport write."""


def _ineligible(what):
    return IneligibleMutation(
        f"{what} is ineligible for the AWRP transport path: only "
        f"action_class='transport_write' to repository "
        f"'{TRANSPORT_REPOSITORY}' path 'bridge/requests/<request_id>.json' "
        f"may be delegated; issue/PR/comment/label/close/merge/release/branch "
        f"mutations never reach a delegated call")


def canonical_contents_bytes(contents):
    return (json.dumps(contents, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8')


def validate_transport_request(request):
    """Return (request_id, contents_bytes) or raise IneligibleMutation.

    Pure validation: no I/O, no delegation, no side effects.
    """
    if not isinstance(request, dict):
        raise _ineligible('non-object transport intent')
    unknown = set(request) - TRANSPORT_REQUEST_KEYS
    if unknown:
        raise _ineligible(f'transport intent with forbidden keys {sorted(unknown)}')
    for key in TRANSPORT_REQUEST_KEYS:
        if request.get(key) is None:
            raise _ineligible(f'transport intent missing {key!r}')
    action_class = request['action_class']
    if action_class != TRANSPORT_ACTION_CLASS:
        raise _ineligible(f'action_class {action_class!r}')
    if request['repository'] != TRANSPORT_REPOSITORY:
        raise _ineligible(f"repository {request['repository']!r} (want {TRANSPORT_REPOSITORY!r})")
    path = request['path']
    if not isinstance(path, str) or not TRANSPORT_PATH_RE.match(path) or path.endswith('.result.json'):
        raise _ineligible(f'path {path!r}')
    request_id = path[len('bridge/requests/'):-len('.json')]
    contents = request['contents']
    if not isinstance(contents, dict):
        raise _ineligible('non-object contents')
    missing = CONTENTS_REQUIRED_KEYS - set(contents)
    if missing:
        raise _ineligible(f'contents missing {sorted(missing)}')
    if contents.get('request_id') != request_id:
        raise _ineligible('contents request_id does not match path stem')
    action = contents.get('action')
    if action in PUBLIC_MUTATION_ACTIONS or action not in TRANSPORT_ACTIONS:
        raise _ineligible(f'contents action {action!r}')
    params = contents.get('params')
    if not isinstance(params, dict):
        raise _ineligible('non-object contents params')
    bad = [k for k in params if k in PUBLIC_MUTATION_PARAMS]
    if bad:
        raise _ineligible(f'contents public-mutation params {sorted(bad)}')
    return request_id, canonical_contents_bytes(contents)


class FakeTransport:
    """Deterministic test double: records delegated writes, performs none."""

    def __init__(self):
        self.calls = []

    def write_file(self, path, data):
        self.calls.append({'path': path, 'sha256': 'sha256:' + hashlib.sha256(data).hexdigest(), 'size_bytes': len(data)})
        return self.calls[-1]


def transport_write(request, delegate, preflight=None):
    """Validate a transport intent, optionally gate on preflight, then delegate.

    ``delegate`` must expose ``write_file(path, data: bytes)``. ``preflight``,
    when given, is called as ``preflight(request)`` and must return a mapping
    with ``status == 'plannable'``; anything else raises before delegation.
    Returns the delegate receipt plus the content fingerprint.
    """
    request_id, data = validate_transport_request(request)
    if preflight is not None:
        verdict = preflight(request)
        if not isinstance(verdict, dict) or verdict.get('status') != 'plannable':
            raise IneligibleMutation(f'preflight refused transport for {request_id!r}: {verdict!r}; zero delegated calls')
    receipt = delegate.write_file(request['path'], data)
    return {'status': 'delegated', 'request_id': request_id, 'path': request['path'],
            'sha256': 'sha256:' + hashlib.sha256(data).hexdigest(), 'size_bytes': len(data),
            'delegate_receipt': receipt}
