"""Minimal single-purpose MCP facade for AWRP coordinator transport.

Exposes EXACTLY ONE tool, ``awrp_transport_write``, over newline-delimited
JSON-RPC on stdio (MCP-compatible framing). Every call is validated by
``tools/awrp_transport.py`` (transport_write binding + contents schema +
optional preflight hook) and, only on success, written as a file under the
rooted ``--base-dir``. No issue/PR/comment/label/close/merge/release/branch
operation exists on this surface, so a drifted selection cannot become a
public-object mutation through this facade — it fails here, before any
write, with zero side effects.

This facade cannot replace or reconfigure the native ChatGPT/GitHub
Connector router: a coordinator that keeps calling the native connector
bypasses this process entirely (as the observed Issues #7-#12 / #6022
proved). Platform-level closure requires the host to wire THIS server
instead of the native connector for AWRP transport and to run the live
acceptance in bridge/README.md. Until then the risk stays open by name.

Usage:
  python tools/awrp_mcp_transport.py --base-dir <relay-checkout-or-dir> [--preflight-cmd CMD]

--preflight-cmd, when given, runs after validation and before the write
with the canonical transport request JSON on its stdin; exit code 0 is
required. Wire it to a staging ``bridge-preflight`` check where available.
"""

import argparse
import hashlib
import json
import shlex
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import awrp_transport as T

TOOL_NAME = 'awrp_transport_write'
INPUT_SCHEMA = {
    'type': 'object',
    'required': ['action_class', 'repository', 'path', 'contents'],
    'additionalProperties': False,
    'properties': {
        'action_class': {'const': 'transport_write'},
        'repository': {'const': 'Bruce-Yii/awrp'},
        'path': {'type': 'string', 'pattern': r'^bridge/requests/[A-Za-z0-9][A-Za-z0-9_-]*\.json$'},
        'contents': {'type': 'object'},
    },
}


def _err(req_id, code, message):
    return {'jsonrpc': '2.0', 'id': req_id, 'error': {'code': code, 'message': message}}


def _run_preflight(cmd, request):
    try:
        cp = subprocess.run(shlex.split(cmd), input=json.dumps(request).encode(),
                            capture_output=True, timeout=120)
    except Exception as e:
        raise T.IneligibleMutation(f'preflight hook failed to run ({e}); zero writes')
    if cp.returncode != 0:
        tail = ((cp.stderr or cp.stdout) or b'').decode('utf-8', 'replace').strip()[:300]
        raise T.IneligibleMutation(f'preflight hook refused transport ({tail}); zero writes')
    return {'status': 'plannable'}


class Server:
    def __init__(self, base_dir, preflight_cmd=None):
        self.base = Path(base_dir).resolve()
        if not self.base.is_dir():
            raise RuntimeError(f'mcp transport base dir does not exist: {base_dir!r}')
        self.preflight_cmd = preflight_cmd

    def contained_path(self, rel):
        full = (self.base / rel).resolve()
        try:
            full.relative_to(self.base)
        except ValueError:
            raise T.IneligibleMutation(f'path {rel!r} escapes base dir; zero writes')
        return full

    def handle(self, msg):
        if not isinstance(msg, dict) or msg.get('jsonrpc') != '2.0' or 'method' not in msg:
            return _err(msg.get('id') if isinstance(msg, dict) else None, -32600, 'invalid JSON-RPC envelope')
        method = msg['method']
        req_id = msg.get('id')
        if method == 'initialize':
            if req_id is None:
                return None
            return {'jsonrpc': '2.0', 'id': req_id,
                    'result': {'protocolVersion': '2024-11-05', 'capabilities': {'tools': {}},
                               'serverInfo': {'name': 'awrp-transport', 'version': '0.1.0'}}}
        if method.startswith('notifications/'):
            return None
        if method == 'tools/list':
            return {'jsonrpc': '2.0', 'id': req_id,
                    'result': {'tools': [{'name': TOOL_NAME,
                                          'description': 'Write one AWRP bridge transport request file. No public-object mutations exist on this surface.',
                                          'inputSchema': INPUT_SCHEMA}]}}
        if method == 'tools/call':
            params = msg.get('params') or {}
            if params.get('name') != TOOL_NAME:
                return _err(req_id, -32602, f"unknown tool {params.get('name')!r}: this surface exposes only '{TOOL_NAME}'; zero writes")
            try:
                arguments = params.get('arguments') or {}
                hook = (lambda r: _run_preflight(self.preflight_cmd, r)) if self.preflight_cmd else None
                request_id, data = T.validate_transport_request(arguments)
                if hook is not None:
                    verdict = hook(arguments)
                    if not isinstance(verdict, dict) or verdict.get('status') != 'plannable':
                        raise T.IneligibleMutation(f'preflight refused transport for {request_id!r}; zero writes')
                dest = self.contained_path(arguments['path'])
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                digest = 'sha256:' + hashlib.sha256(data).hexdigest()
                return {'jsonrpc': '2.0', 'id': req_id,
                        'result': {'content': [{'type': 'text', 'text': json.dumps(
                            {'status': 'delegated', 'request_id': request_id, 'path': arguments['path'],
                             'sha256': digest, 'size_bytes': len(data)}, indent=2)}]}}
            except T.IneligibleMutation as e:
                return _err(req_id, -32602, str(e))
            except Exception as e:
                return _err(req_id, -32603, f'internal error before write completion: {e}')
        return _err(req_id, -32601, f'method {method!r} not found; this surface has no such operation')


def main(argv=None):
    ap = argparse.ArgumentParser(prog='awrp_mcp_transport')
    ap.add_argument('--base-dir', required=True)
    ap.add_argument('--preflight-cmd', default=None)
    a = ap.parse_args(argv)
    server = Server(a.base_dir, a.preflight_cmd)
    stdin = sys.stdin
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            sys.stdout.write(json.dumps(_err(None, -32700, 'parse error')) + '\n')
            sys.stdout.flush()
            continue
        try:
            resp = server.handle(msg)
        except Exception as e:
            resp = _err(msg.get('id') if isinstance(msg, dict) else None, -32603, f'internal error: {e}')
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + '\n')
            sys.stdout.flush()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
