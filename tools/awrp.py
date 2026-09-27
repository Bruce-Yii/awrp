#!/usr/bin/env python3
from __future__ import annotations
import argparse, copy, datetime as dt, hashlib, json, os, subprocess, sys, uuid
from pathlib import Path

PROTOCOL='awrp/0.1'
TASK_STATES={'submitted','working','input_required','completed','failed','canceled','rejected'}
TERMINAL={'completed','failed','canceled','rejected'}
EVENT_TYPES={'TASK_CREATED','DISPATCH','ACK','INPUT_REQUEST','INPUT_PROVIDED','HANDOFF','REVIEW','APPROVAL','CANCEL','ERROR','RECONCILE','NOTE'}
RUN_STATES={'dispatched','working','succeeded','failed','canceled'}
EXECUTION_TYPES={'DISPATCH','ACK','HANDOFF','INPUT_REQUEST','INPUT_PROVIDED','ERROR'}
ACTIVE_RUN_STATES={'dispatched','working'}
CLOSED_RUN_STATES={'succeeded','failed','canceled'}
ALLOWED={None:{'submitted'},'submitted':{'submitted','working','input_required','failed','canceled','rejected'},'working':{'working','input_required','completed','failed','canceled','rejected'},'input_required':{'input_required','working','completed','failed','canceled','rejected'},'completed':set(),'failed':set(),'canceled':set(),'rejected':set()}

