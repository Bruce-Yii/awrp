#!/usr/bin/env python3
# Disposable end-to-end demo. Intentionally uses the legacy no-routing
# shape (no channel/endpoint): it exercises compatibility, not the
# Project-first path. Project-first flows need exact routing + binding.
import json, shutil, subprocess, sys
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]; DEMO=HERE/'.demo'
if DEMO.exists(): shutil.rmtree(DEMO)
DEMO.mkdir()
def run(*a):
    cp=subprocess.run([sys.executable,str(HERE/'tools'/'awrp.py'),*a],cwd=DEMO,text=True,capture_output=True)
    if cp.returncode: raise SystemExit(cp.stderr)
    return cp.stdout.strip()
run('init-context','--root','.','--context-id','ctx_demo','--title','Demo')
# Legacy shape on purpose: production create-task requires --project-id /
# --channel-id / --worker-endpoint unless --legacy is passed explicitly.
tid=run('create-task','--root','.','--context-id','ctx_demo','--title','Demo task','--goal','Demonstrate AWRP flow','--worker','codex','--legacy')
td=f'tasks/{tid}'
d=json.loads(run('emit','--task-dir',td,'--type','DISPATCH','--actor-role','coordinator','--actor-id','chatgpt','--recipient-role','worker','--recipient-id','codex','--new-run','--state','working','--phase','implementation','--waiting-on','codex','--run-state','dispatched','--summary','Do demo work.'))
rid=d['run_id']
run('emit','--task-dir',td,'--type','ACK','--actor-role','worker','--actor-id','codex','--recipient-role','coordinator','--recipient-id','chatgpt','--run-id',rid,'--state','working','--phase','implementation','--waiting-on','codex','--run-state','working','--summary','Accepted.')
run('emit','--task-dir',td,'--type','HANDOFF','--actor-role','worker','--actor-id','codex','--recipient-role','coordinator','--recipient-id','chatgpt','--run-id',rid,'--state','working','--phase','review','--waiting-on','chatgpt','--run-state','succeeded','--summary','Demo handoff.')
print(run('validate','--task-dir',td))
print(run('replay','--task-dir',td))