def now(): return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
def newid(prefix): return f"{prefix}_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:10]}"
def readj(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def write_new(p,obj):
    # LF-stable worktree bytes on every platform: .gitattributes forces
    # eol=lf for canonical paths, and text-mode translation would otherwise
    # leave CRLF on Windows checkouts (blobs still normalize to LF, but
    # worktree-to-worktree byte comparisons across a rebase would then trip
    # on line endings instead of content).
    p=Path(p); p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists(): raise RuntimeError(f'refusing to overwrite canonical file: {p}')
    p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
def nofloats(v,path='$'):
    if isinstance(v,float): raise RuntimeError(f'floats forbidden in canonical machine data at {path}')
    if isinstance(v,dict):
        for k,x in v.items(): nofloats(x,f'{path}.{k}')
    elif isinstance(v,list):
        for i,x in enumerate(v): nofloats(x,f'{path}[{i}]')
def canon(e):
    o=copy.deepcopy(e); nofloats(o); o.setdefault('integrity',{}).pop('event_hash',None)
    return json.dumps(o,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def eh(e): return 'sha256:'+hashlib.sha256(canon(e)).hexdigest()

def load_events(td):
    rows=[]
    for p in (Path(td)/'events').glob('*.json'): rows.append((p,readj(p)))
    rows.sort(key=lambda x:x[1].get('seq',10**9)); return rows

def validate(td):
    td=Path(td); task=readj(td/'task.json'); rows=load_events(td)
    if task.get('protocol')!=PROTOCOL: raise RuntimeError('unsupported task protocol')
    if not rows: raise RuntimeError('task has no events')
    prev_id=prev_hash=prev_state=None; seqs=set(); ids=set(); runs={}; idemp={}; head=None
    for expected,(p,e) in enumerate(rows,1):
        for k in ['protocol','event_id','seq','context_id','task_id','type','actor','created_at','task_projection','summary','artifacts','integrity']:
            if k not in e: raise RuntimeError(f'{p}: missing {k}')
        if e['protocol']!=PROTOCOL: raise RuntimeError(f'{p}: bad protocol')
        if e['seq']!=expected or e['seq'] in seqs: raise RuntimeError(f'{p}: sequence gap/duplicate')
        seqs.add(e['seq'])
        if e['event_id'] in ids: raise RuntimeError(f'{p}: duplicate event_id')
        ids.add(e['event_id'])
        if e['task_id']!=task['task_id'] or e['context_id']!=task['context_id']: raise RuntimeError(f'{p}: task/context mismatch')
        if e['type'] not in EVENT_TYPES: raise RuntimeError(f'{p}: bad event type')
        st=e['task_projection']['state']
        if st not in TASK_STATES: raise RuntimeError(f'{p}: bad task state')
        if e['type']!='RECONCILE' and st not in ALLOWED.get(prev_state,set()): raise RuntimeError(f'{p}: illegal transition {prev_state}->{st}')
        integ=e['integrity']
        if integ.get('prev_event_id')!=prev_id or integ.get('prev_event_hash')!=prev_hash: raise RuntimeError(f'{p}: chain link mismatch')
        actual=eh(e)
        if integ.get('event_hash')!=actual: raise RuntimeError(f'{p}: event hash mismatch')
        rid=e.get('run_id'); run=e.get('run')
        if run and run.get('state') not in RUN_STATES: raise RuntimeError(f'{p}: bad run state')
        if e['type']=='DISPATCH':
            if not rid: raise RuntimeError(f'{p}: DISPATCH requires run_id')
            if rid in runs: raise RuntimeError(f'{p}: duplicate dispatch run_id')
            runs[rid]={'state':run.get('state') if run else None,'events':[e['event_id']],'executor':None}
        elif rid:
            if rid not in runs and e['type']!='RECONCILE': raise RuntimeError(f'{p}: undispatched run_id')
            if rid in runs:
                if run: runs[rid]['state']=run.get('state')
                runs[rid]['events'].append(e['event_id'])
                if e['type']=='ACK' and runs[rid].get('executor') is None:
                    runs[rid]['executor']=(e.get('actor') or {}).get('id')
        k=e.get('idempotency_key')
        if isinstance(k,str) and k and k not in idemp: idemp[k]=e['event_id']
        nofloats(e); prev_id=e['event_id']; prev_hash=integ['event_hash']; prev_state=st; head=e
    check_task_project(td,task)
    return {'task':task,'events':[e for _,e in rows],'head':head,'runs':runs,'active_run_id':derive_active_run([e for _,e in rows],prev_state),'idempotency':idemp}

def derive_active_run(events,head_state):
    if head_state in TERMINAL: return None
    active=None
    # NOTE is intentionally absent here: it is a non-execution communication
    # primitive and must never activate, close, or otherwise move a run.
    for e in events:
        t=e['type']; rid=e.get('run_id'); rs=(e.get('run') or {}).get('state')
        if t=='DISPATCH':
            if rid and rs in ACTIVE_RUN_STATES: active=rid
        elif t=='RECONCILE':
            active=rid if (rid and rs in ACTIVE_RUN_STATES) else None
        elif t=='CANCEL':
            active=None
        elif t=='HANDOFF':
            if rid and rs in CLOSED_RUN_STATES and active==rid: active=None
    return active

def beijing_time(iso):
    """Human-display helper: UTC canonical instant rendered as UTC+08:00.

    Canonical ordering/authority never uses wall-clock time; this is display
    only and must never be written into canonical fields.
    """
    try:
        d=dt.datetime.fromisoformat(str(iso).replace('Z','+00:00')).astimezone(dt.timezone(dt.timedelta(hours=8)))
        return d.strftime('%Y-%m-%d %H:%M:%S')+' UTC+08:00'
    except Exception: return '?'
def render_text(task,head):
    t=task; h=head; p=h['task_projection']; src=t.get('source')
    lines=[f"# [AWRP] {t['title']}",'','> Human-readable projection. Canonical state is the AWRP event log.','',f"- **Task ID:** `{t['task_id']}`",f"- **Context:** `{t['context_id']}`",f"- **State:** `{p['state']}`",f"- **Phase:** `{p['phase']}`",f"- **Waiting on:** `{p['waiting_on']}`",f"- **Head event:** `{h['event_id']}`",f"- **Head time (UTC+08:00):** `{beijing_time(h.get('created_at'))}`",f"- **Latest run:** `{h.get('run_id')}`"]
    if isinstance(src,dict) and src: lines.append(f"- **Source:** `{src.get('repo','')}#{src.get('number','')}`")
    elif isinstance(src,str) and src: lines.append(f"- **Source:** `{src}`")
    lines += ['','## Goal','',t['goal'],'','## Latest summary','',h.get('summary','')]
    return '\n'.join(lines)+'\n'
def render(td):
    v=validate(td); out=Path(td)/'TASK.md'; out.write_text(render_text(v['task'],v['head']),encoding='utf-8'); return out
def render_best_effort(td):
    try: return render(td)
    except Exception as e: print(f'AWRP WARNING: projection render failed; canonical event is durable: {e}',file=sys.stderr); return None

def relay_identity(root):
    """Canonical relay identity for stamping task transport.

    Reads root/'relay.json' ({"protocol":..., "relay":"OWNER/REPO"}).
    Returns the relay name, or None when the file is absent (legacy/local
    creation keeps working; render-bootstrap then fails closed with reason).
    A present-but-malformed file fails closed: never stamp a guessed identity.
    """
    p=Path(root)/'relay.json'
    if not p.exists(): return None
    try: o=json.loads(p.read_text(encoding='utf-8'))
    except Exception: raise RuntimeError(f'relay identity file {p} is unreadable; refusing to stamp relay identity')
    if o.get('protocol')!=PROTOCOL or not isinstance(o.get('relay'),str) or not o['relay'].strip():
        raise RuntimeError(f'relay identity file {p} is malformed; refusing to stamp relay identity')
    return o['relay'].strip()
def init_context(a):
    obj={'protocol':PROTOCOL,'context_id':a.context_id,'title':a.title,'created_at':now(),'description':a.description or ''}
    p=Path(a.root)/'contexts'/f'{a.context_id}.json'; write_new(p,obj); print(p)
def task_readiness(task,root=None):
    """Execution-readiness of a task manifest (read-only).

    Returns {'ok': bool, 'missing': [...], 'transport': ident-or-None}.
    Production (Project-first) readiness requires: project_id,
    routing.channel_id, routing.worker_endpoint, default_worker, authority,
    side_effect_policy, plus project/channel ownership when a root registry
    is available. Transport identity (relay.json) is reported, not
    required: it binds at publication time (bridge stamps what exists) so
    local creation stays portable; doctor surfaces its absence.
    """
    missing=[]
    if not task.get('project_id'): missing.append('project_id')
    r=task.get('routing') or {}
    if not r.get('channel_id'): missing.append('routing.channel_id')
    if not r.get('worker_endpoint'): missing.append('routing.worker_endpoint')
    if not task.get('default_worker'): missing.append('default_worker')
    auth=task.get('authority')
    if not isinstance(auth,dict) or not auth.get('coordinator') or not auth.get('final_authority'):
        missing.append('authority.coordinator+final_authority (non-empty identities required)')
    pol=task.get('side_effect_policy')
    _need={'local_read','local_write','local_commit','relay_write','push_user_fork','upstream_comment','upstream_pr_create','merge'}
    _known={'allow','dispatch_only','human_approval','deny'}
    if not isinstance(pol,dict):
        missing.append('side_effect_policy (object with policy keys required)')
    else:
        _absent=sorted(_need-set(pol))
        if _absent: missing.append(f"side_effect_policy missing keys: {', '.join(_absent)}")
        _bad=sorted(f'{k}={pol[k]!r}' for k in _need if k in pol and (not isinstance(pol[k],str) or not pol[k].strip() or pol[k] not in _known))
        if _bad: missing.append(f"side_effect_policy unrecognized values: {', '.join(_bad)}")
    if root is not None and task.get('project_id') and r.get('channel_id'):
        try:
            owner=channel_project(root,r['channel_id'])
        except RuntimeError as e:
            return {'ok':False,'missing':missing+[f'ownership: {e}'],'transport':relay_identity(root)}
        if owner!=task['project_id']:
            missing.append(f"ownership: channel {r['channel_id']!r} owned by {owner!r}, not {task['project_id']!r}")
    ident=relay_identity(root) if root is not None else None
    return {'ok':not missing,'missing':missing,'transport':ident}
def create_task(a):
    root=Path(a.root); cp=root/'contexts'/f'{a.context_id}.json'
    if not cp.exists(): raise RuntimeError(f'context not found: {cp}')
    tid=a.task_id or newid('task'); td=root/'tasks'/tid
    if td.exists(): raise RuntimeError('task already exists')
    cid=getattr(a,'channel_id',None); lid=getattr(a,'lane_id',None); ep=getattr(a,'worker_endpoint',None)
    proj=getattr(a,'project_id',None)
    if not getattr(a,'legacy',False):
        need={'--project-id':proj,'--channel-id':cid,'--worker-endpoint':ep}
        absent=[k for k,v in need.items() if not v]
        if absent: raise RuntimeError(f"create-task refuses incomplete execution manifest (missing {', '.join(absent)}); production tasks require project/routing identity — pass --legacy to explicitly mark historical/legacy shape, never omit silently")
    (td/'events').mkdir(parents=True); (td/'artifacts').mkdir()
    source=None if not (a.source_repo or a.source_issue is not None) else {'type':'github_issue','repo':a.source_repo or '','number':a.source_issue}
    ident=relay_identity(root)
    task={'protocol':PROTOCOL,'task_id':tid,'context_id':a.context_id,'title':a.title,'goal':a.goal,'created_at':now(),'created_by':a.created_by,'default_worker':a.worker,'source':source,'authority':{'coordinator':'chatgpt','final_authority':'human'},'side_effect_policy':{'local_read':'allow','local_write':'allow','local_commit':'allow','relay_write':'allow','push_user_fork':'dispatch_only','upstream_comment':'human_approval','upstream_pr_create':'human_approval','merge':'human_approval'},'transport':({'relay_repo':ident} if ident else {})}
    routing=None
    cid=getattr(a,'channel_id',None); lid=getattr(a,'lane_id',None); ep=getattr(a,'worker_endpoint',None)
    if cid or lid or ep: routing={'channel_id':cid,'lane_id':lid,'worker_endpoint':ep}; task['routing']=routing
    proj=getattr(a,'project_id',None)
    if proj:
        read_project(root,proj)
        if cid:
            owner=channel_project(root,cid)
            if owner!=proj: raise RuntimeError(f"project {proj!r} does not own channel {cid!r} (owned by {owner!r}); create-task rejects project/channel mismatch")
        task['project_id']=proj
    write_new(td/'task.json',task)
    e={'protocol':PROTOCOL,'event_id':newid('evt'),'seq':1,'context_id':a.context_id,'task_id':tid,'run_id':None,'type':'TASK_CREATED','actor':{'role':'coordinator','id':a.created_by},'recipient':None,'causation_id':None,'created_at':now(),'task_projection':{'state':'submitted','phase':'intake','waiting_on':'chatgpt'},'run':None,'artifacts':[],'summary':'Task created.','details':None,'approval':None,'integrity':{'prev_event_id':None,'prev_event_hash':None,'event_hash':''}}
    e['integrity']['event_hash']=eh(e); write_new(td/'events'/f"000001_{e['event_id']}.json",e); validate(td); render_best_effort(td); print(tid)
def recover_task(a):
    """Create a recovery Task from a corrupted predecessor's provenance.

    The predecessor chain is never copied and never touched: audit_chain()
    establishes the last-valid prefix, and the new task starts at its own
    seq1 TASK_CREATED carrying a provenance record (predecessor id,
    last-valid seq/event/hash, bad-event summary, approval digest +
    contract). A stored copy of the human approval bytes ships under the
    new task's artifacts/. Refuses when the predecessor is missing,
    unreadable, fully valid (nothing to recover), or has no valid prefix,
    and when the target task id already exists (create-only idempotency).
    With --run-id, the same invocation continues through the normal
    validated composer (_prepare_event, same as emit/dispatch-guarded) to
    append a seq2 DISPATCH for the successor run: recipient/waiting_on come
    from the new task's registered endpoint (identity gate applies),
    artifacts carry the approval + provenance refs, and the idempotency key
    defaults to a stable recovery-dispatch value so duplicate invocation
    refuses instead of forking. An explicit --expected-head pins CAS;
    --fencing-generation and --legacy-route pass through unchanged.
    """
    root=Path(a.root)
    pred=str(getattr(a,'predecessor_task',None) or '')
    ptd=root/'tasks'/pred
    if not (ptd/'task.json').exists(): raise RuntimeError(f'predecessor task {pred!r} is not in the relay; recover explicit exact predecessors, never inferred ones')
    audit=audit_chain(ptd)
    if audit.get('ok'):
        raise RuntimeError(f'predecessor task {pred!r} validates cleanly; recovery-task is for corrupted predecessors — nothing to recover')
    last_valid=audit.get('last_valid')
    if not last_valid:
        raise RuntimeError(f'predecessor task {pred!r} has no valid prefix (even seq1 fails); nothing trustworthy to anchor provenance to')
    bad=[{'seq':e.get('seq'),'event_id':e.get('event_id'),'failed':sorted(k for k,v in (e.get('checks') or {}).items() if not v.get('ok'))} for e in audit.get('events',[]) if not e.get('ok')]
    ap=Path(a.approval_file) if getattr(a,'approval_file',None) else None
    if ap is None or not ap.exists(): raise RuntimeError('recover-task requires --approval-file (human approval bytes); recovery without scoped approval is refused')
    contract=getattr(a,'contract',None)
    if not isinstance(contract,str) or not contract.strip(): raise RuntimeError('recover-task requires --contract (the approval contract text); recovery without a stated contract is refused')
    cp=root/'contexts'/f'{a.context_id}.json'
    if not cp.exists(): raise RuntimeError(f'context not found: {cp}')
    tid=a.task_id
    if not tid: raise RuntimeError('recover-task requires an explicit --task-id; never auto-name a recovery lineage')
    td=root/'tasks'/tid
    if td.exists(): raise RuntimeError(f'task already exists: {td}; re-running recovery refuses instead of duplicating')
    (td/'events').mkdir(parents=True); (td/'artifacts').mkdir()
    raw=ap.read_bytes(); fp=artifact_fingerprint(str(ap))
    aname='recovery-approval'+(''.join(Path(ap.name).suffixes[-1:]) if Path(ap.name).suffix else '.txt')
    (td/'artifacts'/aname).write_bytes(raw)
    ident=relay_identity(root)
    task={'protocol':PROTOCOL,'task_id':tid,'context_id':a.context_id,'title':a.title,'goal':a.goal,'created_at':now(),'created_by':a.created_by,'default_worker':a.worker,'source':None,'authority':{'coordinator':'chatgpt','final_authority':'human'},'side_effect_policy':{'local_read':'allow','local_write':'allow','local_commit':'allow','relay_write':'allow','push_user_fork':'dispatch_only','upstream_comment':'human_approval','upstream_pr_create':'human_approval','merge':'human_approval'},'transport':({'relay_repo':ident} if ident else {})}
    cid=getattr(a,'channel_id',None); lid=getattr(a,'lane_id',None); ep=getattr(a,'worker_endpoint',None)
    if cid or lid or ep: task['routing']={'channel_id':cid,'lane_id':lid,'worker_endpoint':ep}
    proj=getattr(a,'project_id',None)
    if proj:
        read_project(root,proj)
        if cid:
            owner=channel_project(root,cid)
            if owner!=proj: raise RuntimeError(f"project {proj!r} does not own channel {cid!r} (owned by {owner!r}); recover-task rejects project/channel mismatch")
        task['project_id']=proj
    details={'recovery_of':{'task_id':pred,'last_valid':last_valid},'bad_events':bad,'approval':{'path':f'tasks/{tid}/artifacts/{aname}','sha256':fp['sha256'],'size_bytes':fp['size_bytes'],'contract':contract.strip()},'note':'Recovery task: references predecessor provenance only; no predecessor events copied; predecessor history untouched.'}
    write_new(td/'task.json',task)
    e={'protocol':PROTOCOL,'event_id':newid('evt'),'seq':1,'context_id':a.context_id,'task_id':tid,'run_id':None,'type':'TASK_CREATED','actor':{'role':'coordinator','id':a.created_by},'recipient':None,'causation_id':None,'created_at':now(),'task_projection':{'state':'submitted','phase':'intake','waiting_on':'chatgpt'},'run':None,'artifacts':[],'summary':f'Recovery task for corrupted {pred} (last valid seq {last_valid["seq"]}); see details.','details':json.dumps(details,ensure_ascii=False,indent=2),'approval':None,'integrity':{'prev_event_id':None,'prev_event_hash':None,'event_hash':''}}
    e['integrity']['event_hash']=eh(e); write_new(td/'events'/f"000001_{e['event_id']}.json",e); validate(td); render_best_effort(td)
    if not getattr(a,'run_id',None):
        print(tid); return
    if not ep:
        raise RuntimeError('recover-task successor dispatch requires a registered routing.worker_endpoint; legacy tasks take the compat path via explicit dispatch instead')
    import tempfile as _tf2
    rid=a.run_id
    approval_ref={'kind':'recovery_approval','path':f'tasks/{tid}/artifacts/{aname}','sha256':fp['sha256'],'size_bytes':fp['size_bytes']}
    provenance_ref={'kind':'recovery_provenance','predecessor':pred,'last_valid_seq':last_valid['seq'],'last_valid_event':last_valid['event_id'],'last_valid_hash':last_valid['event_hash']}
    dtext=json.dumps({'recovery_of':{'task_id':pred,'last_valid':last_valid},'approval':{**approval_ref,'contract':contract.strip()},'successor_run':rid},ensure_ascii=False,indent=2)
    dfd,dfn=_tf2.mkstemp(suffix='.md'); afd,afn=_tf2.mkstemp(suffix='.json')
    try:
        import os as _os2
        _os2.close(dfd); _os2.close(afd)
        Path(dfn).write_text(dtext,encoding='utf-8')
        Path(afn).write_text(json.dumps([approval_ref,provenance_ref],ensure_ascii=False,indent=2),encoding='utf-8')
        class _D: pass
        d=_D(); d.task_dir=str(td); d.type='DISPATCH'; d.actor_role='coordinator'; d.actor_id=a.created_by
        d.recipient_role='worker'; d.recipient_id=ep
        d.run_id=rid; d.new_run=False; d.state='working'; d.phase=getattr(a,'phase',None) or 'recovery_execution'
        d.waiting_on=ep; d.run_state='dispatched'; d.summary=getattr(a,'run_summary',None) or f'Recovery successor run for corrupted {pred} (last valid seq {last_valid["seq"]})'
        d.details_file=dfn; d.artifacts_file=afn; d.approval_file=None; d.causation_id=None
        d.expected_head=getattr(a,'expected_head',None); d.expected_hash=None; d.claimant=None
        d.fencing_generation=getattr(a,'fencing_generation',None)
        d.idempotency_key=getattr(a,'idempotency_key',None) or f'recovery-dispatch-{pred}-seq{last_valid["seq"]}-{tid}'
        d.require_fresh=False; d.legacy_route=bool(getattr(a,'legacy_route',False))
        require_guarded_dispatch_path(td,d)
        v2,t2,h2,rid2,ev2=_prepare_event(td,d)
        ev2['integrity']['event_hash']=eh(ev2); _append_event_file(td,ev2)
        print(json.dumps({'task_id':tid,'run_id':rid2,'event_id':ev2['event_id'],'seq':ev2['seq'],'event_hash':ev2['integrity']['event_hash']},indent=2))
    finally:
        for _p in (dfn,afn):
            try: Path(_p).unlink()
            except OSError: pass
def require_guarded_dispatch_path(td,a):
    if a.type!='DISPATCH': return
    if getattr(a,'legacy_route',False): return
    root=task_root_of(td)
    if root is None: return
    t=readj(Path(td)/'task.json')
    ch=(t.get('routing') or {}).get('channel_id')
    if not ch: return
    owner=channel_project(root,ch)
    if owner is not None: raise RuntimeError(f"channel {ch!r} is owned by project {owner!r}; generic DISPATCH bypasses the binding-derived route guard — publish bound-workspace work with dispatch-guarded, or pass --legacy-route to explicitly mark legacy/internal use")
def emit(a):
    td=Path(a.task_dir)
    require_guarded_dispatch_path(td,a)
    v,t,h,rid,e=_prepare_event(td,a)
    e['integrity']['event_hash']=eh(e); _append_event_file(td,e)
    print(json.dumps({'event_id':e['event_id'],'seq':e['seq'],'run_id':rid,'event_hash':e['integrity']['event_hash']},indent=2))
def dispatch_identity(task,dispatch_event):
    """Classify routing/recipient identity consistency (read-only).

    Returns {'status': 'consistent'|'legacy_compat'|'mismatch', 'reason'}.
    Project-first tasks (registered routing.worker_endpoint) require the
    full triple: recipient.role == worker AND routing.worker_endpoint ==
    recipient.id == task_projection.waiting_on. Anything less is mismatch.
    Legacy tasks without a registered endpoint take the compatibility path
    — an endpoint is never guessed. Used as a pre-publication gate
    (mismatch refuses the append with zero trace) and as additive surfacing
    on inbox/replay/audit so historical malformed chains read as
    inconsistent, never as healthy actionable work.
    """
    ch,lane,ep=task_routing(task)
    if not ep:
        return {'status':'legacy_compat','reason':'task has no registered routing.worker_endpoint; legacy compatibility applies, endpoint never guessed'}
    rec=(dispatch_event or {}).get('recipient') or {}
    if rec.get('role')!='worker':
        return {'status':'mismatch','reason':f"routing.worker_endpoint is {ep!r} but DISPATCH recipient role is {rec.get('role')!r} (want 'worker')"}
    if rec.get('id')!=ep:
        return {'status':'mismatch','reason':f"routing.worker_endpoint is {ep!r} but DISPATCH recipient is worker/{rec.get('id')!r}"}
    w=((dispatch_event or {}).get('task_projection') or {}).get('waiting_on')
    if w!=ep:
        return {'status':'mismatch','reason':f"worker-dispatched execution waiting_on is {w!r}, not the registered endpoint {ep!r}"}
    return {'status':'consistent','reason':'recipient role/id and waiting_on match the registered endpoint'}
def _prepare_event(td,a):
    td=Path(td); v=validate(td); t=v['task']; h=v['head']; prev=h['task_projection']['state']
    key=getattr(a,'idempotency_key',None)
    if key is not None:
        if not isinstance(key,str) or not key: raise RuntimeError('idempotency_key must be a non-empty string when present')
        hit=(v.get('idempotency') or {}).get(key)
        if hit is not None:
            he=next((x for x in v['events'] if x['event_id']==hit),None)
            hh=(he.get('integrity') or {}).get('event_hash') if he else None
            where=f'event {hit} (hash {hh})' if hh else f'event {hit}'
            raise RuntimeError(f'duplicate command: idempotency_key {key!r} already recorded as {where}; fetch that outcome instead of resubmitting')
    if getattr(a,'require_fresh',False):
        rtd=Path(a.task_dir); rroot=rtd.parent.parent if rtd.parent.name=='tasks' else Path('.')
        check_freshness(rroot)
    if prev in TERMINAL and a.type!='RECONCILE': raise RuntimeError('task is terminal; only RECONCILE may continue')
    rid=newid('run') if a.new_run else a.run_id
    if a.type=='DISPATCH' and not rid: raise RuntimeError('DISPATCH requires --new-run or --run-id')
    if a.type=='DISPATCH' and rid in v['runs']: raise RuntimeError('run_id already dispatched')
    if a.type!='DISPATCH' and rid and rid not in v['runs'] and a.type!='RECONCILE': raise RuntimeError('unknown run_id')
    if getattr(a,'expected_head',None) and h['event_id']!=a.expected_head: raise RuntimeError(f"stale task head: expected {a.expected_head}, have {h['event_id']}; re-sync/replay before append")
    if getattr(a,'expected_hash',None) and h['integrity']['event_hash']!=a.expected_hash: raise RuntimeError(f"stale task head hash: expected {a.expected_hash}; re-sync/replay before append")
    active=v.get('active_run_id')
    if a.type=='DISPATCH':
        if active is not None: raise RuntimeError(f'run {active} is still active; terminate/supersede it via CANCEL/RECONCILE before dispatching a new run')
        _w=None if getattr(a,'waiting_on',None)=='null' else getattr(a,'waiting_on',None)
        _di=dispatch_identity(t,{'recipient':{'role':a.recipient_role,'id':a.recipient_id},'task_projection':{'waiting_on':_w}})
        if _di['status']=='mismatch': raise RuntimeError(f"DISPATCH identity refused: {_di['reason']}; Project-first DISPATCH must name the registered endpoint — re-plan, never publish crossed identity")
    elif a.type in EXECUTION_TYPES:
        if not rid or rid!=active: raise RuntimeError(f'run {rid} is not the authoritative active run (active={active}); re-sync/replay and use the current run')
    if a.type in ('REVIEW','APPROVAL') and rid:
        ordered=list((v.get('runs') or {}))
        latest=ordered[-1] if ordered else None
        # Attribution, not execution authority: the active run, or — when no
        # run is active — the latest dispatched run ONLY if it is a
        # legitimately closed reviewable succeeded result with valid
        # HANDOFF lineage. A latest failed/canceled/non-HANDOFF run does not
        # qualify merely by being latest; older runs were superseded.
        if rid!=active:
            ok_latest=(rid==latest and (v.get('runs') or {}).get(rid,{}).get('state')=='succeeded'
                       and any(x['type']=='HANDOFF' and x.get('run_id')==rid for x in v['events']))
            if not ok_latest:
                raise RuntimeError(f'{a.type} targets run {rid} which is neither the authoritative active run (active={active}) nor the latest reviewable succeeded result (latest={latest}); stale lineage refused — review the current result')
    if a.type=='ACK':
        if any(e['type']=='ACK' and e.get('run_id')==rid for e in v['events']): raise RuntimeError(f'run {rid} is already claimed (ACK exists); a second session must stop as owned/interrupted, never re-execute or re-ACK')
        # Execution identity: on Project-first tasks the ACK proves the
        # exact dispatched lineage — actor must equal the canonical
        # dispatched endpoint. Legacy tasks without a registered endpoint
        # take compatibility and skip this check (endpoint never guessed).
        _dsp=next((x for x in v['events'] if x['type']=='DISPATCH' and x.get('run_id')==rid),None)
        if _dsp is None: raise RuntimeError(f'ACK refuses: no DISPATCH for run {rid!r}; ACK never creates lineage, only claims dispatched work')
        _ch,_ln,_ep=task_routing(t)
        if _ep:
            _rec=_dsp.get('recipient') or {}
            if _rec.get('role')!='worker' or _rec.get('id')!=_ep: raise RuntimeError(f"ACK refuses: DISPATCH recipient ({_rec.get('role')}/{_rec.get('id')!r}) does not match the registered endpoint ({_ep!r}); crossed identity never executes")
            if a.actor_id!=_ep: raise RuntimeError(f"ACK refuses: actor {a.actor_id!r} is not the canonical dispatched endpoint ({_ep!r}); UI/session windows may change, execution identity may not drift")
            # Fencing-at-creation (positive-proof parity with the shared
            # fencing_authority validator): the DISPATCH must have been
            # validly fenced when created (generation+owner present in the
            # channel claim log) or predate claims (grandfathered). Later
            # claim rotation alone never revokes a valid worker Run — the
            # current generation is deliberately NOT consulted here.
            _f=_dsp.get('fencing')
            if _f:
                _root=td.parent.parent if td.parent.name=='tasks' else None
                if not claim_history_contains(_root,_f.get('channel_id'),_f.get('generation'),_f.get('owner')):
                    raise RuntimeError(f"ACK refuses: DISPATCH fencing {(_f.get('channel_id'),_f.get('generation'),_f.get('owner'))!r} has no matching channel claim-log entry; forged or orphaned fencing never seats execution")
    if a.type=='NOTE':
        # Non-execution communication primitive: projection-neutral narrative/
        # evidence only. It must not move Task/Run authority by construction:
        # same state/phase/waiting_on/run-state as the current head, a directed
        # recipient, no fencing stamp, no new run, and any referenced run must
        # already exist (reference only — never activation, claim, or lineage).
        if a.actor_role not in ('worker','coordinator'): raise RuntimeError(f"NOTE actor role must be worker or coordinator, got {a.actor_role!r}; forged authority refused")
        if not getattr(a,'recipient_role',None) or not getattr(a,'recipient_id',None): raise RuntimeError('NOTE requires an explicit recipient (directed message); broadcast notes are refused')
        if getattr(a,'new_run',False): raise RuntimeError('NOTE never opens a run; revisions need a coordinator DISPATCH')
        if getattr(a,'fencing_generation',None) is not None: raise RuntimeError('NOTE carries no fencing stamp; it mutates no authority')
        hp=h['task_projection']
        if a.state!=hp['state'] or a.phase!=hp['phase']: raise RuntimeError(f"NOTE is projection-neutral: state/phase must repeat the head ({hp['state']}/{hp['phase']}), got ({a.state}/{a.phase})")
        want_wait=hp['waiting_on']
        got_wait=None if getattr(a,'waiting_on',None)=='null' else getattr(a,'waiting_on',None)
        if got_wait!=want_wait: raise RuntimeError(f'NOTE is projection-neutral: waiting_on must repeat the head ({want_wait!r}), got ({got_wait!r})')
        if rid is None:
            if getattr(a,'run_state',None): raise RuntimeError('task-level NOTE (no run) carries no run state')
        else:
            cur_rs=(v.get('runs') or {}).get(rid,{}).get('state')
            if getattr(a,'run_state',None) and a.run_state!=cur_rs: raise RuntimeError(f"NOTE is projection-neutral: run state must repeat the referenced run ({cur_rs!r}), got ({a.run_state!r})")
        # Provenance: canonical evidence must be attributable, or any worker
        # id could inject untrusted content into history. A run-referenced
        # worker NOTE binds to the run's legitimate author — the seated
        # executor once one exists, else the DISPATCH recipient. A task-level
        # worker NOTE binds to the task routing worker identity. A coordinator
        # NOTE binds to the task coordinator. Attribution without authority:
        # passing this check grants no execution right.
        if a.actor_role=='worker':
            if rid is None:
                _ch,_ln,_ep=task_routing(t)
                _want=_ep or t.get('default_worker')
                if a.actor_id!=_want: raise RuntimeError(f"task-level worker NOTE must come from the task worker identity ({_want!r}), not {a.actor_id!r}; unattributed evidence refused")
            else:
                _ex=(v.get('runs') or {}).get(rid,{}).get('executor')
                if _ex is not None:
                    if a.actor_id!=_ex: raise RuntimeError(f"run-referenced worker NOTE must come from the run executor ({_ex!r}), not {a.actor_id!r}; unattributed evidence refused")
                else:
                    _rec=None
                    for _e in v['events']:
                        if _e['type']=='DISPATCH' and _e.get('run_id')==rid:
                            _rec=(_e.get('recipient') or {}).get('id'); break
                    if a.actor_id!=_rec: raise RuntimeError(f"pre-claim worker NOTE must come from the dispatched recipient ({_rec!r}), not {a.actor_id!r}; unattributed evidence refused")
        else:
            _coord=(t.get('authority') or {}).get('coordinator')
            if a.actor_id!=_coord: raise RuntimeError(f"coordinator NOTE must come from the task coordinator ({_coord!r}), not {a.actor_id!r}")
    if a.state in TERMINAL and a.actor_role!='coordinator':
        raise RuntimeError(f"task terminal transition {prev}->{a.state} requires coordinator authority; worker completion never equals Task acceptance (actor {a.actor_role}/{a.actor_id!r})")
    if a.type=='RECONCILE' and a.actor_role!='coordinator':
        raise RuntimeError(f"RECONCILE is coordinator governance (actor {a.actor_role}/{a.actor_id!r}); workers report via HANDOFF/INPUT_REQUEST/ERROR")
    if a.type in ('ACK','HANDOFF','INPUT_REQUEST','INPUT_PROVIDED','ERROR') and rid:
        ex=(v.get('runs') or {}).get(rid,{}).get('executor')
        if ex is not None and a.actor_id!=ex:
            raise RuntimeError(f"run {rid} is owned by executor {ex!r} (first ACK); reports from {a.actor_id!r} are refused — a replacement needs CANCEL/RECONCILE plus a new DISPATCH, never hijack")
    fg=getattr(a,'fencing_generation',None)
    fencing_stamp=None
    def _require_claim_owner(ch,cur):
        if a.actor_role!='coordinator' or a.actor_id!=cur.get('owner'):
            raise RuntimeError(f"coordinator authority mismatch on channel {ch}: claim generation {cur.get('generation')} is owned by {cur.get('owner')!r}, but the event actor is {a.actor_role}/{a.actor_id!r}; a worker event must never carry another owner's fencing identity (seq17-class bypass); re-sync, hold the claim, and publish as the claim owner")
    def _fencing_claim():
        td=Path(a.task_dir)
        root=td.parent.parent if td.parent.name=='tasks' else None
        ch,_,_=task_routing(t)
        if not ch:
            if fg is not None: raise RuntimeError('fencing requires a channel-bound task; legacy tasks have no claim domain')
            return (None,None)
        if root is None: return (ch,None)
        return (ch,read_claim(root,ch))
    def _fencing_authority_for_task():
        _td=Path(a.task_dir)
        _root=_td.parent.parent if _td.parent.name=='tasks' else None
        _ch,_,_=task_routing(t)
        if not _ch or _root is None: return (_ch,None)
        return (_ch,fencing_authority(_root,_ch))
    if a.type in ('DISPATCH','RECONCILE','REVIEW','APPROVAL','CANCEL'):
        ch,auth=_fencing_authority_for_task()
        if auth is not None and auth['status'] in ('inconsistent','legacy-claim'):
            raise RuntimeError(f"channel {ch} fencing authority is {auth['status']} ({auth['detail']}); claim.json alone never authorizes a new fenced mutation — run migrate-claim to record the exact existing claim bytes as history first (repair-claim when history is ahead or the live claim is missing)")
        ch,cur=_fencing_claim()
        if cur is not None:
            _require_claim_owner(ch,cur)
            if fg is None: raise RuntimeError(f'channel {ch} has an active coordinator claim (generation {cur.get("generation")}); coordinator writes must carry --fencing-generation; legacy opt-out is closed')
            if cur.get('generation')!=int(fg): raise RuntimeError(f"stale coordinator fencing: claim generation is {cur.get('generation')}, need {fg}; re-sync, re-acquire claim, never append on stale authority")
            fencing_stamp={'channel_id':ch,'generation':int(fg),'owner':cur.get('owner')}
        elif fg is not None:
            raise RuntimeError(f'no active coordinator claim for channel {ch}; acquire the claim first, never fence against a missing generation')
    elif fg is not None:
        ch,auth=_fencing_authority_for_task()
        if auth is not None and auth['status'] in ('inconsistent','legacy-claim'):
            raise RuntimeError(f"channel {ch} fencing authority is {auth['status']} ({auth['detail']}); claim.json alone never authorizes a new fenced mutation — run migrate-claim to record the exact existing claim bytes as history first (repair-claim when history is ahead or the live claim is missing)")
        ch,cur=_fencing_claim()
        if cur is None or cur.get('generation')!=int(fg): raise RuntimeError(f"stale coordinator fencing: claim generation is {cur.get('generation') if cur else None}, need {fg}; re-sync, re-acquire claim, never append on stale authority")
        _require_claim_owner(ch,cur)
        fencing_stamp={'channel_id':ch,'generation':int(fg),'owner':cur.get('owner')}
    if a.type!='RECONCILE' and a.state not in ALLOWED.get(prev,set()): raise RuntimeError(f'illegal transition {prev}->{a.state}')
    details=Path(a.details_file).read_text(encoding='utf-8') if a.details_file else None
    artifacts=readj(a.artifacts_file) if a.artifacts_file else []
    approval=readj(a.approval_file) if a.approval_file else None
    nofloats({'details':details,'artifacts':artifacts,'approval':approval})
    e={'protocol':PROTOCOL,'event_id':newid('evt'),'seq':h['seq']+1,'context_id':t['context_id'],'task_id':t['task_id'],'run_id':rid,'type':a.type,'actor':{'role':a.actor_role,'id':a.actor_id},'recipient':({'role':a.recipient_role,'id':a.recipient_id} if a.recipient_role and a.recipient_id else None),'causation_id':a.causation_id,'created_at':now(),'task_projection':{'state':a.state,'phase':a.phase,'waiting_on':None if a.waiting_on=='null' else a.waiting_on},'run':({'state':a.run_state} if a.run_state else None),'artifacts':artifacts,'summary':a.summary,'details':details,'approval':approval,'integrity':{'prev_event_id':h['event_id'],'prev_event_hash':h['integrity']['event_hash'],'event_hash':''}}
    if key is not None: e['idempotency_key']=key
    if getattr(a,'claimant',None): e['claimant']=a.claimant
    if fencing_stamp: e['fencing']=fencing_stamp
    return (v,t,h,rid,e)
def _append_event_file(td,e):
    """Write one candidate event file, then validate, then render.

    A rejected candidate must leave zero canonical trace: if post-write
    validation fails, the new file is unlinked before the error propagates.
    The TASK.md projection renders only after validation succeeds, so a
    rejection never touches it either.
    """
    td=Path(td)
    p=td/'events'/f"{e['seq']:06d}_{e['event_id']}.json"
    write_new(p,e)
    try:
        validate(td)
    except BaseException:
        try: p.unlink()
        except OSError: pass
        raise
    render_best_effort(td)
    return p
# ---- Bridge two-base + semantic-CAS semantics ----
# A live connector captures expected_base (the canonical snapshot H0) BEFORE
# creating bridge/requests/<id>.json. Creating that request advances main to
# H1, so by the time Actions runs bridge-process, remote main (H1) rarely
# equals expected_base (H0). Treating every advance as a stale-write race
# deterministically rejects live requests — including drift caused solely by
# UNRELATED tasks (cross-project false contention).
# The bridge therefore applies semantic-CAS-first: a gap is accepted, and the
# already-composed (post-pull, latest-state) event published, when every
# semantic invariant still holds. Only bridge-process opts in
# (allow_transport_gap=True); direct planning paths (plan-task-create,
# compose-intent, publish-atomic, publish-connector) stay strict.
BRIDGE_REQUEST_DIR_PREFIX='bridge/requests/'
BRIDGE_MAX_ATTEMPTS=3
def _is_transport_only_path(path):
    if not isinstance(path,str): return False
    if '..' in Path(path).parts: return False
    if not path.startswith(BRIDGE_REQUEST_DIR_PREFIX): return False
    rest=path[len(BRIDGE_REQUEST_DIR_PREFIX):]
    if '/' in rest or not rest.endswith('.json'): return False
    if rest.endswith('.result.json'): return False
    return True
def _bridge_semantic_base(repo,remote,branch,expected_base,task_id=None,channel_id=None,exp_head=None,exp_hash=None,latest_head=None):
    """Two-base + semantic-CAS check for the bridge path.

    Returns (remote_head, gap_kind, gap_files). gap_kind is 'exact',
    'transport-only', 'target-verified', or 'unrelated-canonical'. Raises
    RuntimeError (stale) when the drift touches the target task without the
    request explicitly naming the current head (expected_head/hash equal to
    latest), when it touches the target channel's claim files (fencing
    authority moved), or when the base is missing/diverged. Callers still
    enforce the remaining semantic invariants live (expected_head/hash,
    active run, terminal state, idempotency/target-path uniqueness, route
    ownership) against post-pull state before any write. Creation uses the
    same rule: task-absence checks already guard uniqueness, so unrelated
    drift never blocks it.
    """
    rh=git_out(repo,'ls-remote',remote,branch)
    remote_head=rh.split()[0] if rh else None
    if not expected_base:
        raise RuntimeError('bridge request requires the captured remote head as expected_base')
    if remote_head==expected_base:
        return (remote_head,'exact',None)
    if not remote_head:
        raise RuntimeError(f'remote {remote}/{branch} has no head to compare; re-sync before bridge composition')
    cp=subprocess.run(['git','-C',str(repo),'merge-base','--is-ancestor',expected_base,remote_head],capture_output=True,text=True)
    if cp.returncode!=0:
        raise RuntimeError(f'remote {remote}/{branch} moved since captured base (have {remote_head}, expected {expected_base}); history diverged or was rewritten: re-plan, never publish stale')
    try:
        out=git_out(repo,'diff','--name-only',expected_base,remote_head,'--')
    except RuntimeError:
        raise RuntimeError(f'remote {remote}/{branch} moved since captured base (have {remote_head}, expected {expected_base}); re-plan, never publish stale')
    files=[l.strip() for l in out.splitlines() if l.strip()]
    other=[f for f in files if not _is_transport_only_path(f)]
    if not other:
        return (remote_head,'transport-only',files)
    if task_id:
        hit=[f for f in other if f.startswith(f'tasks/{task_id}/')]
        if hit:
            if exp_head and exp_hash and latest_head and exp_head==latest_head[0] and exp_hash==latest_head[1]:
                return (remote_head,'target-verified',files)
            extra='...' if len(hit)>5 else ''
            raise RuntimeError(f"remote {remote}/{branch} moved the target task since captured base (have {remote_head}, expected {expected_base}); target files changed ({', '.join(hit[:5])}{extra}); re-plan, never publish stale")
    if channel_id:
        hit=[f for f in other if f.startswith(f'channels/{channel_id}/')]
        if hit:
            raise RuntimeError(f"remote {remote}/{branch} moved channel {channel_id!r} claim state since captured base (have {remote_head}, expected {expected_base}); fencing authority moved: re-plan, never publish stale")
    return (remote_head,'unrelated-canonical',other)
def _plan_new_task(root,task_id,context_id,title,goal,worker,created_by,source_repo,source_issue,channel_id,lane_id,worker_endpoint,project_id,created_at,expected_base,repo,branch,remote,allow_transport_gap=False):
    import re as _re2
    root=Path(root)
    tid=task_id or ''
    if not tid or not _re2.match(r'^[A-Za-z0-9][A-Za-z0-9_-]*$',tid): raise RuntimeError(f'invalid task_id {tid!r}; planner refuses path-unsafe identities')
    cp=root/'contexts'/f'{context_id}.json'
    if not cp.exists(): raise RuntimeError(f'context not found: {cp}')
    if project_id: read_project(root,project_id)
    if project_id and channel_id:
        owner=channel_project(root,channel_id)
        if owner!=project_id: raise RuntimeError(f"project {project_id!r} does not own channel {channel_id!r} (owned by {owner!r})")
    td=root/'tasks'/tid
    if td.exists(): raise RuntimeError(f'task already exists: {td}; create-only refuses overwrite')
    if not expected_base: raise RuntimeError('task creation planning requires a captured remote head (expected-base); without a CAS anchor there is no safe publication plan')
    if allow_transport_gap:
        remote_head,gap_kind,gap=_bridge_semantic_base(repo,remote,branch,expected_base,tid,channel_id)
    else:
        remote_head=remote_head_of(repo,remote,branch)
        if remote_head!=expected_base: raise RuntimeError(f'remote {remote}/{branch} moved since captured base (have {remote_head}, expected {expected_base}); re-plan, never publish stale')
        gap_kind,gap='exact',None
    eff_base=remote_head if remote_head!=expected_base else expected_base
    base_tree=git_out(repo,'rev-parse',f'{eff_base}^{{tree}}')
    created=created_at or now()
    evid='evt_'+created.replace('-','').replace(':','')+'_'+hashlib.sha256(tid.encode()).hexdigest()[:10]
    source=None if not (source_repo or source_issue is not None) else {'type':'github_issue','repo':source_repo or '','number':source_issue}
    ident=relay_identity(root)
    task={'protocol':PROTOCOL,'task_id':tid,'context_id':context_id,'title':title,'goal':goal,'created_at':created,'created_by':created_by,'default_worker':worker,'source':source,'authority':{'coordinator':'chatgpt','final_authority':'human'},'side_effect_policy':{'local_read':'allow','local_write':'allow','local_commit':'allow','relay_write':'allow','push_user_fork':'dispatch_only','upstream_comment':'human_approval','upstream_pr_create':'human_approval','merge':'human_approval'},'transport':({'relay_repo':ident} if ident else {})}
    routing=None
    if channel_id or lane_id or worker_endpoint: routing={'channel_id':channel_id,'lane_id':lane_id,'worker_endpoint':worker_endpoint}; task['routing']=routing
    if project_id: task['project_id']=project_id
    e={'protocol':PROTOCOL,'event_id':evid,'seq':1,'context_id':context_id,'task_id':tid,'run_id':None,'type':'TASK_CREATED','actor':{'role':'coordinator','id':created_by},'recipient':None,'causation_id':None,'created_at':created,'task_projection':{'state':'submitted','phase':'intake','waiting_on':'chatgpt'},'run':None,'artifacts':[],'summary':'Task created.','details':None,'approval':None,'integrity':{'prev_event_id':None,'prev_event_hash':None,'event_hash':''}}
    e['integrity']['event_hash']=eh(e)
    taskmd=render_text(task,e)
    event_name=f"000001_{evid}.json"
    paths={'task_json':f'tasks/{tid}/task.json','event':f'tasks/{tid}/events/{event_name}','projection':f'tasks/{tid}/TASK.md'}
    api_plan={'steps':['verify-absent('+paths['task_json']+') via read-back 404','create-blob(task.json)','create-blob(event JSON)','create-blob(TASK.md projection)','create-tree(base_tree=<captured head tree>, entries=3 paths)','create-commit(message, tree, parents=[<captured remote head>])','update-ref(refs/heads/<branch>, sha=<new commit>, force=false)','read-back event + recompute event_hash + validate'],'parents':[eff_base],'base_tree':base_tree,'event_path':paths['event'],'ref':f'refs/heads/{branch}','force':False}
    return {'task_id':tid,'event_id':evid,'event_hash':e['integrity']['event_hash'],'task_json':task,'event':e,'taskmd_projection':taskmd,'paths':paths,'api_plan':api_plan,'expected_base':expected_base,'remote_head':remote_head,'transport_gap':gap,'gap_kind':gap_kind}
def do_plan_task_create(a):
    print(json.dumps(_plan_new_task(a.root,a.task_id,a.context_id,a.title,a.goal,a.worker,a.created_by,a.source_repo,a.source_issue,a.channel_id,a.lane_id,a.worker_endpoint,a.project_id,getattr(a,'created_at',None),a.expected_base,getattr(a,'repo',None) or '.',getattr(a,'branch',None) or 'main',getattr(a,'remote',None) or 'origin'),indent=2))
INTENT_ACTIONS={
 'create-task':{'required':['task_id','context_id','title','goal'],'optional':['worker','created_by','source_repo','source_issue','channel_id','lane_id','worker_endpoint','project_id','created_at']},
 'dispatch':{'required':['task_id','state','phase','summary'],'optional':['run_id','new_run','recipient_role','recipient_id','waiting_on','run_state','details','artifacts','approval','causation_id','expected_head','expected_hash','claimant','fencing_generation','idempotency_key']},
 'review':{'required':['task_id','state','phase','summary'],'optional':['run_id','new_run','recipient_role','recipient_id','waiting_on','run_state','details','artifacts','approval','causation_id','expected_head','expected_hash','claimant','fencing_generation','idempotency_key']},
 'approval':{'required':['task_id','state','phase','summary'],'optional':['run_id','new_run','recipient_role','recipient_id','waiting_on','run_state','details','artifacts','approval','causation_id','expected_head','expected_hash','claimant','fencing_generation','idempotency_key']},
  'reconcile':{'required':['task_id','state','phase','summary'],'optional':['run_id','new_run','recipient_role','recipient_id','waiting_on','run_state','details','artifacts','approval','causation_id','expected_head','expected_hash','claimant','fencing_generation','idempotency_key']},
  'incident-create':{'required':['incident_id','title','summary','severity','category','reporter_id','symptom','impact','evidence'],'optional':['reporter_role','reporter_surface','detected_at','refs','violated_invariant','expected_behavior','containment','remediation','related_incidents','note','idempotency_key']},
  'incident-update':{'required':['incident_id','reporter_id'],'optional':['reporter_role','status','note','evidence_add','remediation','root_cause','resolution_evidence','related_add','duplicate_of','idempotency_key']},
}
# ---- External-mutation action guard ----
# The AWRP coordinator transport path performs only file writes under
# bridge/requests/ + tasks/ + channels/ and git push to the relay remote; it
# never calls GitHub Issues/PRs/comments/labels/close/merge APIs. A past
# incident class selected a public-object mutation (create_issue) where the
# intent was a transport write, before any repository code could intervene.
# The repository cannot control that upstream router, but it CAN refuse to
# give such intents a canonical shape: any action or param naming a
# public-object mutation is explicitly ineligible here, rejected before
# composition with a message that names the ineligible class. (Unknown keys
# were already refused; this denylist exists so the refusal is targeted and
# machine-checkable, and so the transport surface stays pinned.)
PUBLIC_MUTATION_ACTIONS=frozenset({'create_issue','create_pull_request','comment_issue','comment_pull_request','close_issue','close_pull_request','reopen_issue','merge_pull_request','add_label','remove_label','assign_issue','set_milestone','create_release','delete_branch','push_upstream'})
PUBLIC_MUTATION_PARAMS=frozenset({'issue_number','issue_id','pull_number','comment_id','comment_body','labels','assignees','milestone_number','merge_method','close_reason','pr_head','pr_base','release_tag'})
def _reject_public_mutation(action,params,where):
    if action in PUBLIC_MUTATION_ACTIONS:
        raise RuntimeError(f"{where} names public-mutation action {action!r}: issue/PR/comment/label/close/merge mutations are ineligible for the AWRP transport path (transport writes only bridge/requests/*.json plus canonical task/channel files)")
    bad=[k for k in (params or {}) if k in PUBLIC_MUTATION_PARAMS]
    if bad:
        raise RuntimeError(f"{where} carries public-mutation params {sorted(bad)}: issue/PR/comment/label/close/merge mutations are ineligible for the AWRP transport path (transport writes only bridge/requests/*.json plus canonical task/channel files)")
def _compose_append_plan(root,repo,branch,remote,expected_base,action,params,actor_role,actor_id,allow_transport_gap=False):
    import tempfile as _tf2
    p=params; tid=p['task_id']
    td=Path(root)/'tasks'/tid
    if not (td/'task.json').exists(): raise RuntimeError(f'exact target {tid!r} is not in the relay; the bridge never scans for alternatives')
    tmps=[]
    def _inline(content,suffix):
        if content is None: return None
        fd,nm=_tf2.mkstemp(suffix=suffix); tmps.append(nm)
        try: os.close(fd)
        except OSError: pass
        Path(nm).write_text(content if isinstance(content,str) else json.dumps(content,ensure_ascii=False,indent=2),encoding='utf-8')
        return nm
    try:
        g=argparse.Namespace(task_dir=str(td),type={'dispatch':'DISPATCH','review':'REVIEW','approval':'APPROVAL','reconcile':'RECONCILE'}[action],actor_role=actor_role,actor_id=actor_id,recipient_role=p.get('recipient_role'),recipient_id=p.get('recipient_id'),run_id=p.get('run_id'),new_run=bool(p.get('new_run')),state=p['state'],phase=p['phase'],waiting_on=p.get('waiting_on','null'),run_state=p.get('run_state'),summary=p['summary'],details_file=_inline(p.get('details'),'.md'),artifacts_file=_inline(p.get('artifacts'),'.json'),approval_file=_inline(p.get('approval'),'.json'),causation_id=p.get('causation_id'),expected_head=p.get('expected_head'),expected_hash=p.get('expected_hash'),claimant=p.get('claimant'),fencing_generation=p.get('fencing_generation'),idempotency_key=p.get('idempotency_key'),require_fresh=False)
        v,t,h,rid,e=_prepare_event(td,g)
        if allow_transport_gap:
            tch=(t.get('routing') or {}).get('channel_id')
            remote_head,gap_kind,gap=_bridge_semantic_base(repo,remote,branch,expected_base,tid,tch,p.get('expected_head'),p.get('expected_hash'),(h['event_id'],h['integrity']['event_hash']))
        else:
            remote_head=remote_head_of(repo,remote,branch)
            if remote_head!=expected_base: raise RuntimeError(f'remote {remote}/{branch} moved since captured base (have {remote_head}, expected {expected_base}); re-plan, never publish stale')
            gap_kind,gap='exact',None
        e,event_bytes,taskmd_text,api_plan=_plan_append(td,t,h,e,repo,branch,remote,expected_base,remote_head)
        plan={'event_id':e['event_id'],'seq':e['seq'],'run_id':rid,'event_hash':e['integrity']['event_hash'],'event':e,'taskmd_projection':taskmd_text,'api_plan':api_plan,'expected_base':expected_base,'remote_head':remote_head,'transport_gap':gap,'gap_kind':gap_kind}
        return (tid,rid,plan)
    finally:
        for nm in tmps:
            try: Path(nm).unlink()
            except OSError: pass
def do_compose_intent(a):
    intent=readj(a.intent_file)
    if not isinstance(intent,dict): raise RuntimeError('intent file must contain one JSON object')
    unknown_top=set(intent)-{'action','idempotency_key','params'}
    if unknown_top: raise RuntimeError(f'intent file carries forbidden top-level keys {sorted(unknown_top)}; canonical material (event ids, seq, hashes, links, actors, fencing) can never be supplied, only composed')
    action=intent.get('action'); key=intent.get('idempotency_key')
    _reject_public_mutation(action,intent.get('params'),'intent file')
    if action not in INTENT_ACTIONS: raise RuntimeError(f'intent action must be one of {sorted(INTENT_ACTIONS)}; got {action!r}')
    if not isinstance(key,str) or not key: raise RuntimeError('intent requires an opaque non-empty idempotency_key (echoed, never interpreted)')
    params=intent.get('params')
    if not isinstance(params,dict): raise RuntimeError('intent params must be an object')
    spec=INTENT_ACTIONS[action]
    unknown=set(params)-set(spec['required']+spec['optional'])
    if unknown: raise RuntimeError(f'intent params contain forbidden keys {sorted(unknown)}; canonical bytes (ids, seq, hashes, links, states outside content fields, fencing objects) can never be supplied, only composed')
    for k in spec['required']:
        if params.get(k) is None: raise RuntimeError(f'intent params missing required {k!r} for action {action!r}')
    root=Path(a.root); repo=getattr(a,'repo',None) or '.'; branch=getattr(a,'branch',None) or 'main'; remote=getattr(a,'remote',None) or 'origin'
    if not a.expected_base: raise RuntimeError('compose-intent requires --expected-base (captured remote head); plans are only valid against a pinned base')
    if action=='create-task':
        p=params
        plan=_plan_new_task(root,p['task_id'],p['context_id'],p['title'],p['goal'],p.get('worker') or 'codex',p.get('created_by') or 'chatgpt',p.get('source_repo'),p.get('source_issue'),p.get('channel_id'),p.get('lane_id'),p.get('worker_endpoint'),p.get('project_id'),p.get('created_at'),a.expected_base,repo,branch,remote)
        print(json.dumps({'action':action,'idempotency_key':key,'task_id':p['task_id'],'plan':plan},indent=2)); return
    p=params
    if action in ('incident-create','incident-update'):
        plan,iid,eid,ehash=_plan_incident(root,action,p,key)
        print(json.dumps({'action':action,'idempotency_key':key,'incident_id':iid,'event_id':eid,'event_hash':ehash,'plan':{k:(v if k not in ('immutable','mutable') else [[r,(t[:120]+'…') if len(t)>120 else t] for r,t in v]) for k,v in plan.items()}},indent=2)); return
    tid=p['task_id']
    td=root/'tasks'/tid
    if not (td/'task.json').exists(): raise RuntimeError(f'exact target {tid!r} is not in the relay; the bridge never scans for alternatives')
    if getattr(a,'binding_root',None):
        b=read_binding(a.binding_root)
        t0=readj(td/'task.json')
        err=route_compat_error(b,t0,str(root))
        if err: raise RuntimeError(f'compose-intent refused: {err}')
    tid,rid,plan=_compose_append_plan(root,repo,branch,remote,a.expected_base,action,p,a.actor_role,a.actor_id)
    print(json.dumps({'action':action,'idempotency_key':key,'task_id':tid,'run_id':rid,'plan':plan},indent=2))
BRIDGE_REQUEST_KEYS={'protocol','request_id','action','idempotency_key','expected_base','params'}
def read_bridge_request(root,rid):
    import re as _re3
    if not rid or not _re3.match(r'^[A-Za-z0-9][A-Za-z0-9_-]*$',rid): raise RuntimeError(f'invalid request id {rid!r}')
    p=Path(root)/'bridge'/'requests'/f'{rid}.json'
    if not p.exists(): raise RuntimeError(f'bridge request {rid!r} is not in the relay')
    try: o=readj(p)
    except Exception as e: raise RuntimeError(f'bridge request {rid!r} is malformed ({e}); refusing')
    if not isinstance(o,dict) or o.get('protocol')!=PROTOCOL: raise RuntimeError(f'bridge request {rid!r} has bad protocol envelope')
    unknown=set(o)-BRIDGE_REQUEST_KEYS
    if unknown: raise RuntimeError(f'bridge request {rid!r} carries forbidden top-level keys {sorted(unknown)}; canonical material (event ids, seq, hashes, links, fencing objects) can never be supplied, only composed')
    if o.get('request_id')!=rid: raise RuntimeError(f'bridge request filename {rid!r} does not match embedded request_id {o.get("request_id")!r}')
    _reject_public_mutation(o.get('action'),o.get('params'),f'bridge request {rid!r}')
    if o.get('action') not in INTENT_ACTIONS: raise RuntimeError(f'bridge request action must be one of {sorted(INTENT_ACTIONS)}')
    if not isinstance(o.get('idempotency_key'),str) or not o['idempotency_key']: raise RuntimeError('bridge request requires an opaque non-empty idempotency_key')
    if not isinstance(o.get('params'),dict): raise RuntimeError('bridge request params must be an object')
    if not o.get('expected_base'): raise RuntimeError('bridge request requires the captured remote head as expected_base')
    return o
def bridge_result_path(root,rid): return Path(root)/'bridge'/'requests'/f'{rid}.result.json'
def _materialize_plan_files(repo_root,plan):
    if 'task_json' in plan:
        items=[(plan['paths']['task_json'],json.dumps(plan['task_json'],ensure_ascii=False,indent=2)+'\n',False),(plan['paths']['event'],json.dumps(plan['event'],ensure_ascii=False,indent=2)+'\n',False),(plan['paths']['projection'],plan['taskmd_projection'],True)]
        check_hash=plan['event_hash']
        event_text=items[1][1]
    else:
        items=[(plan['api_plan']['event_path'],json.dumps(plan['event'],ensure_ascii=False,indent=2)+'\n',False),(plan['api_plan']['taskmd_path'],plan['taskmd_projection'],True)]
        check_hash=plan['event_hash']
        event_text=items[0][1]
    if eh(json.loads(event_text))!=check_hash: raise RuntimeError('composed event bytes do not match the composer hash; refusing to materialize')
    for rel,text,mutable in items:
        if not isinstance(rel,str) or rel.startswith('/') or '..' in Path(rel).parts or not rel.startswith('tasks/'): raise RuntimeError(f'plan path {rel!r} escapes tasks/; refusing')
        if not mutable and (Path(repo_root)/rel).exists(): raise RuntimeError(f'plan path {rel!r} already exists; create/append-only refuses overwrite')
    snaps={}
    for rel,text,mutable in items:
        fp=Path(repo_root)/rel
        if fp.exists(): snaps[rel]=fp.read_bytes()
    written=[]
    try:
        for rel,text,mutable in items:
            full=Path(repo_root)/rel
            full.parent.mkdir(parents=True,exist_ok=True)
            full.write_bytes(text.encode('utf-8') if isinstance(text,str) else text)
            written.append(rel)
    except BaseException:
        for rel in written:
            fp=Path(repo_root)/rel
            if rel in snaps:
                try: fp.write_bytes(snaps[rel])
                except OSError: pass
            else:
                try: fp.unlink()
                except OSError: pass
        raise
    return written
def _bridge_claim_owner(root,channel):
    auth=fencing_authority(root,channel)
    if auth['status']!='proven': raise RuntimeError(f"channel {channel!r} fencing authority is {auth['status']} ({auth['detail']}); bridge publication requires proven claim-history authority — run migrate-claim/repair-claim first, never publish fenced work on claim.json alone")
    return {'generation':auth['generation'],'owner':auth['owner']}
def _bridge_plan_once(root,repo,remote,branch,o):
    """Pure compose pass against current state: no writes, no commit.

    Returns (plan,task_id,event_id,event_hash). Raises RuntimeError on any
    semantic rejection, exactly as publication would. Shared by bridge-process
    and the read-only bridge-preflight gate.
    """
    action=o['action']; p=o['params']
    if action=='create-task':
        ch=p.get('channel_id')
        if not ch: raise RuntimeError('bridge create-task requires an exact channel_id')
        owner=_bridge_claim_owner(root,ch)['owner']
        plan=_plan_new_task(root,p['task_id'],p['context_id'],p['title'],p['goal'],p.get('worker') or 'codex',owner,p.get('source_repo'),p.get('source_issue'),p.get('channel_id'),p.get('lane_id'),p.get('worker_endpoint'),p.get('project_id'),p.get('created_at'),o['expected_base'],repo,branch,remote,True)
        return (plan,p['task_id'],plan['event_id'],plan['event_hash'])
    if action in ('incident-create','incident-update'):
        plan,iid,eid,ehash=_plan_incident(root,action,p,o['idempotency_key'])
        return (plan,iid,eid,ehash)
    tid=p['task_id']
    tdf=root/'tasks'/tid/'task.json'
    if not tdf.exists(): raise RuntimeError(f'exact target {tid!r} is not in the relay')
    t0=readj(tdf)
    ch=(t0.get('routing') or {}).get('channel_id')
    if not ch: raise RuntimeError(f'target task {tid!r} has no channel route')
    claim=_bridge_claim_owner(root,ch)
    full=dict(p); full['fencing_generation']=claim['generation']; full['idempotency_key']=o['idempotency_key']
    _,_,plan=_compose_append_plan(root,repo,branch,remote,o['expected_base'],action,full,'coordinator',claim['owner'],True)
    return (plan,tid,plan['event_id'],plan['event_hash'])
def _bridge_compose_once(root,repo,remote,branch,o):
    """One compose+materialize+validate pass against current post-pull state.

    Returns (plan,task_id,event_id,event_hash,written). Raises RuntimeError on
    any semantic rejection (stale target/claim/terminal/route/idempotency);
    the caller records that decision visibly without retry. Nothing is
    committed here, so a later transport race only discards uncommitted files.
    """
    plan,task_id,event_id,event_hash=_bridge_plan_once(root,repo,remote,branch,o)
    if plan.get('incident'):
        snaps={}
        for rel,_ in plan['mutable']:
            fp=Path(root)/rel
            snaps[rel]=fp.read_bytes() if fp.exists() else None
        written=[]
        try:
            written=_materialize_incident_files(root,plan)
            incident_validate(Path(root)/'incidents'/task_id)
        except BaseException:
            for rel in written:
                if rel in snaps and snaps[rel] is not None:
                    try: (Path(root)/rel).write_bytes(snaps[rel])
                    except OSError: pass
                else:
                    try: (Path(root)/rel).unlink()
                    except OSError: pass
            raise
        return (plan,task_id,event_id,event_hash,written)
    proj_rel=plan['paths']['projection'] if 'task_json' in plan else plan['api_plan']['taskmd_path']
    proj_fp=Path(root)/proj_rel
    proj_snap=proj_fp.read_bytes() if proj_fp.exists() else None
    written=[]
    try:
        written=_materialize_plan_files(root,plan)
        validate(root/'tasks'/task_id)
    except BaseException:
        for rel in written:
            fp=Path(root)/rel
            if rel==proj_rel and proj_snap is not None:
                try: fp.write_bytes(proj_snap)
                except OSError: pass
            else:
                try: fp.unlink()
                except OSError: pass
        raise
    return (plan,task_id,event_id,event_hash,written)
def _bridge_record_result(root,repo,remote,branch,rid,result,written):
    """Commit and push one result file plus already-materialized canonical files."""
    res_p=bridge_result_path(root,rid)
    res_p.parent.mkdir(parents=True,exist_ok=True)
    res_p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    git_out(repo,'add','--',f'bridge/requests/{res_p.name}',*written)
    git_out(repo,'commit','-m',f"awrp: bridge {rid} {result['status']}")
    return subprocess.run(['git','-C',str(repo),'push',remote,branch],capture_output=True,text=True)
def _bridge_retry_eligible(repo):
    """Whether a transport retry may rewind this checkout.

    Eligible when the worktree holds nothing but uncommitted bridge request
    inputs (`bridge/requests/*.json`, which `reset --hard` never touches and
    recomposition needs anyway). Any other dirt — modified tracked files,
    staged entries, foreign untracked files — disables retry: rewinding could
    destroy non-bridge work, so the run fails closed to single-attempt with a
    re-request reason instead.
    """
    out=git_out(repo,'status','--porcelain')
    for line in out.splitlines():
        if not line.strip(): continue
        st,path=line[:2],line[3:].strip().strip('"')
        if st=='??' and _is_transport_only_path(path): continue
        return False
    return True
def _bridge_rewind_to_remote(repo,remote,branch):
    """Discard this attempt's unpublished outputs and reset to remote head.

    Allowed only when the worktree holds nothing but uncommitted bridge
    request inputs (see _bridge_retry_eligible): any foreign dirt aborts the
    retry (fail closed, coordinator resubmits). Attempt outputs are committed
    at this point, so `reset --hard` drops exactly our unpublished commit.
    """
    git_out(repo,'fetch',remote,branch)
    rh=git_out(repo,'ls-remote',remote,branch).split()
    remote_head=rh[0] if rh else None
    if not remote_head: raise RuntimeError(f'cannot resolve remote {remote}/{branch}; retry refused, re-request with a fresh base')
    if not _bridge_retry_eligible(repo):
        out=git_out(repo,'status','--porcelain')
        foreign=[l.strip() for l in out.splitlines() if l.strip()][:3]
        raise RuntimeError(f'retry refused: worktree holds non-bridge changes ({", ".join(foreign)}); re-request with a fresh base, never reset foreign work')
    git_out(repo,'reset','--hard',remote_head)
    return remote_head
def _bridge_pending_requests(root,first=None):
    """Ordered request ids for one bounded bridge sweep: the triggering
    request first (when still pending), then every other pending request
    (request file present, no result file yet), deterministic sorted order.
    Already-resolved requests are NEVER reprocessed here — idempotent replay
    stays a per-request result-file check inside _bridge_process_one, so a
    resolved history of any size costs one directory listing, not one
    process (and one pull) per file. No pending request is lost merely
    because it was not the triggering file."""
    import re as _re6
    reqdir=Path(root)/'bridge'/'requests'
    pending=[]
    if reqdir.exists():
        for p in sorted(reqdir.glob('*.json')):
            if p.name.endswith('.result.json'): continue
            rid=p.name[:-len('.json')]
            if not rid or not _re6.match(r'^[A-Za-z0-9][A-Za-z0-9_-]*$',rid): continue
            if (reqdir/f'{rid}.result.json').exists(): continue
            pending.append(rid)
    ordered=[]
    if first and first in pending:
        ordered.append(first)
    ordered.extend(r for r in pending if r!=first)
    return ordered
def _bridge_process_one(root,repo,remote,branch,rid):
    """Process exactly one bridge request against current local state.

    The caller owns synchronization (single mode pulls before calling;
    batch mode pulls once for the whole sweep). Returns the result dict for
    skipped/rejected/published outcomes; raises RuntimeError only on
    transport defeat (another writer won with no safe retry), exactly as the
    single-request path always has. Idempotent replay, CAS, fencing,
    transport-gap retry, and post-push verification are unchanged.
    """
    res_p=bridge_result_path(root,rid)
    if res_p.exists():
        return {'request_id':rid,'status':'skipped','reason':'result already recorded; idempotent replay does not recompose','result':readj(res_p)}
    pristine=_bridge_retry_eligible(repo)
    key=None
    try:
        o=read_bridge_request(root,rid)
        key=o['idempotency_key']
        spec=INTENT_ACTIONS[o['action']]
        unknown=set(o['params'])-set(spec['required']+spec['optional'])
        if unknown: raise RuntimeError(f'request params contain forbidden keys {sorted(unknown)}')
        for k in spec['required']:
            if o['params'].get(k) is None: raise RuntimeError(f'request params missing required {k!r}')
    except RuntimeError as e:
        result={'protocol':PROTOCOL,'request_id':rid,'idempotency_key':key,'status':'rejected','reason':str(e)}
        cp=_bridge_record_result(root,repo,remote,branch,rid,result,[])
        if cp.returncode!=0: raise RuntimeError(f'bridge rejection record rejected (another writer won): {cp.stderr.strip()}; stop and inspect')
        return result
    last_race=None
    for attempt in range(1,BRIDGE_MAX_ATTEMPTS+1):
        try:
            plan,task_id,event_id,event_hash,written=_bridge_compose_once(root,repo,remote,branch,o)
        except RuntimeError as e:
            result={'protocol':PROTOCOL,'request_id':rid,'idempotency_key':key,'status':'rejected','reason':str(e)}
            cp=_bridge_record_result(root,repo,remote,branch,rid,result,[])
            if cp.returncode!=0: raise RuntimeError(f'bridge rejection record rejected (another writer won): {cp.stderr.strip()}; stop and inspect')
            return result
        if plan.get('incident'):
            result={'protocol':PROTOCOL,'request_id':rid,'idempotency_key':key,'status':'published','incident_id':task_id,'event_id':event_id,'event_hash':event_hash,'written':written,'attempts':attempt}
        else:
            result={'protocol':PROTOCOL,'request_id':rid,'idempotency_key':key,'status':'published','task_id':task_id,'event_id':event_id,'event_hash':event_hash,'written':written,'transport_gap':plan.get('transport_gap'),'gap_kind':plan.get('gap_kind'),'attempts':attempt}
        res_p.parent.mkdir(parents=True,exist_ok=True)
        res_p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        git_out(repo,'add','--',f'bridge/requests/{res_p.name}',*written)
        msg=f"awrp: bridge {rid} published"+(f" (attempt {attempt})" if attempt>1 else "")
        git_out(repo,'commit','-m',msg)
        cp=subprocess.run(['git','-C',str(repo),'push',remote,branch],capture_output=True,text=True)
        if cp.returncode==0:
            if plan.get('incident'):
                _tip=_incident_post_push_verify(repo,remote,branch,task_id,plan['immutable'][0][0],plan['event_hash'])
                result={**result,'published_head':_tip}
            else:
                _hh=validate(Path(root)/'tasks'/task_id)['head']
                _tip=post_push_verify(repo,remote,branch,Path(root)/'tasks'/task_id,_hh['event_id'],_hh['integrity']['event_hash'])
                result={**result,'published_head':_tip}
            return result
        last_race=cp.stderr.strip()
        if attempt<BRIDGE_MAX_ATTEMPTS and pristine:
            _bridge_rewind_to_remote(repo,remote,branch)
            continue
        if attempt>=BRIDGE_MAX_ATTEMPTS and pristine:
            try: _bridge_rewind_to_remote(repo,remote,branch)
            except RuntimeError: pass
            raise RuntimeError(f'bridge publication race exhausted after {BRIDGE_MAX_ATTEMPTS} attempts (last: {last_race}); re-request with a fresh base, never force-push')
        raise RuntimeError(f'bridge publication rejected (another writer won): {last_race}; local commit stays unpublished: re-request with a fresh base, never force-push')
    raise RuntimeError(f'bridge publication race exhausted after {BRIDGE_MAX_ATTEMPTS} attempts (last: {last_race}); re-request with a fresh base, never force-push')
def do_bridge_process(a):
    root=Path(a.root); repo=str(getattr(a,'repo',None) or a.root); branch=getattr(a,'branch',None) or 'main'; remote=getattr(a,'remote',None) or 'origin'
    if getattr(a,'all_pending',False):
        first=(getattr(a,'request',None) or '').strip() or None
        git_out(repo,'pull','--ff-only')
        ids=_bridge_pending_requests(root,first)
        results={}
        for rid in ids:
            results[rid]=_bridge_process_one(root,repo,remote,branch,rid)
        print(json.dumps({'mode':'all-pending','trigger':first,'processed':ids,'results':results},indent=2)); return
    rid=a.request or ''
    import re as _re4
    if not rid or not _re4.match(r'^[A-Za-z0-9][A-Za-z0-9_-]*$',rid): raise RuntimeError(f'invalid request id {rid!r}')
    git_out(repo,'pull','--ff-only')
    print(json.dumps(_bridge_process_one(root,repo,remote,branch,rid),indent=2))
def do_bridge_preflight(a):
    """Read-only pre-side-effect gate for one bridge request.

    Runs the exact composition the workflow would run (envelope, action and
    params schema incl. the public-mutation ineligibility denylist, target
    existence, claim ownership, idempotency, semantic-CAS base, append-path
    uniqueness) and prints the planned file writes — without writing,
    committing, pushing, or recording anything. A coordinator (or its
    connector wrapper) runs this BEFORE delegating any external mutation so
    a wrong action/route/target fails here, with zero side effects, instead
    of becoming a public object first. Any rejection raises before a byte
    is written.
    """
    root=Path(a.root); repo=str(getattr(a,'repo',None) or a.root); branch=getattr(a,'branch',None) or 'main'; remote=getattr(a,'remote',None) or 'origin'
    rid=a.request or ''
    import re as _re5
    if not rid or not _re5.match(r'^[A-Za-z0-9][A-Za-z0-9_-]*$',rid): raise RuntimeError(f'invalid request id {rid!r}')
    res_p=bridge_result_path(root,rid)
    if res_p.exists():
        print(json.dumps({'request_id':rid,'status':'already_recorded','result':readj(res_p)},indent=2)); return
    o=read_bridge_request(root,rid)
    key=o['idempotency_key']
    spec=INTENT_ACTIONS[o['action']]
    unknown=set(o['params'])-set(spec['required']+spec['optional'])
    if unknown: raise RuntimeError(f'request params contain forbidden keys {sorted(unknown)}')
    for k in spec['required']:
        if o['params'].get(k) is None: raise RuntimeError(f'request params missing required {k!r}')
    plan,task_id,event_id,event_hash=_bridge_plan_once(root,repo,remote,branch,o)
    if plan.get('incident'):
        writes=[r for r,_ in plan['immutable']]+[r for r,_ in plan['mutable']]
        print(json.dumps({'request_id':rid,'status':'plannable','action':o['action'],'idempotency_key':key,'incident_id':task_id,'event_id':event_id,'event_hash':event_hash,'planned_writes':writes,'expected_base':o['expected_base']},indent=2)); return
    if 'task_json' in plan:
        writes=[plan['paths']['task_json'],plan['paths']['event'],plan['paths']['projection']]
    else:
        writes=[plan['api_plan']['event_path'],plan['api_plan']['taskmd_path']]
    print(json.dumps({'request_id':rid,'status':'plannable','action':o['action'],'idempotency_key':key,'task_id':task_id,'event_id':event_id,'event_hash':event_hash,'planned_writes':writes,'gap_kind':plan.get('gap_kind'),'transport_gap':plan.get('transport_gap'),'expected_base':o['expected_base'],'remote_head':plan.get('remote_head')},indent=2))
def publish_atomic(a):
    if not a.expected_base: raise RuntimeError('publish-atomic requires --expected-base (captured remote head); without a CAS anchor there is no atomic publication')
    td=Path(a.task_dir); repo=a.repo or '.'; branch=a.branch; remote=a.remote or 'origin'
    require_guarded_dispatch_path(td,a)
    v,t,h,rid,e=_prepare_event(td,a)
    if not branch: branch=git_out(repo,'rev-parse','--abbrev-ref','HEAD')
    remote_head=remote_head_of(repo,remote,branch)
    if remote_head!=a.expected_base: raise RuntimeError(f'remote {remote}/{branch} moved since captured base (have {remote_head}, expected {a.expected_base}); stop, re-sync/replay, recompose; never force')
    e['integrity']['event_hash']=eh(e); _append_event_file(td,e)
    rel=os.path.relpath(td,repo) if Path(td).is_absolute() else str(td)
    msg=a.commit_message or f"awrp: {e['type']} {t['task_id']} {rid or ''}".strip()
    git_out(repo,'add',rel); git_out(repo,'commit','-m',msg)
    cp=subprocess.run(['git','-C',str(repo),'push',remote,branch],capture_output=True,text=True)
    if cp.returncode!=0: raise RuntimeError(f'plain push rejected (another writer won): {cp.stderr.strip()}; local commit stays unpublished: re-sync/replay, discard/recompose, never force-push')
    _hh=validate(td)['head']
    _tip=post_push_verify(repo,remote,branch,td,_hh['event_id'],_hh['integrity']['event_hash'])
    print(json.dumps({'event_id':e['event_id'],'seq':e['seq'],'run_id':rid,'event_hash':e['integrity']['event_hash'],'commit_message':msg,'remote_head':_tip},indent=2))
def _repo_rel_posix(repo,path):
    rp=Path(repo).resolve(); pp=Path(path).resolve()
    try: rel=pp.relative_to(rp)
    except ValueError: raise RuntimeError(f'task dir {path} is outside repo {repo}; connector publication refuses cross-repo trees')
    return rel.as_posix()
def _plan_append(td,t,h,e,repo,branch,remote,expected_base,remote_head):
    e['integrity']['event_hash']=eh(e)
    event_name=f"{e['seq']:06d}_{e['event_id']}.json"
    rel=_repo_rel_posix(repo,td)
    event_path=f'{rel}/events/{event_name}'
    taskmd_path=f'{rel}/TASK.md'
    if git_out(repo,'ls-tree',expected_base,'--',event_path): raise RuntimeError(f'event path {event_path} already exists at captured base {expected_base}; append-only path violated, recompose with a fresh event')
    if remote_head!=expected_base and git_out(repo,'ls-tree',remote_head,'--',event_path): raise RuntimeError(f'event path {event_path} already exists at transport head {remote_head}; append-only path violated, recompose with a fresh event')
    event_bytes=(json.dumps(e,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    taskmd_text=render_text(t,e)
    rt=json.loads(event_bytes.decode('utf-8'))
    if eh(rt)!=e['integrity']['event_hash'] or rt['seq']!=e['seq'] or rt['integrity']['prev_event_id']!=h['event_id']: raise RuntimeError('serialization round-trip changed the canonical event; refusing publication')
    eff_base=remote_head if remote_head!=expected_base else expected_base
    base_tree=git_out(repo,'rev-parse',f'{eff_base}^{{tree}}')
    api_plan={'steps':['create-blob(event JSON)','create-blob(TASK.md projection)','create-tree(base_tree=<captured head tree>, entries=[event_path, taskmd_path])','create-commit(message, tree, parents=[<captured remote head>])','update-ref(refs/heads/<branch>, sha=<new commit>, force=false)'],'parents':[eff_base],'base_tree':base_tree,'event_path':event_path,'taskmd_path':taskmd_path,'ref':f'refs/heads/{branch}','force':False}
    return (e,event_bytes,taskmd_text,api_plan)
def publish_connector(a):
    if not a.expected_base: raise RuntimeError('publish-connector requires --expected-base (captured remote head); without a CAS anchor there is no atomic publication')
    td=Path(a.task_dir); repo=a.repo or '.'; branch=a.branch; remote=a.remote or 'origin'
    require_guarded_dispatch_path(td,a)
    v,t,h,rid,e=_prepare_event(td,a)
    if not branch: branch=git_out(repo,'rev-parse','--abbrev-ref','HEAD')
    remote_head=remote_head_of(repo,remote,branch)
    if remote_head!=a.expected_base: raise RuntimeError(f'remote {remote}/{branch} moved since captured base (have {remote_head}, expected {a.expected_base}); stop, re-read canonical state, recompose; never force')
    e,event_bytes,taskmd_text,api_plan=_plan_append(td,t,h,e,repo,branch,remote,a.expected_base,remote_head)
    event_path=api_plan['event_path']; taskmd_path=api_plan['taskmd_path']; base_tree=api_plan['base_tree']
    if getattr(a,'print_plan',False):
        print(json.dumps({'event_id':e['event_id'],'seq':e['seq'],'run_id':rid,'event_hash':e['integrity']['event_hash'],'event':e,'taskmd_projection':taskmd_text,'api_plan':api_plan,'remote_head':remote_head},indent=2)); return
    import tempfile as _tf
    ef=_tf.NamedTemporaryFile(delete=False); mf=_tf.NamedTemporaryFile(delete=False,mode='w',encoding='utf-8')
    try:
        ef.write(event_bytes); ef.close(); mf.write(taskmd_text); mf.close()
        eblob=git_out(repo,'hash-object','-w',ef.name)
        mblob=git_out(repo,'hash-object','-w',mf.name)
        idx=_tf.mktemp(prefix='awrp-idx-')
        env=dict(os.environ); env['GIT_INDEX_FILE']=idx
        def gg(*args):
            cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True,env=env)
            if cp.returncode!=0: raise RuntimeError(f"git {' '.join(args)} failed: {cp.stderr.strip()}")
            return cp.stdout.strip()
        try:
            gg('read-tree',base_tree)
            gg('update-index','--add','--cacheinfo',f'100644,{eblob},{event_path}')
            gg('update-index','--add','--cacheinfo',f'100644,{mblob},{taskmd_path}')
            tree=gg('write-tree')
            msg=a.commit_message or f"awrp: {e['type']} {t['task_id']} {rid or ''}".strip()
            commit=gg('commit-tree',tree,'-p',a.expected_base,'-m',msg)
        finally:
            try: Path(idx).unlink()
            except OSError: pass
        cp=subprocess.run(['git','-C',str(repo),'push',remote,f'{commit}:refs/heads/{branch}'],capture_output=True,text=True)
        if cp.returncode!=0: raise RuntimeError(f'connector ref update rejected (another writer won): {cp.stderr.strip()}; re-read canonical state, recompose; never force')
        _tip=post_push_verify(repo,remote,branch,td,e['event_id'],e['integrity']['event_hash'],expect_tip=commit)
        print(json.dumps({'event_id':e['event_id'],'seq':e['seq'],'run_id':rid,'event_hash':e['integrity']['event_hash'],'commit':commit,'remote_head':_tip,'event_path':event_path},indent=2))
    finally:
        for p in (ef.name,mf.name):
            try: Path(p).unlink()
            except OSError: pass
def replay(a):
    v=validate(a.task_dir); h=v['head']; t=v['task']; p=h['task_projection']
    _di={'status':'no_active_run','reason':'no authoritative active run'}
    if v.get('active_run_id'):
        _de=next((x for x in v['events'] if x['type']=='DISPATCH' and x.get('run_id')==v.get('active_run_id')),None)
        if _de is not None: _di=dispatch_identity(t,_de)
    print(json.dumps({'task_id':t['task_id'],'context_id':t['context_id'],'title':t['title'],'state':p['state'],'phase':p['phase'],'waiting_on':p['waiting_on'],'head_event_id':h['event_id'],'head_seq':h['seq'],'head_created_at_beijing':beijing_time(h.get('created_at')),'latest_run_id':h.get('run_id'),'active_run_id':v.get('active_run_id'),'dispatch_identity':_di,'runs':v['runs'],'idempotency':v.get('idempotency') or {},'event_count':len(v['events'])},indent=2))
def do_validate(a):
    v=validate(a.task_dir); h=v['head']; print(json.dumps({'ok':True,'task_id':v['task']['task_id'],'events':len(v['events']),'head_event_id':h['event_id'],'head_hash':h['integrity']['event_hash']},indent=2))
def do_render(a): print(render(a.task_dir))
def task_routing(t):
    r=(t or {}).get('routing') or {}
    return (r.get('channel_id'),r.get('lane_id'),r.get('worker_endpoint'))
def dispatch_created_at(events,run_id):
    for e in events:
        if e['type']=='DISPATCH' and e.get('run_id')==run_id: return e.get('created_at')
    return None
def _read_manifest_route(td):
    """Cheap static route read: task.json only, never chain validation.

    Returns (True, {'task_id','channel_id','lane_id','worker_endpoint'}) on a
    readable manifest, else (False, error). Callers use this ONLY to skip
    histories that cannot route here; anything unreadable still fails closed
    through full validation, and project-ownership mismatch still surfaces
    as INVALID_CANONICAL (it needs validation, never the static filter).
    """
    try: t=readj(Path(td)/'task.json')
    except Exception as e: return (False,f'unreadable task manifest ({e})')
    if not isinstance(t,dict) or t.get('protocol')!=PROTOCOL or not t.get('task_id'):
        return (False,'unreadable task manifest (bad envelope)')
    r=t.get('routing') or {}
    return (True,{'task_id':t['task_id'],'channel_id':r.get('channel_id'),'lane_id':r.get('lane_id'),'worker_endpoint':r.get('worker_endpoint')})
def scan_inbox(root,channel=None,worker_endpoint=None,task_id=None,include_legacy=False,project=None):
    root=Path(root); actionable=[]; invalid=[]; snapshots={}
    tdir=root/'tasks'
    dirs=[tdir/task_id] if task_id else (sorted(tdir.iterdir()) if tdir.exists() else [])
    for td in dirs:
        tid=td.name
        if not task_id:
            # P1 resume fast-path: static channel/endpoint pre-filter on the
            # cheap manifest read. Histories that cannot route here are never
            # validated; unreadable manifests still go through validation so
            # corruption never hides behind the filter. The project filter
            # stays post-validation (ownership mismatch is INVALID_CANONICAL,
            # never a silent skip).
            mok,minfo=_read_manifest_route(td)
            if mok:
                mch=minfo['channel_id']; mep=minfo['worker_endpoint']
                if not mch:
                    if not include_legacy: continue
                elif include_legacy: continue
                elif channel is not None and mch!=channel: continue
                elif worker_endpoint and mep!=worker_endpoint: continue
        try: v=validate(td)
        except Exception as e:
            try: _fx=audit_chain(td)
            except Exception as fe: _fx={'task_id':tid,'ok':False,'error':f'forensics unavailable: {fe}','events':[]}
            invalid.append({'task_id':tid,'path':str(td),'error':str(e),'forensics':_fx}); continue
        snapshots[tid]=v
        t=v['task']; h=v['head']; p=h['task_projection']; active=v.get('active_run_id')
        ch,lane,ep=task_routing(t)
        _di={'status':'no_active_run','reason':'no authoritative active run'}
        if active:
            _de=next((x for x in v['events'] if x['type']=='DISPATCH' and x.get('run_id')==active),None)
            if _de is not None: _di=dispatch_identity(t,_de)
        rec={'task_id':t['task_id'],'title':t.get('title'),'state':p['state'],'phase':p['phase'],'waiting_on':p['waiting_on'],'run_id':h.get('run_id'),'active_run_id':active,'head_seq':h['seq'],'head_event_id':h['event_id'],'project_id':t.get('project_id'),'channel_id':ch,'lane_id':lane,'worker_endpoint':ep,'dispatch_created_at':dispatch_created_at(v['events'],active),'identity':_di}
        live=bool(active and p['state'] not in TERMINAL)
        if task_id:
            rec['actionable']=live; rec['legacy']=not ch; actionable.append(rec); continue
        if not ch:
            if include_legacy and live: rec['actionable']=True; rec['legacy']=True; actionable.append(rec)
            continue
        if include_legacy: continue
        if channel is not None and ch!=channel: continue
        if worker_endpoint and ep!=worker_endpoint: continue
        if not live: continue
        rec['actionable']=True; rec['legacy']=False; actionable.append(rec)
    if project is not None: actionable=[r for r in actionable if r.get('project_id')==project]
    actionable.sort(key=lambda r:((r.get('dispatch_created_at') or ''),r['task_id']))
    # snapshots carries the already-validated candidate chains so the
    # selector reuses them instead of validating the selected task again
    # (same invocation only — never a cross-command cache). do_inbox strips
    # it before printing; selection/transport paths must never serialize it.
    return {'actionable':actionable,'invalid':invalid,'snapshots':snapshots}
def resolve_inbox_root(root):
    """Authoritative Relay root for an inbox scan.

    A bound workspace root (``.awrp/binding.json`` present) holds no
    ``tasks/`` itself — canonical state lives under the binding's
    ``relay_dir``, which is exactly what resume/replay/validate observe.
    Scanning the workspace root instead yields a silent empty view that
    diverges from resume for the same live work, so the binding wins and
    the resolved root is reported. An unbound root scans as given (relay
    checkouts keep working unchanged). Missing/unreadable bindings or a
    relay dir that does not exist fail closed: guessing a root would risk
    reading the wrong Relay.
    Returns (relay_root, workspace_root_or_None).
    """
    r=Path(root)
    bp=r/'.awrp'/'binding.json'
    if not bp.exists():
        return (str(r),None)
    try:
        b=json.loads(bp.read_text(encoding='utf-8'))
    except Exception as e:
        raise RuntimeError(f'inbox refuses ambiguous root {str(r)!r}: binding at {bp} is unreadable ({e}); fix or remove the binding, never scan a guessed root')
    rd=b.get('relay_dir')
    if not rd:
        raise RuntimeError(f'inbox refuses ambiguous root {str(r)!r}: binding at {bp} names no relay_dir; re-bind before discovery')
    if not Path(rd).exists():
        raise RuntimeError(f'inbox refuses wrong root {str(r)!r}: bound relay_dir {rd!r} does not exist; re-bind before discovery')
    return (str(Path(rd)),str(r))
def do_inbox(a):
    if not a.task_id and not a.channel and not a.legacy and not getattr(a,'project',None): raise RuntimeError('inbox requires --channel, exact --task-id, --project, or explicit --legacy mode; global cross-channel discovery is not a worker trigger')
    relay_root,workspace_root=resolve_inbox_root(a.root)
    r=scan_inbox(relay_root,channel=a.channel,worker_endpoint=a.worker_endpoint,task_id=a.task_id,include_legacy=bool(a.legacy),project=getattr(a,'project',None))
    r.pop('snapshots',None)
    print(json.dumps({'channel':a.channel,'worker_endpoint':a.worker_endpoint,'legacy_mode':bool(a.legacy),'root':relay_root,'workspace_root':workspace_root,**r},indent=2))
def git_out(repo,*args):
    cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
    if cp.returncode!=0: raise RuntimeError(f"git {' '.join(args)} failed: {cp.stderr.strip()}")
    return cp.stdout.strip()
def remote_head_of(repo,remote,branch):
    """Resolve the remote branch head SHA (strict transport read).

    Shared choke point for every pre-publication base comparison: raises on
    transport failure, returns None only when the remote has no such head.
    Policy messages stay at the call sites, so behavior is unchanged.
    (Contrast relay_head_of, which swallows transport errors for
    best-effort planning display.)
    """
    rh=git_out(repo,'ls-remote',remote,branch)
    return rh.split()[0] if rh else None
def is_ancestor(repo,anc,desc):
    cp=subprocess.run(['git','-C',str(repo),'merge-base','--is-ancestor',anc,desc],capture_output=True,text=True)
    return cp.returncode==0
def do_preflight(a):
    v=validate(a.task_dir); h=v['head']
    if getattr(a,'expected_head',None) and h['event_id']!=a.expected_head: raise RuntimeError(f"stale task head: expected {a.expected_head}, have {h['event_id']}; re-sync/replay before publish")
    if getattr(a,'expected_hash',None) and h['integrity']['event_hash']!=a.expected_hash: raise RuntimeError('stale task head hash; re-sync/replay before publish')
    rid=getattr(a,'run_id',None)
    run_authority=None
    if rid:
        # Side-effect publication preflight: a stale worker whose run was
        # superseded or cancelled must fail here, before any push — even
        # when its captured head still matches. Same narrow rule as
        # transport: the active run, or the just-closed tip run (incl. its
        # NOTE-evidence chain). A coordinator takeover (CANCEL + new
        # DISPATCH) therefore atomically revokes the old run's publication
        # authority the moment the new run dispatches.
        _worker_semantic_check(a.task_dir,rid,h['event_id'],h['integrity']['event_hash'],snapshot=v)
        run_authority={'run_id':rid,'active_run_id':v.get('active_run_id')}
    branch=a.branch or git_out(a.repo,'rev-parse','--abbrev-ref','HEAD')
    base=git_out(a.repo,'rev-parse',branch)
    remote_head=remote_head_of(a.repo,a.remote,branch)
    sync=getattr(a,'expected_base',None)
    if sync:
        if remote_head and remote_head!=sync: raise RuntimeError(f'remote {a.remote}/{branch} advanced since captured base {sync}; re-sync/replay before publish')
        if not is_ancestor(a.repo,sync,base): raise RuntimeError(f'local {branch} is not built on captured base {sync}; re-sync/replay before publish')
    elif remote_head and not is_ancestor(a.repo,remote_head,base):
        raise RuntimeError(f'remote {a.remote}/{branch} advanced ({remote_head} is not an ancestor of local {base}); plain push would be non-fast-forward: stop, pull --ff-only, re-sync/replay, never force-push')
    print(json.dumps({'ok':True,'task_id':v['task']['task_id'],'head_event_id':h['event_id'],'branch':branch,'base':base,'remote_head':remote_head,'run_authority':run_authority},indent=2))
# ---- Worker transport retry on unrelated-main drift ----
# A worker that holds valid unpublished local Relay work (canonical event
# files and/or ordinary implementation commits) can lose a plain-push race
# when an unrelated Project/Task advances origin/main. The safe manual
# recovery is: inspect the remote delta, prove zero overlap, recompose the
# unpublished commit(s) onto the new head, rerun verification, plain-push.
# This helper automates ONLY that safe case, bounded and fail-closed.
# Repo-head drift is transport drift, not semantic staleness — but only while
# every semantic invariant still holds. Anything else stops with no
# force-push, no merge, and no canonical-byte change, leaving the unpublished
# work intact for inspection. It reuses the Bridge transport-CAS vocabulary
# (exact / transport-only / unrelated-canonical, bounded attempts) without
# sharing coordinator bridge authority: worker events carry no fencing and
# the target-verified exception does not exist here — any same-task advance
# is semantic staleness for a worker.
WORKER_MAX_ATTEMPTS=3
def _worker_push(repo,remote,branch):
    return subprocess.run(['git','-C',str(repo),'push',remote,branch],capture_output=True,text=True)
def _worker_push_is_drift(cp):
    err=((cp.stderr or '')+'\n'+(cp.stdout or '')).lower()
    return ('non-fast-forward' in err or 'fetch first' in err or ('failed to push some refs' in err and 'rejected' in err))
def _worker_name_only(repo,frm,to):
    out=git_out(repo,'diff','--name-only',frm,to,'--')
    return [l.strip() for l in out.splitlines() if l.strip()]
def _worker_name_status(repo,frm,to):
    out=git_out(repo,'diff','--name-status',frm,to,'--')
    rows=[]
    for line in out.splitlines():
        if not line.strip(): continue
        parts=line.split('\t')
        rows.append((parts[0],parts[-1]))
    return rows
def _worker_note_lineage(v,run_id):
    """Prove a NOTE tip descends from the requested run's legitimate close.

    Walks back from the validated tip through consecutive same-run worker
    NOTEs to the run's closing HANDOFF. Every step must be worker-authored
    by the run's seated executor, the anchor must be that run's closed-state
    HANDOFF, and the stored run state must be closed. Anything else — a
    coordinator governance event, another run's event, a non-HANDOFF anchor,
    an open stored state, a missing executor, or a foreign author anywhere
    in the chain — fails closed. This re-proves provenance at transport time
    so even pre-enforcement history cannot ride the helper.
    """
    evs=v['events']; h=v['head']
    if h['type']!='NOTE' or h.get('run_id')!=run_id:
        raise RuntimeError(f"run {run_id!r} has no transport authority: current tip {h['event_id']} is not its NOTE chain (older/superseded runs never transport) — re-sync/replay, never publish stale")
    ex=(v.get('runs') or {}).get(run_id,{}).get('executor')
    if ex is None:
        raise RuntimeError(f"run {run_id!r} has no transport authority: no seated executor to attribute the NOTE chain to — re-sync/replay, never publish stale")
    if (v.get('runs') or {}).get(run_id,{}).get('state') not in CLOSED_RUN_STATES:
        raise RuntimeError(f"run {run_id!r} has no transport authority: stored run state is not closed — re-sync/replay, never publish stale")
    i=len(evs)-1
    while i>=0 and evs[i]['type']=='NOTE' and evs[i].get('run_id')==run_id:
        if (evs[i].get('actor') or {}).get('role')!='worker' or (evs[i].get('actor') or {}).get('id')!=ex:
            raise RuntimeError(f"run {run_id!r} has no transport authority: chain NOTE {evs[i]['event_id']} is not authored by the executor ({ex!r}) — re-sync/replay, never publish stale")
        i-=1
    anchor=evs[i] if i>=0 else None
    if anchor is None or anchor['type']!='HANDOFF' or anchor.get('run_id')!=run_id:
        raise RuntimeError(f"run {run_id!r} has no transport authority: NOTE chain does not descend directly from its closing HANDOFF (a governance event, another run, or a semantic change intervened) — re-sync/replay, never publish stale")
    if (anchor.get('actor') or {}).get('role')!='worker' or (anchor.get('actor') or {}).get('id')!=ex:
        raise RuntimeError(f"run {run_id!r} has no transport authority: closing HANDOFF is not the executor's ({ex!r}) — re-sync/replay, never publish stale")
    if (anchor.get('run') or {}).get('state') not in CLOSED_RUN_STATES:
        raise RuntimeError(f"run {run_id!r} has no transport authority: closing HANDOFF is not a closed run state — re-sync/replay, never publish stale")
    return True
def _worker_semantic_check(task_dir,run_id,exp_head,exp_hash,snapshot=None):
    """Re-verify worker execution authority against current local state.

    snapshot optionally carries the already-validated chain for the same
    task_dir from the same invocation (do_preflight validates, then checks
    run authority against unchanged state — sharing it removes a duplicate
    full validation with identical semantics). Retry loops must NOT pass
    one: every attempt re-observes state after rewind/recompose, and final
    post-push verification always re-reads authoritative remote state.

    Returns (task, head, recipient, route). Raises RuntimeError on any drift:
    moved head/hash, terminal state, a missing/non-worker DISPATCH for the
    run, or a run with no transport authority. Callers compare
    recipient/route against the baseline captured before the first push
    attempt. Transport authority is narrow: the authoritative active run;
    the just-closed tip run (tip is its closing worker HANDOFF); or a
    NOTE-tipped chain proven by _worker_note_lineage to descend directly
    from that run's legitimate executor close with no intervening
    governance. That covers delivery of already-composed closes and their
    post-run evidence, and nothing else: liveness was enforced at append
    time by emit, and an unchanged tip proves no same-task advance since.
    There is no separate worker failure-closing event in protocol semantics
    (derive_active_run clears the active run only on HANDOFF with a closed
    run state; ERROR never closes), so failed closes travel as
    HANDOFF/failed under the same rules. Older, superseded, or otherwise
    non-tip runs never transport.
    """
    v=snapshot if snapshot is not None else validate(task_dir); t=v['task']; h=v['head']
    if h['event_id']!=exp_head or h['integrity']['event_hash']!=exp_hash:
        raise RuntimeError(f"worker semantic staleness: task head moved (have {h['event_id']}, expected {exp_head}); re-sync/replay and recompose explicitly, never publish stale")
    active=v.get('active_run_id')
    if active==run_id:
        pass
    elif active is not None:
        raise RuntimeError(f"run {run_id!r} is not transportable: authoritative active run is {active!r}; only the active run or the just-closed tip run may be transported — re-sync/replay, never publish stale")
    elif run_id not in (v.get('runs') or {}):
        raise RuntimeError(f"worker semantic staleness: run {run_id!r} is unknown locally; stop, re-sync/replay, never publish stale")
    else:
        tip_state=(h.get('run') or {}).get('state')
        if h['type']=='HANDOFF' and h.get('run_id')==run_id and (h.get('actor') or {}).get('role')=='worker' and tip_state in CLOSED_RUN_STATES:
            pass
        else:
            _worker_note_lineage(v,run_id)
    if h['task_projection']['state'] in TERMINAL:
        raise RuntimeError('worker semantic staleness: task is terminal; only coordinator RECONCILE may continue')
    rec=None
    for e in v['events']:
        if e['type']=='DISPATCH' and e.get('run_id')==run_id:
            rec=e.get('recipient') or {}
            break
    if not rec or rec.get('role')!='worker':
        raise RuntimeError(f'worker semantic staleness: no worker DISPATCH for run {run_id!r}; fail closed')
    ch,lane,ep=task_routing(t)
    return (t,h,rec,{'project_id':t.get('project_id'),'channel_id':ch,'lane_id':lane,'worker_endpoint':ep})
def do_worker_retry_push(a):
    import shlex as _shlex
    repo=str(getattr(a,'repo',None) or '.')
    remote=getattr(a,'remote',None) or 'origin'
    branch=getattr(a,'branch',None) or 'main'
    td=Path(a.task_dir)
    max_attempts=int(getattr(a,'max_attempts',None) or WORKER_MAX_ATTEMPTS)
    if max_attempts<1 or max_attempts>5:
        raise RuntimeError('worker-retry-push --max-attempts must be within 1..5 (bounded by design; default 3)')
    verifies=list(getattr(a,'verify_cmd',None) or [])
    base=getattr(a,'expected_base',None)
    if not base:
        raise RuntimeError('worker-retry-push requires --expected-base (the captured remote head this work is built on); without a CAS anchor there is no safe recompose')
    v0=validate(td); task_id=v0['task']['task_id']
    t0,h0,rec0,route0=_worker_semantic_check(td,a.run_id,a.expected_head,a.expected_hash)
    ch0=route0['channel_id']
    dirt=git_out(repo,'status','--porcelain')
    if dirt.strip():
        first=[l.strip() for l in dirt.splitlines() if l.strip()][:3]
        raise RuntimeError(f"worker worktree is not clean ({'; '.join(first)}); commit local work first — the helper transports commits, never stray files")
    if not is_ancestor(repo,base,git_out(repo,'rev-parse','HEAD')):
        raise RuntimeError(f'local HEAD is not built on captured base {base}; re-sync/replay before publication, never recompose across rewritten history')
    if int(git_out(repo,'rev-list','--count',f'{base}..HEAD'))<1:
        raise RuntimeError(f'no unpublished commits above captured base {base}; nothing to transport')
    for st,path in _worker_name_status(repo,base,'HEAD'):
        if st.startswith('A'): continue
        if path.startswith('tasks/') and (path.endswith('/task.json') or '/events/' in path):
            raise RuntimeError(f'unpublished work rewrites canonical path {path} ({st}); manifests/events are append-only — recompose refused, never rewrite history')
    local_files=set(_worker_name_only(repo,base,'HEAD'))
    canon_before={}
    for p in sorted(local_files):
        if p.startswith(f'tasks/{task_id}/events/') and p.endswith('.json'):
            fp=Path(repo)/p
            canon_before[p]=fp.read_bytes() if fp.exists() else None
    gap_kind='exact'; last_race=None
    for attempt in range(1,max_attempts+1):
        cp=_worker_push(repo,remote,branch)
        if cp.returncode==0:
            _hh=validate(td)['head']
            _tip=post_push_verify(repo,remote,branch,td,_hh['event_id'],_hh['integrity']['event_hash'])
            print(json.dumps({'status':'published','task_id':task_id,'run_id':a.run_id,'attempts':attempt,'gap_kind':gap_kind,'published_head':_tip},indent=2)); return
        last_race=((cp.stderr or '')+' '+(cp.stdout or '')).strip()
        if not _worker_push_is_drift(cp):
            raise RuntimeError(f'worker push failed without a drift signature ({last_race}); fix the transport cause and retry explicitly — never force-push')
        git_out(repo,'fetch',remote,branch)
        remote_head=remote_head_of(repo,remote,branch)
        if not remote_head:
            raise RuntimeError(f'cannot resolve remote {remote}/{branch} after fetch; drift is unclassifiable, retry refused')
        if not is_ancestor(repo,base,remote_head):
            raise RuntimeError(f'remote {remote}/{branch} diverged from captured base {base} (history rewritten or foreign lineage); recompose refused, never rebase across rewritten history')
        gap=_worker_name_only(repo,base,remote_head)
        if gap:
            other=[f for f in gap if not _is_transport_only_path(f)]
            if not other:
                gap_kind='transport-only'
            else:
                hit=[f for f in other if f.startswith(f'tasks/{task_id}/')]
                if hit:
                    extra='...' if len(hit)>5 else ''
                    raise RuntimeError(f"remote {remote}/{branch} advanced the target task since captured base (target files: {', '.join(hit[:5])}{extra}); semantic staleness — re-sync/replay and recompose explicitly, never auto-retry")
                if ch0:
                    hit=[f for f in other if f.startswith(f'channels/{ch0}/')]
                    if hit:
                        raise RuntimeError(f"remote {remote}/{branch} moved channel {ch0!r} claim state since captured base; fencing authority moved — re-sync, never auto-retry")
                over=[f for f in other if f in local_files]
                if over:
                    extra='...' if len(over)>5 else ''
                    raise RuntimeError(f"remote {remote}/{branch} overlaps unpublished worker files ({', '.join(over[:5])}{extra}); real contention — inspect, never force-push or silently merge")
                gap_kind='unrelated-canonical'
        t1,h1,rec1,route1=_worker_semantic_check(td,a.run_id,a.expected_head,a.expected_hash)
        if rec1!=rec0 or route1!=route0:
            raise RuntimeError(f'worker recipient/route moved during drift (was {rec0}/{route0}, now {rec1}/{route1}); re-sync, never auto-retry')
        # Recompose: replay our commits onto the latest transport head. Zero
        # file overlap was proven above, so this rebase is content-identical
        # by construction; any conflict aborts with zero trace and fails
        # closed. Commit objects gain a new parent, but canonical file bytes
        # must not change — verified below file by file.
        rb=subprocess.run(['git','-C',str(repo),'rebase',remote_head],capture_output=True,text=True)
        if rb.returncode!=0:
            subprocess.run(['git','-C',str(repo),'rebase','--abort'],capture_output=True,text=True)
            raise RuntimeError(f"unrelated-drift rebase conflicted ({(rb.stderr or '').strip()}); overlap slipped the file check (rename/deletion?) — aborted cleanly, inspect manually, never force")
        for p,blob in canon_before.items():
            fp=Path(repo)/p
            now=fp.read_bytes() if fp.exists() else None
            # LF-canonical comparison (same doctrine as artifact-hash):
            # content changes refuse publication, but bare line-ending
            # renormalization across a rebase checkout (CRLF worktree left
            # by text-mode writes vs eol=lf blobs) must not false-positive.
            if now is None or blob is None or canonical_artifact_bytes(now)!=canonical_artifact_bytes(blob):
                raise RuntimeError(f'canonical event bytes changed across recompose ({p}); refusing publication — inspect, never publish rewritten events')
        _worker_semantic_check(td,a.run_id,a.expected_head,a.expected_hash)
        validate(td)
        for cmd in verifies:
            vc=subprocess.run(_shlex.split(cmd),capture_output=True,text=True,cwd=str(repo))
            if vc.returncode!=0:
                raise RuntimeError(f'verification failed after recompose ({cmd}: {((vc.stderr or vc.stdout) or "").strip()[:300]}); publication blocked with work preserved — fix and re-run explicitly')
    raise RuntimeError(f'worker publication race exhausted after {max_attempts} attempts (last: {last_race}); unpublished work preserved locally — re-sync/replay and re-run explicitly, never force-push')
# ---- Ephemeral canonical publication transport ----
# A long-lived execution workspace accumulates unrelated local commits,
# untracked files, and dirty state; when origin/main also advances, plain
# push and even bounded recompose can stall behind work that has nothing to
# do with the canonical events awaiting delivery (the verified #5595 shape:
# local-only unrelated commits plus remote-only unrelated commits, with a
# completed HANDOFF unpublished). This command decouples the two concerns:
# execution stays stateful wherever it is, while each canonical publication
# starts from the current remote canonical head in an isolated disposable
# clone, revalidates Task/Run/channel authority there, imports ONLY the
# explicitly listed event/artifact bytes, and publishes with non-force CAS
# and bounded retries. The execution workspace is only ever READ (file
# bytes); it is never pulled, rebased, merged, cleaned, or repaired as a
# publication prerequisite. Unrelated local commits can never hitchhike:
# the scratch commit contains exactly the listed paths plus the rendered
# TASK.md projection, asserted before commit.
EPHEMERAL_MAX_ATTEMPTS=3
def _ephemeral_read_inputs(td,repo,event_files,artifacts):
    td=Path(td); rpo=Path(repo).resolve(); evdir=(Path(td)/'events').resolve()
    items=[]
    for f in event_files or []:
        fp=Path(f)
        fp=(rpo/fp if not fp.is_absolute() else fp).resolve()
        try:
            evrel=fp.relative_to(evdir)
            rel=fp.relative_to(rpo)
        except ValueError:
            raise RuntimeError(f'event file {f!r} is outside the task events dir of this repo; only explicitly listed task events transport')
        if fp.suffix!='.json' or '/' in evrel.as_posix() or '..' in evrel.parts:
            raise RuntimeError(f'event file {f!r} is not a direct events/*.json member; refusing')
        try:
            blob=fp.read_bytes(); o=json.loads(blob.decode('utf-8'))
        except Exception as e:
            raise RuntimeError(f'event file {f!r} is unreadable ({e}); refusing')
        items.append((rel.as_posix(),blob,o))
    arts=[]
    for a in artifacts or []:
        fp=(Path(td)/a).resolve() if not Path(a).is_absolute() else Path(a).resolve()
        try:
            fp.relative_to(Path(td).resolve())
            rel=fp.relative_to(rpo)
        except ValueError:
            raise RuntimeError(f'artifact {a!r} escapes the task dir of this repo; only explicitly listed task artifacts transport')
        try:
            blob=fp.read_bytes()
        except Exception as e:
            raise RuntimeError(f'artifact {a!r} is unreadable ({e}); refusing')
        arts.append((rel.as_posix(),blob))
    if not items:
        raise RuntimeError('publish-ephemeral requires at least one --event-file')
    items.sort(key=lambda t:(t[2].get('seq') if isinstance(t[2].get('seq'),int) else -1,t[0]))
    tids={o.get('task_id') for _,_,o in items}
    core=[o for _,_,o in items if not (o.get('type')=='TASK_CREATED' and o.get('run_id') is None)]
    rids={o.get('run_id') for o in core}
    if len(tids)!=1 or len(rids)!=1 or None in rids:
        raise RuntimeError('publish-ephemeral transports one run of one task per invocation (a leading TASK_CREATED may ride along and is skipped when already published); split wider sets explicitly')
    for (r1,b1,o1),(r2,b2,o2) in zip(items,items[1:]):
        if not isinstance(o1.get('seq'),int) or o2.get('seq')!=o1.get('seq')+1:
            raise RuntimeError(f'event files are not consecutive ({r1} seq={o1.get("seq")}, {r2} seq={o2.get("seq")}); refusing')
        if o2.get('integrity',{}).get('prev_event_id')!=o1.get('event_id') or o2.get('integrity',{}).get('prev_event_hash')!=(o1.get('integrity') or {}).get('event_hash'):
            raise RuntimeError(f'event files are not hash-linked ({r1} -> {r2}); refusing')
    return items,arts,next(iter(rids))
def _remote_blob(work,rev,rel):
    """Blob bytes at rev:path, or None when absent. Raw bytes, no decoding."""
    cp=subprocess.run(['git','-C',str(work),'show',f'{rev}:{rel}'],capture_output=True)
    if cp.returncode!=0: return None
    return cp.stdout
def do_publish_ephemeral(a):
    import shutil as _shutil
    import tempfile as _tf
    td=Path(a.task_dir); repo=str(getattr(a,'repo',None) or '.')
    remote=getattr(a,'remote',None) or 'origin'; branch=getattr(a,'branch',None) or 'main'
    max_attempts=int(getattr(a,'max_attempts',None) or EPHEMERAL_MAX_ATTEMPTS)
    if max_attempts<1 or max_attempts>5:
        raise RuntimeError('publish-ephemeral --max-attempts must be within 1..5 (bounded by design; default 3)')
    try:
        url=git_out(repo,'config','--get',f'remote.{remote}.url')
    except RuntimeError:
        raise RuntimeError(f'execution repo has no {remote} remote to publish through; configure it explicitly, never guess a URL')
    if not url:
        raise RuntimeError(f'execution repo has no {remote} remote URL; configure it explicitly, never guess a URL')
    tdf=Path(td)/'task.json'
    if not tdf.exists():
        raise RuntimeError(f'task manifest not found at {tdf}; refusing')
    tid=json.loads(tdf.read_text(encoding='utf-8')).get('task_id')
    items,arts,run_id=_ephemeral_read_inputs(td,repo,getattr(a,'event_file',None),getattr(a,'artifact',None) or [])
    if a.run_id!=run_id:
        raise RuntimeError(f'publish-ephemeral run mismatch: asked for {a.run_id!r}, listed events belong to {run_id!r}; transport one run per invocation')
    last_race=None; first_base=None; gap_kind='exact'
    for attempt in range(1,max_attempts+1):
        work=_tf.mkdtemp(prefix='awrp-epub-')
        try:
            cp=subprocess.run(['git','clone','--branch',branch,url,work],capture_output=True,text=True)
            if cp.returncode!=0:
                raise RuntimeError(f"ephemeral clone failed ({(cp.stderr or '').strip()[:200]}); retry explicitly, never publish from a stale view")
            remote_head=git_out(work,'rev-parse','HEAD')
            if first_base is None: first_base=remote_head
            std=Path(work)/'tasks'/tid
            if not (std/'task.json').exists():
                raise RuntimeError(f'task {tid!r} is absent at fresh remote head {remote_head}; task creation stays on the bridge path, never here')
            rv=validate(std); hh=rv['head']
            # Idempotent prefix skip: events/artifacts already present
            # remotely with identical LF-canonical bytes need no transport
            # (bridge 'skipped' philosophy). Different bytes at an existing
            # path is a collision and refuses; a first-fresh event whose
            # prev link misses the fresh head is same-task staleness.
            fresh=[]; fresh_arts=[]
            for rel,blob,o in items:
                rb=_remote_blob(work,remote_head,rel)
                if rb is None:
                    fresh.append((rel,blob,o))
                elif canonical_artifact_bytes(rb)!=canonical_artifact_bytes(blob):
                    raise RuntimeError(f'path {rel} exists at fresh remote head with different bytes; refusing — inspect, never overwrite')
            for rel,blob in arts:
                rb=_remote_blob(work,remote_head,rel)
                if rb is None:
                    fresh_arts.append((rel,blob))
                elif canonical_artifact_bytes(rb)!=canonical_artifact_bytes(blob):
                    raise RuntimeError(f'artifact path {rel} exists at fresh remote head with different bytes; refusing — inspect, never overwrite')
            if not fresh and not fresh_arts:
                print(json.dumps({'status':'already_published','task_id':tid,'run_id':run_id,'events':[o.get('event_id') for _,_,o in items],'attempts':attempt},indent=2)); return
            if fresh:
                first=fresh[0][2]
                if first.get('integrity',{}).get('prev_event_id')!=hh['event_id'] or first.get('integrity',{}).get('prev_event_hash')!=hh['integrity']['event_hash']:
                    raise RuntimeError(f"same-task semantic staleness: first fresh event links to {first.get('integrity',{}).get('prev_event_id')}, but fresh remote head is {hh['event_id']}; re-sync/recompose explicitly, never auto-retry")
                last_id=fresh[-1][2].get('event_id'); last_hash=(fresh[-1][2].get('integrity') or {}).get('event_hash')
            else:
                last_id=hh['event_id']; last_hash=hh['integrity']['event_hash']
            for rel,blob,_ in fresh:
                fp=Path(work)/rel; fp.parent.mkdir(parents=True,exist_ok=True); fp.write_bytes(blob)
            for rel,blob in fresh_arts:
                fp=Path(work)/rel; fp.parent.mkdir(parents=True,exist_ok=True); fp.write_bytes(blob)
            validate(std)
            v2=validate(std); h2=v2['head']
            if h2['event_id']!=last_id or h2['integrity']['event_hash']!=last_hash:
                raise RuntimeError('materialized head does not match the authorized events; refusing — inspect, never publish recomposed bytes')
            for rel,blob,_ in fresh:
                if (Path(work)/rel).read_bytes()!=blob:
                    raise RuntimeError(f'imported bytes changed in flight ({rel}); refusing — inspect, never publish rewritten events')
            _worker_semantic_check(std,run_id,last_id,last_hash)
            render(std)
            taskmd_rel=f'tasks/{tid}/TASK.md'
            commit_paths=[rel for rel,_,_ in fresh]+[rel for rel,_ in fresh_arts]+[taskmd_rel]
            git_out(work,'add','--',*commit_paths)
            staged=git_out(work,'diff','--cached','--name-only').splitlines()
            if sorted(s.strip() for s in staged if s.strip())!=sorted(commit_paths):
                raise RuntimeError(f'scratch commit would carry unexpected paths ({staged}); refusing — only listed events/artifacts plus TASK.md may transport')
            msg=getattr(a,'commit_message',None) or f"awrp: publish {tid} {run_id} ({len(fresh)} events, {len(fresh_arts)} artifacts)"
            try:
                git_out(work,'config','--get','user.email')
            except RuntimeError:
                git_out(work,'config','user.email','awrp-ephemeral@users.noreply.github.com')
                git_out(work,'config','user.name','awrp-ephemeral')
            git_out(work,'commit','-m',msg)
            cp=subprocess.run(['git','-C',str(work),'push',remote,branch],capture_output=True,text=True)
            if cp.returncode==0:
                _hh=validate(std)['head']
                _tip=post_push_verify(work,remote,branch,std,_hh['event_id'],_hh['integrity']['event_hash'])
                if attempt>1:
                    others=[g.strip() for g in git_out(work,'diff','--name-only',first_base,_tip+'^','--').splitlines() if g.strip()]
                    others=[f for f in others if not _is_transport_only_path(f)]
                    gap_kind='transport-only' if not others else 'unrelated-canonical'
                print(json.dumps({'status':'published','task_id':tid,'run_id':run_id,'events':[o.get('event_id') for _,_,o in fresh],'artifacts':[rel for rel,_ in fresh_arts],'attempts':attempt,'gap_kind':gap_kind,'published_head':_tip},indent=2)); return
            last_race=((cp.stderr or '')+' '+(cp.stdout or '')).strip()
            if not _worker_push_is_drift(cp):
                raise RuntimeError(f'ephemeral push failed without a drift signature ({last_race}); fix the transport cause and retry explicitly — never force-push')
        finally:
            _shutil.rmtree(work,ignore_errors=True)
    raise RuntimeError(f'ephemeral publication race exhausted after {max_attempts} attempts (last: {last_race}); execution workspace untouched — re-sync/recompose explicitly, never force-push')
def post_push_verify(repo,remote,branch,task_dir,event_id,event_hash,expect_tip=None):
    """Remote post-push read-back / recompute / validate (strict transport read).

    After a push reports success: fetch, prove the remote tip is exactly the
    published commit (explicit expect_tip, else the local branch tip), read
    the published event bytes back from the remote, recompute the hash
    against the recorded value, and validate the chain. Any mismatch raises
    BEFORE success is reported, so no caller can claim delivery on a
    diverged or miswritten remote. Returns the verified tip SHA.
    """
    git_out(repo,'fetch',remote,branch)
    rh=remote_head_of(repo,remote,branch)
    want=expect_tip or git_out(repo,'rev-parse',branch)
    if not rh or rh!=want:
        raise RuntimeError(f'post-push verification failed: remote head {rh} != published {want}; do not report success')
    td=Path(task_dir)
    cands=sorted(td.glob(f'events/*_{event_id}.json'))
    if len(cands)==1:
        try:
            rel=cands[0].resolve().relative_to(Path(repo).resolve()).as_posix()
        except ValueError:
            raise RuntimeError(f'post-push verification failed: event file is outside repo {repo}; do not report success')
        local_bytes=cands[0].read_bytes()
    else:
        tid=Path(task_dir).name
        tree=git_out(repo,'ls-tree','-r','--name-only',rh,'--',f'tasks/{tid}/events/')
        hits=[l.strip() for l in tree.splitlines() if l.strip().endswith(f'_{event_id}.json')]
        if len(hits)!=1:
            raise RuntimeError(f'post-push verification failed: event {event_id} resolves to {len(hits)} remote paths; do not report success')
        rel=hits[0]; local_bytes=None
    cp=subprocess.run(['git','-C',str(repo),'show',f'{rh}:{rel}'],capture_output=True)
    if cp.returncode!=0:
        raise RuntimeError(f'post-push verification failed: published path {rel} unreadable at remote head {rh}; do not report success')
    try:
        back=json.loads(cp.stdout.decode('utf-8'))
    except Exception as ex:
        raise RuntimeError(f'post-push verification failed: remote bytes do not parse ({ex}); do not report success')
    if eh(back)!=event_hash:
        raise RuntimeError(f'post-push verification failed: recomputed {eh(back)} != recorded {event_hash}; do not report success')
    if local_bytes is not None:
        if canonical_artifact_bytes(local_bytes)!=canonical_artifact_bytes(cp.stdout):
            raise RuntimeError(f'post-push verification failed: remote bytes differ from local file {rel}; do not report success')
        validate(td)
    return rh
def do_doctor(a):
    """Read-only aggregated dispatch/publication preflight (P1).

    Runs the same underlying invariant functions the mutation paths use —
    validate, task_readiness, audit_chain, dispatch_identity, claim read,
    remote freshness — and reports each verdict as data. Writes nothing,
    mutates nothing, never raises on content (per-check errors are
    reported, not thrown). A failing check here predicts a refusal on the
    corresponding mutation path; fix the cause, never bypass the gate.
    """
    td=Path(a.task_dir); repo=str(getattr(a,'repo',None) or '.')
    remote=getattr(a,'remote',None) or 'origin'; branch=getattr(a,'branch',None)
    checks={}
    try:
        v=validate(td); h=v['head']; t=v['task']
        checks['chain']={'ok':True,'events':len(v['events']),'head_event_id':h['event_id'],'active_run_id':v.get('active_run_id')}
    except Exception as e:
        v=None; h=None; t=None
        checks['chain']={'ok':False,'error':str(e)}
    try:
        _root=td.parent.parent if td.parent.name=='tasks' else Path(repo)
        _t=t or readj(td/'task.json')
        checks['readiness']=task_readiness(_t,str(_root))
    except Exception as e:
        checks['readiness']={'ok':False,'error':str(e)}
    try:
        _ac=audit_chain(td)
        checks['integrity']={'ok':_ac.get('ok'),'last_valid':_ac.get('last_valid')}
    except Exception as e:
        checks['integrity']={'ok':False,'error':str(e)}
    try:
        if v is None or not v.get('active_run_id'):
            checks['identity']={'status':'no_active_run','reason':'no authoritative active run'}
        else:
            _de=next((x for x in v['events'] if x['type']=='DISPATCH' and x.get('run_id')==v.get('active_run_id')),None)
            checks['identity']=dispatch_identity(t,_de) if _de is not None else {'status':'mismatch','reason':'active run has no DISPATCH'}
    except Exception as e:
        checks['identity']={'status':'error','reason':str(e)}
    try:
        _ch=((t or {}).get('routing') or {}).get('channel_id')
        _root=td.parent.parent if td.parent.name=='tasks' else Path(repo)
        _auth=fencing_authority(_root,_ch) if _ch else None
        if _auth is None:
            checks['claim']={'claimed':False,'authority':'unclaimed','detail':'task has no channel route; nothing to fence'}
        else:
            checks['claim']={'claimed':_auth['status']=='proven','authority':_auth['status'],'generation':_auth.get('generation'),'owner':_auth.get('owner'),'strict':_auth.get('strict'),'detail':_auth.get('detail')}
            if _auth['status'] in ('inconsistent','legacy-claim'):
                checks['claim']['remediation']='run migrate-claim for the claim-only case, repair-claim when history is ahead or the live claim is missing, or resolve explicitly; this channel cannot safely fence until proven'
    except Exception as e:
        checks['claim']={'claimed':None,'authority':'error','error':str(e)}
    try:
        _br=branch or git_out(repo,'rev-parse','--abbrev-ref','HEAD')
        _base=git_out(repo,'rev-parse',_br)
        _rh=remote_head_of(repo,remote,_br)
        checks['freshness']={'ok':bool(_rh and is_ancestor(repo,_rh,_base)),'local':_base,'remote_head':_rh,'branch':_br}
    except Exception as e:
        checks['freshness']={'ok':False,'error':str(e)}
    ok=bool(
        checks.get('chain',{}).get('ok')
        and checks.get('readiness',{}).get('ok')
        and checks.get('integrity',{}).get('ok')
        and checks.get('identity',{}).get('status') in ('consistent','legacy_compat','no_active_run')
        and checks.get('claim',{}).get('authority') in ('proven','unclaimed',None)
        and checks.get('freshness',{}).get('ok')
    )
    print(json.dumps({'task_id':(t or {}).get('task_id') or td.name,'ok':ok,'checks':checks},indent=2))
def canonical_artifact_bytes(data):
    return data.replace(b'\r\n',b'\n').replace(b'\r',b'\n')
def artifact_fingerprint(path):
    raw=Path(path).read_bytes(); canon=canonical_artifact_bytes(raw)
    return {'path':str(path),'sha256':'sha256:'+hashlib.sha256(canon).hexdigest(),'size_bytes':len(canon),'line_ending':'lf-stable' if canon==raw else 'normalized-to-lf'}
def audit_chain(task_dir,repo=None):
    """Per-event corruption diagnostics (read-only, never raises on content).

    Classifies each event file independently: required keys, seq continuity,
    prev-link vs the previous file, and hash recomputation — the exact
    byte-level checks that distinguish a hand-composed producer failure
    (hash mismatch with intact links, e.g. single-file human commit) from
    link breaks, renames/gaps, and malformed JSON. Optionally attributes
    each file to its introducing commit (sha, author, single-file or not)
    when repo is a git checkout. Semantic/authority questions stay with
    validate/replay; this reports integrity evidence only. Audit-only:
    nothing here repairs history.
    """
    td=Path(task_dir)
    try:
        task=readj(td/'task.json'); tid=task.get('task_id')
    except Exception as e:
        return {'task_id':None,'ok':False,'error':f'unreadable task manifest: {e}','events':[]}
    rows=load_events(td)
    out=[]; ok=True; prev_id=None; prev_hash=None
    last_valid=None; prefix_open=True
    for expected,(p,e) in enumerate(rows,1):
        checks={}
        try:
            missing=[k for k in ['protocol','event_id','seq','context_id','task_id','type','actor','created_at','task_projection','summary','artifacts','integrity'] if k not in e]
            checks['required_keys']={'ok':not missing,'detail':None if not missing else f"missing {missing}"}
        except Exception as ex:
            checks['required_keys']={'ok':False,'detail':f'uninspectable: {ex}'}
        checks['sequence']={'ok':e.get('seq')==expected,'detail':None if e.get('seq')==expected else f"seq {e.get('seq')} at position {expected}"}
        integ=e.get('integrity') or {}
        if expected==1:
            checks['prev_link']={'ok':integ.get('prev_event_id') is None and integ.get('prev_event_hash') is None,'detail':None if (integ.get('prev_event_id') is None and integ.get('prev_event_hash') is None) else 'first event must carry null previous values'}
        else:
            match=integ.get('prev_event_id')==prev_id and integ.get('prev_event_hash')==prev_hash
            checks['prev_link']={'ok':match,'detail':None if match else f"links to {integ.get('prev_event_id')}, previous file is {prev_id}"}
        try:
            actual=eh(e)
            checks['event_hash']={'ok':integ.get('event_hash')==actual,'detail':None if integ.get('event_hash')==actual else f"recorded {integ.get('event_hash')}, recomputed {actual}"}
        except Exception as ex:
            checks['event_hash']={'ok':False,'detail':f'unhashable: {ex}'}
        ev_ok=all(c['ok'] for c in checks.values())
        ok=ok and ev_ok
        if ev_ok and prefix_open:
            try:
                last_valid={'seq':e.get('seq'),'event_id':e.get('event_id'),'event_hash':eh(e)}
            except Exception:
                prefix_open=False
        else:
            prefix_open=False
        rec={'seq':e.get('seq'),'event_id':e.get('event_id'),'type':e.get('type'),'run_id':e.get('run_id'),'checks':checks,'ok':ev_ok,'introduced_by':None}
        if repo is not None:
            try:
                rel=Path(p).resolve().relative_to(Path(repo).resolve()).as_posix()
            except ValueError:
                rel=None
            if rel is not None:
                cp=subprocess.run(['git','-C',str(repo),'log','--diff-filter=A','--format=%H|%an|%ae|%ad','--',rel],capture_output=True,text=True)
                if cp.returncode==0 and cp.stdout.strip():
                    sha,an,ae,ad=cp.stdout.strip().split('\n')[0].split('|',3)
                    cp2=subprocess.run(['git','-C',str(repo),'show','--pretty=format:','--name-only',sha],capture_output=True,text=True)
                    files=[l.strip() for l in cp2.stdout.splitlines() if l.strip()] if cp2.returncode==0 else []
                    rec['introduced_by']={'commit':sha,'author_name':an,'author_email':ae,'author_date':ad,'files_in_commit':len(files),'single_file':len(files)==1}
        out.append(rec)
        prev_id=e.get('event_id')
        try:
            prev_hash=eh(e)
        except Exception:
            prev_hash=integ.get('event_hash')
    return {'task_id':tid,'ok':ok,'last_valid':last_valid,'events':out}
def do_audit_chain(a):
    print(json.dumps(audit_chain(a.task_dir,getattr(a,'repo',None)),indent=2))
def do_artifact_hash(a):
    print(json.dumps(artifact_fingerprint(a.path),indent=2))
def binding_path(root): return Path(root)/'.awrp'/'binding.json'
def do_bind(a):
    bp=binding_path(a.root)
    if bp.exists() and not a.force: raise RuntimeError(f'binding already exists at {bp}; use --force to replace')
    proj=getattr(a,'project_id',None)
    if proj:
        rdir=Path(a.relay_dir or a.root)
        if not rdir.exists(): raise RuntimeError(f'cannot verify project {proj!r}: relay dir {rdir} is absent')
        read_project(rdir,proj)
        owner=channel_project(rdir,a.channel)
        if owner is not None and owner!=proj: raise RuntimeError(f'workspace channel {a.channel!r} belongs to project {owner!r}, not {proj!r}; a workspace bound to another project fails closed')
    obj={'protocol':PROTOCOL,'relay':a.relay,'relay_dir':str(Path(a.relay_dir or a.root).resolve()),'channel_id':a.channel,'worker_endpoint':a.worker_endpoint,'lane_id':a.lane,'bound_at':now(),'bound_by':a.bound_by}
    if proj: obj['project_id']=proj
    bp.parent.mkdir(parents=True,exist_ok=True)
    bp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(obj,indent=2))
def read_binding(root):
    bp=binding_path(root)
    if not bp.exists(): raise RuntimeError(f'no AWRP binding at {bp}; bind this workspace first')
    o=readj(bp)
    for k in ['relay','channel_id','worker_endpoint']:
        if not o.get(k): raise RuntimeError(f'binding at {bp} missing {k}')
    return o
def run_claimed(events,run_id):
    return any(e['type']=='ACK' and e.get('run_id')==run_id for e in events)
def select_for_resume(relay_root,channel,endpoint,lane=None,project=None):
    r=scan_inbox(relay_root,channel=channel,worker_endpoint=endpoint)
    cands=r['actionable']
    # A lane-unset task is visible to any lane of the same channel+endpoint
    # (mirrors the project filter below): the coordinator cannot know a worker
    # window's lane pin, so null must mean "any lane", never "no lane".
    # Lane-set tasks stay exclusive; 2+ actionable in one lane view is still
    # AMBIGUOUS; first-writer-wins ACK still serializes races.
    if lane: cands=[c for c in cands if c.get('lane_id') in (None,lane)]
    if project is not None: cands=[c for c in cands if c.get('project_id') in (None,project)]
    if not cands:
        _inv=[{'task_id':t['task_id'],'path':t.get('path'),'error':t.get('error'),'forensics':t.get('forensics')} for t in r['invalid']]
        if _inv:
            return {'status':'INVALID_CANONICAL','reason':'no actionable bound task; corrupt canonical chains present — see invalid_canonical, do not ACK or execute','invalid_canonical':_inv}
        return {'status':'NO_TASK','reason':'no actionable bound task; do not ACK','invalid_canonical':[]}
    if len(cands)>1: return {'status':'AMBIGUOUS','reason':'more than one actionable task for this endpoint; resolve explicitly, never silent FIFO','candidates':[c['task_id'] for c in cands]}
    c=cands[0]
    # P1 snapshot reuse: the candidate was fully validated by the scan above
    # in this same invocation — validating it again is pure duplicate work.
    # The snapshot is never stored, never stale: same process, same state.
    v=r['snapshots'][c['task_id']]
    if run_claimed(v['events'],c['active_run_id']):
        return {'status':'OWNED','task_id':c['task_id'],'reason':'active run already ACKed without HANDOFF; do not redo material work; surface coordinator recovery'}
    h=v['head']
    return {'status':'EXECUTE','task_id':c['task_id'],'run_id':c['active_run_id'],'head_event_id':h['event_id'],'head_hash':h['integrity']['event_hash']}
def do_resume(a):
    b=read_binding(a.root)
    channel=a.channel or b['channel_id']; endpoint=a.worker_endpoint or b['worker_endpoint']; lane=a.lane if a.lane is not None else b.get('lane_id')
    proj=b.get('project_id')
    if proj:
        read_project(b['relay_dir'],proj)
        owner=channel_project(b['relay_dir'],channel)
        if owner is not None and owner!=proj: raise RuntimeError(f'bound project {proj!r} does not own channel {channel!r} (owned by {owner!r}); fail closed, never select across projects')
    fresh=check_freshness(b['relay_dir'])
    r=select_for_resume(b['relay_dir'],channel,endpoint,lane,proj)
    try: _fa=fencing_authority(b['relay_dir'],channel)
    except Exception as e: _fa={'channel_id':channel,'status':'error','generation':None,'owner':None,'strict':False,'detail':f'fencing authority unreadable ({e})'}
    print(json.dumps({'binding':{k:b.get(k) for k in ['relay','channel_id','worker_endpoint','lane_id','project_id']},'freshness':fresh,'fencing_authority':_fa,**r},indent=2))
def _verify_first_bind_override(relay_name,bound_dir,want):
    """Verify an explicit --relay-dir override for first-bind (read-only checks).

    Returns the resolved override dir. The override must exist, must prove
    the same canonical Relay (relay.json identity where present, plus equal
    origin remotes on both sides so a renamed directory cannot stand in for
    another repo), and is NEVER written back into the binding — it is an
    invocation-scoped execution view only. Anything else fails closed with
    the existing binding left untouched.
    """
    rd=Path(want)
    if not rd.exists(): raise RuntimeError(f'first-bind --relay-dir override {str(rd)!r} is absent; clone the relay first — the existing binding is left untouched')
    if not rd.is_dir(): raise RuntimeError(f'first-bind --relay-dir override {str(rd)!r} is not a directory; refusing — the existing binding is left untouched')
    oid=relay_identity(str(rd))
    if oid is not None and oid!=relay_name: raise RuntimeError(f"first-bind --relay-dir override {str(rd)!r} identifies as relay {oid!r}, not {relay_name!r}; refusing a wrong repo — the existing binding is left untouched")
    try: ourl=git_out(str(rd),'config','--get','remote.origin.url')
    except RuntimeError: ourl=None
    try: burl=git_out(str(bound_dir),'config','--get','remote.origin.url')
    except RuntimeError: burl=None
    if not ourl or not burl: raise RuntimeError('first-bind --relay-dir override cannot prove the same canonical Relay (origin remote unresolvable on one side); refusing — the existing binding is left untouched')
    if ourl!=burl: raise RuntimeError(f'first-bind --relay-dir override remote {ourl!r} does not match the bound clone remote {burl!r}; refusing a different repo — the existing binding is left untouched')
    return str(rd.resolve())
def do_first_bind(a):
    if not a.task_id: raise RuntimeError('first-bind requires an exact --task-id; global/cross-project discovery is forbidden on the first window')
    if not getattr(a,'project_id',None): raise RuntimeError('first-bind requires an exact --project-id; project identity must be proven by the coordinator instruction, never inferred from tasks/channels/recency')
    bp=binding_path(a.root)
    override=False
    if bp.exists():
        b=read_binding(a.root)
        for k,v in [('relay',a.relay),('channel_id',a.channel),('worker_endpoint',a.worker_endpoint),('project_id',a.project_id)]:
            if b.get(k)!=v: raise RuntimeError(f'existing binding {k}={b.get(k)!r} conflicts with first-bind target {v!r}; fail closed, never overwrite the binding or scan other channels')
        if a.lane and b.get('lane_id') and a.lane!=b.get('lane_id'): raise RuntimeError(f"binding lane pin is {b.get('lane_id')!r}; requested lane {a.lane!r} would silently cross an explicitly pinned lane boundary")
        bound_dir=b['relay_dir']
        want=getattr(a,'relay_dir',None)
        if want and Path(want).resolve()!=Path(bound_dir).resolve():
            relay_dir=_verify_first_bind_override(a.relay,bound_dir,want)
            override=True
        else:
            relay_dir=bound_dir
    else:
        relay_dir=a.relay_dir or str(Path(a.root))
        rd=Path(relay_dir)
        if not rd.exists(): raise RuntimeError(f'relay dir {rd} is absent; clone the relay first')
        read_project(rd,a.project_id)
        owner=channel_project(rd,a.channel)
        if owner is not None and owner!=a.project_id: raise RuntimeError(f'channel {a.channel!r} belongs to project {owner!r}, not {a.project_id!r}; fail closed')
        obj={'protocol':PROTOCOL,'relay':a.relay,'relay_dir':str(rd.resolve()),'channel_id':a.channel,'worker_endpoint':a.worker_endpoint,'lane_id':a.lane,'bound_at':now(),'bound_by':a.bound_by or 'first-bind','project_id':a.project_id}
        bp.parent.mkdir(parents=True,exist_ok=True)
        bp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    git_out(relay_dir,'pull','--ff-only')
    td=Path(relay_dir)/'tasks'/a.task_id
    if not (td/'task.json').exists(): raise RuntimeError(f'exact target {a.task_id!r} is not in the relay; never infer an alternative target')
    v=validate(td); t=v['task']; h=v['head']; p=h['task_projection']
    if t.get('project_id'):
        if t['project_id']!=a.project_id: raise RuntimeError(f"target task project is {t.get('project_id')!r}, not {a.project_id!r}; exact-project match required")
    else:
        require_migration(relay_dir,a.project_id,a.task_id,t)
    ch,lane,ep=task_routing(t)
    if ch!=a.channel or ep!=a.worker_endpoint: raise RuntimeError(f'target task route ({ch!r}/{ep!r}) does not match first-bind target ({a.channel!r}/{a.worker_endpoint!r}); never execute across routes')
    active=v.get('active_run_id')
    bout={'relay':a.relay,'channel_id':a.channel,'worker_endpoint':a.worker_endpoint,'project_id':a.project_id,'relay_dir':relay_dir,'override':override}
    if p['state'] in TERMINAL or not active:
        print(json.dumps({'binding':bout,'status':'NO_TASK','task_id':a.task_id,'reason':'exact target has no actionable run; do not ACK'},indent=2)); return
    ds=[e for e in v['events'] if e['type']=='DISPATCH' and e.get('run_id')==active]
    if not ds: raise RuntimeError(f'active run {active!r} has no DISPATCH; fail closed')
    rec=ds[0].get('recipient') or {}
    if rec.get('role')!='worker': raise RuntimeError(f'active run recipient is not a worker ({rec!r}); fail closed')
    eff=read_binding(a.root)
    eff_lane=eff.get('lane_id'); eff_project=eff.get('project_id')
    r=select_for_resume(relay_dir,a.channel,a.worker_endpoint,eff_lane,eff_project)
    if r['status']=='OWNED' and r.get('task_id')==a.task_id:
        print(json.dumps({'binding':bout,'status':'OWNED','task_id':a.task_id,'run_id':active,'reason':'active run already ACKed without HANDOFF; do not redo material work'},indent=2)); return
    if not (r['status']=='EXECUTE' and r.get('task_id')==a.task_id and r.get('run_id')==active):
        raise RuntimeError(f"target run is not visible to the bound workspace (binding project={eff_project!r} channel={a.channel!r} lane={eff_lane!r} endpoint={a.worker_endpoint!r} resumes {r['status']}); first-bind refuses EXECUTE that ordinary resume cannot see")
    if a.run_id and a.run_id!=active: raise RuntimeError(f'first-bind run mismatch: target run is {active!r}, asked for {a.run_id!r}; ACK only the matching active run')
    try: _fa=fencing_authority(relay_dir,a.channel)
    except Exception as e: _fa={'channel_id':a.channel,'status':'error','generation':None,'owner':None,'strict':False,'detail':f'fencing authority unreadable ({e})'}
    print(json.dumps({'binding':bout,'status':'EXECUTE','task_id':a.task_id,'run_id':active,'head_event_id':h['event_id'],'head_hash':h['integrity']['event_hash'],'fencing_authority':_fa},indent=2))
def check_freshness(relay_dir,remote='origin',branch='main'):
    local=git_out(relay_dir,'rev-parse',branch)
    rh=git_out(relay_dir,'ls-remote',remote,branch)
    remote_head=rh.split()[0] if rh else None
    if not remote_head: raise RuntimeError(f'cannot resolve remote {remote}/{branch}; cannot prove freshness, re-sync before resume/ACK')
    if local!=remote_head: raise RuntimeError(f'stale local Relay view: local {branch} is {local}, remote {remote}/{branch} is {remote_head}; git pull --ff-only and re-sync/replay before resume/ACK')
    return {'local':local,'remote_head':remote_head,'aligned':True}
def claim_path(root,channel): return Path(root)/'channels'/channel/'claim.json'
def claim_log_path(root,channel): return Path(root)/'channels'/channel/'claim.log.jsonl'
def read_claim(root,channel):
    p=claim_path(root,channel)
    return readj(p) if p.exists() else None
def read_claim_log(root,channel):
    p=claim_log_path(root,channel)
    if not p.exists(): return []
    out=[]
    for line in p.read_text(encoding='utf-8').splitlines():
        line=line.strip()
        if line: out.append(json.loads(line))
    return out
# ---- Channel fencing positive-proof authority (P0) ----
# A fenced coordinator mutation (especially DISPATCH) must never be
# publishable on claim.json alone: the referenced (channel_id, generation,
# owner) has to be verifiably present in canonical claim history
# (channels/<id>/claim.log.jsonl). Every fencing decision in this module —
# dispatch/publication gates, ACK seating, bridge publication, audit-fencing,
# doctor, resume/recovery diagnostics, claim acquire/migrate/repair — goes
# through fencing_authority() below, so the verdicts cannot drift apart.
# The append-only history is the trust anchor; claim.json is a live
# projection of its tip and is always re-derivable from it.
AUTHORITY_FIELDS=('channel_id','generation','owner','prev_owner','takeover')
def _authority_core(o):
    if not isinstance(o,dict): return None
    if not isinstance(o.get('generation'),int): return None
    return tuple(o.get(k) for k in AUTHORITY_FIELDS)
def claim_history_view(root,channel):
    """One validated view over canonical claim history (read-only).

    Returns {'entries': [...], 'problems': [...]}. entries holds clean,
    deduplicated history rows in file order. problems holds fatal proof
    defects — non_object_row, non_integer_generation, bad_owner,
    channel_mismatch, generation_conflict (one generation, two owners) —
    each naming the 1-based log line. Any fatal problem means the history
    as a whole proves nothing: callers fail closed rather than trusting a
    partially readable log. Identical (channel, generation, owner) repeats
    are deduplicated (first wins) without failing: they prove the same
    triple. Raises only when the log file itself is unreadable.
    """
    rows=read_claim_log(root,channel)
    entries=[]; problems=[]; seen={}
    for i,raw in enumerate(rows,1):
        if not isinstance(raw,dict):
            problems.append({'type':'non_object_row','line':i}); continue
        ch=raw.get('channel_id'); gen=raw.get('generation'); owner=raw.get('owner')
        if ch!=channel:
            problems.append({'type':'channel_mismatch','line':i,'row_channel_id':ch}); continue
        if not isinstance(gen,int):
            problems.append({'type':'non_integer_generation','line':i,'generation':gen}); continue
        if not isinstance(owner,str) or not owner:
            problems.append({'type':'bad_owner','line':i,'owner':owner}); continue
        key=(ch,gen)
        if key in seen:
            if seen[key]!=owner:
                problems.append({'type':'generation_conflict','line':i,'generation':gen,'owners':sorted([seen[key],owner])})
            continue
        seen[key]=owner; entries.append(raw)
    return {'entries':entries,'problems':problems}
def claim_history_contains(root,channel,generation,owner):
    """True iff canonical claim history positively proves the full triple.

    The history entry itself must carry the matching channel_id (not just
    the file path), an integer generation, and the owner — and the history
    must be free of fatal proof defects. Any malformed/ambiguous history
    fails closed: it proves nothing, including otherwise clean rows.
    """
    if root is None or not channel: return False
    try: view=claim_history_view(root,channel)
    except Exception: return False
    if view['problems']: return False
    return any(e.get('generation')==generation and e.get('owner')==owner for e in view['entries'])
def fencing_authority(root,channel):
    """Positive-proof fencing authority for one channel (read-only).

    Returns {'channel_id','status','generation','owner','strict','detail'}.
    status is one of:
      proven        live claim.json matches the history tip on every
                    authority field — new fenced authority may be granted;
      unclaimed     no claim.json and no history — the legacy unfenced path;
      legacy-claim  claim.json without history on a channel owned by no
                    project — pre-claim-adoption readability is preserved and
                    the old fenced-against-claim.json gate still applies;
      inconsistent  anything else (strict claim-only orphan, owner/generation
                    mismatch, history ahead of the live claim, live claim
                    missing while history exists on a strict channel).
    strict is True when a registered project owns the channel: only there is
    the orphaned-authority condition hard. detail names the evidence and the
    bounded remediation (migrate-claim for the claim-only case, repair-claim
    for history-ahead / missing-live-claim, explicit human decision
    otherwise). Never raises on content: unreadable files fail closed as
    inconsistent, an unreadable registry propagates (fail closed).
    """
    if not channel: raise RuntimeError('fencing authority requires a channel_id')
    try: cur=read_claim(root,channel)
    except Exception as e: return {'channel_id':channel,'status':'inconsistent','generation':None,'owner':None,'strict':False,'detail':f'claim.json unreadable ({e}); fail closed'}
    try: view=claim_history_view(root,channel)
    except Exception as e: return {'channel_id':channel,'status':'inconsistent','generation':(cur or {}).get('generation'),'owner':(cur or {}).get('owner'),'strict':False,'detail':f'claim history unreadable ({e}); fail closed'}
    log=view['entries']
    owner=channel_project(root,channel)
    strict=owner is not None
    if not log and cur is None:
        return {'channel_id':channel,'status':'unclaimed','generation':None,'owner':None,'strict':strict,'detail':'no live claim and no claim history; legacy unfenced path'}
    if not log:
        if strict:
            return {'channel_id':channel,'status':'inconsistent','generation':cur.get('generation'),'owner':cur.get('owner'),'strict':True,'detail':f"orphaned authority: claim.json generation {cur.get('generation')} owned by {cur.get('owner')!r} has no canonical claim history; run migrate-claim to record the exact existing claim bytes as history, never publish fenced authority on claim.json alone"}
        return {'channel_id':channel,'status':'legacy-claim','generation':cur.get('generation'),'owner':cur.get('owner'),'strict':False,'detail':'claim.json without history on a project-less channel; readable history preserved, but claim.json alone authorizes no NEW fenced mutation — run migrate-claim before any new fenced write'}
    if view['problems']:
        kinds=sorted({p['type'] for p in view['problems']})
        return {'channel_id':channel,'status':'inconsistent','generation':(cur or {}).get('generation'),'owner':(cur or {}).get('owner'),'strict':strict,'detail':f"claim history is malformed/ambiguous ({', '.join(kinds)}); ambiguous history proves nothing — resolve explicitly, never fence on it"}
    tip=log[-1]
    if cur is None:
        if strict:
            return {'channel_id':channel,'status':'inconsistent','generation':None,'owner':None,'strict':True,'detail':f"live claim missing while {len(log)} history entries exist (tip generation {tip.get('generation')}); claim history alone grants no live authority; run repair-claim to restore claim.json from exact history-tip bytes"}
        return {'channel_id':channel,'status':'unclaimed','generation':None,'owner':None,'strict':False,'detail':f'live claim missing with {len(log)} history entries on a project-less channel; legacy unfenced path'}
    if _authority_core(cur)!=_authority_core(tip):
        return {'channel_id':channel,'status':'inconsistent','generation':cur.get('generation'),'owner':cur.get('owner'),'strict':strict,'detail':f"live claim {(_authority_core(cur))!r} diverges from history tip {(_authority_core(tip))!r}; {'run repair-claim to restore claim.json from exact history-tip bytes when history is ahead, otherwise resolve explicitly — never publish on diverged authority' if strict else 'resolve explicitly before fencing against either side'}"}
    return {'channel_id':channel,'status':'proven','generation':cur.get('generation'),'owner':cur.get('owner'),'strict':strict,'detail':'live claim matches canonical history tip on every authority field'}
def acquire_claim(root,channel,owner,expected_generation=None,takeover=False,note=None):
    """Crash-consistent coordinator claim acquisition (CAS).

    Commit point is the append-only history: the new entry is flushed and
    fsynced to claim.log.jsonl FIRST, then the live claim.json projection is
    replaced atomically. A crash between the two can only leave history
    AHEAD of claim.json — a state repair-claim restores deterministically
    from exact history-tip bytes. The old order (claim.json first) could
    leave an unprovable claim-ahead state; that ordering is gone.
    The new generation must exceed every generation already in history, so a
    stale claim.json (e.g. restored from an older checkout) can never fork
    authority by re-minting a generation the history already contains.
    """
    cur=read_claim(root,channel)
    log=read_claim_log(root,channel)
    logged_gens=[x.get('generation') for x in log if isinstance(x,dict) and isinstance(x.get('generation'),int)]
    max_logged=max(logged_gens) if logged_gens else 0
    if cur is None:
        if expected_generation not in (None,0): raise RuntimeError(f'stale coordinator claim: expected generation {expected_generation} but no claim exists; re-sync')
        if log: raise RuntimeError(f'coordinator claim fork refused: live claim is missing while history holds {len(log)} entries; run repair-claim to restore claim.json from exact history-tip bytes, never mint over a missing live claim')
        gen=1; prev=None
    else:
        if not takeover and expected_generation!=cur.get('generation'): raise RuntimeError(f"stale coordinator claim: have generation {cur.get('generation')}, expected {expected_generation}; re-sync, never append on stale authority")
        if not isinstance(cur.get('generation'),int): raise RuntimeError(f'coordinator claim on channel {channel} carries a non-integer generation; fail closed, resolve explicitly')
        if log and _authority_core(cur)!=_authority_core(log[-1]): raise RuntimeError(f'coordinator claim fork refused: live claim diverges from history tip; run repair-claim when history is ahead, otherwise resolve explicitly — never mint a generation over diverged authority')
        gen=cur['generation']+1; prev=cur.get('owner')
    if gen<=max_logged: raise RuntimeError(f'coordinator claim fork refused: history already holds generation {max_logged}, cannot mint {gen}; claim.json is behind canonical history — run repair-claim to restore it from exact history-tip bytes, never re-mint a logged generation')
    obj={'protocol':PROTOCOL,'channel_id':channel,'generation':gen,'owner':owner,'updated_at':now(),'prev_owner':prev,'takeover':bool(takeover),'note':note}
    lp=claim_log_path(root,channel); lp.parent.mkdir(parents=True,exist_ok=True)
    with open(lp,'a',encoding='utf-8') as fh:
        fh.write(json.dumps(obj,ensure_ascii=False,sort_keys=True)+'\n'); fh.flush()
        try: os.fsync(fh.fileno())
        except OSError: pass
    atomic_write_json(claim_path(root,channel),obj)
    return obj
def migrate_claim(root,channel,note=None,by=None):
    """Bounded explicit migration for pre-claim-adoption channels.

    Only the claim-only case qualifies: claim.json present, history
    missing/empty. The migration appends the EXACT existing claim bytes
    (authority fields preserved, generation NOT bumped) plus explicit
    provenance (migrated flag, operator, reason, timestamp) — it never
    fabricates a new authority generation and never rewrites event history.
    Anything else (history present, claim missing) is refused: that is
    repair territory (repair-claim) or an explicit human decision, never a
    silent migration.
    """
    cur=read_claim(root,channel)
    if cur is None: raise RuntimeError(f'migrate-claim refused: channel {channel!r} has no claim.json; migration records exact existing claim bytes and invents none')
    log=read_claim_log(root,channel)
    if log: raise RuntimeError(f'migrate-claim refused: channel {channel!r} already holds {len(log)} history entries; migration is for history-less channels only — use repair-claim or resolve explicitly')
    if _authority_core(cur) is None: raise RuntimeError(f'migrate-claim refused: claim.json on channel {channel!r} carries no integer generation; resolve explicitly')
    entry=dict(cur); entry['migrated']=True; entry['migrated_by']=by; entry['migrated_note']=note; entry['migrated_at']=now()
    lp=claim_log_path(root,channel); lp.parent.mkdir(parents=True,exist_ok=True)
    with open(lp,'a',encoding='utf-8') as fh:
        fh.write(json.dumps(entry,ensure_ascii=False,sort_keys=True)+'\n'); fh.flush()
        try: os.fsync(fh.fileno())
        except OSError: pass
    return {'channel_id':channel,'generation':cur.get('generation'),'owner':cur.get('owner'),'migrated':True,'history_entries':1}
def repair_claim(root,channel):
    """Bounded deterministic repair from canonical history bytes.

    Restores claim.json to the EXACT history-tip bytes. Qualifies only when
    history is present and the live claim is missing or behind (tip
    generation greater than the live one, or no live claim): the provable
    direction, log -> claim.json. A live claim AHEAD of history (or
    diverging at the same generation) is refused — history is the trust
    anchor and cannot be conjured from an unproven claim; that needs an
    explicit human decision. Creates no new generation, rewrites no history.
    """
    log=read_claim_log(root,channel)
    if not log: raise RuntimeError(f'repair-claim refused: channel {channel!r} holds no claim history; nothing provable to restore from — use migrate-claim for the claim-only case')
    tip=log[-1]
    if _authority_core(tip) is None: raise RuntimeError(f'repair-claim refused: history tip on channel {channel!r} carries no integer generation; resolve explicitly')
    cur=read_claim(root,channel)
    if cur is not None:
        cur_gen=cur.get('generation'); tip_gen=tip.get('generation')
        if isinstance(cur_gen,int) and isinstance(tip_gen,int) and cur_gen>tip_gen:
            raise RuntimeError(f'repair-claim refused: live claim generation {cur_gen} is ahead of history tip {tip_gen}; history is the trust anchor — resolve explicitly, never conjure history from an unproven claim')
        if _authority_core(cur)==_authority_core(tip):
            return {'channel_id':channel,'generation':tip.get('generation'),'owner':tip.get('owner'),'repaired':False,'detail':'live claim already matches history tip; nothing to repair'}
        if isinstance(cur_gen,int) and isinstance(tip_gen,int) and cur_gen==tip_gen:
            raise RuntimeError(f'repair-claim refused: live claim diverges from history tip at generation {cur_gen}; which side is truth needs an explicit human decision')
    atomic_write_json(claim_path(root,channel),tip)
    return {'channel_id':channel,'generation':tip.get('generation'),'owner':tip.get('owner'),'repaired':True,'detail':'claim.json restored from exact history-tip bytes; commit and push claim.json with claim.log.jsonl together'}
def do_migrate_claim(a):
    print(json.dumps(migrate_claim(a.root,a.channel,getattr(a,'note',None),getattr(a,'by',None)),indent=2))
def do_repair_claim(a):
    print(json.dumps(repair_claim(a.root,a.channel),indent=2))
def do_acquire_claim(a):
    print(json.dumps(acquire_claim(a.root,a.channel,a.owner,a.expected_generation,a.takeover,a.note),indent=2))
def do_read_claim(a):
    cur=read_claim(a.root,a.channel)
    print(json.dumps(cur,indent=2) if cur else json.dumps({'channel_id':a.channel,'claimed':False},indent=2))
import re as _re
PROJECT_ID_RE=_re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]*$')
def check_project_id(pid):
    if not pid or not PROJECT_ID_RE.match(pid): raise RuntimeError(f'invalid project_id {pid!r}; use letters/digits/_/- starting with alnum')
    return pid
def project_path(root,pid): return Path(root)/'projects'/f'{pid}.json'
def read_project(root,pid):
    p=project_path(root,check_project_id(pid))
    if not p.exists(): raise RuntimeError(f'unknown project_id {pid!r}; create it with project-create first')
    o=readj(p)
    if o.get('project_id')!=pid or o.get('protocol')!=PROTOCOL: raise RuntimeError(f'project file {p} identity mismatch')
    return o
def list_projects(root):
    d=Path(root)/'projects'
    if not d.exists(): return []
    return sorted(p.stem for p in d.glob('*.json'))
def channel_project(root,channel):
    owners=[]
    for pid in list_projects(root):
        try: o=read_project(root,pid)
        except RuntimeError: continue
        if channel in (o.get('channels') or []): owners.append(pid)
    if len(owners)>1: raise RuntimeError(f'channel {channel!r} is claimed by multiple projects {owners}; ownership is exclusive, resolve explicitly')
    return owners[0] if owners else None
def project_create(root,pid,title,channels=(),notion=None,created_by='chatgpt',aliases=(),notion_page_id=None):
    check_project_id(pid)
    if notion is not None and (not isinstance(notion,str) or not notion.strip()): raise RuntimeError('project notion pointer must be a non-empty string when present; worker code never calls Notion')
    if notion_page_id is not None and (not isinstance(notion_page_id,str) or not notion_page_id.strip()): raise RuntimeError('project notion_page_id must be a non-empty string when present; worker code never calls Notion')
    if any(not isinstance(x,str) or not x for x in (aliases or [])): raise RuntimeError('project aliases must be exact non-empty strings; metadata only, never fuzzy selection')
    for ch in channels or []:
        owner=channel_project(root,ch)
        if owner is not None: raise RuntimeError(f'channel {ch!r} already belongs to project {owner!r}; one channel cannot silently belong to two projects')
    obj={'protocol':PROTOCOL,'project_id':pid,'title':title,'channels':list(channels or []),'aliases':list(aliases or []),'notion':notion,'notion_page_id':notion_page_id,'created_at':now(),'created_by':created_by}
    write_new(project_path(root,pid),obj); return obj
def do_project_create(a):
    print(json.dumps(project_create(a.root,a.project_id,a.title,a.channel or [],a.notion,a.created_by,getattr(a,'alias',None) or [],getattr(a,'notion_page_id',None)),indent=2))
def project_assign_channel(root,pid,channel):
    o=read_project(root,pid)
    owner=channel_project(root,channel)
    if owner is not None and owner!=pid: raise RuntimeError(f'channel {channel!r} already belongs to project {owner!r}; one channel cannot silently belong to two projects')
    if channel not in (o.get('channels') or []):
        o['channels']=list(o.get('channels') or [])+[channel]
        project_path(root,pid).write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return read_project(root,pid)
def do_project_assign_channel(a):
    print(json.dumps(project_assign_channel(a.root,a.project_id,a.channel),indent=2))
def resolve_project(root,project_id=None,alias=None,title=None):
    given=[x for x in [project_id,alias,title] if x is not None]
    if len(given)!=1: raise RuntimeError('resolve-project needs exactly one of --project-id, --alias, or --title; never combine, never omit')
    if project_id is not None:
        o=read_project(root,project_id)
        return {'status':'RESOLVED','via':'project_id','project':o}
    key='aliases' if alias is not None else 'title'
    want=alias if alias is not None else title
    hits=[]
    for pid in list_projects(root):
        try: o=read_project(root,pid)
        except RuntimeError: continue
        vals=o.get(key) or ([] if key=='aliases' else None)
        if key=='aliases':
            if want in vals: hits.append(o)
        elif vals==want: hits.append(o)
    if not hits: return {'status':'NOT_FOUND','via':('alias' if alias is not None else 'title'),'value':want}
    if len(hits)>1: return {'status':'AMBIGUOUS','via':('alias' if alias is not None else 'title'),'value':want,'candidates':sorted(o['project_id'] for o in hits)}
    return {'status':'RESOLVED','via':('alias' if alias is not None else 'title'),'project':hits[0]}
def do_resolve_project(a):
    print(json.dumps(resolve_project(a.root,getattr(a,'project_id',None),getattr(a,'alias',None),getattr(a,'title',None)),indent=2))
def snapshot_task_entry(root,td):
    t=readj(td/'task.json')
    try: v=validate(td)
    except Exception as e: return {'task_id':t.get('task_id',td.name),'valid':False,'error':str(e)}
    h=v['head']; p=h['task_projection']
    sig=None
    for e in reversed(v['events']):
        if e['type'] in ('HANDOFF','REVIEW','APPROVAL'):
            sig={'event_id':e['event_id'],'type':e['type'],'created_at':e.get('created_at'),'summary':e.get('summary')}; break
    return {'task_id':t['task_id'],'valid':True,'title':t.get('title'),'state':p['state'],'phase':p['phase'],'waiting_on':p['waiting_on'],'head_event_id':h['event_id'],'active_run_id':v.get('active_run_id'),'actionable':bool(v.get('active_run_id') and p['state'] not in TERMINAL),'last_significant':sig}
def do_project_snapshot(a):
    o=read_project(a.root,a.project_id)
    pid=o['project_id']
    members=[]; unresolvable=[]; invalid=[]
    tdir=Path(a.root)/'tasks'
    for td in sorted(tdir.iterdir()) if tdir.exists() else []:
        if not (td/'task.json').exists(): continue
        try: t=readj(td/'task.json'); tid=t['task_id']
        except Exception as e: invalid.append({'task_id':td.name,'valid':False,'error':str(e)}); continue
        belongs=False; via=None
        if t.get('project_id')==pid: belongs=True; via='intrinsic'
        elif not t.get('project_id'):
            try:
                require_migration(a.root,pid,t['task_id'],t); belongs=True; via='migration'
            except RuntimeError as e:
                if migration_path(a.root,pid,t['task_id']).exists(): unresolvable.append({'task_id':t['task_id'],'error':str(e)})
                continue
        if not belongs: continue
        entry=snapshot_task_entry(a.root,td); entry['via']=via
        (members if entry.get('valid',True) else invalid).append(entry)
    cands=[m['task_id'] for m in members if m.get('actionable')]
    print(json.dumps({'project':o,'tasks':members,'unresolvable_migrations':unresolvable,'invalid_tasks':[e['task_id'] for e in invalid],'actionable_candidates':cands,'ambiguous':len(cands)>1},indent=2))
def audit_projects(root):
    violations=[]
    seen_notion={}; seen_alias={}
    for pid in list_projects(root):
        try: o=read_project(root,pid)
        except RuntimeError as e: violations.append({'type':'unreadable','project_id':pid,'error':str(e)}); continue
        npg=o.get('notion_page_id')
        if npg is not None:
            if not isinstance(npg,str) or not npg.strip(): violations.append({'type':'malformed_notion_pointer','project_id':pid})
            elif npg in seen_notion: violations.append({'type':'duplicate_notion_page','notion_page_id':npg,'projects':sorted([seen_notion[npg],pid])})
            else: seen_notion[npg]=pid
        for al in o.get('aliases') or []:
            if al in seen_alias: violations.append({'type':'ambiguous_alias','alias':al,'projects':sorted([seen_alias[al],pid])})
            else: seen_alias[al]=pid
    return {'ok':not violations,'violations':violations}
def do_audit_projects(a):
    print(json.dumps(audit_projects(a.root),indent=2))
def migration_path(root,pid,tid): return Path(root)/'projects'/pid/'migrations'/f'{tid}.json'
def migration_associate(root,pid,tid,reason=None,created_by='chatgpt'):
    read_project(root,pid)
    tdir=Path(root)/'tasks'/tid
    if not (tdir/'task.json').exists(): raise RuntimeError(f'migration target task {tid!r} is not in the relay; never associate ghosts')
    t=readj(tdir/'task.json')
    if t.get('project_id'): raise RuntimeError(f'task {tid!r} already carries intrinsic project_id {t.get("project_id")!r}; the migration bridge is for project-less legacy tasks only')
    ch=(t.get('routing') or {}).get('channel_id')
    if not ch: raise RuntimeError(f'legacy task {tid!r} has no channel route; project membership cannot be proven')
    owner=channel_project(root,ch)
    if owner!=pid: raise RuntimeError(f'channel {ch!r} is owned by {owner!r}, not {pid!r}; migration association fails closed on conflict')
    obj={'protocol':PROTOCOL,'project_id':pid,'task_id':tid,'channel_id':ch,'created_at':now(),'created_by':created_by,'reason':reason}
    write_new(migration_path(root,pid,tid),obj); return obj
def do_migration_associate(a):
    print(json.dumps(migration_associate(a.root,a.project_id,a.task_id,a.reason,a.created_by),indent=2))
def read_migration(root,pid,tid):
    p=migration_path(root,pid,tid)
    return readj(p) if p.exists() else None
def require_migration(root,pid,tid,task):
    m=read_migration(root,pid,tid)
    if m is None: raise RuntimeError(f'project-less legacy task {tid!r} has no migration association for project {pid!r}; channel membership alone is insufficient, Strong First Bind refused')
    if m.get('project_id')!=pid or m.get('task_id')!=tid or m.get('protocol')!=PROTOCOL: raise RuntimeError(f'migration association for {tid!r} is corrupt; fail closed')
    ch=(task.get('routing') or {}).get('channel_id')
    if m.get('channel_id')!=ch: raise RuntimeError(f'migration association channel {m.get("channel_id")!r} does not match task route {ch!r}; fail closed')
    owner=channel_project(root,ch)
    if owner!=pid: raise RuntimeError(f'channel {ch!r} is owned by {owner!r}, not {pid!r}; the migration association is no longer valid')
    return m
def plan_fingerprint(binding_route,task_id,task_head,relay_head,mode='bound'):
    body={'v':'awrp-plan/v1','mode':mode,'binding_route':binding_route,'task_id':task_id,'task_head':{'event_id':task_head['event_id'],'event_hash':task_head['integrity']['event_hash']},'relay_head':relay_head}
    return 'awrp-plan/v1:sha256:'+hashlib.sha256(json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def relay_head_of(repo,branch='main',remote='origin'):
    try:
        out=git_out(repo,'ls-remote',remote,branch)
    except RuntimeError: return None
    return out.split()[0] if out else None
def route_compat_error(binding,task,relay_root):
    bch=binding['channel_id']; bep=binding['worker_endpoint']; bl=binding.get('lane_id'); bp=binding.get('project_id')
    ch,lane,ep=task_routing(task); tp=task.get('project_id')
    if not ch or not ep: return 'task has no exact channel/endpoint route; set routing at creation before planning'
    if ch!=bch: return f'channel mismatch: binding {bch!r} vs task {ch!r}'
    if ep!=bep: return f'worker-endpoint mismatch: binding {bep!r} vs task {ep!r}'
    if bl and lane and bl!=lane: return f'lane pin mismatch: binding pins {bl!r} vs task {lane!r}'
    if bp and tp and bp!=tp: return f'project mismatch: binding {bp!r} vs task {tp!r}'
    if tp:
        owner=channel_project(relay_root,ch)
        if owner is not None and owner!=tp: return f'task project {tp!r} does not own channel {ch!r} (owned by {owner!r})'
    return None
def do_plan_dispatch(a):
    has_root=bool(getattr(a,'binding_root',None)); unbound=bool(getattr(a,'no_binding',False))
    if has_root==unbound: raise RuntimeError('plan-dispatch needs exactly one of --binding-root (bound workspace) or --no-binding with explicit --project-id/--channel/--worker-endpoint')
    if unbound:
        for k in ['project_id','channel','worker_endpoint']:
            if not getattr(a,k,None): raise RuntimeError(f'--no-binding planning requires an explicit --{k.replace("_","-")}; never infer the route')
        b={'project_id':a.project_id,'channel_id':a.channel,'lane_id':getattr(a,'lane',None),'worker_endpoint':a.worker_endpoint}
        relay_dir=a.root; mode='unbound'
    else:
        b=read_binding(a.binding_root)
        relay_dir=b['relay_dir']; mode='bound'
    tdir=Path(relay_dir)/'tasks'/a.task_id
    if not (tdir/'task.json').exists(): raise RuntimeError(f'exact target {a.task_id!r} is not in the relay; the planner never scans for alternatives')
    v=validate(tdir); t=v['task']; h=v['head']
    binding_route={'project_id':b.get('project_id'),'channel_id':b['channel_id'],'lane_id':b.get('lane_id'),'worker_endpoint':b['worker_endpoint']}
    ch,lane,ep=task_routing(t)
    task_route={'project_id':t.get('project_id'),'channel_id':ch,'lane_id':lane,'worker_endpoint':ep}
    active=v.get('active_run_id')
    rh=relay_head_of(relay_dir,getattr(a,'branch',None) or 'main',getattr(a,'remote',None) or 'origin')
    fp=plan_fingerprint(binding_route,a.task_id,h,rh,mode)
    base={'mode':mode,'binding_route':binding_route,'task_route':task_route,'task_id':a.task_id,'active_run_id':active,'head_event_id':h['event_id'],'plan_fingerprint':fp,'relay_head':rh}
    if h['task_projection']['state'] in TERMINAL or not active:
        err=route_compat_error(b,t,relay_dir)
        if err:
            print(json.dumps({**base,'plannable':False,'reason':err},indent=2)); return
        print(json.dumps({**base,'plannable':True,'route':binding_route,'reason':'no actionable run yet; publish DISPATCH with exactly this route and the plan stays valid while binding/task/heads are unchanged'},indent=2)); return
    if a.run_id and a.run_id!=active:
        print(json.dumps({**base,'visible':False,'reason':f"expected run is {active!r}, asked for {a.run_id!r}; dispatch planning refuses run mismatch"},indent=2)); return
    r=select_for_resume(relay_dir,b['channel_id'],b['worker_endpoint'],b.get('lane_id'),b.get('project_id'))
    if r['status']=='EXECUTE' and r.get('task_id')==a.task_id and r.get('run_id')==active:
        print(json.dumps({**base,'visible':True,'run_id':active,'reason':'dispatch route matches the binding; ordinary resume sees EXECUTE for this run'},indent=2)); return
    print(json.dumps({**base,'visible':False,'reason':f"binding resumes {r['status']} while the target run is {active!r}; fix the dispatch route to equal the binding route before canonical DISPATCH"},indent=2))
def do_dispatch_guarded(a):
    has_root=bool(getattr(a,'binding_root',None)); unbound=bool(getattr(a,'no_binding',False))
    if has_root==unbound: raise RuntimeError('dispatch-guarded needs exactly one of --binding-root (bound workspace) or --no-binding with explicit --project-id/--channel/--worker-endpoint; never silently fall back')
    publish=bool(getattr(a,'publish',False))
    repo_arg=getattr(a,'repo',None); branch=getattr(a,'branch',None) or 'main'; remote=getattr(a,'remote',None) or 'origin'
    if unbound:
        for k in ['project_id','channel','worker_endpoint']:
            if not getattr(a,k,None): raise RuntimeError(f'--no-binding dispatch requires an explicit --{k.replace("_","-")}; never infer the route')
        if not repo_arg: raise RuntimeError('--no-binding dispatch requires an explicit --repo pointing at the relay checkout holding tasks/ and the git remote')
        b={'project_id':a.project_id,'channel_id':a.channel,'lane_id':getattr(a,'lane',None),'worker_endpoint':a.worker_endpoint}
        relay_dir=repo=repo_arg; mode='unbound'
    else:
        b=read_binding(a.binding_root)
        relay_dir=b['relay_dir']; repo=repo_arg or relay_dir; mode='bound'
    tdir=Path(relay_dir)/'tasks'/a.task_id
    if not (tdir/'task.json').exists(): raise RuntimeError(f'exact target {a.task_id!r} is not in the relay; guarded publication never scans for alternatives')
    v0=validate(tdir)
    if v0.get('active_run_id') is not None: raise RuntimeError(f"task {a.task_id!r} already has active run {v0.get('active_run_id')!r}; guarded dispatch is the pre-DISPATCH path only")
    err=route_compat_error(b,v0['task'],relay_dir)
    if err: raise RuntimeError(f'guarded dispatch refused: {err}')
    rh=relay_head_of(repo if publish else relay_dir,branch,remote)
    live_fp=plan_fingerprint({'project_id':b.get('project_id'),'channel_id':b['channel_id'],'lane_id':b.get('lane_id'),'worker_endpoint':b['worker_endpoint']},a.task_id,v0['head'],rh,mode)
    if getattr(a,'expected_plan',None) and a.expected_plan!=live_fp: raise RuntimeError('guarded dispatch refused: live plan fingerprint differs from --expected-plan (binding, task, or heads changed since planning); re-plan and recompose')
    g=argparse.Namespace(task_dir=str(tdir),type='DISPATCH',actor_role=a.actor_role,actor_id=a.actor_id,recipient_role=a.recipient_role,recipient_id=a.recipient_id,run_id=a.run_id,new_run=bool(a.new_run),state=a.state,phase=a.phase,waiting_on=a.waiting_on,run_state=a.run_state,summary=a.summary,details_file=a.details_file,artifacts_file=a.artifacts_file,approval_file=a.approval_file,causation_id=a.causation_id,expected_head=a.expected_head,expected_hash=a.expected_hash,claimant=a.claimant,fencing_generation=a.fencing_generation,idempotency_key=getattr(a,'idempotency_key',None),require_fresh=False)
    v,t,h,rid,e=_prepare_event(tdir,g)
    e['integrity']['event_hash']=eh(e); _append_event_file(tdir,e)
    out={'event_id':e['event_id'],'seq':e['seq'],'run_id':rid,'event_hash':e['integrity']['event_hash'],'plan_fingerprint':live_fp,'relay_head':rh}
    if not publish:
        print(json.dumps(out,indent=2)); return
    rel=os.path.relpath(tdir,repo) if Path(tdir).is_absolute() else str(tdir)
    msg=getattr(a,'commit_message',None) or f"awrp: {e['type']} {t['task_id']} {rid or ''}".strip()
    git_out(repo,'add',rel); git_out(repo,'commit','-m',msg)
    cp=subprocess.run(['git','-C',str(repo),'push',remote,branch],capture_output=True,text=True)
    if cp.returncode!=0: raise RuntimeError(f'guarded publication rejected (another writer won): {cp.stderr.strip()}; local commit stays unpublished: re-sync/replay, discard/recompose, never force-push')
    _hh=validate(tdir)['head']
    _tip=post_push_verify(repo,remote,branch,tdir,_hh['event_id'],_hh['integrity']['event_hash'])
    print(json.dumps({**out,'commit_message':msg,'published_head':_tip},indent=2))
def session_path(root): return Path(root)/'.awrp'/'session.json'
def session_exists(root): return session_path(root).exists()
def check_session_shape(o,path='session'):
    if not isinstance(o,dict): raise RuntimeError(f'invalid session state at {path}: not an object; bytes preserved, refusing to proceed')
    if o.get('protocol')!=PROTOCOL: raise RuntimeError(f'invalid session state at {path}: bad protocol; bytes preserved, refusing to proceed')
    attached=o.get('attached')
    if not isinstance(attached,list) or any(not isinstance(x,dict) or not isinstance(x.get('project_id'),str) for x in attached): raise RuntimeError(f'invalid session state at {path}: bad attached list; bytes preserved, refusing to proceed')
    cur=o.get('current')
    if not isinstance(cur,dict) or any(k not in cur or (cur[k] is not None and not isinstance(cur[k],str)) for k in ['project_id','task_id','run_id']): raise RuntimeError(f'invalid session state at {path}: bad current focus; bytes preserved, refusing to proceed')
    gen=o.get('generation',0)
    if not isinstance(gen,int) or gen<0: raise RuntimeError(f'invalid session state at {path}: bad generation; bytes preserved, refusing to proceed')
    return o
def read_session(root):
    p=session_path(root)
    if not p.exists(): raise RuntimeError(f'no session state at {p}; attach an exact project_id first, never infer one')
    try: o=readj(p)
    except Exception as e: raise RuntimeError(f'invalid session state at {p}: unreadable ({e}); bytes preserved, refusing to proceed')
    return check_session_shape(o,str(p))
def atomic_write_json(path,obj):
    import tempfile as _tf
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fd,nm=_tf.mkstemp(dir=str(path.parent),prefix='.tmp-')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as fh: fh.write(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
        os.replace(nm,str(path))
    except BaseException:
        try: os.unlink(nm)
        except OSError: pass
        raise
SESSION_LOCK_TTL=30
def session_lock_path(root): return Path(root)/'.awrp'/'session.lock.json'
def acquire_session_lock(root):
    lp=session_lock_path(root); lp.parent.mkdir(parents=True,exist_ok=True)
    token=uuid.uuid4().hex
    payload=json.dumps({'pid':os.getpid(),'time':now(),'token':token})
    try:
        fd=os.open(str(lp),os.O_CREAT|os.O_EXCL|os.O_WRONLY); os.write(fd,payload.encode()); os.close(fd); return token
    except FileExistsError: pass
    try: cur=json.loads(lp.read_text(encoding='utf-8'))
    except Exception: cur={}
    try: age=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(str(cur.get('time','')).replace('Z','+00:00'))).total_seconds()
    except Exception: age=None
    if age is not None and age<=SESSION_LOCK_TTL: raise RuntimeError(f'session is locked by a concurrent writer; refusing silent overwrite — retry the command (lock age {age:.1f}s)')
    lp.write_text(payload,encoding='utf-8')
    return token
def release_session_lock(root,token):
    try:
        cur=json.loads(session_lock_path(root).read_text(encoding='utf-8'))
        if cur.get('token')==token: session_lock_path(root).unlink()
    except OSError: pass
def relay_name_for(root,rd):
    bp=binding_path(root)
    if not bp.exists(): return None
    try: b=read_binding(root)
    except RuntimeError: return None
    if os.path.normcase(str(Path(b['relay_dir']).resolve()))==os.path.normcase(str(Path(rd).resolve())): return b.get('relay')
    return None
def pin_session_relay(root,s_or_none,rd,explicit_relay_dir):
    rd=str(Path(rd).resolve())
    if s_or_none is None: return (None,relay_name_for(root,rd))
    stored=(s_or_none.get('relay_dir') if isinstance(s_or_none,dict) else None)
    if not stored:
        if not explicit_relay_dir: raise RuntimeError('existing session has no pinned Relay (pre-identity format); pass an explicit --relay-dir once to pin it deliberately, never by workspace default')
        return (None,relay_name_for(root,rd))
    if os.path.normcase(stored)!=os.path.normcase(rd): raise RuntimeError(f'session is pinned to Relay dir {stored!r}; requested {rd!r} — refusing cross-Relay reinterpretation of the same project_id')
    nm=relay_name_for(root,rd)
    if s_or_none.get('relay') and nm and s_or_none['relay']!=nm: raise RuntimeError(f"session Relay identity {s_or_none['relay']!r} does not match workspace Relay {nm!r}; refusing cross-Relay reinterpretation")
    return (stored,s_or_none.get('relay') or nm)
def commit_session_locked(root,obj):
    obj=dict(obj); obj['generation']=int(obj.get('generation') or 0)+1
    atomic_write_json(session_path(root),obj)
    return obj
def stamp_relay_pin(s,pinned,nm):
    s['relay_dir']=pinned
    if nm and not s.get('relay'): s['relay']=nm
    return s
def session_relay_dir(root,relay_dir_arg):
    if relay_dir_arg: return str(Path(relay_dir_arg))
    bp=binding_path(root)
    if bp.exists(): return read_binding(root)['relay_dir']
    raise RuntimeError('no workspace binding and no --relay-dir; exact relay identity is required, never inferred')
def session_current(root):
    return read_session(root).get('current') or {}
def do_attach(a):
    rd=session_relay_dir(a.root,getattr(a,'relay_dir',None))
    read_project(rd,a.project_id)
    tok=acquire_session_lock(a.root)
    try:
        if session_exists(a.root):
            s=read_session(a.root)
            pinned,nm=pin_session_relay(a.root,s,rd,bool(getattr(a,'relay_dir',None)))
            stamp_relay_pin(s,pinned or str(Path(rd).resolve()),nm)
        else:
            _,nm=pin_session_relay(a.root,None,rd,bool(getattr(a,'relay_dir',None)))
            s={'protocol':PROTOCOL,'attached':[],'current':{'project_id':None,'task_id':None,'run_id':None}}
            s['relay_dir']=str(Path(rd).resolve())
            if nm: s['relay']=nm
        if not any(x.get('project_id')==a.project_id for x in s.get('attached',[])):
            s.setdefault('attached',[]).append({'project_id':a.project_id,'attached_at':now(),'by':getattr(a,'by',None) or 'session'})
        cur=s.get('current') or {}
        if not cur.get('project_id'):
            s['current']={'project_id':a.project_id,'task_id':None,'run_id':None,'updated_at':now()}
        s=commit_session_locked(a.root,s)
    finally: release_session_lock(a.root,tok)
    print(json.dumps({'attached':[x['project_id'] for x in s['attached']],'current':s['current'],'generation':s['generation']},indent=2))
def session_task_check(rd,pid,tid,run_id=None):
    tdir=Path(rd)/'tasks'/tid
    if not (tdir/'task.json').exists(): raise RuntimeError(f'switch target task {tid!r} is not in the relay; never infer an alternative')
    v=validate(tdir); t=v['task']
    if t.get('project_id'):
        if t['project_id']!=pid: raise RuntimeError(f"switch target task project is {t.get('project_id')!r}, not {pid!r}")
    else:
        require_migration(rd,pid,tid,t)
    active=v.get('active_run_id')
    if run_id is not None and run_id!=active: raise RuntimeError(f'switch target run is {active!r}, asked for {run_id!r}; switch only onto the authoritative active run')
    return v
def do_switch(a):
    rd=session_relay_dir(a.root,getattr(a,'relay_dir',None))
    read_project(rd,a.project_id)
    tid=getattr(a,'task_id',None); rid=getattr(a,'run_id',None)
    if rid is not None and tid is None: raise RuntimeError('switch --run-id requires --task-id')
    want_task=None; want_run=None
    if tid is not None:
        v=session_task_check(rd,a.project_id,tid,rid)
        active=v.get('active_run_id')
        if active is not None:
            try: check_freshness(rd)
            except RuntimeError as e: raise RuntimeError(f'stale Relay view: refusing to persist Task/Run execution context without proven freshness: {e}')
        want_task, want_run = tid, (rid or active)
    tok=acquire_session_lock(a.root)
    try:
        s=read_session(a.root)
        pinned,nm=pin_session_relay(a.root,s,rd,bool(getattr(a,'relay_dir',None)))
        stamp_relay_pin(s,pinned or str(Path(rd).resolve()),nm)
        if not any(x.get('project_id')==a.project_id for x in s.get('attached',[])): raise RuntimeError(f'project {a.project_id!r} is not attached to this session; attach first, never auto-attach on switch')
        if want_task is not None:
            s['current']={'project_id':a.project_id,'task_id':want_task,'run_id':want_run,'updated_at':now()}
        else:
            s['current']={'project_id':a.project_id,'task_id':None,'run_id':None,'updated_at':now()}
        s=commit_session_locked(a.root,s)
    finally: release_session_lock(a.root,tok)
    print(json.dumps({'current':s['current'],'generation':s['generation']},indent=2))
def do_focus(a):
    rd=session_relay_dir(a.root,getattr(a,'relay_dir',None))
    s=read_session(a.root)
    pin_session_relay(a.root,s,rd,bool(getattr(a,'relay_dir',None)))
    cur=s.get('current') or {}
    if not cur.get('project_id'):
        print(json.dumps({'status':'FOCUS_NONE','reason':'session has no current project; attach an exact project_id first, never infer one'},indent=2)); return
    read_project(rd,cur['project_id'])
    if not cur.get('task_id'):
        print(json.dumps({'status':'FOCUS_PROJECT','current':cur,'reason':'project focus only; switch --task-id for task focus'},indent=2)); return
    tdir=Path(rd)/'tasks'/cur['task_id']
    if not (tdir/'task.json').exists(): raise RuntimeError(f'focused task {cur["task_id"]!r} is not in the relay; re-resolve explicitly')
    v=validate(tdir)
    active=v.get('active_run_id'); h=v['head']
    if cur.get('run_id') and cur['run_id']!=active:
        print(json.dumps({'status':'FOCUS_STALE','current':cur,'active_run_id':active,'head_event_id':h['event_id'],'reason':'focused run is no longer authoritative; switch explicitly, never follow silently'},indent=2)); return
    if active and run_claimed(v['events'],active):
        print(json.dumps({'status':'FOCUS_OWNED','current':{**cur,'run_id':active},'reason':'focused run already ACKed without HANDOFF; do not redo material work'},indent=2)); return
    if not active:
        print(json.dumps({'status':'FOCUS_NONE','current':cur,'active_run_id':None,'reason':'focused task has no actionable run; do not ACK'},indent=2)); return
    try: check_freshness(rd)
    except RuntimeError as e:
        print(json.dumps({'status':'FOCUS_NOT_FRESH','current':{**cur,'run_id':active},'reason':f'cannot prove Relay freshness, refusing actionable verdict: {e}'},indent=2)); return
    _fch=(v['task'].get('routing') or {}).get('channel_id')
    try: _fa=fencing_authority(rd,_fch) if _fch else None
    except Exception as e: _fa={'channel_id':_fch,'status':'error','generation':None,'owner':None,'strict':False,'detail':f'fencing authority unreadable ({e})'}
    print(json.dumps({'status':'FOCUS_EXECUTE','current':{**cur,'run_id':active},'head_event_id':h['event_id'],'head_hash':h['integrity']['event_hash'],'fencing_authority':_fa,'reason':'focused run is actionable on a fresh Relay view; ACK with the reported expected head before material work'},indent=2))
def canonical_task_project(relay_dir,task_id,task):
    if task.get('project_id'): return (task['project_id'],False)
    found=None
    for pid in list_projects(relay_dir):
        if migration_path(relay_dir,pid,task_id).exists():
            if found is not None: raise RuntimeError(f'task {task_id!r} has migration associations in multiple projects ({found!r}, {pid!r}); ambiguous, fail closed')
            found=pid
    if found is None: return (None,False)
    require_migration(relay_dir,found,task_id,task)
    return (found,True)
def do_check_lineage(a):
    rd=session_relay_dir(a.root,getattr(a,'relay_dir',None))
    tdir=Path(rd)/'tasks'/a.task_id
    if not (tdir/'task.json').exists(): raise RuntimeError(f'lineage task {a.task_id!r} is not in the relay; cannot verify ghosts')
    v=validate(tdir)
    canon_proj,via_migration=canonical_task_project(rd,a.task_id,v['task'])
    actual={'project_id':canon_proj,'via_migration':via_migration,'task_id':a.task_id,'run_id':v.get('active_run_id')}
    try: s=read_session(a.root)
    except RuntimeError:
        print(json.dumps({'match':None,'lineage':{'project_id':a.project_id,'task_id':a.task_id,'run_id':a.run_id},'reason':'session has no focus; attach/switch first, never default-accept'},indent=2)); return
    pin_session_relay(a.root,s,rd,bool(getattr(a,'relay_dir',None)))
    cur=s.get('current') or {}
    want={'project_id':a.project_id,'task_id':a.task_id,'run_id':a.run_id}
    focus={'project_id':cur.get('project_id'),'task_id':cur.get('task_id'),'run_id':cur.get('run_id')}
    if canon_proj is None:
        print(json.dumps({'match':False,'focus':focus,'lineage':want,'canonical':actual,'reason':'no canonical project proof for this task (neither intrinsic id nor valid migration); refusing to bind lineage by agreement alone'},indent=2)); return
    if (want['project_id'],want['task_id'])!=(focus.get('project_id'),focus.get('task_id')):
        print(json.dumps({'match':False,'focus':focus,'lineage':want,'canonical':actual,'reason':'lineage route conflicts with current focus; fail closed or explicitly re-route against canonical Relay state, never reinterpret into the current project'},indent=2)); return
    known=set((v.get('runs') or {}))
    if want['project_id']!=canon_proj or (want['run_id'] is not None and want['run_id'] not in known):
        print(json.dumps({'match':False,'focus':focus,'lineage':want,'canonical':actual,'known_runs':sorted(known),'reason':'lineage agrees with focus but names an unknown project/run; completed historical runs are known (see known_runs), ghosts are not'},indent=2)); return
    historical=want['run_id'] is not None and want['run_id']!=actual['run_id']
    print(json.dumps({'match':True,'focus':focus,'canonical':actual,'historical':historical,'reason':'lineage equals current focus and names a canonical run (historical when it is not the active run); attribution only, never execution authority'},indent=2))
def do_probe_project(a):
    projs=[]
    for pid in list_projects(a.root):
        try: o=read_project(a.root,pid)
        except RuntimeError: continue
        projs.append({'project_id':pid,'title':o.get('title'),'channels':o.get('channels') or []})
    if not projs:
        print(json.dumps({'status':'PROJECT_BIND_REQUIRED','projects':[],'reason':'no projects registered in this relay view; exact project identity cannot be proven, nothing selected'},indent=2)); return
    print(json.dumps({'status':'AMBIGUOUS','projects':projs,'reason':'exact project identity must be proven by the coordinator instruction (relay/project/channel/endpoint/exact task); this probe never selects, even with a single project/route'},indent=2))
def do_render_bootstrap(a):
    tdir=Path(a.root)/'tasks'/a.task_id
    if not (tdir/'task.json').exists(): raise RuntimeError(f'exact target {a.task_id!r} is not in the relay; the renderer never scans for a likely project')
    read_project(a.root,a.project_id)
    v=validate(tdir); t=v['task']; h=v['head']; p=h['task_projection']
    if t.get('project_id'):
        if t['project_id']!=a.project_id: raise RuntimeError(f"target task project is {t.get('project_id')!r}, not {a.project_id!r}")
        ch0=(t.get('routing') or {}).get('channel_id')
        owner=channel_project(a.root,ch0) if ch0 else None
        if owner is not None and owner!=a.project_id: raise RuntimeError(f'task channel {ch0!r} is owned by {owner!r}, not {a.project_id!r}')
    else:
        require_migration(a.root,a.project_id,a.task_id,t)
    ch,lane,ep=task_routing(t)
    if not ch or not ep: raise RuntimeError('target task has no exact channel/endpoint route; refusing to render')
    active=v.get('active_run_id')
    if p['state'] in TERMINAL or not active: raise RuntimeError('exact target has no authoritative run to render')
    ds=[e for e in v['events'] if e['type']=='DISPATCH' and e.get('run_id')==active]
    if not ds or (ds[0].get('recipient') or {}).get('role')!='worker': raise RuntimeError('authoritative run recipient is not a worker; refusing to render')
    if a.run_id and a.run_id!=active: raise RuntimeError(f'render run mismatch: authoritative run is {active!r}, asked for {a.run_id!r}')
    relay=(t.get('transport') or {}).get('relay_repo')
    if not relay: raise RuntimeError('target task carries no canonical relay identity; refusing to render')
    lane_flag=f' --lane {lane}' if lane else ''
    cmd=f'python tools/awrp.py first-bind --root <workspace> --relay {relay} --project-id {a.project_id} --channel {ch} --worker-endpoint {ep}{lane_flag} --task-id {t["task_id"]} --run-id {active}'
    print(json.dumps({'relay':relay,'project_id':a.project_id,'channel_id':ch,'lane_id':lane,'worker_endpoint':ep,'task_id':t['task_id'],'run_id':active,'head_event_id':h['event_id'],'head_hash':h['integrity']['event_hash'],'command':cmd},indent=2))
def task_root_of(td):
    td=Path(td)
    return td.parent.parent if td.parent.name=='tasks' else None
def check_task_project(td,task):
    pid=task.get('project_id')
    if not pid: return None
    root=task_root_of(td)
    if root is None: raise RuntimeError('project-scoped task outside a tasks/ tree; cannot resolve project registry')
    read_project(root,pid)
    ch=(task.get('routing') or {}).get('channel_id')
    if ch:
        owner=channel_project(root,ch)
        if owner!=pid: raise RuntimeError(f"task project {pid!r} does not own channel {ch!r} (owned by {owner!r}); create with a matching --project-id")
    return pid
def audit_append_only(repo,task_id,ref='origin/main'):
    td=Path(repo)/'tasks'/task_id
    cp=subprocess.run(['git','-C',str(repo),'diff','--name-status','-M',ref,'--',f'tasks/{task_id}/events'],capture_output=True,text=True)
    if cp.returncode!=0: raise RuntimeError(f"git diff failed: {cp.stderr.strip()}")
    violations=[]
    for line in cp.stdout.splitlines():
        parts=line.split('\t'); st=parts[0]
        if st.startswith('R'): violations.append({'type':'renamed','from':parts[1],'to':parts[2]})
        elif st in ('M','D','T','C'): violations.append({'type':{'M':'modified','D':'deleted','T':'typechange','C':'copied'}[st],'path':parts[1]})
    try: validate(td)
    except Exception as e: violations.append({'type':'chain_invalid','error':str(e)})
    return {'ok':not violations,'task_id':task_id,'ref':ref,'violations':violations}
def do_audit_history(a):
    print(json.dumps(audit_append_only(a.repo,a.task_id,a.ref),indent=2))
COORD_MUTATION_TYPES={'DISPATCH','RECONCILE','REVIEW','APPROVAL','CANCEL'}
def audit_fencing(task_dir):
    td=Path(task_dir); v=validate(td)
    t=v['task']; ch,_,_=task_routing(t)
    root=td.parent.parent if td.parent.name=='tasks' else None
    auth=fencing_authority(root,ch) if (ch and root is not None) else None
    view=claim_history_view(root,ch) if (ch and root is not None) else {'entries':[],'problems':[]}
    log=view['entries']
    if not ch or (auth is not None and auth['status']=='unclaimed'):
        return {'ok':True,'task_id':t['task_id'],'fenced':False,'reason':'no channel claim history; legacy/compat path','authority':auth,'violations':[],'pre_claim':[]}
    if auth is not None and auth['status']=='legacy-claim':
        fenced_evs=[e for e in v['events'] if e['type'] in COORD_MUTATION_TYPES and (e.get('fencing') or {}).get('generation') is not None]
        if not fenced_evs:
            return {'ok':True,'task_id':t['task_id'],'fenced':False,'reason':'claim.json without history on a project-less channel and no fenced events; readability preserved, migrate-claim required before any new fenced write','authority':auth,'violations':[],'pre_claim':[]}
        return {'ok':False,'task_id':t['task_id'],'fenced':True,'channel_id':ch,'claim_generation':auth.get('generation'),'claim_owner':auth.get('owner'),'authority':auth,'history_problems':view['problems'],'violations':[{'type':'unfenced_or_mismatch','event_id':e['event_id'],'seq':e['seq'],'event_type':e['type'],'fencing':e.get('fencing')} for e in fenced_evs],'pre_claim':[]}
    if auth is not None and auth['status']=='inconsistent':
        return {'ok':False,'task_id':t['task_id'],'fenced':True,'channel_id':ch,'claim_generation':auth.get('generation'),'claim_owner':auth.get('owner'),'authority':auth,'history_problems':view['problems'],'violations':[{'type':'orphaned_authority','channel_id':ch,'generation':auth.get('generation'),'owner':auth.get('owner'),'detail':auth.get('detail')}],'pre_claim':[]}
    by_gen={e['generation']:e.get('owner') for e in log}
    regime_start=min((e.get('updated_at') or '') for e in log)
    violations=[]; pre=[]
    for e in v['events']:
        if e['type'] not in COORD_MUTATION_TYPES: continue
        if (e.get('created_at') or '')<regime_start:
            pre.append(e['event_id']); continue
        f=e.get('fencing') or {}
        g=f.get('generation')
        if not isinstance(g,int) or by_gen.get(g)!=f.get('owner'):
            violations.append({'type':'unfenced_or_mismatch','event_id':e['event_id'],'seq':e['seq'],'event_type':e['type'],'fencing':f or None})
        elif (e.get('actor') or {}).get('role')!='coordinator' or (e.get('actor') or {}).get('id')!=f.get('owner'):
            violations.append({'type':'authority_mismatch','event_id':e['event_id'],'seq':e['seq'],'event_type':e['type'],'fencing':f or None,'actor':e.get('actor')})
    cur=read_claim(root,ch)
    return {'ok':not violations,'task_id':t['task_id'],'fenced':True,'channel_id':ch,'claim_generation':cur.get('generation') if cur else None,'claim_owner':cur.get('owner') if cur else None,'authority':auth,'violations':violations,'pre_claim':pre}
def do_audit_fencing(a):
    print(json.dumps(audit_fencing(a.task_dir),indent=2))
def audit_dispatch_identity(root,task_id=None):
    """Fleet/task audit of DISPATCH routing/recipient identity (read-only).

    Reports every canonical DISPATCH as consistent / legacy_compat /
    mismatch without touching validation or selection semantics: historical
    malformed chains keep validating (byte authority is separate), but they
    read as inconsistent here instead of healthy.
    """
    root=Path(root)
    if task_id:
        tids=[task_id]
    else:
        tdir=root/'tasks'
        tids=sorted(p.name for p in tdir.iterdir() if (p/'task.json').exists()) if tdir.exists() else []
    out=[]
    for tid in tids:
        try:
            v=validate(root/'tasks'/tid)
        except Exception as e:
            out.append({'task_id':tid,'ok':False,'error':str(e)}); continue
        out.append({'task_id':tid,'ok':True,'dispatches':[
            {'run_id':e.get('run_id'),'event_id':e['event_id'],'seq':e['seq'],
             'identity':dispatch_identity(v['task'],e)}
            for e in v['events'] if e['type']=='DISPATCH']})
    return {'root':str(root),'tasks':out}
def do_audit_dispatch_identity(a):
    print(json.dumps(audit_dispatch_identity(a.root,getattr(a,'task_id',None)),indent=2))
# ---- AWRP Incident Registry (thin, additive) ----
# Operational learning/audit for confirmed AWRP-system incidents. This is NOT
# Task/Run execution authority: incident records grant no execution right,
# carry no fencing, and never gate worker selection. One incident identity
# (incidents/<id>/incident.json, immutable discovery) plus create-only
# append-only update events (incidents/<id>/events/) plus derived projections
# (INCIDENT.md per incident, INDEX.md registry-wide). Parallel writers are
# safe by construction: each incident is an independent directory, creation
# is create-only, updates are append-only, and shared projections
# (INDEX.md) converge through the same CAS/retry publication as tasks.
INCIDENT_ID_RE=None
def _incident_id_re():
    global INCIDENT_ID_RE
    if INCIDENT_ID_RE is None:
        import re as _re7
        INCIDENT_ID_RE=_re7.compile(r'^inc_[A-Za-z0-9][A-Za-z0-9_-]*$')
    return INCIDENT_ID_RE
INCIDENT_SEVERITIES={'critical','high','medium','low'}
INCIDENT_CATEGORIES={'protocol','governance','routing','fencing','transport','recovery','host-integration','bridge','docs','other'}
INCIDENT_REPORTER_ROLES={'coordinator','worker','human'}
INCIDENT_STATUSES={'open','mitigated','resolved','duplicate','accepted_risk'}
INCIDENT_TRANSITIONS={'open':{'mitigated','resolved','duplicate','accepted_risk'},'mitigated':{'resolved','open'},'resolved':{'open'},'duplicate':set(),'accepted_risk':{'open'}}
INCIDENT_REF_KEYS={'project_id','channel_id','task_id','run_id','request_id','commit','event_id'}
INCIDENT_CREATE_KEYS={'incident_id','title','summary','severity','category','reporter_role','reporter_id','reporter_surface','symptom','impact','evidence','detected_at','refs','violated_invariant','expected_behavior','containment','remediation','related_incidents','note','idempotency_key'}
INCIDENT_UPDATE_KEYS={'status','note','evidence_add','remediation','root_cause','resolution_evidence','related_add','duplicate_of','reporter_role','reporter_id','idempotency_key'}
INCIDENT_UPDATE_CONTENT_KEYS={'note','evidence_add','remediation','root_cause','resolution_evidence','related_add','duplicate_of'}
def incident_dir(root,iid): return Path(root)/'incidents'/iid
def _incident_check_id(iid):
    if not iid or not _incident_id_re().match(iid): raise RuntimeError(f'invalid incident_id {iid!r}; use ^inc_[A-Za-z0-9][A-Za-z0-9_-]*$ (names only — hashes are composed, never hand-authored)')
    return iid
def _incident_check_iso8601(s,what):
    import datetime as _dt
    if not isinstance(s,str) or not s: raise RuntimeError(f'incident {what} must be a non-empty UTC ISO-8601 timestamp')
    try: _dt.datetime.fromisoformat(s.replace('Z','+00:00'))
    except Exception: raise RuntimeError(f'incident {what} {s!r} is not valid ISO-8601')
    if not s.endswith('Z'): raise RuntimeError(f'incident {what} {s!r} must be UTC (trailing Z)')
    return s
def _incident_nonempty(v,what):
    if not isinstance(v,str) or not v.strip(): raise RuntimeError(f'incident {what} must be a non-empty string (canonical creation requires concrete evidence, never speculation)')
    return v
def _incident_discovery_subset(o):
    return {k:o.get(k) for k in sorted(o) if k!='discovery_hash'}
def incident_discovery_hash(o):
    return 'sha256:'+hashlib.sha256(json.dumps(_incident_discovery_subset(o),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
def incident_load_updates(idir):
    rows=[]
    evd=Path(idir)/'events'
    if evd.exists():
        for p in sorted(evd.glob('*.json')):
            try: rows.append((p,readj(p)))
            except Exception as e: raise RuntimeError(f'{p}: unreadable incident update ({e})')
    return rows
def incident_validate(idir):
    """Strict validation of one incident directory (read-only).

    Checks envelope, discovery-hash recomputation (discovery is immutable),
    seq continuity, prev-link chain from the discovery record, per-event hash
    recomputation, legal status transitions, and link-target existence
    (related/duplicate links must resolve — no dangling references).
    Returns {'incident','updates','head_status','head_seq','head_event_id',
    'resolved_at','update_count'}.
    """
    idir=Path(idir); ip=idir/'incident.json'
    if not ip.exists(): raise RuntimeError(f'{idir}: no incident.json; incidents are created with incident-create, never inferred')
    t=readj(ip)
    if t.get('protocol')!=PROTOCOL or t.get('kind')!='incident': raise RuntimeError(f'{ip}: bad protocol/kind envelope')
    if t.get('incident_id')!=idir.name: raise RuntimeError(f'{ip}: incident_id does not match directory name')
    unknown=set(t)-{'protocol','kind','incident_id','title','summary','severity','category','reporter','detected_at','recorded_at','status','symptom','impact','evidence','refs','violated_invariant','expected_behavior','containment','remediation','related_incidents','duplicate_of','note','idempotency_key','discovery_hash'}
    if unknown: raise RuntimeError(f'{ip}: unknown discovery keys {sorted(unknown)}; schema is strict, extend deliberately')
    if incident_discovery_hash(t)!=t.get('discovery_hash'): raise RuntimeError(f'{ip}: discovery record was rewritten (hash mismatch); discovery is immutable — append an update instead')
    rows=incident_load_updates(idir)
    prev_id=f"incident:{t['incident_id']}:discovery"; prev_hash=t['discovery_hash']; prev_state='open'
    if t.get('status')!='open' and not (t.get('status')=='duplicate' and t.get('duplicate_of')): raise RuntimeError(f'{ip}: initial status must be open (or duplicate with duplicate_of)')
    cur=t.get('status'); resolved_at=None
    if cur not in INCIDENT_STATUSES: raise RuntimeError(f'{ip}: bad initial status {cur!r}')
    if cur=='duplicate' and not t.get('duplicate_of'): raise RuntimeError(f'{ip}: duplicate requires duplicate_of')
    seqs=set()
    for expected,(p,e) in enumerate(rows,1):
        for k in ['protocol','kind','event_id','seq','incident_id','created_at','actor','integrity']:
            if k not in e: raise RuntimeError(f'{p}: missing {k}')
        if e['protocol']!=PROTOCOL or e.get('kind')!='incident-update': raise RuntimeError(f'{p}: bad protocol/kind')
        unknown_e=set(e)-{'protocol','kind','event_id','seq','incident_id','created_at','actor','reporter','status','prev_status','note','evidence_add','remediation','root_cause','resolution_evidence','related_add','duplicate_of','idempotency_key','integrity'}
        if unknown_e: raise RuntimeError(f'{p}: unknown update keys {sorted(unknown_e)}; updates carry status/content/links only, never discovery fields')
        if e['seq']!=expected or e['seq'] in seqs: raise RuntimeError(f'{p}: sequence gap/duplicate')
        seqs.add(e['seq'])
        if e['incident_id']!=t['incident_id']: raise RuntimeError(f'{p}: incident mismatch')
        integ=e['integrity']
        if integ.get('prev_event_id')!=prev_id or integ.get('prev_event_hash')!=prev_hash: raise RuntimeError(f'{p}: chain link mismatch')
        actual=eh(e)
        if integ.get('event_hash')!=actual: raise RuntimeError(f'{p}: event hash mismatch')
        for f in ('note','evidence_add','remediation','root_cause','resolution_evidence'):
            if f in e and e[f] is not None and (not isinstance(e[f],str) or not e[f].strip()): raise RuntimeError(f'{p}: {f} must be a non-empty string when present')
        ns=e.get('status',cur)
        if ns not in INCIDENT_STATUSES: raise RuntimeError(f'{p}: bad status {ns!r}')
        if ns!=cur and ns not in INCIDENT_TRANSITIONS.get(cur,set()): raise RuntimeError(f'{p}: illegal status transition {cur}->{ns}')
        if ns!=cur and ns=='duplicate' and not e.get('duplicate_of'): raise RuntimeError(f'{p}: duplicate requires duplicate_of')
        if ns=='accepted_risk' and not (e.get('remediation') or e.get('note')): raise RuntimeError(f'{p}: accepted_risk requires a rationale (remediation or note)')
        for link in (e.get('related_add') or []):
            if not (incident_dir(idir.parent.parent,link)/'incident.json').exists(): raise RuntimeError(f'{p}: related link to unknown incident {link!r}')
        if e.get('duplicate_of') and not (incident_dir(idir.parent.parent,e['duplicate_of'])/'incident.json').exists(): raise RuntimeError(f'{p}: duplicate_of unknown incident {e["duplicate_of"]!r}')
        nofloats(e)
        if ns!=cur and ns=='resolved': resolved_at=e['created_at']
        cur=ns; prev_id=e['event_id']; prev_hash=integ['event_hash']
    for link in (t.get('related_incidents') or []):
        if not (idir.parent/link/'incident.json').exists(): raise RuntimeError(f'{ip}: related link to unknown incident {link!r}')
    if t.get('duplicate_of') and not (idir.parent/t['duplicate_of']/'incident.json').exists(): raise RuntimeError(f'{ip}: duplicate_of unknown incident')
    return {'incident':t,'updates':[e for _,e in rows],'head_status':cur,'head_seq':len(rows),'head_event_id':prev_id if not rows else rows[-1][1]['event_id'],'resolved_at':resolved_at if cur=='resolved' else None,'update_count':len(rows)}
def _incident_check_reporter(role,rid):
    if role not in INCIDENT_REPORTER_ROLES: raise RuntimeError(f'reporter_role must be one of {sorted(INCIDENT_REPORTER_ROLES)}, got {role!r}')
    if not isinstance(rid,str) or not rid.strip(): raise RuntimeError('reporter_id must be a non-empty string')
def _incident_check_refs(refs):
    if refs is None: return {}
    if not isinstance(refs,dict): raise RuntimeError('refs must be an object')
    unknown=set(refs)-INCIDENT_REF_KEYS
    if unknown: raise RuntimeError(f'refs carries unknown keys {sorted(unknown)}; allowed: {sorted(INCIDENT_REF_KEYS)}')
    for k,v in refs.items():
        if not isinstance(v,str) or not v.strip(): raise RuntimeError(f'refs[{k}] must be a non-empty string')
    return dict(refs)
def _incident_check_links(root,links):
    out=[]
    for link in links or []:
        _incident_check_id(link)
        if not (incident_dir(root,link)/'incident.json').exists(): raise RuntimeError(f'related link to unknown incident {link!r}; create the target first, never link ghosts')
        out.append(link)
    return out
def _compose_incident_create(root,incident_id,title,summary,severity,category,reporter_role,reporter_id,symptom,impact,evidence,detected_at=None,refs=None,violated_invariant=None,expected_behavior=None,containment=None,remediation=None,related_incidents=None,note=None,idempotency_key=None,reporter_surface=None):
    """Pure incident discovery composer: no writes.

    All validation, hashes, and timestamps-of-record are composed here —
    callers (CLI, bridge) never hand-author canonical bytes. Shared by every
    publication path so preflight and execution cannot diverge.
    """
    root=Path(root); _incident_check_id(incident_id)
    if severity not in INCIDENT_SEVERITIES: raise RuntimeError(f'severity must be one of {sorted(INCIDENT_SEVERITIES)}, got {severity!r}')
    if category not in INCIDENT_CATEGORIES: raise RuntimeError(f'category must be one of {sorted(INCIDENT_CATEGORIES)}, got {category!r}')
    _incident_check_reporter(reporter_role,reporter_id)
    if reporter_surface is not None and (not isinstance(reporter_surface,str) or not reporter_surface.strip()): raise RuntimeError('reporter_surface must be a non-empty string when present')
    for name,val in [('title',title),('summary',summary),('symptom',symptom),('impact',impact),('evidence',evidence)]:
        _incident_nonempty(val,name)
    if detected_at is None: detected_at=now()
    else: _incident_check_iso8601(detected_at,'detected_at')
    for name,val in [('violated_invariant',violated_invariant),('expected_behavior',expected_behavior),('containment',containment),('remediation',remediation),('note',note)]:
        if val is not None and (not isinstance(val,str) or not val.strip()): raise RuntimeError(f'{name} must be a non-empty string when present')
    obj={'protocol':PROTOCOL,'kind':'incident','incident_id':incident_id,'title':title.strip(),'summary':summary.strip(),'severity':severity,'category':category,'reporter':{'role':reporter_role,'id':reporter_id.strip(),'surface':reporter_surface.strip() if reporter_surface else None},'detected_at':detected_at,'recorded_at':now(),'status':'open','symptom':symptom.strip(),'impact':impact.strip(),'evidence':evidence.strip(),'refs':_incident_check_refs(refs),'violated_invariant':violated_invariant.strip() if violated_invariant else None,'expected_behavior':expected_behavior.strip() if expected_behavior else None,'containment':containment.strip() if containment else None,'remediation':remediation.strip() if remediation else None,'related_incidents':_incident_check_links(root,related_incidents or []),'duplicate_of':None,'note':note.strip() if note else None,'idempotency_key':idempotency_key}
    obj['discovery_hash']=incident_discovery_hash(obj)
    nofloats(obj)
    return obj
def incident_create(root,incident_id,title,summary,severity,category,reporter_role,reporter_id,symptom,impact,evidence,detected_at=None,refs=None,violated_invariant=None,expected_behavior=None,containment=None,remediation=None,related_incidents=None,note=None,idempotency_key=None,reporter_surface=None):
    """Compose + write one incident (worker/CLI path)."""
    root=Path(root)
    obj=_compose_incident_create(root,incident_id,title,summary,severity,category,reporter_role,reporter_id,symptom,impact,evidence,detected_at,refs,violated_invariant,expected_behavior,containment,remediation,related_incidents,note,idempotency_key,reporter_surface=reporter_surface)
    idir=incident_dir(root,incident_id); (idir/'events').mkdir(parents=True,exist_ok=True)
    write_new(idir/'incident.json',obj)
    try:
        v=incident_validate(idir)
    except BaseException:
        try: (idir/'incident.json').unlink()
        except OSError: pass
        raise
    incident_render_projections(root,incident_id,v)
    return obj
def _compose_incident_update(root,incident_id,actor_role,actor_id,v,status=None,note=None,evidence_add=None,remediation=None,root_cause=None,resolution_evidence=None,related_add=None,duplicate_of=None,reporter_role=None,reporter_id=None,idempotency_key=None):
    """Pure incident update composer: no writes. Shared by CLI and bridge."""
    root=Path(root); cur=v['head_status']
    if status is not None:
        if status not in INCIDENT_STATUSES: raise RuntimeError(f'bad status {status!r}')
        if status!=cur and status not in INCIDENT_TRANSITIONS.get(cur,set()): raise RuntimeError(f'illegal status transition {cur}->{status}')
    else: status=cur
    content={'note':note,'evidence_add':evidence_add,'remediation':remediation,'root_cause':root_cause,'resolution_evidence':resolution_evidence}
    for k,val in content.items():
        if val is not None and (not isinstance(val,str) or not val.strip()): raise RuntimeError(f'{k} must be a non-empty string when present')
    if duplicate_of is not None: _incident_check_id(duplicate_of)
    if status!=cur and status=='duplicate' and not duplicate_of: raise RuntimeError('duplicate requires duplicate_of')
    if status!=cur and status=='accepted_risk' and not (remediation or note): raise RuntimeError('accepted_risk requires a rationale (remediation or note)')
    related=_incident_check_links(root,related_add or [])
    if reporter_role is not None or reporter_id is not None:
        _incident_check_reporter(reporter_role,reporter_id)
    if not any([note,evidence_add,remediation,root_cause,resolution_evidence,related,duplicate_of,status!=cur]):
        raise RuntimeError('empty update refused: carry a note, evidence, remediation, root cause, link, or status change — never append noise')
    head_updates=v['updates']
    if head_updates and idempotency_key and head_updates[-1].get('idempotency_key')==idempotency_key:
        raise RuntimeError(f'duplicate update: idempotency_key {idempotency_key!r} already recorded as {head_updates[-1]["event_id"]}; fetch that outcome instead of resubmitting')
    if head_updates:
        prev_id=head_updates[-1]['event_id']; prev_hash=head_updates[-1]['integrity']['event_hash']
    else:
        prev_id=f"incident:{incident_id}:discovery"; prev_hash=v['incident']['discovery_hash']
    e={'protocol':PROTOCOL,'kind':'incident-update','event_id':newid('incevt'),'seq':len(head_updates)+1,'incident_id':incident_id,'created_at':now(),'actor':{'role':actor_role.strip(),'id':actor_id.strip()},'reporter':({'role':reporter_role,'id':reporter_id.strip()} if reporter_role else None),'status':status,'prev_status':cur,'note':note.strip() if note else None,'evidence_add':evidence_add.strip() if evidence_add else None,'remediation':remediation.strip() if remediation else None,'root_cause':root_cause.strip() if root_cause else None,'resolution_evidence':resolution_evidence.strip() if resolution_evidence else None,'related_add':related,'duplicate_of':duplicate_of,'idempotency_key':idempotency_key,'integrity':{'prev_event_id':prev_id,'prev_event_hash':prev_hash,'event_hash':''}}
    nofloats(e)
    e['integrity']['event_hash']=eh(e)
    return e
def incident_update(root,incident_id,actor_role,actor_id,status=None,note=None,evidence_add=None,remediation=None,root_cause=None,resolution_evidence=None,related_add=None,duplicate_of=None,reporter_role=None,reporter_id=None,idempotency_key=None):
    """Append one update event (worker/CLI path)."""
    root=Path(root); _incident_check_id(incident_id)
    idir=incident_dir(root,incident_id)
    if not (idir/'incident.json').exists(): raise RuntimeError(f'incident {incident_id!r} is not in the registry; create it first, never update ghosts')
    if not isinstance(actor_role,str) or not actor_role.strip() or not isinstance(actor_id,str) or not actor_id.strip(): raise RuntimeError('update requires an explicit actor_role/actor_id; unattributed updates are refused')
    v=incident_validate(idir)
    e=_compose_incident_update(root,incident_id,actor_role,actor_id,v,status,note,evidence_add,remediation,root_cause,resolution_evidence,related_add,duplicate_of,reporter_role,reporter_id,idempotency_key)
    p=idir/'events'/f"{e['seq']:06d}_{e['event_id']}.json"
    write_new(p,e)
    try:
        v2=incident_validate(idir)
    except BaseException:
        try: p.unlink()
        except OSError: pass
        raise
    incident_render_projections(root,incident_id,v2)
    return e
def incident_render_text(incident,updates,head_status,resolved_at):
    r=incident.get('reporter') or {}
    refs=incident.get('refs') or {}
    lines=[f"# [Incident] {incident['title']}",'',f"- **ID:** `{incident['incident_id']}`",f"- **Status:** `{head_status}`",f"- **Severity:** `{incident['severity']}`",f"- **Category:** `{incident['category']}`",f"- **Reporter:** `{r.get('role')}/{r.get('id')}`"+(f" via {r.get('surface')}" if r.get('surface') else ''),f"- **Detected:** `{incident['detected_at']}`",f"- **Recorded:** `{incident['recorded_at']}`"]
    if resolved_at: lines.append(f"- **Resolved:** `{resolved_at}`")
    if incident.get('duplicate_of'): lines.append(f"- **Duplicate of:** `{incident['duplicate_of']}`")
    if incident.get('related_incidents'): lines.append(f"- **Related:** `{', '.join(incident['related_incidents'])}`")
    if refs: lines.append(f"- **Refs:** `{json.dumps(refs,ensure_ascii=False,sort_keys=True)}`")
    lines+=['','## Summary','',incident['summary'],'','## Symptom','',incident['symptom'],'','## Impact','',incident['impact'],'','## Evidence','',incident['evidence']]
    if incident.get('violated_invariant'): lines+=['','## Violated invariant','',incident['violated_invariant']]
    if incident.get('expected_behavior'): lines+=['','## Expected behavior','',incident['expected_behavior']]
    if incident.get('containment'): lines+=['','## Containment','',incident['containment']]
    if incident.get('remediation'): lines+=['','## Remediation','',incident['remediation']]
    if incident.get('note'): lines+=['','## Discovery note','',incident['note']]
    if updates:
        lines+=['','## Updates (append-only, newest last)','']
        for u in updates:
            a=u.get('actor') or {}
            lines.append(f"### seq{u['seq']} `{u['event_id']}` — {u.get('status')} ({a.get('role')}/{a.get('id')}, {u.get('created_at')})")
            for f in ('note','evidence_add','remediation','root_cause','resolution_evidence'):
                if u.get(f): lines+=['',f'**{f}:** {u[f]}']
            if u.get('related_add'): lines+=['',f"**related_add:** `{', '.join(u['related_add'])}`"]
            if u.get('duplicate_of'): lines+=['',f"**duplicate_of:** `{u['duplicate_of']}`"]
            lines.append('')
    lines+=['','> Discovery record is immutable. This file is a derived projection; canonical state is incident.json + events/ (verified by incident-audit).','']
    return '\n'.join(lines)
def incident_render_index(root,entries):
    lines=['# AWRP Incident Registry Index','','> Derived projection. Canonical state is incidents/<id>/incident.json + events/. Rebuild with incident-rebuild.','',f"- **Incidents:** `{len(entries)}`",'',"| ID | Status | Severity | Category | Title | Updates | Head |",'|---|---|---|---|---|---|---|']
    for en in sorted(entries,key=lambda x:x['incident_id']):
        lines.append(f"| `{en['incident_id']}` | `{en['status']}` | `{en['severity']}` | `{en['category']}` | {en['title']} | `{en['updates']}` | `{en['head_event_id']}` |")
    return '\n'.join(lines)+'\n'
def _incident_index_entries(root,overlay=None):
    """Validated per-incident index rows; overlay replaces/adds one row.

    Used both for on-disk projection renders and for pure bridge plans
    (where the new/updated incident is not on disk yet). Invalid chains are
    skipped here — incident-audit (not the index) is where they surface.
    """
    root=Path(root); entries=[]
    inc_root=root/'incidents'
    if inc_root.exists():
        for sub in sorted(inc_root.iterdir()):
            if not sub.is_dir() or not (sub/'incident.json').exists(): continue
            try: vv=incident_validate(sub)
            except Exception: continue
            tt=vv['incident']
            entries.append({'incident_id':tt['incident_id'],'status':vv['head_status'],'severity':tt['severity'],'category':tt['category'],'title':tt['title'],'updates':vv['update_count'],'head_event_id':vv['head_event_id']})
    if overlay is not None:
        entries=[e for e in entries if e['incident_id']!=overlay['incident_id']]+[overlay]
    return entries
def incident_render_projections(root,iid,v=None):
    root=Path(root); idir=incident_dir(root,iid)
    v=v or incident_validate(idir)
    t=v['incident']
    (idir/'INCIDENT.md').write_text(incident_render_text(t,v['updates'],v['head_status'],v['resolved_at']),encoding='utf-8')
    (root/'incidents'/'INDEX.md').write_text(incident_render_index(root,_incident_index_entries(root)),encoding='utf-8')
    return {'incident_id':iid,'status':v['head_status']}
def _plan_incident(root,action,p,idempotency_key):
    """Pure incident compose pass for the bridge: no writes, no commit.

    The bridge is coordinator transport: reporter_role must be coordinator
    and the update actor is coordinator/reporter_id (derived, never
    supplied). Returns a plan shaped for _materialize_incident_files plus
    (incident_id, event_id-or-None, event_hash-or-discovery_hash).
    """
    root=Path(root)
    if action=='incident-create':
        if p.get('reporter_role','coordinator')!='coordinator':
            raise RuntimeError(f"bridge incident-create is coordinator transport; reporter_role must be 'coordinator', got {p.get('reporter_role')!r} (workers use incident-create CLI directly)")
        if not p.get('reporter_id'): raise RuntimeError('bridge incident-create requires reporter_id')
        obj=_compose_incident_create(root,p['incident_id'],p['title'],p['summary'],p['severity'],p['category'],p.get('reporter_role') or 'coordinator',p['reporter_id'],p['symptom'],p['impact'],p['evidence'],p.get('detected_at'),p.get('refs'),p.get('violated_invariant'),p.get('expected_behavior'),p.get('containment'),p.get('remediation'),p.get('related_incidents'),p.get('note'),idempotency_key,reporter_surface=p.get('reporter_surface'))
        itext=json.dumps(obj,ensure_ascii=False,indent=2)+'\n'
        overlay={'incident_id':obj['incident_id'],'status':'open','severity':obj['severity'],'category':obj['category'],'title':obj['title'],'updates':0,'head_event_id':f"incident:{obj['incident_id']}:discovery"}
        plan={'incident':True,'incident_id':obj['incident_id'],'event_id':None,'event_hash':obj['discovery_hash'],'immutable':[(f"incidents/{obj['incident_id']}/incident.json",itext)],'mutable':[(f"incidents/{obj['incident_id']}/INCIDENT.md",incident_render_text(obj,[],'open',None)),('incidents/INDEX.md',incident_render_index(root,_incident_index_entries(root,overlay)))]}
        return (plan,obj['incident_id'],None,obj['discovery_hash'])
    if action=='incident-update':
        iid=p['incident_id']; _incident_check_id(iid)
        idir=incident_dir(root,iid)
        if not (idir/'incident.json').exists(): raise RuntimeError(f'incident {iid!r} is not in the registry; create it first, never update ghosts')
        if p.get('reporter_role','coordinator')!='coordinator': raise RuntimeError(f"bridge incident-update is coordinator transport; reporter_role must be 'coordinator', got {p.get('reporter_role')!r}")
        if not p.get('reporter_id'): raise RuntimeError('bridge incident-update requires reporter_id (actor is derived as coordinator/reporter_id, never supplied)')
        v=incident_validate(idir)
        e=_compose_incident_update(root,iid,'coordinator',p['reporter_id'],v,p.get('status'),p.get('note'),p.get('evidence_add'),p.get('remediation'),p.get('root_cause'),p.get('resolution_evidence'),p.get('related_add'),p.get('duplicate_of'),p.get('reporter_role') or 'coordinator',p.get('reporter_id'),idempotency_key)
        etext=json.dumps(e,ensure_ascii=False,indent=2)+'\n'
        if eh(json.loads(etext))!=e['integrity']['event_hash']: raise RuntimeError('composed incident event bytes do not match the composer hash; refusing to materialize')
        nu=v['updates']+[e]
        nstatus=e['status']
        nresolved=e['created_at'] if (nstatus=='resolved') else (v['resolved_at'] if nstatus=='resolved' else None)
        overlay={'incident_id':iid,'status':nstatus,'severity':v['incident']['severity'],'category':v['incident']['category'],'title':v['incident']['title'],'updates':len(nu),'head_event_id':e['event_id']}
        plan={'incident':True,'incident_id':iid,'event_id':e['event_id'],'event_hash':e['integrity']['event_hash'],'immutable':[(f"incidents/{iid}/events/{e['seq']:06d}_{e['event_id']}.json",etext)],'mutable':[(f"incidents/{iid}/INCIDENT.md",incident_render_text(v['incident'],nu,nstatus,nresolved)),('incidents/INDEX.md',incident_render_index(root,_incident_index_entries(root,overlay)))]}
        return (plan,iid,e['event_id'],e['integrity']['event_hash'])
    raise RuntimeError(f'unknown incident action {action!r}')
def _materialize_incident_files(root,plan):
    """Write one incident plan: create-only immutable files, snapshot projections.

    Mirrors _materialize_plan_files guarantees in the incidents/ namespace:
    paths confined to incidents/, immutable paths refused when present,
    mutable projections snapshotted and restored on failure. Returns written
    rel paths.
    """
    root=Path(root)
    for rel,_ in plan['immutable']+plan['mutable']:
        if not isinstance(rel,str) or rel.startswith('/') or '..' in Path(rel).parts or not rel.startswith('incidents/'): raise RuntimeError(f'plan path {rel!r} escapes incidents/; refusing')
    for rel,_ in plan['immutable']:
        if (root/rel).exists(): raise RuntimeError(f'plan path {rel!r} already exists; incident create/append-only refuses overwrite')
    snaps={}
    for rel,_ in plan['mutable']:
        fp=root/rel
        snaps[rel]=fp.read_bytes() if fp.exists() else None
    written=[]
    try:
        for rel,text in plan['immutable']+plan['mutable']:
            fp=root/rel; fp.parent.mkdir(parents=True,exist_ok=True)
            fp.write_text(text,encoding='utf-8'); written.append(rel)
    except BaseException:
        for rel in written:
            if rel in snaps and snaps[rel] is not None:
                try: (root/rel).write_bytes(snaps[rel])
                except OSError: pass
            else:
                try: (root/rel).unlink()
                except OSError: pass
        raise
    return written
def _incident_post_push_verify(repo,remote,branch,iid,expect_path,expect_hash):
    """Read-back verification for one published incident file.

    Mirrors post_push_verify guarantees: fetch, tip equality is established
    by the caller sequence (plain non-force push just succeeded), remote
    bytes are read back and hash-recomputed, and the local incident chain
    re-validates. Raises instead of reporting success on any mismatch.
    """
    rh=git_out(repo,'ls-remote',remote,branch).split()
    remote_head=rh[0] if rh else None
    if not remote_head: raise RuntimeError(f'post-push verification failed: cannot resolve remote {remote}/{branch}; do not report success')
    git_out(repo,'fetch',remote,branch)
    local=git_out(repo,'rev-parse',branch)
    if local!=remote_head: raise RuntimeError(f'post-push verification failed: remote {remote}/{branch} moved since push ({remote_head} vs local {local}); re-verify before reporting success')
    cp=subprocess.run(['git','-C',str(repo),'show',f'{remote_head}:{expect_path}'],capture_output=True)
    if cp.returncode!=0: raise RuntimeError(f'post-push verification failed: published path {expect_path} unreadable at remote head {remote_head}; do not report success')
    try: back=json.loads(cp.stdout.decode('utf-8'))
    except Exception as ex: raise RuntimeError(f'post-push verification failed: remote bytes do not parse ({ex}); do not report success')
    got=back.get('discovery_hash') if expect_path.endswith('/incident.json') else (back.get('integrity') or {}).get('event_hash')
    if got!=expect_hash: raise RuntimeError(f'post-push verification failed: recomputed {got} != recorded {expect_hash}; do not report success')
    incident_validate(Path(repo)/'incidents'/iid)
    return {'remote_head':remote_head,'local':local}
def incident_list(root,status=None,severity=None,category=None):
    root=Path(root); out=[]; invalid=[]
    inc_root=root/'incidents'
    for sub in sorted(inc_root.iterdir()) if inc_root.exists() else []:
        if not sub.is_dir() or not (sub/'incident.json').exists(): continue
        try: v=incident_validate(sub)
        except Exception as e: invalid.append({'incident_id':sub.name,'error':str(e)}); continue
        t=v['incident']
        if status and v['head_status']!=status: continue
        if severity and t['severity']!=severity: continue
        if category and t['category']!=category: continue
        out.append({'incident_id':t['incident_id'],'title':t['title'],'status':v['head_status'],'severity':t['severity'],'category':t['category'],'reporter':t['reporter'],'detected_at':t['detected_at'],'recorded_at':t['recorded_at'],'resolved_at':v['resolved_at'],'updates':v['update_count'],'head_event_id':v['head_event_id']})
    return {'incidents':out,'invalid':invalid}
def incident_show(root,iid):
    _incident_check_id(iid)
    idir=incident_dir(root,iid)
    v=incident_validate(idir)
    t=v['incident']
    return {'incident_id':t['incident_id'],'title':t['title'],'status':v['head_status'],'severity':t['severity'],'category':t['category'],'reporter':t['reporter'],'detected_at':t['detected_at'],'recorded_at':t['recorded_at'],'resolved_at':v['resolved_at'],'discovery':{k:t.get(k) for k in ('summary','symptom','impact','evidence','refs','violated_invariant','expected_behavior','containment','remediation','related_incidents','duplicate_of','note','discovery_hash')},'updates':v['updates'],'head_seq':v['head_seq'],'head_event_id':v['head_event_id']}
def incident_audit(root,iid=None):
    root=Path(root)
    if iid is not None:
        _incident_check_id(iid)
        try: v=incident_validate(incident_dir(root,iid))
        except Exception as e: return {'incident_id':iid,'ok':False,'error':str(e)}
        return {'incident_id':iid,'ok':True,'status':v['head_status'],'updates':v['update_count'],'head_event_id':v['head_event_id'],'discovery_hash':v['incident']['discovery_hash']}
    out=[]; ok=True
    inc_root=root/'incidents'
    for sub in sorted(inc_root.iterdir()) if inc_root.exists() else []:
        if not sub.is_dir() or not (sub/'incident.json').exists(): continue
        try: v=incident_validate(sub); out.append({'incident_id':sub.name,'ok':True,'status':v['head_status'],'updates':v['update_count']})
        except Exception as e: out.append({'incident_id':sub.name,'ok':False,'error':str(e)}); ok=False
    return {'ok':ok,'incidents':out}
def do_incident_create(a):
    import json as _js
    refs=_js.loads(a.refs) if getattr(a,'refs',None) else None
    related=(a.related_incidents.split(',') if getattr(a,'related_incidents',None) else None)
    related=[r.strip() for r in related if r.strip()] if related else None
    params={k:getattr(a,k,None) for k in ('reporter_surface','symptom','impact','evidence','detected_at','violated_invariant','expected_behavior','containment','remediation','note','idempotency_key')}
    print(json.dumps(incident_create(a.root,a.incident_id,a.title,a.summary,a.severity,a.category,a.reporter_role,a.reporter_id,refs=refs,related_incidents=related,**params),indent=2,default=str))
def do_incident_update(a):
    related=(a.related_add.split(',') if getattr(a,'related_add',None) else None)
    related=[r.strip() for r in related if r.strip()] if related else None
    params={k:getattr(a,k,None) for k in ('status','note','evidence_add','remediation','root_cause','resolution_evidence','duplicate_of','reporter_role','reporter_id','idempotency_key')}
    print(json.dumps(incident_update(a.root,a.incident_id,a.actor_role,a.actor_id,related_add=related,**params),indent=2,default=str))
def do_incident_show(a):
    print(json.dumps(incident_show(a.root,a.incident_id),indent=2))
def do_incident_list(a):
    print(json.dumps(incident_list(a.root,getattr(a,'status',None),getattr(a,'severity',None),getattr(a,'category',None)),indent=2))
def do_incident_audit(a):
    print(json.dumps(incident_audit(a.root,getattr(a,'incident_id',None)),indent=2))
def do_incident_rebuild(a):
    root=Path(a.root)
    iid=getattr(a,'incident_id',None)
    if iid is not None:
        _incident_check_id(iid)
        incident_render_projections(root,iid)
        print(json.dumps({'rebuilt':[iid]},indent=2)); return
    done=[]
    inc_root=root/'incidents'
    for sub in sorted(inc_root.iterdir()) if inc_root.exists() else []:
        if not sub.is_dir() or not (sub/'incident.json').exists(): continue
        incident_validate(sub)
        incident_render_projections(root,sub.name); done.append(sub.name)
    print(json.dumps({'rebuilt':done},indent=2))
# ---- Ephemeral clean execution views (O1 default) ----
# Independent task-runs must not share one mutable Relay working tree: any
# unpublished commit, dirty file, or divergence in another window's checkout
# can block pull --ff-only freshness proofs and manufacture a synthetic wait
# between unrelated Tasks. The default is therefore one task-run-scoped clean
# view per worker session, in a STABLE session location (never disposable /
# swept temp dirs), used through the verified first-bind --relay-dir
# override. This section is deliberately tiny: clone + verify + release-gate,
# composed from existing git/AWRP primitives. No pool manager, no worktree
# default, no daemon, no auto-stash/reset/discard of foreign bytes.
EXECUTION_VIEW_DIRNAME='relay'
EXECUTION_VIEW_CANONICAL_TREES=('tasks/','incidents/','channels/','contexts/','projects/','bridge/requests/')
def _execution_view_dir(root): return Path(root)/EXECUTION_VIEW_DIRNAME
def _execution_view_url(relay,origin_url):
    if origin_url: return origin_url
    return f'https://github.com/{relay}.git'
def _execution_view_canonical_dirt(repo):
    """Uncommitted bytes that could be another Task's unpublished work.

    Returns a list of porcelain lines. Modified/staged tracked files always
    count. Untracked files count ONLY under canonical trees (tasks/,
    incidents/, channels/, contexts/, projects/, bridge/requests/) — stray
    scratch (logs, .awrp/, tool output) never blocks a view. Anything listed
    here fails closed: the view is left untouched for its owner.
    """
    out=git_out(repo,'status','--porcelain')
    dirt=[]
    for line in out.splitlines():
        if not line.strip(): continue
        st,path=line[:2],line[3:].strip().strip('"')
        if st=='??':
            if not any(path==t.rstrip('/') or path.startswith(t) for t in EXECUTION_VIEW_CANONICAL_TREES): continue
            dirt.append(line.strip()); continue
        dirt.append(line.strip())
    return dirt
def _execution_view_git_dir(repo):
    cp=subprocess.run(['git','-C',str(repo),'rev-parse','--git-dir'],capture_output=True,text=True)
    if cp.returncode!=0: raise RuntimeError(f'execution view {str(repo)!r} is not a git checkout; refusing — remove it explicitly or choose another session root')
    return cp.stdout.strip()
def execution_view_acquire(root,relay,origin_url=None,remote='origin',branch='main'):
    """Ensure a verified clean execution view at <root>/relay (worker path).

    Creates it (fresh clone) when absent; reuses it only after positively
    proving cleanliness (no foreign uncommitted bytes), canonical Relay
    identity (relay.json where present, plus origin URL equality), and
    freshness (pull --ff-only then local==remote head). A present-but-unusable
    view is NEVER repaired, reset, or deleted here — that decision belongs to
    its owner; this call fails closed naming the cause. Returns a JSON-able
    report; prints nothing (see do_execution_view_acquire).
    """
    root=Path(root)
    if not root.exists(): raise RuntimeError(f'session root {str(root)!r} is absent; create the session directory first — views are never conjured inside disposable temp')
    if not relay or '/' not in relay: raise RuntimeError(f'relay must be a canonical OWNER/REPO identity, got {relay!r}')
    url=_execution_view_url(relay,origin_url)
    vd=_execution_view_dir(root); notes=[]
    if not vd.exists():
        cp=subprocess.run(['git','clone',url,str(vd)],capture_output=True,text=True)
        if cp.returncode!=0: raise RuntimeError(f'execution-view clone failed ({cp.stderr.strip()}); check network/credentials, session root left unchanged')
        created=True
    else:
        created=False
        _execution_view_git_dir(str(vd))
        oid=relay_identity(str(vd))
        if oid is None: raise RuntimeError(f'execution view at {str(vd)!r} has no relay.json; identity unprovable — remove it explicitly or choose another session root, never reuse blindly')
        if oid!=relay: raise RuntimeError(f'execution view at {str(vd)!r} identifies as relay {oid!r}, not {relay!r}; refusing a wrong repo')
        try: ourl=git_out(str(vd),'config','--get','remote.origin.url')
        except RuntimeError: ourl=None
        if not ourl or ourl!=url: raise RuntimeError(f'execution view at {str(vd)!r} points at remote {ourl!r}, want {url!r}; refusing a divergent view')
        dirt=_execution_view_canonical_dirt(str(vd))
        if dirt: raise RuntimeError(f"execution view at {str(vd)!r} holds uncommitted bytes that could be another Task's unpublished work ({'; '.join(dirt[:3])}); refusing to touch — its owner must commit/publish/clear first, or use a fresh session root")
        notes.append('reused verified-clean view')
    try:
        oid=relay_identity(str(vd))
    except RuntimeError as e:
        if created:
            raise RuntimeError(f'fresh execution view at {str(vd)!r} failed relay identity ({e}); remove it and retry')
        raise
    if oid!=relay: raise RuntimeError(f'execution view at {str(vd)!r} identifies as relay {oid!r}, not {relay!r}; refusing')
    git_out(str(vd),'pull','--ff-only')
    fresh=check_freshness(str(vd),remote,branch)
    return {'relay_dir':str(vd.resolve()),'created':created,'fresh':fresh['aligned'],'remote_head':fresh['remote_head'],'relay':relay,'notes':notes}
def execution_view_release(root,task_id,run_id,remote='origin',branch='main'):
    """Safe-cleanup gate for an execution view (worker path).

    Deletes <root>/relay ONLY after positively proving all of: no unpublished
    local commits, no uncommitted canonical bytes, and the given run's HANDOFF
    present both locally (validated chain) and on the remote (read-back of the
    exact event file). Anything uncertain refuses and leaves the view intact
    as an inert orphan — deletion is never the default. Returns a report.
    """
    import shutil as _sh
    root=Path(root); vd=_execution_view_dir(root)
    if not vd.exists(): raise RuntimeError(f'no execution view at {str(vd)!r}; nothing to release')
    _execution_view_git_dir(str(vd))
    git_out(str(vd),'fetch',remote,branch)
    rh=git_out(str(vd),'ls-remote',remote,branch).split()
    remote_head=rh[0] if rh else None
    if not remote_head: raise RuntimeError(f'cannot resolve remote {remote}/{branch}; cannot prove delivery — view left intact')
    local=git_out(str(vd),'rev-parse',branch)
    if local!=remote_head: raise RuntimeError(f'view has unpublished local commits ({local} vs remote {remote_head}); refusing to destroy possibly-undelivered work — publish first, then release')
    dirt=_execution_view_canonical_dirt(str(vd))
    if dirt: raise RuntimeError(f"view holds uncommitted bytes ({'; '.join(dirt[:3])}); refusing to destroy possibly-undelivered work — commit/publish/clear first")
    td=vd/'tasks'/task_id
    try: v=validate(td)
    except Exception as e: raise RuntimeError(f'cannot prove HANDOFF delivery: task chain invalid ({e}) — view left intact')
    runs=v.get('runs') or {}
    st=(runs.get(run_id) or {}).get('state')
    if st not in CLOSED_RUN_STATES: raise RuntimeError(f'run {run_id!r} is not closed (state {st!r}); cleanup only after HANDOFF — view left intact')
    hid=None
    for e in v['events']:
        if e['type']=='HANDOFF' and e.get('run_id')==run_id: hid=e['event_id']
    if hid is None: raise RuntimeError(f'run {run_id!r} has no HANDOFF event; cleanup only after HANDOFF — view left intact')
    tree=git_out(str(vd),'ls-tree','-r','--name-only',remote_head,'--',f'tasks/{task_id}/events/')
    hits=[l.strip() for l in tree.splitlines() if l.strip().endswith(f'_{hid}.json')]
    if len(hits)!=1: raise RuntimeError(f'HANDOFF {hid} not readable at remote head {remote_head}; delivery unproven — view left intact')
    def _onerr(fn,path,exc):
        import stat as _st
        try: os.chmod(path,_st.S_IWRITE); fn(path)
        except Exception: pass
    _sh.rmtree(vd,onerror=_onerr)
    return {'released':True,'relay_dir':str(vd),'task_id':task_id,'run_id':run_id,'handoff_event_id':hid,'remote_head':remote_head}
def do_execution_view_acquire(a):
    print(json.dumps(execution_view_acquire(a.root,a.relay,getattr(a,'origin_url',None),getattr(a,'remote',None) or 'origin',getattr(a,'branch',None) or 'main'),indent=2))
def do_execution_view_release(a):
    print(json.dumps(execution_view_release(a.root,a.task_id,a.run_id,getattr(a,'remote',None) or 'origin',getattr(a,'branch',None) or 'main'),indent=2))
def parser():
    p=argparse.ArgumentParser(prog='awrp'); s=p.add_subparsers(dest='cmd',required=True)
    q=s.add_parser('init-context'); q.add_argument('--root',default='.'); q.add_argument('--context-id',required=True); q.add_argument('--title',required=True); q.add_argument('--description'); q.set_defaults(fn=init_context)
    q=s.add_parser('create-task'); q.add_argument('--root',default='.'); q.add_argument('--context-id',required=True); q.add_argument('--task-id'); q.add_argument('--title',required=True); q.add_argument('--goal',required=True); q.add_argument('--worker',default='codex'); q.add_argument('--created-by',default='chatgpt'); q.add_argument('--source-repo'); q.add_argument('--source-issue',type=int); q.add_argument('--channel-id'); q.add_argument('--lane-id'); q.add_argument('--worker-endpoint'); q.add_argument('--project-id'); q.add_argument('--legacy',action='store_true'); q.set_defaults(fn=create_task)
    q=s.add_parser('recover-task'); q.add_argument('--root',default='.'); q.add_argument('--task-id',required=True); q.add_argument('--predecessor-task',required=True); q.add_argument('--context-id',required=True); q.add_argument('--title',required=True); q.add_argument('--goal',required=True); q.add_argument('--worker',default='codex'); q.add_argument('--created-by',default='chatgpt'); q.add_argument('--channel-id'); q.add_argument('--lane-id'); q.add_argument('--worker-endpoint'); q.add_argument('--project-id'); q.add_argument('--approval-file',required=True); q.add_argument('--contract',required=True); q.add_argument('--run-id'); q.add_argument('--phase'); q.add_argument('--run-summary'); q.add_argument('--expected-head'); q.add_argument('--fencing-generation',type=int); q.add_argument('--idempotency-key'); q.add_argument('--legacy-route',action='store_true'); q.set_defaults(fn=recover_task)
    q=s.add_parser('plan-task-create'); q.add_argument('--root',default='.'); q.add_argument('--task-id',required=True); q.add_argument('--context-id',required=True); q.add_argument('--title',required=True); q.add_argument('--goal',required=True); q.add_argument('--worker',default='codex'); q.add_argument('--created-by',default='chatgpt'); q.add_argument('--source-repo'); q.add_argument('--source-issue',type=int); q.add_argument('--channel-id'); q.add_argument('--lane-id'); q.add_argument('--worker-endpoint'); q.add_argument('--project-id'); q.add_argument('--created-at'); q.add_argument('--repo',default='.'); q.add_argument('--branch',default='main'); q.add_argument('--remote',default='origin'); q.add_argument('--expected-base',required=True); q.set_defaults(fn=do_plan_task_create)
    q=s.add_parser('compose-intent'); q.add_argument('--root',default='.'); q.add_argument('--intent-file',required=True); q.add_argument('--actor-role',required=True); q.add_argument('--actor-id',required=True); q.add_argument('--repo',default='.'); q.add_argument('--branch',default='main'); q.add_argument('--remote',default='origin'); q.add_argument('--expected-base',required=True); q.add_argument('--binding-root'); q.set_defaults(fn=do_compose_intent)
    q=s.add_parser('bridge-process'); q.add_argument('--root',default='.'); q.add_argument('--request',required=False,default=None); q.add_argument('--all-pending',action='store_true'); q.add_argument('--repo',default=None); q.add_argument('--branch',default='main'); q.add_argument('--remote',default='origin'); q.set_defaults(fn=do_bridge_process)
    q=s.add_parser('bridge-preflight'); q.add_argument('--root',default='.'); q.add_argument('--request',required=True); q.add_argument('--repo',default=None); q.add_argument('--branch',default='main'); q.add_argument('--remote',default='origin'); q.set_defaults(fn=do_bridge_preflight)
    for name,fn in [('validate',do_validate),('replay',replay),('render-card',do_render)]: q=s.add_parser(name); q.add_argument('--task-dir',required=True); q.set_defaults(fn=fn)
    q=s.add_parser('emit'); q.add_argument('--task-dir',required=True); q.add_argument('--type',required=True,choices=sorted(EVENT_TYPES)); q.add_argument('--actor-role',required=True); q.add_argument('--actor-id',required=True); q.add_argument('--recipient-role'); q.add_argument('--recipient-id'); g=q.add_mutually_exclusive_group(); g.add_argument('--run-id'); g.add_argument('--new-run',action='store_true'); q.add_argument('--state',required=True,choices=sorted(TASK_STATES)); q.add_argument('--phase',required=True); q.add_argument('--waiting-on',default='null'); q.add_argument('--run-state',choices=sorted(RUN_STATES)); q.add_argument('--summary',required=True); q.add_argument('--details-file'); q.add_argument('--artifacts-file'); q.add_argument('--approval-file'); q.add_argument('--causation-id');     q.add_argument('--expected-head'); q.add_argument('--expected-hash'); q.add_argument('--claimant'); q.add_argument('--fencing-generation',type=int); q.add_argument('--idempotency-key'); q.add_argument('--require-fresh',action='store_true'); q.add_argument('--legacy-route',action='store_true'); q.set_defaults(fn=emit)
    q=s.add_parser('publish-preflight'); q.add_argument('--task-dir',required=True); q.add_argument('--repo',default='.'); q.add_argument('--branch'); q.add_argument('--remote',default='origin'); q.add_argument('--expected-base'); q.add_argument('--expected-head'); q.add_argument('--expected-hash'); q.add_argument('--run-id'); q.set_defaults(fn=do_preflight)
    q=s.add_parser('worker-retry-push'); q.add_argument('--task-dir',required=True); q.add_argument('--run-id',required=True); q.add_argument('--expected-head',required=True); q.add_argument('--expected-hash',required=True); q.add_argument('--expected-base',required=True); q.add_argument('--repo',default='.'); q.add_argument('--branch',default='main'); q.add_argument('--remote',default='origin'); q.add_argument('--verify-cmd',action='append',default=[]); q.add_argument('--max-attempts',type=int,default=3); q.set_defaults(fn=do_worker_retry_push)
    q=s.add_parser('publish-ephemeral'); q.add_argument('--task-dir',required=True); q.add_argument('--run-id',required=True); q.add_argument('--event-file',action='append',default=[]); q.add_argument('--artifact',action='append',default=[]); q.add_argument('--repo',default='.'); q.add_argument('--branch',default='main'); q.add_argument('--remote',default='origin'); q.add_argument('--commit-message'); q.add_argument('--max-attempts',type=int,default=3); q.set_defaults(fn=do_publish_ephemeral)
    q=s.add_parser('artifact-hash'); q.add_argument('--path',required=True); q.set_defaults(fn=do_artifact_hash)
    q=s.add_parser('doctor'); q.add_argument('--task-dir',required=True); q.add_argument('--repo',default='.'); q.add_argument('--remote',default='origin'); q.add_argument('--branch'); q.set_defaults(fn=do_doctor)
    q=s.add_parser('audit-chain'); q.add_argument('--task-dir',required=True); q.add_argument('--repo'); q.set_defaults(fn=do_audit_chain)
    q=s.add_parser('inbox'); q.add_argument('--root',default='.'); q.add_argument('--channel'); q.add_argument('--worker-endpoint'); q.add_argument('--task-id'); q.add_argument('--project'); q.add_argument('--legacy',action='store_true'); q.set_defaults(fn=do_inbox)
    q=s.add_parser('bind'); q.add_argument('--root',default='.'); q.add_argument('--relay',required=True); q.add_argument('--relay-dir'); q.add_argument('--channel',required=True); q.add_argument('--worker-endpoint',required=True); q.add_argument('--lane'); q.add_argument('--project-id'); q.add_argument('--bound-by'); q.add_argument('--force',action='store_true'); q.set_defaults(fn=do_bind)
    q=s.add_parser('resume'); q.add_argument('--root',default='.'); q.add_argument('--channel'); q.add_argument('--worker-endpoint'); q.add_argument('--lane'); q.set_defaults(fn=do_resume)
    q=s.add_parser('first-bind'); q.add_argument('--root',default='.'); q.add_argument('--relay',required=True); q.add_argument('--relay-dir'); q.add_argument('--project-id',required=True); q.add_argument('--channel',required=True); q.add_argument('--worker-endpoint',required=True); q.add_argument('--task-id',required=True); q.add_argument('--run-id'); q.add_argument('--lane'); q.add_argument('--bound-by'); q.set_defaults(fn=do_first_bind)
    q=s.add_parser('project-create'); q.add_argument('--root',default='.'); q.add_argument('--project-id',required=True); q.add_argument('--title',required=True); q.add_argument('--channel',action='append',default=[]); q.add_argument('--notion'); q.add_argument('--notion-page-id'); q.add_argument('--alias',action='append',default=[]); q.add_argument('--created-by',default='chatgpt'); q.set_defaults(fn=do_project_create)
    q=s.add_parser('project-assign-channel'); q.add_argument('--root',default='.'); q.add_argument('--project-id',required=True); q.add_argument('--channel',required=True); q.set_defaults(fn=do_project_assign_channel)
    q=s.add_parser('resolve-project'); q.add_argument('--root',default='.'); q.add_argument('--project-id'); q.add_argument('--alias'); q.add_argument('--title'); q.set_defaults(fn=do_resolve_project)
    q=s.add_parser('project-snapshot'); q.add_argument('--root',default='.'); q.add_argument('--project-id',required=True); q.set_defaults(fn=do_project_snapshot)
    q=s.add_parser('audit-projects'); q.add_argument('--root',default='.'); q.set_defaults(fn=do_audit_projects)
    q=s.add_parser('migration-associate'); q.add_argument('--root',default='.'); q.add_argument('--project-id',required=True); q.add_argument('--task-id',required=True); q.add_argument('--reason'); q.add_argument('--created-by',default='chatgpt'); q.set_defaults(fn=do_migration_associate)
    q=s.add_parser('probe-project'); q.add_argument('--root',default='.'); q.set_defaults(fn=do_probe_project)
    q=s.add_parser('render-bootstrap'); q.add_argument('--root',default='.'); q.add_argument('--project-id',required=True); q.add_argument('--task-id',required=True); q.add_argument('--run-id'); q.set_defaults(fn=do_render_bootstrap)
    q=s.add_parser('attach'); q.add_argument('--root',default='.'); q.add_argument('--relay-dir'); q.add_argument('--project-id',required=True); q.add_argument('--by'); q.set_defaults(fn=do_attach)
    q=s.add_parser('switch'); q.add_argument('--root',default='.'); q.add_argument('--relay-dir'); q.add_argument('--project-id',required=True); q.add_argument('--task-id'); q.add_argument('--run-id'); q.set_defaults(fn=do_switch)
    q=s.add_parser('focus'); q.add_argument('--root',default='.'); q.add_argument('--relay-dir'); q.set_defaults(fn=do_focus)
    q=s.add_parser('check-lineage'); q.add_argument('--root',default='.'); q.add_argument('--relay-dir'); q.add_argument('--project-id',required=True); q.add_argument('--task-id',required=True); q.add_argument('--run-id'); q.set_defaults(fn=do_check_lineage)
    q=s.add_parser('plan-dispatch'); q.add_argument('--binding-root'); q.add_argument('--no-binding',action='store_true'); q.add_argument('--project-id'); q.add_argument('--channel'); q.add_argument('--worker-endpoint'); q.add_argument('--lane'); q.add_argument('--task-id',required=True); q.add_argument('--run-id'); q.add_argument('--branch',default='main'); q.add_argument('--remote',default='origin'); q.set_defaults(fn=do_plan_dispatch)
    q=s.add_parser('dispatch-guarded'); q.add_argument('--binding-root'); q.add_argument('--no-binding',action='store_true'); q.add_argument('--project-id'); q.add_argument('--channel'); q.add_argument('--worker-endpoint'); q.add_argument('--lane'); q.add_argument('--task-id',required=True); q.add_argument('--branch',default='main'); q.add_argument('--remote',default='origin'); q.add_argument('--repo',default=None); q.add_argument('--publish',action='store_true'); q.add_argument('--commit-message'); q.add_argument('--expected-plan'); g=q.add_mutually_exclusive_group(required=True); g.add_argument('--run-id'); g.add_argument('--new-run',action='store_true'); q.add_argument('--actor-role',required=True); q.add_argument('--actor-id',required=True); q.add_argument('--recipient-role'); q.add_argument('--recipient-id'); q.add_argument('--state',required=True,choices=sorted(TASK_STATES)); q.add_argument('--phase',required=True); q.add_argument('--waiting-on',default='null'); q.add_argument('--run-state',choices=sorted(RUN_STATES)); q.add_argument('--summary',required=True); q.add_argument('--details-file'); q.add_argument('--artifacts-file'); q.add_argument('--approval-file'); q.add_argument('--causation-id'); q.add_argument('--expected-head'); q.add_argument('--expected-hash'); q.add_argument('--claimant'); q.add_argument('--fencing-generation',type=int); q.add_argument('--idempotency-key'); q.set_defaults(fn=do_dispatch_guarded)
    q=s.add_parser('execution-view-acquire'); q.add_argument('--root',required=True); q.add_argument('--relay',required=True); q.add_argument('--origin-url'); q.add_argument('--remote',default='origin'); q.add_argument('--branch',default='main'); q.set_defaults(fn=do_execution_view_acquire)
    q=s.add_parser('execution-view-release'); q.add_argument('--root',required=True); q.add_argument('--task-id',required=True); q.add_argument('--run-id',required=True); q.add_argument('--remote',default='origin'); q.add_argument('--branch',default='main'); q.set_defaults(fn=do_execution_view_release)
    q=s.add_parser('acquire-claim'); q.add_argument('--root',default='.'); q.add_argument('--channel',required=True); q.add_argument('--owner',required=True); q.add_argument('--expected-generation',type=int); q.add_argument('--takeover',action='store_true'); q.add_argument('--note'); q.set_defaults(fn=do_acquire_claim)
    q=s.add_parser('read-claim'); q.add_argument('--root',default='.'); q.add_argument('--channel',required=True); q.set_defaults(fn=do_read_claim)
    q=s.add_parser('migrate-claim'); q.add_argument('--root',default='.'); q.add_argument('--channel',required=True); q.add_argument('--note'); q.add_argument('--by'); q.set_defaults(fn=do_migrate_claim)
    q=s.add_parser('repair-claim'); q.add_argument('--root',default='.'); q.add_argument('--channel',required=True); q.set_defaults(fn=do_repair_claim)
    q=s.add_parser('incident-create'); q.add_argument('--root',default='.'); q.add_argument('--incident-id',required=True); q.add_argument('--title',required=True); q.add_argument('--summary',required=True); q.add_argument('--severity',required=True); q.add_argument('--category',required=True); q.add_argument('--reporter-role',required=True); q.add_argument('--reporter-id',required=True); q.add_argument('--reporter-surface'); q.add_argument('--symptom',required=True); q.add_argument('--impact',required=True); q.add_argument('--evidence',required=True); q.add_argument('--detected-at'); q.add_argument('--refs'); q.add_argument('--violated-invariant'); q.add_argument('--expected-behavior'); q.add_argument('--containment'); q.add_argument('--remediation'); q.add_argument('--related-incidents'); q.add_argument('--note'); q.add_argument('--idempotency-key'); q.set_defaults(fn=do_incident_create)
    q=s.add_parser('incident-update'); q.add_argument('--root',default='.'); q.add_argument('--incident-id',required=True); q.add_argument('--actor-role',required=True); q.add_argument('--actor-id',required=True); q.add_argument('--status'); q.add_argument('--note'); q.add_argument('--evidence-add'); q.add_argument('--remediation'); q.add_argument('--root-cause'); q.add_argument('--resolution-evidence'); q.add_argument('--related-add'); q.add_argument('--duplicate-of'); q.add_argument('--reporter-role'); q.add_argument('--reporter-id'); q.add_argument('--idempotency-key'); q.set_defaults(fn=do_incident_update)
    q=s.add_parser('incident-show'); q.add_argument('--root',default='.'); q.add_argument('--incident-id',required=True); q.set_defaults(fn=do_incident_show)
    q=s.add_parser('incident-list'); q.add_argument('--root',default='.'); q.add_argument('--status'); q.add_argument('--severity'); q.add_argument('--category'); q.set_defaults(fn=do_incident_list)
    q=s.add_parser('incident-audit'); q.add_argument('--root',default='.'); q.add_argument('--incident-id'); q.set_defaults(fn=do_incident_audit)
    q=s.add_parser('incident-rebuild'); q.add_argument('--root',default='.'); q.add_argument('--incident-id'); q.set_defaults(fn=do_incident_rebuild)
    q=s.add_parser('audit-history'); q.add_argument('--repo',default='.'); q.add_argument('--task-id',required=True); q.add_argument('--ref',default='origin/main'); q.set_defaults(fn=do_audit_history)
    q=s.add_parser('audit-fencing'); q.add_argument('--task-dir',required=True); q.set_defaults(fn=do_audit_fencing)
    q=s.add_parser('audit-dispatch-identity'); q.add_argument('--root',default='.'); q.add_argument('--task-id'); q.set_defaults(fn=do_audit_dispatch_identity)
    q=s.add_parser('publish-atomic'); q.add_argument('--task-dir',required=True); q.add_argument('--repo',default='.'); q.add_argument('--branch'); q.add_argument('--remote',default='origin'); q.add_argument('--expected-base',required=True); q.add_argument('--commit-message'); q.add_argument('--type',required=True,choices=sorted(EVENT_TYPES)); q.add_argument('--actor-role',required=True); q.add_argument('--actor-id',required=True); q.add_argument('--recipient-role'); q.add_argument('--recipient-id'); g=q.add_mutually_exclusive_group(); g.add_argument('--run-id'); g.add_argument('--new-run',action='store_true'); q.add_argument('--state',required=True,choices=sorted(TASK_STATES)); q.add_argument('--phase',required=True); q.add_argument('--waiting-on',default='null'); q.add_argument('--run-state',choices=sorted(RUN_STATES)); q.add_argument('--summary',required=True); q.add_argument('--details-file'); q.add_argument('--artifacts-file'); q.add_argument('--approval-file'); q.add_argument('--causation-id');     q.add_argument('--expected-head'); q.add_argument('--expected-hash'); q.add_argument('--claimant'); q.add_argument('--fencing-generation',type=int); q.add_argument('--idempotency-key'); q.add_argument('--require-fresh',action='store_true'); q.add_argument('--legacy-route',action='store_true'); q.set_defaults(fn=publish_atomic)
    q=s.add_parser('publish-connector'); q.add_argument('--task-dir',required=True); q.add_argument('--repo',default='.'); q.add_argument('--branch'); q.add_argument('--remote',default='origin'); q.add_argument('--expected-base',required=True); q.add_argument('--commit-message'); q.add_argument('--print-plan',action='store_true'); q.add_argument('--type',required=True,choices=sorted(EVENT_TYPES)); q.add_argument('--actor-role',required=True); q.add_argument('--actor-id',required=True); q.add_argument('--recipient-role'); q.add_argument('--recipient-id'); g=q.add_mutually_exclusive_group(); g.add_argument('--run-id'); g.add_argument('--new-run',action='store_true'); q.add_argument('--state',required=True,choices=sorted(TASK_STATES)); q.add_argument('--phase',required=True); q.add_argument('--waiting-on',default='null'); q.add_argument('--run-state',choices=sorted(RUN_STATES)); q.add_argument('--summary',required=True); q.add_argument('--details-file'); q.add_argument('--artifacts-file'); q.add_argument('--approval-file'); q.add_argument('--causation-id');     q.add_argument('--expected-head'); q.add_argument('--expected-hash'); q.add_argument('--claimant'); q.add_argument('--fencing-generation',type=int); q.add_argument('--idempotency-key'); q.add_argument('--require-fresh',action='store_true'); q.add_argument('--legacy-route',action='store_true'); q.set_defaults(fn=publish_connector)
    return p

def main():
    try: a=parser().parse_args(); a.fn(a); return 0
    except Exception as e: print(f'AWRP ERROR: {e}',file=sys.stderr); return 2
if __name__=='__main__': raise SystemExit(main())
