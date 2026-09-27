import importlib.util, json, shutil, subprocess, tempfile, unittest
from pathlib import Path
SPEC=importlib.util.spec_from_file_location('awrp',Path(__file__).resolve().parents[1]/'tools'/'awrp.py')
awrp=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(awrp)
TSPEC=importlib.util.spec_from_file_location('awrp_transport',Path(__file__).resolve().parents[1]/'tools'/'awrp_transport.py')
awrp_transport=importlib.util.module_from_spec(TSPEC); TSPEC.loader.exec_module(awrp_transport)
class T(unittest.TestCase):
    def setUp(self):
        self.tmp=Path(tempfile.mkdtemp()); (self.tmp/'contexts').mkdir()
        awrp.write_new(self.tmp/'contexts'/'ctx_test.json',{'protocol':'awrp/0.1','context_id':'ctx_test','title':'Test','created_at':awrp.now(),'description':''})
        class A: pass
        a=A(); a.root=str(self.tmp); a.context_id='ctx_test'; a.task_id='task_test'; a.title='Test task'; a.goal='Test'; a.worker='codex'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.legacy=True
        awrp.create_task(a); self.td=self.tmp/'tasks'/'task_test'
    def tearDown(self): shutil.rmtree(self.tmp)
    def dispatch(self,rid=None):
        class A: pass
        a=A(); a.task_dir=str(self.td); a.type='DISPATCH'; a.actor_role='coordinator'; a.actor_id='chatgpt'; a.recipient_role='worker'; a.recipient_id='codex'; a.run_id=rid; a.new_run=(rid is None); a.state='working'; a.phase='implementation'; a.waiting_on='codex'; a.run_state='dispatched'; a.summary='go'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None
        awrp.emit(a); return awrp.validate(self.td)['head']['run_id']
    def test_flow(self):
        rid=self.dispatch()
        class A: pass
        a=A(); a.task_dir=str(self.td); a.type='ACK'; a.actor_role='worker'; a.actor_id='codex'; a.recipient_role='coordinator'; a.recipient_id='chatgpt'; a.run_id=rid; a.new_run=False; a.state='working'; a.phase='implementation'; a.waiting_on='codex'; a.run_state='working'; a.summary='ack'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None; awrp.emit(a)
        a.type='HANDOFF'; a.phase='review'; a.waiting_on='chatgpt'; a.run_state='succeeded'; a.summary='done'; awrp.emit(a)
        v=awrp.validate(self.td); self.assertEqual(v['head']['task_projection']['phase'],'review'); self.assertEqual(v['runs'][rid]['state'],'succeeded')
    def test_tamper(self):
        self.dispatch(); p=sorted((self.td/'events').glob('*.json'))[-1]; o=json.loads(p.read_text()); o['summary']='tampered'; p.write_text(json.dumps(o))
        with self.assertRaises(RuntimeError): awrp.validate(self.td)
    def test_duplicate_run(self):
        self.dispatch('run_fixed')
        with self.assertRaises(RuntimeError): self.dispatch('run_fixed')
    def set_task_source(self,src):
        tp=self.td/'task.json'; o=json.loads(tp.read_text()); o['source']=src; tp.write_text(json.dumps(o))
    def test_render_string_source(self):
        self.set_task_source('example/project#501')
        txt=Path(awrp.render(self.td)).read_text()
        self.assertIn('example/project#501',txt)
    def test_render_object_source(self):
        self.set_task_source({'type':'github_issue','repo':'o/r','number':7})
        txt=Path(awrp.render(self.td)).read_text()
        self.assertIn('o/r#7',txt)
    def test_render_absent_source(self):
        self.set_task_source(None)
        txt=Path(awrp.render(self.td)).read_text()
        self.assertNotIn('- **Source:**',txt)
    def test_emit_survives_projection_failure(self):
        real=awrp.render
        def boom(td): raise RuntimeError('projection exploded')
        awrp.render=boom
        try: rid=self.dispatch()
        finally: awrp.render=real
        self.assertEqual(awrp.validate(self.td)['head']['run_id'],rid)
class TC(unittest.TestCase):
    def setUp(self):
        self.tmp=Path(tempfile.mkdtemp()); (self.tmp/'contexts').mkdir()
        awrp.write_new(self.tmp/'contexts'/'ctx_test.json',{'protocol':'awrp/0.1','context_id':'ctx_test','title':'Test','created_at':awrp.now(),'description':''})
        class A: pass
        a=A(); a.root=str(self.tmp); a.context_id='ctx_test'; a.task_id='task_test'; a.title='Test task'; a.goal='Test'; a.worker='codex'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.legacy=True
        awrp.create_task(a); self.td=self.tmp/'tasks'/'task_test'
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def ev(self,typ,rid=None,new_run=False,state='working',phase='implementation',waiting_on='codex',run_state=None,expected_head=None,expected_hash=None,actor_role='coordinator',actor_id='chatgpt',recipient_role='worker',recipient_id='codex'):
        class A: pass
        a=A(); a.task_dir=str(self.td); a.type=typ; a.actor_role=actor_role; a.actor_id=actor_id; a.recipient_role=recipient_role; a.recipient_id=recipient_id; a.run_id=rid; a.new_run=new_run; a.state=state; a.phase=phase; a.waiting_on=waiting_on; a.run_state=run_state; a.summary='x'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None; a.expected_head=expected_head; a.expected_hash=expected_hash
        awrp.emit(a)
    def worker_ev(self,typ,rid,**kw):
        kw.setdefault('actor_role','worker'); kw.setdefault('actor_id','codex'); kw.setdefault('recipient_role','coordinator'); kw.setdefault('recipient_id','chatgpt')
        self.ev(typ,rid,**kw)
    def active(self): return awrp.validate(self.td)['active_run_id']
    def head_id(self): return awrp.validate(self.td)['head']['event_id']
    def test_active_run_established(self):
        self.ev('DISPATCH','run_1',run_state='dispatched')
        self.assertEqual(self.active(),'run_1')
    def test_second_dispatch_while_active_rejected(self):
        self.ev('DISPATCH','run_1',run_state='dispatched')
        with self.assertRaises(RuntimeError): self.ev('DISPATCH','run_2',run_state='dispatched')
    def test_stale_run_event_rejected(self):
        self.ev('DISPATCH','run_1',run_state='dispatched')
        self.worker_ev('ACK','run_1',run_state='working')
        self.worker_ev('HANDOFF','run_1',phase='review',waiting_on='chatgpt',run_state='succeeded')
        self.ev('DISPATCH','run_2',run_state='dispatched')
        with self.assertRaises(RuntimeError): self.worker_ev('ACK','run_1',run_state='working')
        self.worker_ev('ACK','run_2',run_state='working')
        self.assertEqual(self.active(),'run_2')
    def test_redispatch_after_handoff_succeeded(self):
        self.ev('DISPATCH','run_1',run_state='dispatched')
        self.worker_ev('HANDOFF','run_1',phase='review',waiting_on='chatgpt',run_state='succeeded')
        self.assertIsNone(self.active())
        self.ev('DISPATCH','run_2',run_state='dispatched')
        self.assertEqual(self.active(),'run_2')
    def test_reconcile_clears_then_redispatch(self):
        self.ev('DISPATCH','run_1',run_state='dispatched')
        self.ev('RECONCILE',None)
        self.assertIsNone(self.active())
        self.ev('DISPATCH','run_2',run_state='dispatched')
        self.assertEqual(self.active(),'run_2')
    def test_reconcile_reaffirms_run(self):
        self.ev('DISPATCH','run_1',run_state='dispatched')
        self.ev('RECONCILE','run_1',run_state='working')
        self.assertEqual(self.active(),'run_1')
        self.worker_ev('ACK','run_1',run_state='working')
    def test_expected_head_mismatch_rejects(self):
        self.ev('DISPATCH','run_1',run_state='dispatched')
        with self.assertRaises(RuntimeError):
            self.worker_ev('ACK','run_1',run_state='working',expected_head='evt_bogus')
    def test_expected_head_match_accepts(self):
        self.ev('DISPATCH','run_1',run_state='dispatched')
        hid=self.head_id()
        self.worker_ev('ACK','run_1',run_state='working',expected_head=hid)
        self.assertEqual(self.active(),'run_1')
    def git(self,repo,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def make_remote_pair(self):
        remote=self.tmp/'r.git'; wa=self.tmp/'a'; wb=self.tmp/'b'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(self.tmp,'init','-b','main',str(wa))
        self.git(wa,'config','user.email','t@e'); self.git(wa,'config','user.name','t')
        (wa/'f.txt').write_text('base\n'); self.git(wa,'add','f.txt')
        self.git(wa,'commit','-m','base'); self.git(wa,'remote','add','origin',str(remote))
        self.git(wa,'push','-u','origin','main'); self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
        self.git(self.tmp,'clone',str(remote),str(wb))
        self.git(wb,'config','user.email','t@e'); self.git(wb,'config','user.name','t')
        return remote,wa,wb
    def preflight(self,repo,branch='main',**kw):
        class A: pass
        a=A(); a.task_dir=str(self.td); a.repo=str(repo); a.branch=branch; a.remote='origin'
        a.expected_base=kw.get('expected_base'); a.expected_head=kw.get('expected_head'); a.expected_hash=kw.get('expected_hash')
        awrp.do_preflight(a)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_preflight_ok_then_detects_remote_advancement(self):
        remote,wa,wb=self.make_remote_pair()
        self.preflight(wa)
        (wa/'w.txt').write_text('worker event\n'); self.git(wa,'add','w.txt'); self.git(wa,'commit','-m','append')
        self.preflight(wa)
        base=self.git(wa,'rev-parse','main')
        (wb/'r.txt').write_text('rival\n'); self.git(wb,'add','r.txt'); self.git(wb,'commit','-m','rival'); self.git(wb,'push','origin','main')
        with self.assertRaises(RuntimeError): self.preflight(wa)
        cp=subprocess.run(['git','-C',str(wa),'push','origin','main'],capture_output=True,text=True)
        self.assertNotEqual(cp.returncode,0)
        self.assertEqual(self.git(remote,'rev-parse','main'),self.git(wb,'rev-parse','main'))
        self.git(wa,'fetch','origin'); self.git(wa,'reset','--hard','origin/main')
        self.preflight(wa)
        with self.assertRaises(RuntimeError): self.preflight(wa,expected_base=base)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_preflight_new_branch_without_remote(self):
        remote,wa,wb=self.make_remote_pair()
        self.git(wa,'checkout','-b','feature-new')
        self.preflight(wa,branch='feature-new')
class TG(unittest.TestCase):
    CHM='channel_alpha_github'; CHO='channel_beta_automation'
    def setUp(self):
        self.tmp=Path(tempfile.mkdtemp()); (self.tmp/'contexts').mkdir()
        awrp.write_new(self.tmp/'contexts'/'ctx_test.json',{'protocol':'awrp/0.1','context_id':'ctx_test','title':'Test','created_at':awrp.now(),'description':''})
    def tearDown(self): shutil.rmtree(self.tmp,ignore_errors=True)
    def mk(self,tid,channel=None,lane=None,endpoint=None):
        class A: pass
        a=A(); a.root=str(self.tmp); a.context_id='ctx_test'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=channel; a.lane_id=lane; a.worker_endpoint=endpoint
        a.legacy=True
        awrp.create_task(a); return str(self.tmp/'tasks'/tid)
    def dis(self,td,rid,ep='opencode'):
        class A: pass
        a=A(); a.task_dir=td; a.type='DISPATCH'; a.actor_role='coordinator'; a.actor_id='chatgpt'; a.recipient_role='worker'; a.recipient_id=ep; a.run_id=rid; a.new_run=False; a.state='working'; a.phase='implementation'; a.waiting_on=ep; a.run_state='dispatched'; a.summary='go'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None; a.expected_head=None; a.expected_hash=None
        awrp.emit(a)
    def hand(self,td,rid):
        class A: pass
        a=A(); a.task_dir=td; a.type='HANDOFF'; a.actor_role='worker'; a.actor_id='opencode'; a.recipient_role='coordinator'; a.recipient_id='chatgpt'; a.run_id=rid; a.new_run=False; a.state='working'; a.phase='review'; a.waiting_on='chatgpt'; a.run_state='succeeded'; a.summary='done'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None; a.expected_head=None; a.expected_hash=None
        awrp.emit(a)
    def inbox(self,**kw):
        import io, contextlib
        class A: pass
        a=A(); a.root=str(self.tmp); a.channel=kw.get('channel'); a.worker_endpoint=kw.get('worker_endpoint'); a.task_id=kw.get('task_id'); a.legacy=kw.get('legacy',False)
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_inbox(a)
        return json.loads(buf.getvalue())
    def pair(self):
        m=self.mk('task_alpha',self.CHM,'lane_alpha','opencode_alpha')
        o=self.mk('task_beta',self.CHO,'lane_beta','opencode_beta')
        self.dis(m,'run_m',ep='opencode_alpha'); self.dis(o,'run_o',ep='opencode_beta')
        return m,o
    def test_channel_isolation(self):
        m,o=self.pair()
        gm=[t['task_id'] for t in self.inbox(channel=self.CHM)['actionable']]
        go=[t['task_id'] for t in self.inbox(channel=self.CHO)['actionable']]
        self.assertEqual(gm,['task_alpha']); self.assertEqual(go,['task_beta'])
    def test_endpoint_mismatch_fails_closed(self):
        self.pair()
        r=self.inbox(channel=self.CHM,worker_endpoint='opencode_beta')
        self.assertEqual(r['actionable'],[])
        r=self.inbox(channel=self.CHM,worker_endpoint='opencode_alpha')
        self.assertEqual([t['task_id'] for t in r['actionable']],['task_alpha'])
    def test_exact_task_id_escape(self):
        m,o=self.pair()
        r=self.inbox(task_id='task_beta')
        self.assertEqual(len(r['actionable']),1); self.assertTrue(r['actionable'][0]['actionable'])
    def test_taskmd_absent_no_effect(self):
        m,o=self.pair()
        (Path(m)/'TASK.md').unlink()
        gm=[t['task_id'] for t in self.inbox(channel=self.CHM)['actionable']]
        self.assertEqual(gm,['task_alpha'])
    def test_legacy_excluded_then_optin(self):
        m,o=self.pair()
        g=self.mk('task_legacy'); self.dis(g,'run_g')
        gm=[t['task_id'] for t in self.inbox(channel=self.CHM)['actionable']]
        self.assertNotIn('task_legacy',gm)
        rl=self.inbox(legacy=True)
        self.assertEqual([t['task_id'] for t in rl['actionable']],['task_legacy'])
        self.assertTrue(rl['actionable'][0]['legacy'])
    def test_multi_lane_same_channel_fifo(self):
        a=self.mk('task_lane_a',self.CHM,'lane_one','opencode_alpha'); self.dis(a,'run_a',ep='opencode_alpha')
        b=self.mk('task_lane_b',self.CHM,'lane_two','opencode_alpha'); self.dis(b,'run_b',ep='opencode_alpha')
        got=[t['task_id'] for t in self.inbox(channel=self.CHM)['actionable']]
        self.assertEqual(got,['task_lane_a','task_lane_b'])
        keys=[((t.get('dispatch_created_at') or ''),t['task_id']) for t in self.inbox(channel=self.CHM)['actionable']]
        self.assertEqual(keys,sorted(keys))
    def test_global_discovery_rejected(self):
        self.pair()
        with self.assertRaises(RuntimeError): self.inbox()
    def test_terminal_not_actionable(self):
        m,o=self.pair()
        self.hand(m,'run_m')
        gm=[t['task_id'] for t in self.inbox(channel=self.CHM)['actionable']]
        self.assertEqual(gm,[])
    def test_create_task_routing_shape(self):
        td=self.mk('task_routed',self.CHM,'lane_x','ep_x')
        r=json.loads(((Path(td)/'task.json')).read_text())
        self.assertEqual(r['routing'],{'channel_id':self.CHM,'lane_id':'lane_x','worker_endpoint':'ep_x'})
        td2=self.mk('task_plain')
        self.assertNotIn('routing',json.loads(((Path(td2)/'task.json')).read_text()))
class TH(unittest.TestCase):
    def test_artifact_hash_lf_crlf_stable(self):
        import hashlib
        d=Path(tempfile.mkdtemp())
        try:
            body=b'diff --git a/f b/f\n+line1\n+line2\n'
            lf=d/'a.diff'; crlf=d/'b.diff'
            lf.write_bytes(body); crlf.write_bytes(body.replace(b'\n',b'\r\n'))
            fl=awrp.artifact_fingerprint(str(lf)); fc=awrp.artifact_fingerprint(str(crlf))
            self.assertEqual(fl['sha256'],fc['sha256']); self.assertEqual(fl['size_bytes'],fc['size_bytes'])
            self.assertEqual(fl['line_ending'],'lf-stable'); self.assertEqual(fc['line_ending'],'normalized-to-lf')
            self.assertEqual(fl['sha256'],'sha256:'+hashlib.sha256(body).hexdigest())
            self.assertEqual(fl['size_bytes'],len(body))
        finally: shutil.rmtree(d,ignore_errors=True)
    def test_naive_hash_disagrees_across_line_endings(self):
        import hashlib
        body=b'x\n'
        self.assertNotEqual(hashlib.sha256(body).hexdigest(),hashlib.sha256(body.replace(b'\n',b'\r\n')).hexdigest())
    def test_gitattributes_pins_canonical_lf(self):
        ga=(Path(__file__).resolve().parents[1]/'.gitattributes').read_text()
        self.assertIn('artifacts',ga); self.assertIn('events',ga); self.assertIn('eol=lf',ga)
    def test_artifact_hash_cli_registered(self):
        ns=awrp.parser().parse_args(['artifact-hash','--path','x'])
        self.assertIs(ns.fn,awrp.do_artifact_hash)
class TW(unittest.TestCase):
    CH='channel_awrp_infrastructure'; EP='opencode_awrp'; LANE='lane_session_resume'
    def setUp(self):
        self.tmp=Path(tempfile.mkdtemp()); (self.tmp/'contexts').mkdir()
        awrp.write_new(self.tmp/'contexts'/'ctx_test.json',{'protocol':'awrp/0.1','context_id':'ctx_test','title':'Test','created_at':awrp.now(),'description':''})
        self.ws=self.tmp/'ws'; self.ws.mkdir()
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def bind(self,channel=CH,endpoint=EP,lane=LANE,force=False):
        class A: pass
        a=A(); a.root=str(self.ws); a.relay='Bruce-Yii/awrp'; a.relay_dir=str(self.tmp); a.channel=channel; a.worker_endpoint=endpoint; a.lane=lane; a.bound_by='test'; a.force=force
        awrp.do_bind(a)
    def mk(self,tid,channel=CH,lane=LANE,endpoint=EP):
        class A: pass
        a=A(); a.root=str(self.tmp); a.context_id='ctx_test'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=channel; a.lane_id=lane; a.worker_endpoint=endpoint
        a.legacy=True
        awrp.create_task(a); return str(self.tmp/'tasks'/tid)
    def ev(self,td,typ,rid,actor_role='coordinator',actor_id='chatgpt',recipient_role='worker',recipient_id='opencode_awrp',state='working',phase='implementation',waiting_on='opencode_awrp',run_state=None,claimant=None):
        class A: pass
        a=A(); a.task_dir=td; a.type=typ; a.actor_role=actor_role; a.actor_id=actor_id; a.recipient_role=recipient_role; a.recipient_id=recipient_id; a.run_id=rid; a.new_run=False; a.state=state; a.phase=phase; a.waiting_on=waiting_on; a.run_state=run_state; a.summary='x'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=claimant; a.fencing_generation=None
        awrp.emit(a)
    def resume(self):
        return awrp.select_for_resume(str(self.tmp),self.CH,self.EP,self.LANE)
    def test_binding_roundtrip(self):
        self.bind()
        b=awrp.read_binding(str(self.ws))
        self.assertEqual((b['channel_id'],b['worker_endpoint'],b['lane_id']),(self.CH,self.EP,self.LANE))
        with self.assertRaises(RuntimeError): self.bind()
        self.bind(endpoint='other_ep',force=True)
        self.assertEqual(awrp.read_binding(str(self.ws))['worker_endpoint'],'other_ep')
    def test_resume_selects_single_unacked(self):
        td=self.mk('task_a'); self.ev(td,'DISPATCH','run_a',run_state='dispatched')
        r=self.resume()
        self.assertEqual(r['status'],'EXECUTE'); self.assertEqual(r['task_id'],'task_a')
        self.assertTrue(r['head_event_id'] and r['head_hash'])
    def test_resume_wrong_channel_endpoint(self):
        td=self.mk('task_a'); self.ev(td,'DISPATCH','run_a',run_state='dispatched')
        r=awrp.select_for_resume(str(self.tmp),'channel_other',self.EP,self.LANE)
        self.assertEqual(r['status'],'NO_TASK')
        r=awrp.select_for_resume(str(self.tmp),self.CH,'other_ep',self.LANE)
        self.assertEqual(r['status'],'NO_TASK')
    def test_resume_ambiguity_no_ack(self):
        m=self.mk('task_a'); self.ev(m,'DISPATCH','run_a',run_state='dispatched')
        n=self.mk('task_b'); self.ev(n,'DISPATCH','run_b',run_state='dispatched')
        before=len(list((self.tmp/'tasks'/'task_a'/'events').glob('*.json')))
        r=self.resume()
        self.assertEqual(r['status'],'AMBIGUOUS'); self.assertEqual(sorted(r['candidates']),['task_a','task_b'])
        after=len(list((self.tmp/'tasks'/'task_a'/'events').glob('*.json')))
        self.assertEqual(before,after)
    def test_resume_owned_no_rework(self):
        td=self.mk('task_a'); self.ev(td,'DISPATCH','run_a',run_state='dispatched')
        self.ev(td,'ACK','run_a',actor_role='worker',actor_id='opencode_awrp',recipient_role='coordinator',recipient_id='chatgpt',run_state='working',claimant='sess-A')
        before=len(list(Path(td,'events').glob('*.json')))
        r=self.resume()
        self.assertEqual(r['status'],'OWNED'); self.assertEqual(r['task_id'],'task_a')
        self.assertEqual(len(list(Path(td,'events').glob('*.json'))),before)
    def test_race_second_ack_rejected(self):
        td=self.mk('task_a'); self.ev(td,'DISPATCH','run_a',run_state='dispatched')
        self.ev(td,'ACK','run_a',actor_role='worker',actor_id='opencode_awrp',recipient_role='coordinator',recipient_id='chatgpt',run_state='working',claimant='sess-A')
        with self.assertRaises(RuntimeError):
            self.ev(td,'ACK','run_a',actor_role='worker',actor_id='opencode_awrp',recipient_role='coordinator',recipient_id='chatgpt',run_state='working',claimant='sess-B')
        acks=[e for e in awrp.validate(td)['events'] if e['type']=='ACK']
        self.assertEqual(len(acks),1); self.assertEqual(acks[0].get('claimant'),'sess-A')
    def test_duplicate_seq_detected(self):
        td=self.mk('task_a'); self.ev(td,'DISPATCH','run_a',run_state='dispatched')
        evdir=Path(td)/'events'; src=sorted(evdir.glob('*.json'))[-1]
        shutil.copy(src,evdir/('000002_dup_'+src.name.split('_',1)[1]))
        with self.assertRaises(RuntimeError): awrp.validate(td)
    def test_invalid_never_actionable(self):
        td=self.mk('task_a'); self.ev(td,'DISPATCH','run_a',run_state='dispatched')
        p=sorted((Path(td)/'events').glob('*.json'))[-1]
        o=json.loads(p.read_text()); o['summary']='tampered'; p.write_text(json.dumps(o))
        r=self.resume()
        self.assertEqual(r['status'],'INVALID_CANONICAL')
        self.assertEqual(len(r['invalid_canonical']),1)
    def git(self,repo,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def git_task_repo(self):
        repo=self.tmp/'grepo'; repo.mkdir()
        self.git(repo,'init','-b','main'); self.git(repo,'config','user.email','t@e'); self.git(repo,'config','user.name','t')
        (repo/'contexts').mkdir()
        awrp.write_new(repo/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        td=repo/'tasks'/'task_g'
        class A: pass
        a=A(); a.root=str(repo); a.context_id='c'; a.task_id='task_g'; a.title='t'; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=self.CH; a.lane_id=self.LANE; a.worker_endpoint=self.EP
        a.legacy=True
        awrp.create_task(a)
        self.git(repo,'add','-A'); self.git(repo,'commit','-m','base')
        return repo
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_append_only_clean(self):
        repo=self.git_task_repo()
        r=awrp.audit_append_only(str(repo),'task_g',ref='HEAD')
        self.assertTrue(r['ok']); self.assertEqual(r['violations'],[])
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_append_only_detects_modify_and_delete(self):
        repo=self.git_task_repo()
        td=repo/'tasks'/'task_g'
        class A: pass
        a=A(); a.task_dir=str(td); a.type='DISPATCH'; a.actor_role='coordinator'; a.actor_id='chatgpt'; a.recipient_role='worker'; a.recipient_id='opencode_awrp'; a.run_id='run_g'; a.new_run=False; a.state='working'; a.phase='x'; a.waiting_on='opencode_awrp'; a.run_state='dispatched'; a.summary='go'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None
        awrp.emit(a)
        self.git(repo,'add','-A'); self.git(repo,'commit','-m','with-dispatch')
        evs=sorted((repo/'tasks'/'task_g'/'events').glob('*.json'))
        o=json.loads(evs[0].read_text()); o['summary']='rewritten'; evs[0].write_text(json.dumps(o))
        r=awrp.audit_append_only(str(repo),'task_g',ref='HEAD')
        self.assertFalse(r['ok']); self.assertEqual(r['violations'][0]['type'],'modified')
        evs[1].unlink()
        r=awrp.audit_append_only(str(repo),'task_g',ref='HEAD')
        kinds=sorted(v['type'] for v in r['violations'])
        self.assertIn('modified',kinds); self.assertIn('deleted',kinds)
class TK(unittest.TestCase):
    CH='channel_awrp_infrastructure'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self): shutil.rmtree(self.tmp,ignore_errors=True)
    def test_claim_race_one_winner(self):
        c1=awrp.acquire_claim(str(self.tmp),self.CH,'win-A')
        self.assertEqual(c1['generation'],1)
        with self.assertRaises(RuntimeError):
            awrp.acquire_claim(str(self.tmp),self.CH,'win-B',expected_generation=0)
        c2=awrp.acquire_claim(str(self.tmp),self.CH,'win-B',expected_generation=1)
        self.assertEqual((c2['generation'],c2['owner'],c2['prev_owner']),(2,'win-B','win-A'))
    def test_stale_fencing_rejects_append(self):
        (self.tmp/'contexts').mkdir()
        awrp.write_new(self.tmp/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        class A: pass
        a=A(); a.root=str(self.tmp); a.context_id='c'; a.task_id='task_k'; a.title='t'; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=self.CH; a.lane_id=None; a.worker_endpoint='ep'
        a.legacy=True
        awrp.create_task(a); td=str(self.tmp/'tasks'/'task_k')
        awrp.acquire_claim(str(self.tmp),self.CH,'coord-A')
        class E: pass
        e=E(); e.task_dir=td; e.type='RECONCILE'; e.actor_role='coordinator'; e.actor_id='coord-A'; e.recipient_role=None; e.recipient_id=None; e.run_id=None; e.new_run=False; e.state='working'; e.phase='x'; e.waiting_on='opencode'; e.run_state=None; e.summary='r'; e.details_file=None; e.artifacts_file=None; e.approval_file=None; e.causation_id=None; e.expected_head=None; e.expected_hash=None; e.claimant=None; e.fencing_generation=1
        awrp.emit(e)
        awrp.acquire_claim(str(self.tmp),self.CH,'coord-B',takeover=True)
        with self.assertRaises(RuntimeError): awrp.emit(e)
        e.fencing_generation=2; e.actor_id='coord-B'; awrp.emit(e)
    def test_readonly_inspect(self):
        self.assertIsNone(awrp.read_claim(str(self.tmp),self.CH))
        awrp.acquire_claim(str(self.tmp),self.CH,'coord-A')
        cur=awrp.read_claim(str(self.tmp),self.CH)
        self.assertEqual((cur['generation'],cur['owner']),(1,'coord-A'))
    def test_legacy_task_rejects_fencing(self):
        (self.tmp/'contexts').mkdir()
        awrp.write_new(self.tmp/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        class A: pass
        a=A(); a.root=str(self.tmp); a.context_id='c'; a.task_id='task_leg'; a.title='t'; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=None; a.lane_id=None; a.worker_endpoint=None
        a.legacy=True
        awrp.create_task(a); td=str(self.tmp/'tasks'/'task_leg')
        class E: pass
        e=E(); e.task_dir=td; e.type='RECONCILE'; e.actor_role='coordinator'; e.actor_id='chatgpt'; e.recipient_role=None; e.recipient_id=None; e.run_id=None; e.new_run=False; e.state='working'; e.phase='x'; e.waiting_on='opencode'; e.run_state=None; e.summary='r'; e.details_file=None; e.artifacts_file=None; e.approval_file=None; e.causation_id=None; e.expected_head=None; e.expected_hash=None; e.claimant=None; e.fencing_generation=1
        with self.assertRaises(RuntimeError): awrp.emit(e)
    def test_claim_ops_preserve_canonical_events(self):
        (self.tmp/'contexts').mkdir()
        awrp.write_new(self.tmp/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        class A: pass
        a=A(); a.root=str(self.tmp); a.context_id='c'; a.task_id='task_ev'; a.title='t'; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=self.CH; a.lane_id=None; a.worker_endpoint='ep'
        a.legacy=True
        awrp.create_task(a); td=self.tmp/'tasks'/'task_ev'
        before={p.name:awrp.artifact_fingerprint(str(p))['sha256'] for p in sorted((td/'events').glob('*.json'))}
        awrp.acquire_claim(str(self.tmp),self.CH,'coord-A')
        awrp.acquire_claim(str(self.tmp),self.CH,'coord-B',takeover=True)
        after={p.name:awrp.artifact_fingerprint(str(p))['sha256'] for p in sorted((td/'events').glob('*.json'))}
        self.assertEqual(before,after)
        awrp.validate(td)
    def test_fencing_mandatory_when_claim_exists(self):
        (self.tmp/'contexts').mkdir()
        awrp.write_new(self.tmp/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        class A: pass
        a=A(); a.root=str(self.tmp); a.context_id='c'; a.task_id='task_fm'; a.title='t'; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=self.CH; a.lane_id=None; a.worker_endpoint='ep'
        a.legacy=True
        awrp.create_task(a); td=str(self.tmp/'tasks'/'task_fm')
        awrp.acquire_claim(str(self.tmp),self.CH,'coord-A')
        class E: pass
        e=E(); e.task_dir=td; e.type='DISPATCH'; e.actor_role='coordinator'; e.actor_id='coord-A'; e.recipient_role='worker'; e.recipient_id='ep'; e.run_id='run_fm'; e.new_run=False; e.state='working'; e.phase='x'; e.waiting_on='ep'; e.run_state='dispatched'; e.summary='d'; e.details_file=None; e.artifacts_file=None; e.approval_file=None; e.causation_id=None; e.expected_head=None; e.expected_hash=None; e.claimant=None; e.fencing_generation=None
        with self.assertRaises(RuntimeError): awrp.emit(e)
        e.fencing_generation=1; awrp.emit(e)
        v=awrp.validate(td)
        d=[x for x in v['events'] if x['type']=='DISPATCH'][0]
        self.assertEqual(d.get('fencing'),{'channel_id':self.CH,'generation':1,'owner':'coord-A'})
    def frozen_clock(self):
        import datetime as dt
        state = {'t': 1700000000}
        real = awrp.now
        def tick():
            state['t'] += 10
            return dt.datetime.fromtimestamp(state['t'], dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        awrp.now = tick
        self.addCleanup(setattr, awrp, 'now', real)
    def craft_reconcile(self, td, fencing=None):
        v = awrp.validate(td); t = v['task']; h = v['head']
        e = {'protocol': 'awrp/0.1', 'event_id': awrp.newid('evt'), 'seq': h['seq'] + 1, 'context_id': t['context_id'], 'task_id': t['task_id'], 'run_id': None, 'type': 'RECONCILE', 'actor': {'role': 'coordinator', 'id': 'chatgpt'}, 'recipient': None, 'causation_id': None, 'created_at': awrp.now(), 'task_projection': {'state': 'working', 'phase': 'x', 'waiting_on': 'opencode'}, 'run': None, 'artifacts': [], 'summary': 'crafted', 'details': None, 'approval': None, 'integrity': {'prev_event_id': h['event_id'], 'prev_event_hash': h['integrity']['event_hash'], 'event_hash': ''}}
        if fencing is not None:
            e['fencing'] = fencing
        e['integrity']['event_hash'] = awrp.eh(e)
        awrp.write_new(Path(td) / 'events' / f"{e['seq']:06d}_{e['event_id']}.json", e)
        return e['event_id']
    def test_fencing_audit_flags_connector_bypass(self):
        self.frozen_clock()
        (self.tmp/'contexts').mkdir()
        awrp.write_new(self.tmp/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        class A: pass
        a=A(); a.root=str(self.tmp); a.context_id='c'; a.task_id='task_cb'; a.title='t'; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=self.CH; a.lane_id=None; a.worker_endpoint='ep'
        a.legacy=True
        awrp.create_task(a); td=self.tmp/'tasks'/'task_cb'
        class E: pass
        e=E(); e.task_dir=str(td); e.type='DISPATCH'; e.actor_role='coordinator'; e.actor_id='chatgpt'; e.recipient_role='worker'; e.recipient_id='ep'; e.run_id='run_cb'; e.new_run=False; e.state='working'; e.phase='x'; e.waiting_on='ep'; e.run_state='dispatched'; e.summary='d'; e.details_file=None; e.artifacts_file=None; e.approval_file=None; e.causation_id=None; e.expected_head=None; e.expected_hash=None; e.claimant=None; e.fencing_generation=None
        awrp.emit(e)
        awrp.acquire_claim(str(self.tmp),self.CH,'coord-A')
        bypass_id=self.craft_reconcile(str(td))
        r=awrp.audit_fencing(td)
        self.assertFalse(r['ok'])
        self.assertEqual([(v['event_type'],v['event_id']) for v in r['violations']],[('RECONCILE',bypass_id)])
        self.assertTrue(r['fenced'])
    def test_fencing_audit_owner_mismatch(self):
        self.frozen_clock()
        (self.tmp/'contexts').mkdir()
        awrp.write_new(self.tmp/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        class A: pass
        a=A(); a.root=str(self.tmp); a.context_id='c'; a.task_id='task_om'; a.title='t'; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=self.CH; a.lane_id=None; a.worker_endpoint='ep'
        a.legacy=True
        awrp.create_task(a); td=self.tmp/'tasks'/'task_om'
        class E: pass
        e=E(); e.task_dir=str(td); e.type='DISPATCH'; e.actor_role='coordinator'; e.actor_id='chatgpt'; e.recipient_role='worker'; e.recipient_id='ep'; e.run_id='run_om'; e.new_run=False; e.state='working'; e.phase='x'; e.waiting_on='ep'; e.run_state='dispatched'; e.summary='d'; e.details_file=None; e.artifacts_file=None; e.approval_file=None; e.causation_id=None; e.expected_head=None; e.expected_hash=None; e.claimant=None; e.fencing_generation=None
        awrp.emit(e)
        awrp.acquire_claim(str(self.tmp),self.CH,'coord-A')
        bad_id=self.craft_reconcile(str(td),fencing={'channel_id':self.CH,'generation':1,'owner':'impostor'})
        r=awrp.audit_fencing(td)
        self.assertFalse(r['ok'])
        self.assertEqual([(v['event_id']) for v in r['violations']],[bad_id])
    def test_fencing_audit_pre_claim_exempt(self):
        self.frozen_clock()
        (self.tmp/'contexts').mkdir()
        awrp.write_new(self.tmp/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        class A: pass
        a=A(); a.root=str(self.tmp); a.context_id='c'; a.task_id='task_pc'; a.title='t'; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=self.CH; a.lane_id=None; a.worker_endpoint='ep'
        a.legacy=True
        awrp.create_task(a); td=self.tmp/'tasks'/'task_pc'
        class E: pass
        e=E(); e.task_dir=str(td); e.type='DISPATCH'; e.actor_role='coordinator'; e.actor_id='chatgpt'; e.recipient_role='worker'; e.recipient_id='ep'; e.run_id='run_pc'; e.new_run=False; e.state='working'; e.phase='x'; e.waiting_on='ep'; e.run_state='dispatched'; e.summary='d'; e.details_file=None; e.artifacts_file=None; e.approval_file=None; e.causation_id=None; e.expected_head=None; e.expected_hash=None; e.claimant=None; e.fencing_generation=None
        awrp.emit(e)
        awrp.acquire_claim(str(self.tmp),self.CH,'coord-A')
        r=awrp.audit_fencing(td)
        self.assertTrue(r['ok'])
        self.assertEqual(len(r['pre_claim']),1)
    def test_pilot_bound_resume_selects_infra_only(self):
        (self.tmp/'contexts').mkdir()
        awrp.write_new(self.tmp/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        def mk(tid,ch,ep):
            class A: pass
            a=A(); a.root=str(self.tmp); a.context_id='c'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
            a.channel_id=ch; a.lane_id=None; a.worker_endpoint=ep
            a.legacy=True
            awrp.create_task(a)
            class E: pass
            e=E(); e.task_dir=str(self.tmp/'tasks'/tid); e.type='DISPATCH'; e.actor_role='coordinator'; e.actor_id='chatgpt'; e.recipient_role='worker'; e.recipient_id=ep; e.run_id='run_'+tid; e.new_run=False; e.state='working'; e.phase='x'; e.waiting_on=ep; e.run_state='dispatched'; e.summary='d'; e.details_file=None; e.artifacts_file=None; e.approval_file=None; e.causation_id=None; e.expected_head=None; e.expected_hash=None; e.claimant=None; e.fencing_generation=None
            awrp.emit(e)
        mk('task_infra','channel_awrp_infrastructure','opencode_awrp')
        mk('task_oc','channel_beta_automation','opencode_beta')
        mk('task_ms','channel_alpha_github','opencode_alpha')
        r=awrp.select_for_resume(str(self.tmp),'channel_awrp_infrastructure','opencode_awrp')
        self.assertEqual(r['status'],'EXECUTE'); self.assertEqual(r['task_id'],'task_infra')
    def git_fresh_fixture(self):
        remote=self.tmp/'r.git'; w=self.tmp/'w'
        def git(repo,*args):
            cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
            self.assertEqual(cp.returncode,0,cp.stderr)
        git(self.tmp,'init','--bare',str(remote))
        git(self.tmp,'init','-b','main',str(w))
        git(w,'config','user.email','t@e'); git(w,'config','user.name','t')
        (w/'contexts').mkdir()
        awrp.write_new(w/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        class A: pass
        a=A(); a.root=str(w); a.context_id='c'; a.task_id='task_f'; a.title='t'; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id='ch-fresh'; a.lane_id=None; a.worker_endpoint='ep-fresh'
        a.legacy=True
        awrp.create_task(a)
        class E: pass
        e=E(); e.task_dir=str(w/'tasks'/'task_f'); e.type='DISPATCH'; e.actor_role='coordinator'; e.actor_id='chatgpt'; e.recipient_role='worker'; e.recipient_id='ep-fresh'; e.run_id='run_f'; e.new_run=False; e.state='working'; e.phase='x'; e.waiting_on='ep-fresh'; e.run_state='dispatched'; e.summary='d'; e.details_file=None; e.artifacts_file=None; e.approval_file=None; e.causation_id=None; e.expected_head=None; e.expected_hash=None; e.claimant=None; e.fencing_generation=None
        awrp.emit(e)
        git(w,'add','-A'); git(w,'commit','-m','task'); git(w,'remote','add','origin',str(remote)); git(w,'push','-u','origin','main'); git(remote,'symbolic-ref','HEAD','refs/heads/main')
        ws=self.tmp/'ws'; ws.mkdir()
        class B: pass
        b=B(); b.root=str(ws); b.relay='r'; b.relay_dir=str(w); b.channel='ch-fresh'; b.worker_endpoint='ep-fresh'; b.lane=None; b.bound_by='t'; b.force=False
        awrp.do_bind(b)
        return remote,w,ws
    def do_resume(self,ws):
        import io, contextlib
        class A: pass
        a=A(); a.root=str(ws); a.channel=None; a.worker_endpoint=None; a.lane=None
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_resume(a)
        return json.loads(buf.getvalue())
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_resume_fails_on_stale_clone(self):
        remote,w,ws=self.git_fresh_fixture()
        self.assertEqual(self.do_resume(ws)['status'],'EXECUTE')
        b=self.tmp/'wb'; git2=lambda *args: subprocess.run(['git','-C',str(b),*args],capture_output=True,text=True)
        subprocess.run(['git','-C',str(self.tmp),'clone',str(remote),str(b)],check=True,capture_output=True)
        git2('config','user.email','t@e'); git2('config','user.name','t')
        (b/'other.txt').write_text('rival\n')
        for args in (['add','-A'],['commit','-m','rival'],['push','origin','main']):
            subprocess.run(['git','-C',str(b),*args],check=True,capture_output=True)
        with self.assertRaises(RuntimeError): self.do_resume(ws)
        subprocess.run(['git','-C',str(w),'pull','--ff-only'],check=True,capture_output=True)
        self.assertEqual(self.do_resume(ws)['status'],'EXECUTE')
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_ack_require_fresh_rejects_stale(self):
        remote,w,ws=self.git_fresh_fixture()
        b=self.tmp/'wb2'
        subprocess.run(['git','-C',str(self.tmp),'clone',str(remote),str(b)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.email','t@e'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.name','t@e'],check=True,capture_output=True)
        (b/'other.txt').write_text('rival\n')
        subprocess.run(['git','-C',str(b),'add','-A'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'commit','-m','rival'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'push','origin','main'],check=True,capture_output=True)
        class A: pass
        a=A(); a.task_dir=str(w/'tasks'/'task_f'); a.type='ACK'; a.actor_role='worker'; a.actor_id='ep-fresh'; a.recipient_role='coordinator'; a.recipient_id='chatgpt'; a.run_id='run_f'; a.new_run=False; a.state='working'; a.phase='x'; a.waiting_on='ep-fresh'; a.run_state='working'; a.summary='ack'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None; a.require_fresh=True
        with self.assertRaises(RuntimeError): awrp.emit(a)
        subprocess.run(['git','-C',str(w),'pull','--ff-only'],check=True,capture_output=True)
        a.require_fresh=False; awrp.emit(a)
        self.assertEqual(awrp.validate(str(w/'tasks'/'task_f'))['head']['type'],'ACK')
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_remote_single_publication_winner(self):
        remote=self.tmp/'r.git'; wa=self.tmp/'wa'; wb=self.tmp/'wb'
        def git(repo,*args):
            cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
            self.assertEqual(cp.returncode,0,cp.stderr)
        git(self.tmp,'init','--bare',str(remote))
        git(self.tmp,'init','-b','main',str(wa))
        git(wa,'config','user.email','t@e'); git(wa,'config','user.name','t')
        (wa/'tasks').mkdir(); (wa/'tasks'/'t').mkdir()
        (wa/'tasks'/'t'/'task.json').write_text('{}')
        git(wa,'add','-A'); git(wa,'commit','-m','base'); git(wa,'remote','add','origin',str(remote))
        git(wa,'push','-u','origin','main'); git(remote,'symbolic-ref','HEAD','refs/heads/main')
        git(self.tmp,'clone',str(remote),str(wb))
        git(wb,'config','user.email','t@e'); git(wb,'config','user.name','t')
        (wa/'tasks'/'t'/'evtA.json').write_text('{"seq":2,"winner":"A"}')
        git(wa,'add','-A'); git(wa,'commit','-m','A-append'); git(wa,'push','origin','main')
        (wb/'tasks'/'t'/'evtB.json').write_text('{"seq":2,"winner":"B"}')
        git(wb,'add','-A'); git(wb,'commit','-m','B-append')
        cp=subprocess.run(['git','-C',str(wb),'push','origin','main'],capture_output=True,text=True)
        self.assertNotEqual(cp.returncode,0)
        out=subprocess.run(['git','--git-dir',str(remote),'ls-tree','-r','--name-only','main'],capture_output=True,text=True)
        self.assertIn('evtA.json',out.stdout); self.assertNotIn('evtB.json',out.stdout)
        cnt=subprocess.run(['git','--git-dir',str(remote),'rev-list','--count','main'],capture_output=True,text=True).stdout.strip()
        self.assertEqual(cnt,'2')
        git(wb,'fetch','origin'); git(wb,'reset','--hard','origin/main')
        (wb/'tasks'/'t'/'evtB2.json').write_text('{"seq":3,"recomposed":true}')
        git(wb,'add','-A'); git(wb,'commit','-m','B-retry'); git(wb,'push','origin','main')
        names=subprocess.run(['git','--git-dir',str(remote),'ls-tree','-r','--name-only','main'],capture_output=True,text=True).stdout
        self.assertIn('evtA.json',names); self.assertIn('evtB2.json',names); self.assertNotIn('evtB.json',names)
class TP(unittest.TestCase):
    CH='ch-atomic'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def git(self,repo,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def pa_args(self,td,repo,branch,base,typ='RECONCILE',fg=1,state='working',run_state=None,rid=None):
        class A: pass
        a=A(); a.task_dir=str(td); a.repo=str(repo); a.branch=branch; a.remote='origin'; a.expected_base=base; a.commit_message=None
        a.type=typ; a.actor_role='coordinator'; a.actor_id='coord-A'; a.recipient_role=None; a.recipient_id=None; a.run_id=rid; a.new_run=False
        a.state=state; a.phase='x'; a.waiting_on='opencode'; a.run_state=run_state; a.summary='pa'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None
        a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=fg; a.require_fresh=False
        return a
    def mk_repo(self):
        remote=self.tmp/'r.git'; w=self.tmp/'w'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(self.tmp,'init','-b','main',str(w))
        self.git(w,'config','user.email','t@e'); self.git(w,'config','user.name','t')
        (w/'contexts').mkdir()
        awrp.write_new(w/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        class A: pass
        a=A(); a.root=str(w); a.context_id='c'; a.task_id='task_pa'; a.title='t'; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=self.CH; a.lane_id=None; a.worker_endpoint='ep'
        a.legacy=True
        awrp.create_task(a)
        awrp.acquire_claim(str(w),self.CH,'coord-A')
        self.git(w,'add','-A'); self.git(w,'commit','-m','base'); self.git(w,'remote','add','origin',str(remote))
        self.git(w,'push','-u','origin','main'); self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
        return remote,w
    def test_publish_atomic_happy(self):
        remote,w=self.mk_repo()
        base=self.git(w,'rev-parse','main')
        awrp.publish_atomic(self.pa_args(w/'tasks'/'task_pa',w,'main',base))
        evs=sorted((w/'tasks'/'task_pa'/'events').glob('*.json'))
        self.assertEqual(len(evs),2)
        v=awrp.validate(str(w/'tasks'/'task_pa'))
        self.assertEqual(v['head']['type'],'RECONCILE')
        self.assertEqual(v['head'].get('fencing'),{'channel_id':self.CH,'generation':1,'owner':'coord-A'})
        log=self.git(w,'log','--oneline','-1')
        self.assertIn('awrp: RECONCILE',log)
        self.assertEqual(self.git(remote,'rev-parse','main'),self.git(w,'rev-parse','main'))
    def test_publish_atomic_stale_base_loses_before_write(self):
        remote,w=self.mk_repo()
        base=self.git(w,'rev-parse','main')
        b=self.tmp/'wb'
        subprocess.run(['git','-C',str(self.tmp),'clone',str(remote),str(b)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.email','t@e'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.name','t@e'],check=True,capture_output=True)
        (b/'rival.txt').write_text('rival\n')
        for args in (['add','-A'],['commit','-m','rival'],['push','origin','main']):
            subprocess.run(['git','-C',str(b),*args],check=True,capture_output=True)
        before=sorted(p.name for p in (w/'tasks'/'task_pa'/'events').glob('*.json'))
        with self.assertRaises(RuntimeError):
            awrp.publish_atomic(self.pa_args(w/'tasks'/'task_pa',w,'main',base))
        after=sorted(p.name for p in (w/'tasks'/'task_pa'/'events').glob('*.json'))
        self.assertEqual(before,after)
    def test_publish_atomic_missing_claim_fails(self):
        remote,w=self.mk_repo()
        import shutil as _sh
        _sh.rmtree(w/'channels')
        base=self.git(w,'rev-parse','main')
        with self.assertRaises(RuntimeError):
            awrp.publish_atomic(self.pa_args(w/'tasks'/'task_pa',w,'main',base))
    def test_publish_atomic_stale_task_head_fails(self):
        remote,w=self.mk_repo()
        base=self.git(w,'rev-parse','main')
        h=awrp.validate(str(w/'tasks'/'task_pa'))['head']['event_id']
        awrp.publish_atomic(self.pa_args(w/'tasks'/'task_pa',w,'main',base))
        a=self.pa_args(w/'tasks'/'task_pa',w,'main',base)
        a.expected_head=h
        with self.assertRaises(RuntimeError):
            awrp.publish_atomic(a)
    def test_publish_atomic_race_one_winner(self):
        remote,w=self.mk_repo()
        base=self.git(w,'rev-parse','main')
        b=self.tmp/'wb'
        subprocess.run(['git','-C',str(self.tmp),'clone',str(remote),str(b)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.email','t@e'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.name','t@e'],check=True,capture_output=True)
        awrp.publish_atomic(self.pa_args(w/'tasks'/'task_pa',w,'main',base))
        bb=self.tmp/'wb'
        class A: pass
        a=A(); a.task_dir=str(bb/'tasks'/'task_pa'); a.repo=str(bb); a.branch='main'; a.remote='origin'; a.expected_base=base; a.commit_message=None
        a.type='RECONCILE'; a.actor_role='coordinator'; a.actor_id='coord-A'; a.recipient_role=None; a.recipient_id=None; a.run_id=None; a.new_run=False
        a.state='working'; a.phase='x'; a.waiting_on='opencode'; a.run_state=None; a.summary='pb'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None
        a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=1; a.require_fresh=False
        with self.assertRaises(RuntimeError): awrp.publish_atomic(a)
        names=subprocess.run(['git','--git-dir',str(remote),'ls-tree','-r','--name-only','main'],capture_output=True,text=True).stdout
        self.assertEqual(len([l for l in names.splitlines() if '/events/' in l and l.endswith('.json')]),2)
    def test_bypass_valid_but_nonauthoritative(self):
        (self.tmp/'contexts').mkdir()
        awrp.write_new(self.tmp/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        class A: pass
        a=A(); a.root=str(self.tmp); a.context_id='c'; a.task_id='task_bv'; a.title='t'; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=self.CH; a.lane_id=None; a.worker_endpoint='ep'
        a.legacy=True
        awrp.create_task(a); td=self.tmp/'tasks'/'task_bv'
        awrp.acquire_claim(str(self.tmp),self.CH,'coord-A')
        v=awrp.validate(td); t=v['task']; h=v['head']
        e={'protocol':'awrp/0.1','event_id':awrp.newid('evt'),'seq':h['seq']+1,'context_id':t['context_id'],'task_id':t['task_id'],'run_id':None,'type':'RECONCILE','actor':{'role':'coordinator','id':'chatgpt'},'recipient':None,'causation_id':None,'created_at':awrp.now(),'task_projection':{'state':'working','phase':'x','waiting_on':'opencode'},'run':None,'artifacts':[],'summary':'connector-direct','details':None,'approval':None,'integrity':{'prev_event_id':h['event_id'],'prev_event_hash':h['integrity']['event_hash'],'event_hash':''}}
        e['integrity']['event_hash']=awrp.eh(e)
        awrp.write_new(td/'events'/f"{e['seq']:06d}_{e['event_id']}.json",e)
        awrp.validate(td)
        r=awrp.audit_fencing(td)
        self.assertFalse(r['ok'])
        self.assertEqual(r['violations'][0]['event_type'],'RECONCILE')
class TA(unittest.TestCase):
    CH='ch-authority'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def git(self,repo,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def mkctx(self,root):
        (Path(root)/'contexts').mkdir(exist_ok=True)
        awrp.write_new(Path(root)/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
    def mk(self,tid='task_a'):
        self.mkctx(self.tmp)
        class A: pass
        a=A(); a.root=str(self.tmp); a.context_id='c'; a.task_id=tid; a.title='t'; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=self.CH; a.lane_id=None; a.worker_endpoint='ep'
        a.legacy=True
        awrp.create_task(a); return str(self.tmp/'tasks'/tid)
    def args(self,td,typ,rid=None,actor_role='coordinator',actor_id='coord-A',fg=1,state='working',run_state=None):
        class A: pass
        a=A(); a.task_dir=td; a.type=typ; a.actor_role=actor_role; a.actor_id=actor_id; a.recipient_role=None; a.recipient_id=None; a.run_id=rid; a.new_run=False
        a.state=state; a.phase='x'; a.waiting_on='opencode'; a.run_state=run_state; a.summary='x'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None
        a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=fg; a.require_fresh=False
        if typ=='DISPATCH':
            a.recipient_role='worker'; a.recipient_id='ep'; a.waiting_on='ep'
        return a
    def frozen_clock(self):
        import datetime as dt
        state={'t':1700000000}; real=awrp.now
        def tick():
            state['t']+=10
            return dt.datetime.fromtimestamp(state['t'],dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        awrp.now=tick; self.addCleanup(setattr,awrp,'now',real)
    def test_worker_fencing_rejected_seq17_style(self):
        td=self.mk(); awrp.acquire_claim(str(self.tmp),self.CH,'coord-A')
        before=sorted(p.name for p in Path(td,'events').glob('*.json'))
        with self.assertRaises(RuntimeError):
            awrp.emit(self.args(td,'RECONCILE',actor_role='worker',actor_id='opencode',fg=1))
        after=sorted(p.name for p in Path(td,'events').glob('*.json'))
        self.assertEqual(before,after)
    def test_wrong_coordinator_id_rejected(self):
        td=self.mk(); awrp.acquire_claim(str(self.tmp),self.CH,'coord-A')
        with self.assertRaises(RuntimeError):
            awrp.emit(self.args(td,'RECONCILE',actor_role='coordinator',actor_id='eve',fg=1))
    def test_claim_owner_accepted_and_stamped(self):
        td=self.mk(); awrp.acquire_claim(str(self.tmp),self.CH,'coord-A')
        awrp.emit(self.args(td,'RECONCILE',actor_role='coordinator',actor_id='coord-A',fg=1))
        v=awrp.validate(td)
        self.assertEqual(v['head'].get('fencing'),{'channel_id':self.CH,'generation':1,'owner':'coord-A'})
    def test_worker_unfenced_execution_still_allowed(self):
        td=self.mk(); awrp.acquire_claim(str(self.tmp),self.CH,'coord-A')
        awrp.emit(self.args(td,'DISPATCH','run_a',run_state='dispatched'))
        awrp.emit(self.args(td,'ACK','run_a',actor_role='worker',actor_id='ep',fg=None,run_state='working'))
        awrp.emit(self.args(td,'HANDOFF','run_a',actor_role='worker',actor_id='ep',fg=None,run_state='succeeded'))
        self.assertEqual(awrp.validate(td)['active_run_id'],None)
    def test_claim_log_is_durable_history(self):
        self.mkctx(self.tmp)
        awrp.acquire_claim(str(self.tmp),self.CH,'coord-A')
        awrp.acquire_claim(str(self.tmp),self.CH,'coord-B',expected_generation=1)
        log=awrp.read_claim_log(str(self.tmp),self.CH)
        self.assertEqual([(e['generation'],e['owner']) for e in log],[(1,'coord-A'),(2,'coord-B')])
    def test_audit_flags_worker_stamped_authority_mismatch(self):
        self.frozen_clock()
        td=self.mk(); awrp.acquire_claim(str(self.tmp),self.CH,'coord-A')
        v=awrp.validate(td); t=v['task']; h=v['head']
        e={'protocol':'awrp/0.1','event_id':awrp.newid('evt'),'seq':h['seq']+1,'context_id':t['context_id'],'task_id':t['task_id'],'run_id':None,'type':'RECONCILE','actor':{'role':'worker','id':'opencode'},'recipient':None,'causation_id':None,'created_at':awrp.now(),'task_projection':{'state':'working','phase':'x','waiting_on':'opencode'},'run':None,'artifacts':[],'summary':'seq17-style','details':None,'approval':None,'integrity':{'prev_event_id':h['event_id'],'prev_event_hash':h['integrity']['event_hash'],'event_hash':''},'fencing':{'channel_id':self.CH,'generation':1,'owner':'coord-A'}}
        e['integrity']['event_hash']=awrp.eh(e)
        awrp.write_new(Path(td)/'events'/f"{e['seq']:06d}_{e['event_id']}.json",e)
        awrp.validate(td)
        r=awrp.audit_fencing(td)
        self.assertFalse(r['ok'])
        self.assertEqual([(x['type'],x['event_id']) for x in r['violations']],[('authority_mismatch',e['event_id'])])
    def mk_conn_repo(self):
        remote=self.tmp/'rc.git'; w=self.tmp/'wc'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(self.tmp,'init','-b','main',str(w))
        self.git(w,'config','user.email','t@e'); self.git(w,'config','user.name','t')
        self.mkctx(w)
        class A: pass
        a=A(); a.root=str(w); a.context_id='c'; a.task_id='task_pc'; a.title='t'; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=self.CH; a.lane_id=None; a.worker_endpoint='ep'
        a.legacy=True
        awrp.create_task(a)
        awrp.acquire_claim(str(w),self.CH,'coord-A')
        self.git(w,'add','-A'); self.git(w,'commit','-m','base'); self.git(w,'remote','add','origin',str(remote))
        self.git(w,'push','-u','origin','main'); self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
        return remote,w,self.git(w,'rev-parse','main')
    def pc_args(self,td,repo,branch,base,actor_role='coordinator',actor_id='coord-A',fg=1,typ='RECONCILE',rid=None,plan=False):
        class A: pass
        a=A(); a.task_dir=str(td); a.repo=str(repo); a.branch=branch; a.remote='origin'; a.expected_base=base; a.commit_message=None; a.print_plan=plan
        a.type=typ; a.actor_role=actor_role; a.actor_id=actor_id; a.recipient_role=None; a.recipient_id=None; a.run_id=rid; a.new_run=False
        a.state='working'; a.phase='x'; a.waiting_on='opencode'; a.run_state=None; a.summary='pc'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None
        a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=fg; a.require_fresh=False
        return a
    def worktree_clean(self,w):
        self.assertEqual(self.git(w,'status','--porcelain'),'')
    def test_publish_connector_happy_no_worktree_trace(self):
        remote,w,base=self.mk_conn_repo()
        out=awrp.publish_connector(self.pc_args(w/'tasks'/'task_pc',w,'main',base))
        self.assertIsNone(out)
        parent=self.git(remote,'rev-list','--parents','-1','main').split()
        self.assertEqual(parent[1],base)
        names=subprocess.run(['git','--git-dir',str(remote),'ls-tree','-r','--name-only','main'],capture_output=True,text=True).stdout
        evs=[l for l in names.splitlines() if '/events/' in l and l.endswith('.json')]
        self.assertEqual(len(evs),2)
        self.assertIn('TASK.md',names)
        self.assertEqual(len(list((w/'tasks'/'task_pc'/'events').glob('*.json'))),1)
        self.assertEqual(self.git(w,'rev-parse','main'),base)
        self.worktree_clean(w)
    def test_publish_connector_stale_base_no_trace(self):
        remote,w,base=self.mk_conn_repo()
        b=self.tmp/'wb'
        subprocess.run(['git','-C',str(self.tmp),'clone',str(remote),str(b)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.email','t@e'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.name','t@e'],check=True,capture_output=True)
        (b/'rival.txt').write_text('rival\n')
        for args in (['add','-A'],['commit','-m','rival'],['push','origin','main']):
            subprocess.run(['git','-C',str(b),*args],check=True,capture_output=True)
        with self.assertRaises(RuntimeError):
            awrp.publish_connector(self.pc_args(w/'tasks'/'task_pc',w,'main',base))
        self.assertEqual(self.git(remote,'rev-parse','main'),self.git(b,'rev-parse','main'))
        self.assertEqual(len(list((w/'tasks'/'task_pc'/'events').glob('*.json'))),1)
        self.worktree_clean(w)
    def test_publish_connector_missing_claim_fails(self):
        remote,w,base=self.mk_conn_repo()
        shutil.rmtree(w/'channels')
        with self.assertRaises(RuntimeError):
            awrp.publish_connector(self.pc_args(w/'tasks'/'task_pc',w,'main',base))
    def test_publish_connector_wrong_actor_fails(self):
        remote,w,base=self.mk_conn_repo()
        with self.assertRaises(RuntimeError):
            awrp.publish_connector(self.pc_args(w/'tasks'/'task_pc',w,'main',base,actor_id='eve'))
        with self.assertRaises(RuntimeError):
            awrp.publish_connector(self.pc_args(w/'tasks'/'task_pc',w,'main',base,actor_role='worker',actor_id='opencode'))
        self.worktree_clean(w)
    def test_publish_connector_stale_head_fails(self):
        remote,w,base=self.mk_conn_repo()
        awrp.publish_connector(self.pc_args(w/'tasks'/'task_pc',w,'main',base))
        newbase=self.git(remote,'rev-parse','main')
        h1=subprocess.run(['git','--git-dir',str(remote),'ls-tree','-r','--name-only','main'],capture_output=True,text=True).stdout
        a=self.pc_args(w/'tasks'/'task_pc',w,'main',newbase)
        a.expected_head='evt_bogus'
        with self.assertRaises(RuntimeError):
            awrp.publish_connector(a)
        h2=subprocess.run(['git','--git-dir',str(remote),'ls-tree','-r','--name-only','main'],capture_output=True,text=True).stdout
        self.assertEqual(h1,h2)
    def test_publish_connector_race_one_winner(self):
        remote,w,base=self.mk_conn_repo()
        b=self.tmp/'wb'
        subprocess.run(['git','-C',str(self.tmp),'clone',str(remote),str(b)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.email','t@e'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.name','t@e'],check=True,capture_output=True)
        awrp.publish_connector(self.pc_args(w/'tasks'/'task_pc',w,'main',base))
        with self.assertRaises(RuntimeError):
            awrp.publish_connector(self.pc_args(b/'tasks'/'task_pc',b,'main',base))
        names=subprocess.run(['git','--git-dir',str(remote),'ls-tree','-r','--name-only','main'],capture_output=True,text=True).stdout
        self.assertEqual(len([l for l in names.splitlines() if '/events/' in l and l.endswith('.json')]),2)
        self.worktree_clean(b)
    def test_publish_connector_print_plan_no_mutation(self):
        import io, contextlib
        remote,w,base=self.mk_conn_repo()
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf):
            awrp.publish_connector(self.pc_args(w/'tasks'/'task_pc',w,'main',base,plan=True))
        plan=json.loads(buf.getvalue())
        self.assertEqual(plan['api_plan']['parents'],[base])
        self.assertFalse(plan['api_plan']['force'])
        self.assertIn('create-commit',str(plan['api_plan']['steps']))
        self.assertEqual(plan['event']['actor'],{'role':'coordinator','id':'coord-A'})
        self.assertEqual(self.git(remote,'rev-parse','main'),base)
        self.assertEqual(len(list((w/'tasks'/'task_pc'/'events').glob('*.json'))),1)
        self.worktree_clean(w)
class TB(unittest.TestCase):
    CH='ch-proj'; EP='ep-proj'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def git(self,repo,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def mkctx(self,root):
        (Path(root)/'contexts').mkdir(exist_ok=True)
        awrp.write_new(Path(root)/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
    def mkproj(self,root,pid,channels=()):
        return awrp.project_create(str(root),pid,'T-'+pid,channels,None,'chatgpt')
    def mktask(self,root,tid,channel=CH,endpoint=EP,project=None):
        class A: pass
        a=A(); a.root=str(root); a.context_id='c'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=channel; a.lane_id=None; a.worker_endpoint=endpoint; a.project_id=project
        a.legacy=True
        awrp.create_task(a); return str(Path(root)/'tasks'/tid)
    def dis(self,td,rid):
        _ep=(json.loads((Path(td)/'task.json').read_text(encoding='utf-8')).get('routing') or {}).get('worker_endpoint') or 'opencode'
        class A: pass
        a=A(); a.task_dir=td; a.type='DISPATCH'; a.actor_role='coordinator'; a.actor_id='chatgpt'; a.recipient_role='worker'; a.recipient_id=_ep; a.run_id=rid; a.new_run=False; a.state='working'; a.phase='x'; a.waiting_on=_ep; a.run_state='dispatched'; a.summary='go'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None; a.legacy_route=True
        awrp.emit(a)
    def test_channel_exclusive_two_projects(self):
        self.mkproj(self.tmp,'proj-a',(self.CH,))
        with self.assertRaises(RuntimeError):
            self.mkproj(self.tmp,'proj-b',(self.CH,))
        with self.assertRaises(RuntimeError):
            awrp.project_assign_channel(str(self.tmp),'proj-b',self.CH)
        self.assertEqual(awrp.channel_project(str(self.tmp),self.CH),'proj-a')
        r=awrp.project_assign_channel(str(self.tmp),'proj-a',self.CH)
        self.assertEqual(r['channels'],[self.CH])
    def test_create_task_project_validation(self):
        self.mkctx(self.tmp)
        with self.assertRaises(RuntimeError):
            self.mktask(self.tmp,'task_x',project='proj-ghost')
        self.mkproj(self.tmp,'proj-a',('ch-owned',))
        with self.assertRaises(RuntimeError):
            self.mktask(self.tmp,'task_y',channel='ch-other',project='proj-a')
        td=self.mktask(self.tmp,'task_ok',channel='ch-owned',project='proj-a')
        self.assertEqual(json.loads((Path(td)/'task.json').read_text())['project_id'],'proj-a')
        awrp.validate(td)
    def test_bind_project_agreement(self):
        self.mkproj(self.tmp,'proj-a',(self.CH,))
        ws=self.tmp/'ws'; ws.mkdir()
        class A: pass
        def bind(project):
            a=A(); a.root=str(ws); a.relay='r'; a.relay_dir=str(self.tmp); a.channel=self.CH; a.worker_endpoint=self.EP; a.lane=None; a.project_id=project; a.bound_by='t'; a.force=True
            awrp.do_bind(a)
        with self.assertRaises(RuntimeError): bind('proj-ghost')
        self.mkproj(self.tmp,'proj-b',('ch-b',))
        with self.assertRaises(RuntimeError): bind('proj-b')
        bind('proj-a')
        self.assertEqual(awrp.read_binding(str(ws))['project_id'],'proj-a')
    def test_resume_project_scope(self):
        self.mkctx(self.tmp)
        td=self.mktask(self.tmp,'task_leg'); self.dis(td,'run_leg')
        ws=self.tmp/'ws'; ws.mkdir()
        self.mkproj(self.tmp,'proj-a',(self.CH,))
        class A: pass
        a=A(); a.root=str(ws); a.relay='r'; a.relay_dir=str(self.tmp); a.channel=self.CH; a.worker_endpoint=self.EP; a.lane=None; a.project_id='proj-a'; a.bound_by='t'; a.force=False
        awrp.do_bind(a)
        r=awrp.select_for_resume(str(self.tmp),self.CH,self.EP,None,'proj-a')
        self.assertEqual(r['status'],'EXECUTE')
        tp=Path(td)/'task.json'; o=json.loads(tp.read_text()); o['project_id']='proj-a'; tp.write_text(json.dumps(o))
        r=awrp.select_for_resume(str(self.tmp),self.CH,self.EP,None,'proj-a')
        self.assertEqual(r['status'],'EXECUTE')
        self.mkproj(self.tmp,'proj-b')
        o['project_id']='proj-b'; tp.write_text(json.dumps(o))
        r=awrp.select_for_resume(str(self.tmp),self.CH,self.EP,None,'proj-a')
        # Ownership mismatch fails validation, so the verdict is the
        # (still non-executable) INVALID_CANONICAL with forensics intact.
        self.assertEqual(r['status'],'INVALID_CANONICAL')
        self.assertEqual(len(r['invalid_canonical']),1)
    def test_legacy_bytes_untouched_by_project_ops(self):
        self.mkctx(self.tmp)
        td=self.mktask(self.tmp,'task_leg'); self.dis(td,'run_leg')
        before={p.name:awrp.artifact_fingerprint(str(p))['sha256'] for p in sorted((Path(td)/'events').glob('*.json'))}
        self.mkproj(self.tmp,'proj-a',(self.CH,))
        awrp.validate(td)
        after={p.name:awrp.artifact_fingerprint(str(p))['sha256'] for p in sorted((Path(td)/'events').glob('*.json'))}
        self.assertEqual(before,after)
    def git_relay_fixture(self):
        remote=self.tmp/'r.git'; w=self.tmp/'w'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(self.tmp,'init','-b','main',str(w))
        self.git(w,'config','user.email','t@e'); self.git(w,'config','user.name','t')
        self.mkctx(w)
        self.mkproj(w,'proj-a',(self.CH,))
        td=self.mktask(w,'task_pb',project='proj-a')
        self.dis(td,'run_pb')
        self.git(w,'add','-A'); self.git(w,'commit','-m','relay'); self.git(w,'remote','add','origin',str(remote))
        self.git(w,'push','-u','origin','main'); self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
        return remote,w
    def bind_ws(self,ws,relay):
        ws.mkdir(exist_ok=True)
        class A: pass
        a=A(); a.root=str(ws); a.relay='Bruce-Yii/awrp'; a.relay_dir=str(relay); a.channel=self.CH; a.worker_endpoint=self.EP; a.lane=None; a.project_id='proj-a'; a.bound_by='t'; a.force=False
        awrp.do_bind(a)
    def fb_args(self,ws,relay=None,task_id='task_pb',run_id=None):
        import io, contextlib
        class A: pass
        a=A(); a.root=str(ws); a.relay='Bruce-Yii/awrp'; a.relay_dir=relay; a.project_id='proj-a'; a.channel=self.CH; a.worker_endpoint=self.EP; a.task_id=task_id; a.run_id=run_id; a.lane=None; a.bound_by='t'
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_first_bind(a)
        return json.loads(buf.getvalue())
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_first_bind_verify_path_execute(self):
        remote,w=self.git_relay_fixture()
        ws=self.tmp/'ws'; self.bind_ws(ws,w)
        r=self.fb_args(ws)
        self.assertEqual(r['status'],'EXECUTE'); self.assertEqual(r['run_id'],'run_pb')
        self.assertTrue(r['head_event_id'] and r['head_hash'])
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_first_bind_create_path_and_run_match(self):
        remote,w=self.git_relay_fixture()
        ws=self.tmp/'ws2'; ws.mkdir()
        r=self.fb_args(ws,str(w))
        self.assertEqual(r['status'],'EXECUTE')
        self.assertEqual(awrp.read_binding(str(ws))['project_id'],'proj-a')
        with self.assertRaises(RuntimeError):
            self.fb_args(ws,str(w),run_id='run_other')
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_first_bind_rejects_mismatch_and_conflict(self):
        remote,w=self.git_relay_fixture()
        ws=self.tmp/'ws'; self.bind_ws(ws,w)
        with self.assertRaises(RuntimeError):
            self.fb_args(ws,task_id='task_ghost')
        other=self.tmp/'other'; other.mkdir()
        td=self.mktask(w,'task_other',project='proj-a')
        self.dis(td,'run_other')
        self.git(w,'add','-A'); self.git(w,'commit','-m','other'); self.git(w,'push','origin','main')
        with self.assertRaises(RuntimeError):
            self.fb_args(ws,task_id='task_other',run_id='run_pb')
        ws3=self.tmp/'ws3'; ws3.mkdir()
        self.mkproj(w,'proj-b',('ch-b',))
        class A: pass
        a=A(); a.root=str(ws3); a.relay='Bruce-Yii/awrp'; a.relay_dir=str(w); a.channel='ch-b'; a.worker_endpoint=self.EP; a.lane=None; a.project_id='proj-a'; a.bound_by='t'; a.force=False
        with self.assertRaises(RuntimeError): awrp.do_bind(a)
    def test_first_bind_requires_exact_target(self):
        class A: pass
        a=A(); a.root=str(self.tmp); a.relay='r'; a.relay_dir=str(self.tmp); a.project_id='p'; a.channel='c'; a.worker_endpoint='e'; a.task_id=None; a.run_id=None; a.lane=None; a.bound_by='t'
        with self.assertRaises(RuntimeError): awrp.do_first_bind(a)
class TD(unittest.TestCase):
    CH='ch-bridge'; EP='ep-bridge'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def git(self,repo,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def mkctx(self,root):
        (Path(root)/'contexts').mkdir(exist_ok=True)
        awrp.write_new(Path(root)/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
    def mkproj(self,root,pid,channels=()):
        return awrp.project_create(str(root),pid,'T-'+pid,channels,None,'chatgpt')
    def mktask(self,root,tid,channel=CH,endpoint=EP,project=None):
        class A: pass
        a=A(); a.root=str(root); a.context_id='c'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=channel; a.lane_id=None; a.worker_endpoint=endpoint; a.project_id=project
        a.legacy=True
        awrp.create_task(a); return str(Path(root)/'tasks'/tid)
    def dis(self,td,rid):
        _ep=(json.loads((Path(td)/'task.json').read_text(encoding='utf-8')).get('routing') or {}).get('worker_endpoint') or 'opencode'
        class A: pass
        a=A(); a.task_dir=td; a.type='DISPATCH'; a.actor_role='coordinator'; a.actor_id='chatgpt'; a.recipient_role='worker'; a.recipient_id=_ep; a.run_id=rid; a.new_run=False; a.state='working'; a.phase='x'; a.waiting_on=_ep; a.run_state='dispatched'; a.summary='go'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None; a.legacy_route=True
        awrp.emit(a)
    def out(self,fn,*args):
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): fn(*args)
        return json.loads(buf.getvalue())
    def test_probe_never_selects(self):
        self.mkctx(self.tmp)
        m=self.mktask(self.tmp,'task_m','ch-m','ep-m'); self.dis(m,'run_m')
        o=self.mktask(self.tmp,'task_o','ch-o','ep-o'); self.dis(o,'run_o')
        r=self.out(awrp.do_probe_project,type('A',(),{'root':str(self.tmp)})())
        self.assertEqual(r['status'],'PROJECT_BIND_REQUIRED')
        self.mkproj(self.tmp,'proj-a',('ch-m',))
        self.mkproj(self.tmp,'proj-b',('ch-o',))
        r=self.out(awrp.do_probe_project,type('A',(),{'root':str(self.tmp)})())
        self.assertEqual(r['status'],'AMBIGUOUS')
        self.assertNotIn('task_id',json.dumps(r)); self.assertNotIn('run_m',json.dumps(r))
        self.mkproj(self.tmp,'proj-solo',('ch-solo',))
        r=self.out(awrp.do_probe_project,type('A',(),{'root':str(self.tmp)})())
        self.assertEqual(r['status'],'AMBIGUOUS')
    def test_render_bootstrap_exact(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CH,))
        (Path(self.tmp)/'relay.json').write_text(json.dumps({'protocol':'awrp/0.1','relay':'Bruce-Yii/awrp'}),encoding='utf-8')
        td=self.mktask(self.tmp,'task_r',project='proj-a')
        self.assertEqual(json.loads((Path(td)/'task.json').read_text())['transport'],{'relay_repo':'Bruce-Yii/awrp'})
        self.dis(td,'run_r')
        class A: pass
        a=A(); a.root=str(self.tmp); a.project_id='proj-a'; a.task_id='task_r'; a.run_id=None
        r1=self.out(awrp.do_render_bootstrap,a)
        r2=self.out(awrp.do_render_bootstrap,a)
        self.assertEqual(r1,r2)
        self.assertEqual((r1['project_id'],r1['channel_id'],r1['worker_endpoint'],r1['task_id'],r1['run_id']),('proj-a',self.CH,self.EP,'task_r','run_r'))
        self.assertIn('first-bind',r1['command']); self.assertIn('run_r',r1['command'])
        v=awrp.validate(td)
        self.assertEqual((r1['head_event_id'],r1['head_hash']),(v['head']['event_id'],v['head']['integrity']['event_hash']))
    def test_render_rejects_mismatch(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CH,))
        td=self.mktask(self.tmp,'task_r',project='proj-a'); self.dis(td,'run_r')
        class A: pass
        a=A(); a.root=str(self.tmp); a.project_id='proj-a'; a.task_id='task_ghost'; a.run_id=None
        with self.assertRaises(RuntimeError): awrp.do_render_bootstrap(a)
        a.task_id='task_r'; a.project_id='proj-other'
        with self.assertRaises(RuntimeError): awrp.do_render_bootstrap(a)
        a.project_id='proj-a'; a.run_id='run_other'
        with self.assertRaises(RuntimeError): awrp.do_render_bootstrap(a)
    def test_binding_project_conflict(self):
        self.mkproj(self.tmp,'proj-a',(self.CH,))
        ws=self.tmp/'ws'; ws.mkdir()
        class A: pass
        a=A(); a.root=str(ws); a.relay='r'; a.relay_dir=str(self.tmp); a.channel=self.CH; a.worker_endpoint=self.EP; a.lane=None; a.project_id='proj-a'; a.bound_by='t'; a.force=False
        awrp.do_bind(a)
        self.assertEqual(awrp.read_binding(str(ws))['project_id'],'proj-a')
        a.project_id='proj-b'; a.force=False
        with self.assertRaises(RuntimeError): awrp.do_bind(a)
        self.assertEqual(awrp.read_binding(str(ws))['project_id'],'proj-a')
    def test_legacy_bridge_requires_association(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CH,))
        td=self.mktask(self.tmp,'task_leg'); self.dis(td,'run_leg')
        v=awrp.validate(td); t=v['task']
        with self.assertRaises(RuntimeError):
            awrp.require_migration(str(self.tmp),'proj-a','task_leg',t)
        m=awrp.migration_associate(str(self.tmp),'proj-a','task_leg','test bridge')
        self.assertEqual((m['project_id'],m['task_id'],m['channel_id']),('proj-a','task_leg',self.CH))
        self.assertEqual(awrp.require_migration(str(self.tmp),'proj-a','task_leg',t)['task_id'],'task_leg')
    def test_migration_conflicts_rejected(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CH,))
        self.mkproj(self.tmp,'proj-b',('ch-b',))
        td=self.mktask(self.tmp,'task_leg'); self.dis(td,'run_leg')
        with self.assertRaises(RuntimeError):
            awrp.migration_associate(str(self.tmp),'proj-b','task_leg','wrong project')
        with self.assertRaises(RuntimeError):
            awrp.migration_associate(str(self.tmp),'proj-a','task_ghost','ghost')
        td2=self.mktask(self.tmp,'task_scoped',project='proj-a')
        with self.assertRaises(RuntimeError):
            awrp.migration_associate(str(self.tmp),'proj-a','task_scoped','not legacy')
        m=awrp.migration_associate(str(self.tmp),'proj-a','task_leg','ok')
        p=Path(str(self.tmp))/'projects'/'proj-a'/'migrations'/'task_leg.json'
        o=json.loads(p.read_text()); o['channel_id']='ch-evil'; p.write_text(json.dumps(o))
        v=awrp.validate(td)
        with self.assertRaises(RuntimeError):
            awrp.require_migration(str(self.tmp),'proj-a','task_leg',v['task'])
    def git_relay_fixture(self,legacy=True):
        remote=self.tmp/'r.git'; w=self.tmp/'w'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(self.tmp,'init','-b','main',str(w))
        self.git(w,'config','user.email','t@e'); self.git(w,'config','user.name','t')
        self.mkctx(w)
        self.mkproj(w,'proj-a',(self.CH,))
        if legacy:
            td=self.mktask(w,'task_leg'); self.dis(td,'run_leg')
            awrp.migration_associate(str(w),'proj-a','task_leg','fixture')
        else:
            td=self.mktask(w,'task_scoped',project='proj-a'); self.dis(td,'run_scoped')
        self.git(w,'add','-A'); self.git(w,'commit','-m','relay'); self.git(w,'remote','add','origin',str(remote))
        self.git(w,'push','-u','origin','main'); self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
        return remote,w
    def fb(self,ws,relay,task_id,run_id=None,project='proj-a'):
        class A: pass
        a=A(); a.root=str(ws); a.relay='Bruce-Yii/awrp'; a.relay_dir=str(relay); a.project_id=project; a.channel=self.CH; a.worker_endpoint=self.EP; a.task_id=task_id; a.run_id=run_id; a.lane=None; a.bound_by='t'
        return self.out(awrp.do_first_bind,a)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_first_bind_legacy_bridge_execute(self):
        remote,w=self.git_relay_fixture(legacy=True)
        ws=self.tmp/'ws'; ws.mkdir()
        r=self.fb(ws,w,'task_leg','run_leg')
        self.assertEqual((r['status'],r['run_id']),('EXECUTE','run_leg'))
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_first_bind_legacy_without_bridge_rejected(self):
        remote,w=self.git_relay_fixture(legacy=True)
        import shutil as _sh
        _sh.rmtree(w/'projects'/'proj-a'/'migrations')
        ws=self.tmp/'ws'; ws.mkdir()
        with self.assertRaises(RuntimeError):
            self.fb(ws,w,'task_leg','run_leg')
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_first_bind_scoped_still_green(self):
        remote,w=self.git_relay_fixture(legacy=False)
        ws=self.tmp/'ws'; ws.mkdir()
        r=self.fb(ws,w,'task_scoped','run_scoped')
        self.assertEqual(r['status'],'EXECUTE')
        self.assertEqual(r['binding']['project_id'],'proj-a')
    def test_authority_orthogonal_to_projects(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CH,))
        td=self.mktask(self.tmp,'task_f',project='proj-a')
        awrp.acquire_claim(str(self.tmp),self.CH,'coord-A')
        class A: pass
        a=A(); a.task_dir=td; a.type='DISPATCH'; a.actor_role='coordinator'; a.actor_id='coord-A'; a.recipient_role='worker'; a.recipient_id='ep-bridge'; a.run_id='run_f'; a.new_run=False; a.state='working'; a.phase='x'; a.waiting_on='ep-bridge'; a.run_state='dispatched'; a.summary='d'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=1; a.require_fresh=False; a.legacy_route=True
        awrp.emit(a)
        v=awrp.validate(td)
        self.assertEqual(v['head'].get('fencing'),{'channel_id':self.CH,'generation':1,'owner':'coord-A'})
class TE(unittest.TestCase):
    CH='ch-guard'; EP='ep-guard'; LA='lane-a'; LB='lane-b'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def git(self,repo,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def mkctx(self,root):
        (Path(root)/'contexts').mkdir(exist_ok=True)
        awrp.write_new(Path(root)/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
    def mkproj(self,root,pid,channels=()):
        return awrp.project_create(str(root),pid,'T-'+pid,channels,None,'chatgpt')
    def mktask(self,root,tid,lane,project=None,endpoint=EP,channel=CH):
        class A: pass
        a=A(); a.root=str(root); a.context_id='c'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=channel; a.lane_id=lane; a.worker_endpoint=endpoint; a.project_id=project
        a.legacy=True
        awrp.create_task(a); return str(Path(root)/'tasks'/tid)
    def dis(self,td,rid):
        _ep=(json.loads((Path(td)/'task.json').read_text(encoding='utf-8')).get('routing') or {}).get('worker_endpoint') or 'opencode'
        class A: pass
        a=A(); a.task_dir=td; a.type='DISPATCH'; a.actor_role='coordinator'; a.actor_id='chatgpt'; a.recipient_role='worker'; a.recipient_id=_ep; a.run_id=rid; a.new_run=False; a.state='working'; a.phase='x'; a.waiting_on=_ep; a.run_state='dispatched'; a.summary='go'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None; a.legacy_route=True
        awrp.emit(a)
    def bind(self,ws,relay,lane=LA,project=None,endpoint=EP,channel=CH,force=False):
        ws.mkdir(exist_ok=True)
        class A: pass
        a=A(); a.root=str(ws); a.relay='Bruce-Yii/awrp'; a.relay_dir=str(relay); a.channel=channel; a.worker_endpoint=endpoint; a.lane=lane; a.project_id=project; a.bound_by='t'; a.force=force
        awrp.do_bind(a)
    def out(self,fn,args):
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): fn(args)
        return json.loads(buf.getvalue())
    def fb(self,ws,relay,task_id,run_id=None,lane=None,project=None,channel=CH,endpoint=EP):
        class A: pass
        a=A(); a.root=str(ws); a.relay='Bruce-Yii/awrp'; a.relay_dir=str(relay); a.project_id=project; a.channel=channel; a.worker_endpoint=endpoint; a.task_id=task_id; a.run_id=run_id; a.lane=lane; a.bound_by='t'
        return self.out(awrp.do_first_bind,a)
    def plan(self,ws,task_id,run_id=None):
        class A: pass
        a=A(); a.binding_root=str(ws); a.task_id=task_id; a.run_id=run_id
        return self.out(awrp.do_plan_dispatch,a)
    def test_lane_pin_strict(self):
        self.mkctx(self.tmp)
        td=self.mktask(self.tmp,'task_a',self.LA); self.dis(td,'run_a')
        ws=self.tmp/'ws'; self.bind(ws,self.tmp,lane=self.LA)
        r=awrp.select_for_resume(str(self.tmp),self.CH,self.EP,self.LA,None)
        self.assertEqual((r['status'],r['task_id']),('EXECUTE','task_a'))
        td2=self.mktask(self.tmp,'task_b',self.LB); self.dis(td2,'run_b')
        r=awrp.select_for_resume(str(self.tmp),self.CH,self.EP,self.LB,None)
        self.assertEqual((r['status'],r['task_id']),('EXECUTE','task_b'))
        r=awrp.select_for_resume(str(self.tmp),self.CH,self.EP,'lane-ghost',None)
        self.assertEqual(r['status'],'NO_TASK')
    def test_lane_pin_crossing_rejected_before_side_effects(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CH,))
        td=self.mktask(self.tmp,'task_a',self.LA,project='proj-a'); self.dis(td,'run_a')
        ws=self.tmp/'ws'; self.bind(ws,self.tmp,lane=self.LA,project='proj-a')
        before_bind=(ws/'.awrp'/'binding.json').read_bytes()
        before_ev=sorted(p.name for p in (Path(td)/'events').glob('*.json'))
        with self.assertRaises(RuntimeError):
            self.fb(ws,self.tmp,'task_a','run_a',lane=self.LB,project='proj-a')
        self.assertEqual((ws/'.awrp'/'binding.json').read_bytes(),before_bind)
        self.assertEqual(sorted(p.name for p in (Path(td)/'events').glob('*.json')),before_ev)
    def test_plan_dispatch_visible_path(self):
        self.mkctx(self.tmp)
        td=self.mktask(self.tmp,'task_a',self.LA); self.dis(td,'run_a')
        ws=self.tmp/'ws'; self.bind(ws,self.tmp,lane=self.LA)
        r=self.plan(ws,'task_a','run_a')
        self.assertTrue(r['visible'])
        self.assertEqual(r['binding_route'],{'project_id':None,'channel_id':self.CH,'lane_id':self.LA,'worker_endpoint':self.EP})
        self.assertEqual(r['task_route'],r['binding_route'])
        s=awrp.select_for_resume(str(self.tmp),self.CH,self.EP,self.LA,None)
        self.assertEqual((s['status'],s['run_id']),('EXECUTE','run_a'))
    def test_plan_rejects_mismatch(self):
        self.mkctx(self.tmp)
        awrp.project_create(str(self.tmp),'proj-a','A',(self.CH,),None,'chatgpt')
        awrp.project_create(str(self.tmp),'proj-b','B',('ch-b',),None,'chatgpt')
        td2=self.mktask(self.tmp,'task_x2',self.LA,project='proj-b',endpoint=self.EP,channel='ch-b')
        self.dis(td2,'run_x2')
        ws=self.tmp/'ws'; self.bind(ws,self.tmp,lane=self.LA,project='proj-a')
        r=self.plan(ws,'task_x2','run_x2')
        self.assertFalse(r['visible'])
        self.assertNotEqual(r['binding_route'],r['task_route'])
        with self.assertRaises(RuntimeError):
            self.fb(ws,self.tmp,'task_x2','run_x2',lane='lane-ghost',project='proj-a')
    def test_unpinned_project_scope(self):
        self.mkctx(self.tmp)
        awrp.project_create(str(self.tmp),'proj-a','A',(self.CH,),None,'chatgpt')
        td=self.mktask(self.tmp,'task_1',None,project='proj-a'); self.dis(td,'run_1')
        r=awrp.select_for_resume(str(self.tmp),self.CH,self.EP,None,'proj-a')
        self.assertEqual((r['status'],r['task_id']),('EXECUTE','task_1'))
        td2=self.mktask(self.tmp,'task_2',None,project='proj-a'); self.dis(td2,'run_2')
        r=awrp.select_for_resume(str(self.tmp),self.CH,self.EP,None,'proj-a')
        self.assertEqual(r['status'],'AMBIGUOUS')
    def git_pair(self):
        remote=self.tmp/'r.git'; w=self.tmp/'w'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(self.tmp,'init','-b','main',str(w))
        self.git(w,'config','user.email','t@e'); self.git(w,'config','user.name','t')
        return remote,w
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_incident_first_bind_matches_resume(self):
        remote,w=self.git_pair()
        self.mkctx(w)
        self.mkproj(w,'proj-a',(self.CH,))
        td=self.mktask(w,'task_b',self.LB,project='proj-a'); self.dis(td,'run_b')
        self.git(w,'add','-A'); self.git(w,'commit','-m','relay'); self.git(w,'remote','add','origin',str(remote))
        self.git(w,'push','-u','origin','main'); self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
        ws=self.tmp/'ws'; self.bind(ws,w,lane=self.LA,project='proj-a')
        before=sorted(p.name for p in (Path(td)/'events').glob('*.json'))
        with self.assertRaises(RuntimeError):
            self.fb(ws,w,'task_b','run_b',project='proj-a')
        self.assertEqual(sorted(p.name for p in (Path(td)/'events').glob('*.json')),before)
        r=awrp.select_for_resume(str(w),self.CH,self.EP,self.LA,None)
        self.assertEqual(r['status'],'NO_TASK')
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_dispatch_continue_receives_intended_run(self):
        remote,w=self.git_pair()
        self.mkctx(w)
        self.mkproj(w,'proj-a',(self.CH,))
        td=self.mktask(w,'task_w',self.LA,project='proj-a'); self.dis(td,'run_w')
        self.git(w,'add','-A'); self.git(w,'commit','-m','relay'); self.git(w,'remote','add','origin',str(remote))
        self.git(w,'push','-u','origin','main'); self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
        ws=self.tmp/'ws'; self.bind(ws,w,lane=self.LA,project='proj-a')
        r=self.fb(ws,w,'task_w','run_w',project='proj-a')
        self.assertEqual((r['status'],r['task_id'],r['run_id']),('EXECUTE','task_w','run_w'))
        s=awrp.select_for_resume(str(w),self.CH,self.EP,self.LA,None)
        self.assertEqual((s['status'],s['task_id'],s['run_id']),('EXECUTE','task_w','run_w'))
class TF(unittest.TestCase):
    CH='ch-pre'; EP='ep-pre'; LA='lane-pa'; LB='lane-pb'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def mkctx(self,root):
        (Path(root)/'contexts').mkdir(exist_ok=True)
        awrp.write_new(Path(root)/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
    def mkproj(self,root,pid,channels=()):
        return awrp.project_create(str(root),pid,'T-'+pid,channels,None,'chatgpt')
    def mktask(self,root,tid,lane,project=None,endpoint=EP,channel=CH):
        class A: pass
        a=A(); a.root=str(root); a.context_id='c'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=channel; a.lane_id=lane; a.worker_endpoint=endpoint; a.project_id=project
        a.legacy=True
        awrp.create_task(a); return str(Path(root)/'tasks'/tid)
    def dis(self,td,rid):
        _ep=(json.loads((Path(td)/'task.json').read_text(encoding='utf-8')).get('routing') or {}).get('worker_endpoint') or 'opencode'
        class A: pass
        a=A(); a.task_dir=td; a.type='DISPATCH'; a.actor_role='coordinator'; a.actor_id='chatgpt'; a.recipient_role='worker'; a.recipient_id=_ep; a.run_id=rid; a.new_run=False; a.state='working'; a.phase='x'; a.waiting_on=_ep; a.run_state='dispatched'; a.summary='go'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None; a.legacy_route=True
        awrp.emit(a)
    def rec(self,td):
        class A: pass
        a=A(); a.task_dir=td; a.type='RECONCILE'; a.actor_role='coordinator'; a.actor_id='chatgpt'; a.recipient_role=None; a.recipient_id=None; a.run_id=None; a.new_run=False; a.state='submitted'; a.phase='intake'; a.waiting_on='chatgpt'; a.run_state=None; a.summary='r'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None
        awrp.emit(a)
    def bind(self,ws,relay,lane=LA,project=None,endpoint=EP,channel=CH,force=False):
        ws.mkdir(exist_ok=True)
        class A: pass
        a=A(); a.root=str(ws); a.relay='Bruce-Yii/awrp'; a.relay_dir=str(relay); a.channel=channel; a.worker_endpoint=endpoint; a.lane=lane; a.project_id=project; a.bound_by='t'; a.force=force
        awrp.do_bind(a)
    def out(self,fn,args):
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): fn(args)
        return json.loads(buf.getvalue())
    def plan(self,ws,task_id,run_id=None):
        class A: pass
        a=A(); a.binding_root=str(ws); a.task_id=task_id; a.run_id=run_id; a.branch='main'
        return self.out(awrp.do_plan_dispatch,a)
    def dg(self,ws,task_id,run_id,plan=None,head=None):
        _b=awrp.read_binding(str(ws)); _td=Path(_b['relay_dir'])/'tasks'/task_id
        _ep=(json.loads((_td/'task.json').read_text(encoding='utf-8')).get('routing') or {}).get('worker_endpoint') or 'opencode'
        class A: pass
        a=A(); a.binding_root=str(ws); a.task_id=task_id; a.branch='main'; a.expected_plan=plan
        a.run_id=run_id; a.new_run=False
        a.actor_role='coordinator'; a.actor_id='chatgpt'; a.recipient_role='worker'; a.recipient_id=_ep
        a.state='working'; a.phase='x'; a.waiting_on=_ep; a.run_state='dispatched'; a.summary='go'
        a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None
        a.expected_head=head; a.expected_hash=None; a.claimant=None; a.fencing_generation=None
        return self.out(awrp.do_dispatch_guarded,a)
    def evcount(self,td): return len(list((Path(td)/'events').glob('*.json')))
    def test_preplan_without_active_run(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CH,))
        td=self.mktask(self.tmp,'task_p',self.LA,project='proj-a')
        ws=self.tmp/'ws'; self.bind(ws,self.tmp,lane=self.LA,project='proj-a')
        r=self.plan(ws,'task_p')
        self.assertTrue(r['plannable'])
        self.assertEqual(r['route'],{'project_id':'proj-a','channel_id':self.CH,'lane_id':self.LA,'worker_endpoint':self.EP})
        self.assertTrue(r['plan_fingerprint'].startswith('awrp-plan/v1:sha256:'))
        self.assertIsNone(r['active_run_id'])
    def test_guarded_rejects_lane_mismatch_no_write(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CH,))
        td=self.mktask(self.tmp,'task_b',self.LB,project='proj-a')
        ws=self.tmp/'ws'; self.bind(ws,self.tmp,lane=self.LA,project='proj-a')
        before=self.evcount(td)
        with self.assertRaises(RuntimeError):
            self.dg(ws,'task_b','run_b')
        self.assertEqual(self.evcount(td),before)
    def test_guarded_success_then_resume(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CH,))
        td=self.mktask(self.tmp,'task_g',self.LA,project='proj-a')
        ws=self.tmp/'ws'; self.bind(ws,self.tmp,lane=self.LA,project='proj-a')
        p=self.plan(ws,'task_g')
        h=awrp.validate(td)['head']['event_id']
        d=self.dg(ws,'task_g','run_g',plan=p['plan_fingerprint'],head=h)
        self.assertEqual(d['run_id'],'run_g')
        self.assertEqual(d['plan_fingerprint'],p['plan_fingerprint'])
        s=awrp.select_for_resume(str(self.tmp),self.CH,self.EP,self.LA,'proj-a')
        self.assertEqual((s['status'],s['task_id'],s['run_id']),('EXECUTE','task_g','run_g'))
    def test_guard_fails_on_binding_drift(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CH,))
        td=self.mktask(self.tmp,'task_g',self.LA,project='proj-a')
        ws=self.tmp/'ws'; self.bind(ws,self.tmp,lane=self.LA,project='proj-a')
        p=self.plan(ws,'task_g')
        before=self.evcount(td)
        self.bind(ws,self.tmp,lane=self.LB,project='proj-a',force=True)
        h=awrp.validate(td)['head']['event_id']
        with self.assertRaises(RuntimeError):
            self.dg(ws,'task_g','run_g',plan=p['plan_fingerprint'],head=h)
        self.assertEqual(self.evcount(td),before)
    def test_guard_fails_on_task_head_drift(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CH,))
        td=self.mktask(self.tmp,'task_g',self.LA,project='proj-a')
        ws=self.tmp/'ws'; self.bind(ws,self.tmp,lane=self.LA,project='proj-a')
        p=self.plan(ws,'task_g')
        h=awrp.validate(td)['head']['event_id']
        self.rec(td)
        before=self.evcount(td)
        with self.assertRaises(RuntimeError):
            self.dg(ws,'task_g','run_g',plan=p['plan_fingerprint'],head=h)
        self.assertEqual(self.evcount(td),before)
    def test_cross_mismatches_rejected(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CH,))
        self.mkproj(self.tmp,'proj-b',('ch-b',),)
        tdx=self.mktask(self.tmp,'task_x',self.LA,project='proj-b',endpoint=self.EP,channel='ch-b')
        ws=self.tmp/'ws'; self.bind(ws,self.tmp,lane=self.LA,project='proj-a')
        r=self.plan(ws,'task_x')
        self.assertIs(r['plannable'],False)
        with self.assertRaises(RuntimeError):
            self.dg(ws,'task_x','run_x')
        tde=self.mktask(self.tmp,'task_e',self.LA,project='proj-a',endpoint='ep-evil')
        r=self.plan(ws,'task_e')
        self.assertFalse(r['plannable'])
        with self.assertRaises(RuntimeError):
            self.dg(ws,'task_e','run_e')
    def test_named_invariant_preplan_guarded_continue(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CH,))
        td=self.mktask(self.tmp,'task_n',self.LA,project='proj-a')
        ws=self.tmp/'ws'; self.bind(ws,self.tmp,lane=self.LA,project='proj-a')
        p=self.plan(ws,'task_n')
        self.assertTrue(p['plannable'])
        h=awrp.validate(td)['head']['event_id']
        d=self.dg(ws,'task_n','run_n',plan=p['plan_fingerprint'],head=h)
        s=awrp.select_for_resume(str(self.tmp),self.CH,self.EP,self.LA,'proj-a')
        self.assertEqual((s['status'],s['task_id'],s['run_id']),('EXECUTE','task_n',d['run_id']))
class TI(unittest.TestCase):
    CH='ch-guard3'; EP='ep-guard3'; LA='lane-ga'; LB='lane-gb'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def git(self,repo,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def mkctx(self,root):
        (Path(root)/'contexts').mkdir(exist_ok=True)
        awrp.write_new(Path(root)/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
    def mkproj(self,root,pid,channels=()):
        return awrp.project_create(str(root),pid,'T-'+pid,channels,None,'chatgpt')
    def mktask(self,root,tid,lane,project=None,endpoint=EP,channel=CH):
        class A: pass
        a=A(); a.root=str(root); a.context_id='c'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=channel; a.lane_id=lane; a.worker_endpoint=endpoint; a.project_id=project
        a.legacy=True
        awrp.create_task(a); return str(Path(root)/'tasks'/tid)
    def raw_dis(self,td,rid,legacy=False):
        _ep=(json.loads((Path(td)/'task.json').read_text(encoding='utf-8')).get('routing') or {}).get('worker_endpoint') or 'opencode'
        class A: pass
        a=A(); a.task_dir=td; a.type='DISPATCH'; a.actor_role='coordinator'; a.actor_id='chatgpt'; a.recipient_role='worker'; a.recipient_id=_ep; a.run_id=rid; a.new_run=False; a.state='working'; a.phase='x'; a.waiting_on=_ep; a.run_state='dispatched'; a.summary='go'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None; a.legacy_route=legacy
        awrp.emit(a)
    def bind(self,ws,relay,lane=LA,project=None,endpoint=EP,channel=CH,force=False):
        ws.mkdir(exist_ok=True)
        class A: pass
        a=A(); a.root=str(ws); a.relay='Bruce-Yii/awrp'; a.relay_dir=str(relay); a.channel=channel; a.worker_endpoint=endpoint; a.lane=lane; a.project_id=project; a.bound_by='t'; a.force=force
        awrp.do_bind(a)
    def out(self,fn,args):
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): fn(args)
        return json.loads(buf.getvalue())
    def plan(self,ws=None,task_id=None,run_id=None,relay=None,project=None,channel=None,endpoint=None,lane=None):
        class A: pass
        a=A()
        if ws is None:
            a.binding_root=None; a.no_binding=True; a.root=str(relay); a.project_id=project; a.channel=channel; a.worker_endpoint=endpoint; a.lane=lane
        else:
            a.binding_root=str(ws); a.no_binding=False; a.root=str(relay or self.tmp)
        a.task_id=task_id; a.run_id=run_id; a.branch='main'
        return self.out(awrp.do_plan_dispatch,a)
    def dg(self,ws,task_id,run_id,plan=None,head=None,repo=None,nobind=False,project=None,channel=None,endpoint=None,lane=None,publish=False,actor_id='chatgpt',fg=None):
        class A: pass
        a=A()
        if nobind:
            a.binding_root=None; a.no_binding=True; a.project_id=project; a.channel=channel; a.worker_endpoint=endpoint; a.lane=lane
        else:
            a.binding_root=str(ws); a.no_binding=False
        a.task_id=task_id; a.branch='main'; a.remote='origin'; a.repo=repo; a.publish=publish; a.commit_message=None; a.expected_plan=plan
        a.run_id=run_id; a.new_run=False
        a.actor_role='coordinator'; a.actor_id=actor_id; a.recipient_role='worker'; a.recipient_id='ep-guard3'
        a.state='working'; a.phase='x'; a.waiting_on='ep-guard3'; a.run_state='dispatched'; a.summary='go'
        a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None
        a.expected_head=head; a.expected_hash=None; a.claimant=None; a.fencing_generation=fg
        return self.out(awrp.do_dispatch_guarded,a)
    def evcount(self,td): return len(list((Path(td)/'events').glob('*.json')))
    def test_raw_emit_bypass_rejected(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CH,))
        td=self.mktask(self.tmp,'task_r',self.LA,project='proj-a')
        before=self.evcount(td)
        with self.assertRaises(RuntimeError):
            self.raw_dis(td,'run_r',legacy=False)
        self.assertEqual(self.evcount(td),before)
        self.raw_dis(td,'run_r',legacy=True)
        self.assertEqual(awrp.validate(td)['active_run_id'],'run_r')
    def test_atomic_connector_bypass_rejected(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CH,))
        td=self.mktask(self.tmp,'task_r',self.LA,project='proj-a')
        def pa_args(typ):
            class A: pass
            a=A(); a.task_dir=str(td); a.repo=str(self.tmp); a.branch='main'; a.remote='origin'; a.expected_base='deadbeef'; a.commit_message=None; a.print_plan=False
            a.type=typ; a.actor_role='coordinator'; a.actor_id='chatgpt'; a.recipient_role='worker'; a.recipient_id='ep-guard3'; a.run_id='run_r'; a.new_run=False
            a.state='working'; a.phase='x'; a.waiting_on='ep-guard3'; a.run_state='dispatched'; a.summary='x'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None
            a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None; a.require_fresh=False; a.legacy_route=False
            return a
        with self.assertRaises(RuntimeError):
            awrp.publish_atomic(pa_args('DISPATCH'))
        with self.assertRaises(RuntimeError):
            awrp.publish_connector(pa_args('DISPATCH'))
        self.assertEqual(self.evcount(td),1)
    def test_guarded_wrong_route_zero_effects(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CH,))
        td=self.mktask(self.tmp,'task_b',self.LB,project='proj-a')
        ws=self.tmp/'ws'; self.bind(ws,self.tmp,lane=self.LA,project='proj-a')
        before=self.evcount(td)
        with self.assertRaises(RuntimeError):
            self.dg(ws,'task_b','run_b')
        self.assertEqual(self.evcount(td),before)
    def test_fencing_mismatch_rejects_guarded(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CH,))
        td=self.mktask(self.tmp,'task_f',self.LA,project='proj-a')
        ws=self.tmp/'ws'; self.bind(ws,self.tmp,lane=self.LA,project='proj-a')
        awrp.acquire_claim(str(self.tmp),self.CH,'coord-A')
        before=self.evcount(td)
        with self.assertRaises(RuntimeError):
            self.dg(ws,'task_f','run_f',actor_id='eve',fg=1)
        self.assertEqual(self.evcount(td),before)
    def test_unbound_explicit_path(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CH,))
        td=self.mktask(self.tmp,'task_u',self.LA,project='proj-a')
        ws=self.tmp/'ws'; ws.mkdir()
        p=self.plan(None,'task_u',relay=self.tmp,project='proj-a',channel=self.CH,endpoint=self.EP,lane=self.LA)
        self.assertTrue(p['plannable']); self.assertEqual(p['mode'],'unbound')
        before=self.evcount(td)
        d=self.dg(None,'task_u','run_u',repo=str(self.tmp),nobind=True,project='proj-a',channel=self.CH,endpoint=self.EP,lane=self.LA)
        self.assertEqual(d['run_id'],'run_u')
        self.assertFalse((ws/'.awrp').exists())
        self.assertEqual(awrp.validate(td)['active_run_id'],'run_u')
        class A: pass
        a=A(); a.binding_root=None; a.no_binding=True; a.root=str(self.tmp); a.project_id='proj-a'; a.channel=self.CH; a.worker_endpoint=self.EP; a.lane=self.LA; a.task_id='task_u'; a.run_id=None; a.branch='main'
        with self.assertRaises(RuntimeError):
            self.out(awrp.do_dispatch_guarded,a)
        self.assertEqual(self.evcount(td),before+1)
    def test_guard_fails_on_binding_drift(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CH,))
        td=self.mktask(self.tmp,'task_g',self.LA,project='proj-a')
        ws=self.tmp/'ws'; self.bind(ws,self.tmp,lane=self.LA,project='proj-a')
        p=self.plan(ws,'task_g')
        h=awrp.validate(td)['head']['event_id']
        self.bind(ws,self.tmp,lane=self.LB,project='proj-a',force=True)
        before=self.evcount(td)
        with self.assertRaises(RuntimeError):
            self.dg(ws,'task_g','run_g',plan=p['plan_fingerprint'],head=h)
        self.assertEqual(self.evcount(td),before)
    def test_guard_fails_on_task_head_drift(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CH,))
        td=self.mktask(self.tmp,'task_g',self.LA,project='proj-a')
        ws=self.tmp/'ws'; self.bind(ws,self.tmp,lane=self.LA,project='proj-a')
        p=self.plan(ws,'task_g')
        h=awrp.validate(td)['head']['event_id']
        class A: pass
        a=A(); a.task_dir=td; a.type='RECONCILE'; a.actor_role='coordinator'; a.actor_id='chatgpt'; a.recipient_role=None; a.recipient_id=None; a.run_id=None; a.new_run=False; a.state='working'; a.phase='x'; a.waiting_on='opencode'; a.run_state=None; a.summary='r'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None; a.legacy_route=True
        awrp.emit(a)
        before=self.evcount(td)
        with self.assertRaises(RuntimeError):
            self.dg(ws,'task_g','run_g',plan=p['plan_fingerprint'],head=h)
        self.assertEqual(self.evcount(td),before)
    def git_pair(self):
        remote=self.tmp/'r.git'; w=self.tmp/'w'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(self.tmp,'init','-b','main',str(w))
        self.git(w,'config','user.email','t@e'); self.git(w,'config','user.name','t')
        return remote,w
    def git_relay(self):
        remote,w=self.git_pair()
        self.mkctx(w)
        self.mkproj(w,'proj-a',(self.CH,))
        return remote,w
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_guarded_publish_success_resume_execute(self):
        remote,w=self.git_relay()
        td=self.mktask(w,'task_p',self.LA,project='proj-a')
        self.git(w,'add','-A'); self.git(w,'commit','-m','relay'); self.git(w,'remote','add','origin',str(remote))
        self.git(w,'push','-u','origin','main'); self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
        ws=self.tmp/'ws'; self.bind(ws,w,lane=self.LA,project='proj-a')
        base=self.git(remote,'rev-parse','main')
        p=self.plan(ws,'task_p')
        self.assertTrue(p['plannable'])
        h=awrp.validate(td)['head']['event_id']
        d=self.dg(ws,'task_p','run_p',plan=p['plan_fingerprint'],head=h,repo=str(w),publish=True)
        self.assertEqual(d['published_head'],self.git(remote,'rev-parse','main'))
        self.assertNotEqual(d['published_head'],base)
        s=awrp.select_for_resume(str(w),self.CH,self.EP,self.LA,'proj-a')
        self.assertEqual((s['status'],s['task_id'],s['run_id']),('EXECUTE','task_p','run_p'))
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_stale_remote_rejects_before_publication(self):
        remote,w=self.git_relay()
        td=self.mktask(w,'task_p',self.LA,project='proj-a')
        self.git(w,'add','-A'); self.git(w,'commit','-m','relay'); self.git(w,'remote','add','origin',str(remote))
        self.git(w,'push','-u','origin','main'); self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
        ws=self.tmp/'ws'; self.bind(ws,w,lane=self.LA,project='proj-a')
        p=self.plan(ws,'task_p')
        h=awrp.validate(td)['head']['event_id']
        b=self.tmp/'wb'
        subprocess.run(['git','-C',str(self.tmp),'clone',str(remote),str(b)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.email','t@e'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.name','t@e'],check=True,capture_output=True)
        (b/'rival.txt').write_text('rival\n')
        for args in (['add','-A'],['commit','-m','rival'],['push','origin','main']):
            subprocess.run(['git','-C',str(b),*args],check=True,capture_output=True)
        rival=self.git(remote,'rev-parse','main')
        before=self.evcount(td)
        with self.assertRaises(RuntimeError):
            self.dg(ws,'task_p','run_p',plan=p['plan_fingerprint'],head=h,repo=str(w),publish=True)
        self.assertEqual(self.evcount(td),before)
        self.assertEqual(self.git(remote,'rev-parse','main'),rival)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_named_invariant_bound_preplan_guarded_cas_continue(self):
        remote,w=self.git_relay()
        td=self.mktask(w,'task_n',self.LA,project='proj-a')
        self.git(w,'add','-A'); self.git(w,'commit','-m','relay'); self.git(w,'remote','add','origin',str(remote))
        self.git(w,'push','-u','origin','main'); self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
        ws=self.tmp/'ws'; self.bind(ws,w,lane=self.LA,project='proj-a')
        p=self.plan(ws,'task_n')
        self.assertTrue(p['plannable'])
        h=awrp.validate(td)['head']['event_id']
        d=self.dg(ws,'task_n','run_n',plan=p['plan_fingerprint'],head=h,repo=str(w),publish=True)
        s=awrp.select_for_resume(str(w),self.CH,self.EP,self.LA,'proj-a')
        self.assertEqual((s['status'],s['task_id'],s['run_id']),('EXECUTE','task_n',d['run_id']))
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_named_bypass_invariant_raw_rejected_zero_effects(self):
        remote,w=self.git_relay()
        td=self.mktask(w,'task_v',self.LA,project='proj-a')
        self.git(w,'add','-A'); self.git(w,'commit','-m','relay'); self.git(w,'remote','add','origin',str(remote))
        self.git(w,'push','-u','origin','main'); self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
        base=self.git(remote,'rev-parse','main')
        before=self.evcount(td)
        with self.assertRaises(RuntimeError):
            self.raw_dis(td,'run_v',legacy=False)
        self.assertEqual(self.evcount(td),before)
        self.assertEqual(self.git(remote,'rev-parse','main'),base)
class TJ(unittest.TestCase):
    CHA='ch-ja'; CHB='ch-jb'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def mkctx(self,root):
        (Path(root)/'contexts').mkdir(exist_ok=True)
        awrp.write_new(Path(root)/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
    def mkproj(self,root,pid,channels=(),notion=None):
        return awrp.project_create(str(root),pid,'T-'+pid,channels,notion,'chatgpt')
    def mktask(self,root,tid,channel,project=None):
        class A: pass
        a=A(); a.root=str(root); a.context_id='c'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=channel; a.lane_id=None; a.worker_endpoint='ep'; a.project_id=project
        a.legacy=True
        awrp.create_task(a); return str(Path(root)/'tasks'/tid)
    def dis(self,td,rid,fg=None,actor_id='chatgpt'):
        class A: pass
        a=A(); a.task_dir=td; a.type='DISPATCH'; a.actor_role='coordinator'; a.actor_id=actor_id; a.recipient_role='worker'; a.recipient_id='ep'; a.run_id=rid; a.new_run=False; a.state='working'; a.phase='x'; a.waiting_on='ep'; a.run_state='dispatched'; a.summary='go'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=fg; a.legacy_route=True
        awrp.emit(a)
    def ack(self,td,rid):
        class A: pass
        a=A(); a.task_dir=td; a.type='ACK'; a.actor_role='worker'; a.actor_id='ep'; a.recipient_role='coordinator'; a.recipient_id='chatgpt'; a.run_id=rid; a.new_run=False; a.state='working'; a.phase='x'; a.waiting_on='opencode'; a.run_state='working'; a.summary='ack'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None
        awrp.emit(a)
    def out(self,fn,args):
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): fn(args)
        return json.loads(buf.getvalue())
    def attach(self,ws,relay,pid):
        class A: pass
        a=A(); a.root=str(ws); a.relay_dir=str(relay); a.project_id=pid; a.by='test'
        return self.out(awrp.do_attach,a)
    def switch(self,ws,relay,pid,tid=None,rid=None):
        class A: pass
        a=A(); a.root=str(ws); a.relay_dir=str(relay); a.project_id=pid; a.task_id=tid; a.run_id=rid
        return self.out(awrp.do_switch,a)
    def focus(self,ws,relay):
        class A: pass
        a=A(); a.root=str(ws); a.relay_dir=str(relay)
        return self.out(awrp.do_focus,a)
    def lineage(self,ws,relay,pid,tid,rid=None):
        class A: pass
        a=A(); a.root=str(ws); a.relay_dir=str(relay); a.project_id=pid; a.task_id=tid; a.run_id=rid
        return self.out(awrp.do_check_lineage,a)
    def mkws(self,name='ws'):
        ws=self.tmp/name; ws.mkdir(exist_ok=True); return ws
    def test_two_coordinators_share_read_fenced_writes(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CHA,))
        before=awrp.artifact_fingerprint(str(self.tmp/'channels'/self.CHA/'claim.json')) if (self.tmp/'channels'/self.CHA/'claim.json').exists() else None
        awrp.acquire_claim(str(self.tmp),self.CHA,'coord-A')
        cpath=str(self.tmp/'channels'/self.CHA/'claim.json'); chash=awrp.artifact_fingerprint(cpath)['sha256']
        self.attach(self.mkws('ws1'),self.tmp,'proj-a')
        self.attach(self.mkws('ws2'),self.tmp,'proj-a')
        self.assertEqual(awrp.artifact_fingerprint(cpath)['sha256'],chash)
        td=self.mktask(self.tmp,'task_c',self.CHA,project='proj-a')
        with self.assertRaises(RuntimeError):
            self.dis(td,'run_c',fg=None)
        self.dis(td,'run_c',fg=1,actor_id='coord-A')
        self.assertEqual(awrp.validate(td)['active_run_id'],'run_c')
        self.assertIsNone(before)
    def test_switch_changes_focus(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CHA,)); self.mkproj(self.tmp,'proj-b',(self.CHB,))
        ws=self.mkws()
        self.attach(ws,self.tmp,'proj-a'); self.attach(ws,self.tmp,'proj-b')
        self.switch(ws,self.tmp,'proj-a')
        self.assertEqual(self.focus(ws,self.tmp)['current']['project_id'],'proj-a')
        self.switch(ws,self.tmp,'proj-b')
        self.assertEqual(self.focus(ws,self.tmp)['current']['project_id'],'proj-b')
        with self.assertRaises(RuntimeError):
            self.switch(ws,self.tmp,'proj-ghost')
    def git(self,repo,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_worker_switch_stays(self):
        rel=self.tmp/'relay'; rel.mkdir()
        self.mkctx(rel)
        self.mkproj(rel,'proj-a',(self.CHA,)); self.mkproj(rel,'proj-b',(self.CHB,))
        ta=self.mktask(rel,'task_a',self.CHA,project='proj-a'); self.dis(ta,'run_a')
        tb=self.mktask(rel,'task_b',self.CHB,project='proj-b'); self.dis(tb,'run_b')
        remote=self.tmp/'r.git'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(rel,'init','-b','main')
        self.git(rel,'config','user.email','t@e'); self.git(rel,'config','user.name','t')
        self.git(rel,'add','-A'); self.git(rel,'commit','-m','relay')
        self.git(rel,'remote','add','origin',str(remote)); self.git(rel,'push','-u','origin','main')
        ws=self.mkws()
        self.attach(ws,rel,'proj-a'); self.attach(ws,rel,'proj-b')
        self.switch(ws,rel,'proj-a','task_a','run_a')
        self.assertEqual(self.focus(ws,rel)['status'],'FOCUS_EXECUTE')
        self.switch(ws,rel,'proj-b','task_b','run_b')
        f=self.focus(ws,rel)
        self.assertEqual((f['status'],f['current']['project_id'],f['current']['run_id']),('FOCUS_EXECUTE','proj-b','run_b'))
    def test_one_project_two_tasks(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CHA,))
        ta=self.mktask(self.tmp,'task_pra',self.CHA,project='proj-a'); self.dis(ta,'run_pra')
        tb=self.mktask(self.tmp,'task_prb',self.CHA,project='proj-a'); self.dis(tb,'run_prb')
        class A: pass
        a=A(); a.root=str(self.tmp); a.channel=None; a.worker_endpoint=None; a.task_id=None; a.legacy=False; a.project='proj-a'
        got=sorted(t['task_id'] for t in self.out(awrp.do_inbox,a)['actionable'])
        self.assertEqual(got,['task_pra','task_prb'])
        self.assertEqual(awrp.list_projects(str(self.tmp)),['proj-a'])
    def test_concurrent_workers_same_project(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CHA,))
        ta=self.mktask(self.tmp,'task_1',self.CHA,project='proj-a'); self.dis(ta,'run_1')
        tb=self.mktask(self.tmp,'task_2',self.CHA,project='proj-a'); self.dis(tb,'run_2')
        self.ack(ta,'run_1')
        self.ack(tb,'run_2')
        self.assertEqual(awrp.validate(ta)['runs']['run_1']['state'],'working')
        self.assertEqual(awrp.validate(tb)['runs']['run_2']['state'],'working')
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_same_run_double_claim_rejected(self):
        rel=self.tmp/'relay'; rel.mkdir()
        self.mkctx(rel)
        self.mkproj(rel,'proj-a',(self.CHA,))
        td=self.mktask(rel,'task_d',self.CHA,project='proj-a'); self.dis(td,'run_d')
        remote=self.tmp/'r.git'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(rel,'init','-b','main')
        self.git(rel,'config','user.email','t@e'); self.git(rel,'config','user.name','t')
        self.git(rel,'add','-A'); self.git(rel,'commit','-m','relay')
        self.git(rel,'remote','add','origin',str(remote)); self.git(rel,'push','-u','origin','main')
        ws=self.mkws()
        self.attach(ws,rel,'proj-a')
        self.switch(ws,rel,'proj-a','task_d','run_d')
        self.ack(td,'run_d')
        self.assertEqual(self.focus(ws,rel)['status'],'FOCUS_OWNED')
        with self.assertRaises(RuntimeError):
            self.ack(td,'run_d')
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_lineage_guard(self):
        rel=self.tmp/'relay'; rel.mkdir()
        self.mkctx(rel)
        self.mkproj(rel,'proj-a',(self.CHA,)); self.mkproj(rel,'proj-b',(self.CHB,))
        ta=self.mktask(rel,'task_a',self.CHA,project='proj-a'); self.dis(ta,'run_a')
        tb=self.mktask(rel,'task_b',self.CHB,project='proj-b'); self.dis(tb,'run_b')
        remote=self.tmp/'r.git'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(rel,'init','-b','main')
        self.git(rel,'config','user.email','t@e'); self.git(rel,'config','user.name','t')
        self.git(rel,'add','-A'); self.git(rel,'commit','-m','relay')
        self.git(rel,'remote','add','origin',str(remote)); self.git(rel,'push','-u','origin','main')
        ws=self.mkws()
        self.attach(ws,rel,'proj-a')
        self.switch(ws,rel,'proj-a','task_a','run_a')
        r=self.lineage(ws,rel,'proj-a','task_a','run_a')
        self.assertTrue(r['match'])
        r=self.lineage(ws,rel,'proj-b','task_b','run_b')
        self.assertFalse(r['match'])
        self.assertEqual(r['canonical']['run_id'],'run_b')
        ws2=self.mkws('ws2')
        r=self.lineage(ws2,rel,'proj-a','task_a','run_a')
        self.assertIsNone(r['match'])
    def test_fresh_attach_exact(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CHA,))
        ws=self.mkws()
        r=self.attach(ws,self.tmp,'proj-a')
        self.assertEqual((r['current']['project_id'],r['attached']),('proj-a',['proj-a']))
        with self.assertRaises(RuntimeError):
            self.attach(ws,self.tmp,'proj-ghost')
    def test_no_project_fail_closed(self):
        ws=self.mkws()
        class A: pass
        a=A(); a.root=str(ws); a.relay_dir=str(self.tmp)
        with self.assertRaises(RuntimeError):
            awrp.do_focus(a)
        r=self.out(awrp.do_probe_project,type('A',(),{'root':str(self.tmp)})())
        self.assertEqual(r['status'],'PROJECT_BIND_REQUIRED')
    def test_legacy_compat(self):
        self.mkctx(self.tmp)
        td=self.mktask(self.tmp,'task_leg',self.CHA)
        self.dis(td,'run_leg')
        ws=self.mkws()
        class A: pass
        a=A(); a.root=str(ws); a.relay='r'; a.relay_dir=str(self.tmp); a.channel=self.CHA; a.worker_endpoint='ep'; a.lane=None; a.project_id=None; a.bound_by='t'; a.force=False
        awrp.do_bind(a)
        r=awrp.select_for_resume(str(self.tmp),self.CHA,'ep',None,None)
        self.assertEqual((r['status'],r['task_id']),('EXECUTE','task_leg'))
        b=A(); b.root=str(ws); b.relay_dir=str(self.tmp)
        with self.assertRaises(RuntimeError):
            awrp.do_focus(b)
class TL(unittest.TestCase):
    CHA='ch-la'; CHB='ch-lb'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def git(self,repo,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def mkctx(self,root):
        (Path(root)/'contexts').mkdir(exist_ok=True)
        awrp.write_new(Path(root)/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
    def mkproj(self,root,pid,channels=()):
        return awrp.project_create(str(root),pid,'T-'+pid,channels,None,'chatgpt')
    def mktask(self,root,tid,channel,project=None):
        class A: pass
        a=A(); a.root=str(root); a.context_id='c'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=channel; a.lane_id=None; a.worker_endpoint='ep'; a.project_id=project
        a.legacy=True
        awrp.create_task(a); return str(Path(root)/'tasks'/tid)
    def dis(self,td,rid):
        class A: pass
        a=A(); a.task_dir=td; a.type='DISPATCH'; a.actor_role='coordinator'; a.actor_id='chatgpt'; a.recipient_role='worker'; a.recipient_id='ep'; a.run_id=rid; a.new_run=False; a.state='working'; a.phase='x'; a.waiting_on='ep'; a.run_state='dispatched'; a.summary='go'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None; a.legacy_route=True
        awrp.emit(a)
    def out(self,fn,args):
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): fn(args)
        return json.loads(buf.getvalue())
    def attach(self,ws,relay,pid):
        class A: pass
        a=A(); a.root=str(ws); a.relay_dir=str(relay); a.project_id=pid; a.by='test'
        return self.out(awrp.do_attach,a)
    def switch(self,ws,relay,pid,tid=None,rid=None):
        class A: pass
        a=A(); a.root=str(ws); a.relay_dir=str(relay); a.project_id=pid; a.task_id=tid; a.run_id=rid
        return self.out(awrp.do_switch,a)
    def focus(self,ws,relay):
        class A: pass
        a=A(); a.root=str(ws); a.relay_dir=str(relay)
        return self.out(awrp.do_focus,a)
    def lineage(self,ws,relay,pid,tid,rid=None):
        class A: pass
        a=A(); a.root=str(ws); a.relay_dir=str(relay); a.project_id=pid; a.task_id=tid; a.run_id=rid
        return self.out(awrp.do_check_lineage,a)
    def mkws(self,name='ws'):
        ws=self.tmp/name; ws.mkdir(exist_ok=True); return ws
    def git_relay(self):
        rel=self.tmp/'relay'; rel.mkdir()
        self.mkctx(rel)
        remote=self.tmp/'r.git'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(rel,'init','-b','main')
        self.git(rel,'config','user.email','t@e'); self.git(rel,'config','user.name','t')
        return remote,rel
    def commit_push(self,rel,remote,msg='relay'):
        self.git(rel,'add','-A'); self.git(rel,'commit','-m',msg)
        self.git(rel,'remote','add','origin',str(remote)); self.git(rel,'push','-u','origin','main')
        self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_focus_stale_remote_no_execute(self):
        remote,rel=self.git_relay()
        self.mkproj(rel,'proj-a',(self.CHA,))
        td=self.mktask(rel,'task_f',self.CHA,project='proj-a'); self.dis(td,'run_f')
        self.commit_push(rel,remote)
        ws=self.mkws()
        self.attach(ws,rel,'proj-a')
        self.switch(ws,rel,'proj-a','task_f','run_f')
        self.assertEqual(self.focus(ws,rel)['status'],'FOCUS_EXECUTE')
        b=self.tmp/'wb'
        subprocess.run(['git','-C',str(self.tmp),'clone',str(remote),str(b)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.email','t@e'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.name','t@e'],check=True,capture_output=True)
        (b/'rival.txt').write_text('rival\n')
        for args in (['add','-A'],['commit','-m','rival'],['push','origin','main']):
            subprocess.run(['git','-C',str(b),*args],check=True,capture_output=True)
        r=self.focus(ws,rel)
        self.assertEqual(r['status'],'FOCUS_NOT_FRESH')
        self.assertNotIn('head_hash',json.dumps(r))
    def test_session_lock_conflict_no_silent_loss(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CHA,)); self.mkproj(self.tmp,'proj-b',(self.CHB,))
        ws=self.mkws()
        self.attach(ws,self.tmp,'proj-a')
        sp=ws/'.awrp'/'session.json'
        before=sp.read_bytes()
        lp=ws/'.awrp'/'session.lock.json'
        lp.write_text(json.dumps({'pid':999999,'time':awrp.now(),'token':'holder'}),encoding='utf-8')
        with self.assertRaises(RuntimeError):
            self.attach(ws,self.tmp,'proj-b')
        self.assertEqual(sp.read_bytes(),before)
        lp.write_text(json.dumps({'pid':999999,'time':'2000-01-01T00:00:00Z','token':'stale'}),encoding='utf-8')
        r=self.attach(ws,self.tmp,'proj-b')
        self.assertEqual(sorted(r['attached']),['proj-a','proj-b'])
        self.assertEqual(r['generation'],2)
    def test_corrupt_session_fails_closed(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CHA,))
        ws=self.mkws()
        sp=ws/'.awrp'/'session.json'; sp.parent.mkdir(parents=True,exist_ok=True)
        sp.write_bytes(b'{not json')
        with self.assertRaises(RuntimeError):
            self.attach(ws,self.tmp,'proj-a')
        self.assertEqual(sp.read_bytes(),b'{not json')
        sp.write_text(json.dumps({'protocol':'awrp/0.0','attached':[],'current':{}}),encoding='utf-8')
        with self.assertRaises(RuntimeError):
            self.attach(ws,self.tmp,'proj-a')
        sp.write_text(json.dumps({'protocol':'awrp/0.1','attached':{},'current':{}}),encoding='utf-8')
        with self.assertRaises(RuntimeError):
            self.attach(ws,self.tmp,'proj-a')
        sp.unlink()
        r=self.attach(ws,self.tmp,'proj-a')
        self.assertEqual(r['attached'],['proj-a'])
    def test_relay_pin_rejects_cross_relay(self):
        ra=self.tmp/'ra'; ra.mkdir(); self.mkctx(ra); self.mkproj(ra,'proj-a',(self.CHA,))
        rb=self.tmp/'rb'; rb.mkdir(); self.mkctx(rb); self.mkproj(rb,'proj-a',(self.CHA,))
        ws=self.mkws()
        self.attach(ws,ra,'proj-a')
        sp=ws/'.awrp'/'session.json'
        before=sp.read_bytes()
        with self.assertRaises(RuntimeError):
            self.attach(ws,rb,'proj-a')
        with self.assertRaises(RuntimeError):
            self.switch(ws,rb,'proj-a')
        self.assertEqual(sp.read_bytes(),before)
        self.assertEqual(json.loads(before.decode())['relay_dir'],str(ra.resolve()))
    def test_unpinned_legacy_session_demands_explicit(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CHA,))
        ws=self.mkws()
        class A: pass
        a=A(); a.root=str(ws); a.relay='r'; a.relay_dir=str(self.tmp); a.channel=self.CHA; a.worker_endpoint='ep'; a.lane=None; a.project_id=None; a.bound_by='t'; a.force=False
        awrp.do_bind(a)
        sp=ws/'.awrp'/'session.json'; sp.parent.mkdir(parents=True,exist_ok=True)
        sp.write_text(json.dumps({'protocol':'awrp/0.1','attached':[{'project_id':'proj-a','attached_at':awrp.now(),'by':'old'}],'current':{'project_id':'proj-a','task_id':None,'run_id':None}}),encoding='utf-8')
        before=sp.read_bytes()
        b=A(); b.root=str(ws); b.relay_dir=None; b.project_id='proj-a'; b.by='t'
        with self.assertRaises(RuntimeError):
            awrp.do_attach(b)
        self.assertEqual(sp.read_bytes(),before)
        b.relay_dir=str(self.tmp)
        r=self.out(awrp.do_attach,b)
        self.assertEqual(r['attached'],['proj-a'])
        pinned=json.loads(sp.read_text())
        self.assertEqual(pinned['relay_dir'],str(Path(self.tmp).resolve()))
    @unittest.skipUnless(shutil.which('git'),'git required')
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_lineage_migration_aware(self):
        rel=self.tmp/'relay'; rel.mkdir()
        self.mkctx(rel)
        self.mkproj(rel,'proj-a',(self.CHA,))
        td=self.mktask(rel,'task_leg',self.CHA); self.dis(td,'run_leg')
        remote=self.tmp/'r.git'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(rel,'init','-b','main')
        self.git(rel,'config','user.email','t@e'); self.git(rel,'config','user.name','t')
        self.git(rel,'add','-A'); self.git(rel,'commit','-m','relay')
        self.git(rel,'remote','add','origin',str(remote)); self.git(rel,'push','-u','origin','main')
        ws=self.mkws()
        self.attach(ws,rel,'proj-a')
        r=self.lineage(ws,rel,'proj-a','task_leg','run_leg')
        self.assertFalse(r['match'])
        m=awrp.migration_associate(str(rel),'proj-a','task_leg','test')
        self.assertEqual(m['task_id'],'task_leg')
        self.switch(ws,rel,'proj-a','task_leg','run_leg')
        r=self.lineage(ws,rel,'proj-a','task_leg','run_leg')
        self.assertTrue(r['match'])
        self.assertTrue(r['canonical']['via_migration'])
        f=self.focus(ws,rel)
        self.assertEqual(f['status'],'FOCUS_EXECUTE')
class TM(unittest.TestCase):
    CHA='ch-ma'; CHB='ch-mb'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def git(self,repo,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def mkctx(self,root):
        (Path(root)/'contexts').mkdir(exist_ok=True)
        awrp.write_new(Path(root)/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
    def mkproj(self,root,pid,channels=()):
        return awrp.project_create(str(root),pid,'T-'+pid,channels,None,'chatgpt')
    def mktask(self,root,tid,channel,project=None):
        class A: pass
        a=A(); a.root=str(root); a.context_id='c'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=channel; a.lane_id=None; a.worker_endpoint='ep'; a.project_id=project
        a.legacy=True
        awrp.create_task(a); return str(Path(root)/'tasks'/tid)
    def dis(self,td,rid):
        class A: pass
        a=A(); a.task_dir=td; a.type='DISPATCH'; a.actor_role='coordinator'; a.actor_id='chatgpt'; a.recipient_role='worker'; a.recipient_id='ep'; a.run_id=rid; a.new_run=False; a.state='working'; a.phase='x'; a.waiting_on='ep'; a.run_state='dispatched'; a.summary='go'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None; a.legacy_route=True
        awrp.emit(a)
    def out(self,fn,args):
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): fn(args)
        return json.loads(buf.getvalue())
    def attach(self,ws,relay,pid):
        class A: pass
        a=A(); a.root=str(ws); a.relay_dir=str(relay); a.project_id=pid; a.by='test'
        return self.out(awrp.do_attach,a)
    def switch(self,ws,relay,pid,tid=None,rid=None):
        class A: pass
        a=A(); a.root=str(ws); a.relay_dir=str(relay); a.project_id=pid; a.task_id=tid; a.run_id=rid
        return self.out(awrp.do_switch,a)
    def focus(self,ws,relay):
        class A: pass
        a=A(); a.root=str(ws); a.relay_dir=str(relay)
        return self.out(awrp.do_focus,a)
    def mkws(self,name='ws'):
        ws=self.tmp/name; ws.mkdir(exist_ok=True); return ws
    def snap(self,ws):
        sp=ws/'.awrp'/'session.json'
        return sp.read_bytes()
    def git_relay(self):
        rel=self.tmp/'relay'; rel.mkdir()
        self.mkctx(rel)
        remote=self.tmp/'r.git'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(rel,'init','-b','main')
        self.git(rel,'config','user.email','t@e'); self.git(rel,'config','user.name','t')
        return remote,rel
    def push_u(self,rel,remote,msg='relay'):
        self.git(rel,'add','-A'); self.git(rel,'commit','-m',msg)
        self.git(rel,'remote','add','origin',str(remote)); self.git(rel,'push','-u','origin','main')
        self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
    def rival_advance(self,remote):
        b=self.tmp/'wb'
        subprocess.run(['git','-C',str(self.tmp),'clone',str(remote),str(b)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.email','t@e'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.name','t@e'],check=True,capture_output=True)
        (b/'rival.txt').write_text('rival\n')
        for args in (['add','-A'],['commit','-m','rival'],['push','origin','main']):
            subprocess.run(['git','-C',str(b),*args],check=True,capture_output=True)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_stale_switch_fails_before_mutation(self):
        remote,rel=self.git_relay()
        self.mkproj(rel,'proj-a',(self.CHA,))
        td=self.mktask(rel,'task_s',self.CHA,project='proj-a'); self.dis(td,'run_s')
        self.push_u(rel,remote)
        ws=self.mkws()
        self.attach(ws,rel,'proj-a')
        before_gen=json.loads((ws/'.awrp'/'session.json').read_text())['generation']
        self.rival_advance(remote)
        with self.assertRaises(RuntimeError):
            self.switch(ws,rel,'proj-a','task_s','run_s')
        after=json.loads((ws/'.awrp'/'session.json').read_text())
        self.assertEqual((after['current']['project_id'],after['current']['task_id'],after['current']['run_id']),('proj-a',None,None))
        self.assertEqual(after['generation'],before_gen)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_sync_fresh_switch_succeeds(self):
        remote,rel=self.git_relay()
        self.mkproj(rel,'proj-a',(self.CHA,))
        td=self.mktask(rel,'task_s',self.CHA,project='proj-a'); self.dis(td,'run_s')
        self.push_u(rel,remote)
        ws=self.mkws()
        self.attach(ws,rel,'proj-a')
        self.rival_advance(remote)
        with self.assertRaises(RuntimeError):
            self.switch(ws,rel,'proj-a','task_s','run_s')
        subprocess.run(['git','-C',str(rel),'pull','--ff-only'],check=True,capture_output=True)
        r=self.switch(ws,rel,'proj-a','task_s','run_s')
        self.assertEqual((r['current']['task_id'],r['current']['run_id']),('task_s','run_s'))
        self.assertEqual(self.focus(ws,rel)['status'],'FOCUS_EXECUTE')
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_project_only_switch_needs_no_freshness(self):
        remote,rel=self.git_relay()
        self.mkproj(rel,'proj-a',(self.CHA,)); self.mkproj(rel,'proj-b',(self.CHB,))
        self.push_u(rel,remote)
        ws=self.mkws()
        self.attach(ws,rel,'proj-a')
        self.attach(ws,rel,'proj-b')
        self.rival_advance(remote)
        r=self.switch(ws,rel,'proj-b')
        self.assertEqual((r['current']['project_id'],r['current']['task_id'],r['current']['run_id']),('proj-b',None,None))
        self.assertEqual(self.focus(ws,rel)['status'],'FOCUS_PROJECT')
    def test_task_only_no_run_switch_deterministic(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CHA,))
        td=self.mktask(self.tmp,'task_t',self.CHA,project='proj-a')
        ws=self.mkws()
        self.attach(ws,self.tmp,'proj-a')
        r=self.switch(ws,self.tmp,'proj-a','task_t')
        self.assertEqual((r['current']['task_id'],r['current']['run_id']),('task_t',None))
        f=self.focus(ws,self.tmp)
        self.assertEqual(f['status'],'FOCUS_NONE')
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_legacy_migration_same_freshness_rule(self):
        remote,rel=self.git_relay()
        self.mkproj(rel,'proj-a',(self.CHA,))
        td=self.mktask(rel,'task_leg',self.CHA); self.dis(td,'run_leg')
        awrp.migration_associate(str(rel),'proj-a','task_leg','test')
        self.push_u(rel,remote)
        ws=self.mkws()
        self.attach(ws,rel,'proj-a')
        self.rival_advance(remote)
        with self.assertRaises(RuntimeError):
            self.switch(ws,rel,'proj-a','task_leg','run_leg')
        subprocess.run(['git','-C',str(rel),'pull','--ff-only'],check=True,capture_output=True)
        r=self.switch(ws,rel,'proj-a','task_leg','run_leg')
        self.assertEqual(r['current']['run_id'],'run_leg')
class TO(unittest.TestCase):
    CHA='ch-oa'; CHB='ch-ob'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def mkctx(self,root):
        (Path(root)/'contexts').mkdir(exist_ok=True)
        awrp.write_new(Path(root)/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
    def mkproj(self,root,pid,channels=(),aliases=(),notion=None,notion_page_id=None):
        return awrp.project_create(str(root),pid,'T-'+pid,channels,notion,'chatgpt',aliases,notion_page_id)
    def mktask(self,root,tid,channel,project=None):
        class A: pass
        a=A(); a.root=str(root); a.context_id='c'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=channel; a.lane_id=None; a.worker_endpoint='ep'; a.project_id=project
        a.legacy=True
        awrp.create_task(a); return str(Path(root)/'tasks'/tid)
    def dis(self,td,rid):
        class A: pass
        a=A(); a.task_dir=td; a.type='DISPATCH'; a.actor_role='coordinator'; a.actor_id='chatgpt'; a.recipient_role='worker'; a.recipient_id='ep'; a.run_id=rid; a.new_run=False; a.state='working'; a.phase='x'; a.waiting_on='ep'; a.run_state='dispatched'; a.summary='go'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None; a.legacy_route=True
        awrp.emit(a)
    def hand(self,td,rid):
        class A: pass
        a=A(); a.task_dir=td; a.type='HANDOFF'; a.actor_role='worker'; a.actor_id='opencode'; a.recipient_role='coordinator'; a.recipient_id='chatgpt'; a.run_id=rid; a.new_run=False; a.state='working'; a.phase='review'; a.waiting_on='chatgpt'; a.run_state='succeeded'; a.summary='done'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None
        awrp.emit(a)
    def out(self,fn,args):
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): fn(args)
        return json.loads(buf.getvalue())
    def resolve(self,**kw):
        class A: pass
        a=A(); a.root=str(self.tmp); a.project_id=kw.get('project_id'); a.alias=kw.get('alias'); a.title=kw.get('title')
        return self.out(awrp.do_resolve_project,a)
    def snap(self,pid):
        class A: pass
        a=A(); a.root=str(self.tmp); a.project_id=pid
        return self.out(awrp.do_project_snapshot,a)
    def test_exact_id_wins_over_collisions(self):
        self.mkproj(self.tmp,'proj-a',(self.CHA,),aliases=('Shared Name',),notion_page_id='pg-1')
        self.mkproj(self.tmp,'proj-b',(self.CHB,),aliases=('Shared Name',),notion_page_id='pg-2')
        r=self.resolve(project_id='proj-b')
        self.assertEqual((r['status'],r['project']['project_id'],r['via']),('RESOLVED','proj-b','project_id'))
    def test_alias_title_exact_and_ambiguous(self):
        self.mkproj(self.tmp,'proj-a',(self.CHA,),aliases=('Alpha',))
        self.mkproj(self.tmp,'proj-b',(self.CHB,),aliases=('Alpha',))
        r=self.resolve(alias='Alpha')
        self.assertEqual(r['status'],'AMBIGUOUS'); self.assertEqual(r['candidates'],['proj-a','proj-b'])
        self.mkproj(self.tmp,'proj-c',(),aliases=('Solo',))
        r=self.resolve(alias='Solo')
        self.assertEqual((r['status'],r['project']['project_id']),('RESOLVED','proj-c'))
        r=self.resolve(alias='Alp')
        self.assertEqual(r['status'],'NOT_FOUND')
        r=self.resolve(title='T-proj-a')
        self.assertEqual((r['status'],r['project']['project_id']),('RESOLVED','proj-a'))
    def test_no_guessing(self):
        self.mkproj(self.tmp,'proj-only',(self.CHA,),aliases=('Only',))
        r=self.resolve(alias='Something Else')
        self.assertEqual(r['status'],'NOT_FOUND')
        r=self.resolve(title='T-proj-only')
        self.assertEqual(r['status'],'RESOLVED')
        with self.assertRaises(RuntimeError):
            self.resolve()
        with self.assertRaises(RuntimeError):
            self.resolve(project_id='proj-only',alias='Only')
    def test_duplicate_notion_page_fails_audit(self):
        self.mkproj(self.tmp,'proj-a',(self.CHA,),notion_page_id='pg-dup')
        self.mkproj(self.tmp,'proj-b',(self.CHB,),notion_page_id='pg-dup')
        r=self.out(awrp.do_audit_projects,type('A',(),{'root':str(self.tmp)})())
        self.assertFalse(r['ok'])
        self.assertEqual(r['violations'][0]['type'],'duplicate_notion_page')
        self.mkproj(self.tmp,'proj-c',(),aliases=('Clash',))
        self.mkproj(self.tmp,'proj-d',(),aliases=('Clash',))
        r=self.out(awrp.do_audit_projects,type('A',(),{'root':str(self.tmp)})())
        kinds=sorted(v['type'] for v in r['violations'])
        self.assertIn('ambiguous_alias',kinds)
    def test_snapshot_two_tasks_no_second_project(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CHA,))
        ta=self.mktask(self.tmp,'task_pra',self.CHA,project='proj-a'); self.dis(ta,'run_pra')
        tb=self.mktask(self.tmp,'task_prb',self.CHA,project='proj-a'); self.dis(tb,'run_prb')
        r=self.snap('proj-a')
        self.assertEqual(sorted(t['task_id'] for t in r['tasks']),['task_pra','task_prb'])
        self.assertTrue(r['ambiguous'])
        self.assertEqual(sorted(r['actionable_candidates']),['task_pra','task_prb'])
        self.assertEqual(awrp.list_projects(str(self.tmp)),['proj-a'])
    def test_snapshot_excludes_other_projects(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CHA,)); self.mkproj(self.tmp,'proj-b',(self.CHB,))
        ta=self.mktask(self.tmp,'task_similar_a',self.CHA,project='proj-a'); self.dis(ta,'run_a')
        tb=self.mktask(self.tmp,'task_similar_b',self.CHB,project='proj-b'); self.dis(tb,'run_b')
        r=self.snap('proj-a')
        self.assertEqual([t['task_id'] for t in r['tasks']],['task_similar_a'])
        self.assertFalse(r['ambiguous'])
    def test_snapshot_migration_and_invalid(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CHA,))
        td=self.mktask(self.tmp,'task_leg',self.CHA); self.dis(td,'run_leg')
        awrp.migration_associate(str(self.tmp),'proj-a','task_leg','test')
        r=self.snap('proj-a')
        self.assertEqual([(t['task_id'],t['via']) for t in r['tasks']],[('task_leg','migration')])
        p=Path(td)/'task.json'; o=json.loads(p.read_text()); o['project_id']='proj-ghost'; p.write_text(json.dumps(o))
        r=self.snap('proj-a')
        self.assertEqual([t['task_id'] for t in r['tasks']],[])
    def test_snapshot_completed_task_representation(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CHA,))
        td=self.mktask(self.tmp,'task_done',self.CHA,project='proj-a'); self.dis(td,'run_done')
        self.hand(td,'run_done')
        r=self.snap('proj-a')
        self.assertEqual(len(r['tasks']),1)
        self.assertEqual(r['tasks'][0]['last_significant']['type'],'HANDOFF')
        self.assertEqual(r['actionable_candidates'],[])
        self.assertFalse(r['ambiguous'])
    def test_legacy_notion_readable(self):
        self.mkproj(self.tmp,'proj-old',(self.CHA,),notion='https://notion.so/old-page')
        r=self.snap('proj-old')
        self.assertEqual(r['project']['notion'],'https://notion.so/old-page')
        self.assertIsNone(r['project']['notion_page_id'])
        r=self.out(awrp.do_audit_projects,type('A',(),{'root':str(self.tmp)})())
        self.assertTrue(r['ok'])
    def test_no_network_imports(self):
        import ast
        tree=ast.parse((Path(__file__).resolve().parents[1]/'tools'/'awrp.py').read_text(encoding='utf-8'))
        mods=set()
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                mods.update(x.name.split('.')[0] for x in node.names)
            elif isinstance(node,ast.ImportFrom) and node.module:
                mods.add(node.module.split('.')[0])
        self.assertTrue(mods.isdisjoint({'urllib','urllib3','requests','httpx','http','socket','ssl','notion_client','notion'}))
    def test_illegal_created_state_rejected_everywhere(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CHA,))
        td=self.mktask(self.tmp,'task_bad',self.CHA,project='proj-a')
        p=Path(td)/'events'; src=sorted(p.glob('*.json'))[0]
        o=json.loads(src.read_text()); o['task_projection']['state']='ready'
        o['integrity']['event_hash']=awrp.eh({k:v for k,v in o.items() if k!='integrity'} | {'integrity':{k:v for k,v in o['integrity'].items() if k!='event_hash'}})
        src.write_text(json.dumps(o))
        with self.assertRaises(RuntimeError):
            awrp.validate(td)
        r=self.out(awrp.do_inbox,type('A',(),{'root':str(self.tmp),'channel':None,'worker_endpoint':None,'task_id':'task_bad','legacy':False,'project':None})())
        self.assertEqual(r['actionable'],[])
        self.assertEqual(len(r['invalid']),1)
        self.assertEqual(awrp.select_for_resume(str(self.tmp),self.CHA,'ep',None,'proj-a')['status'],'INVALID_CANONICAL')
        class A: pass
        a=A(); a.root=str(self.tmp); a.relay='r'; a.relay_dir=str(self.tmp); a.project_id='proj-a'; a.channel=self.CHA; a.worker_endpoint='ep'; a.task_id='task_bad'; a.run_id=None; a.lane=None; a.bound_by='t'
        with self.assertRaises(RuntimeError):
            awrp.do_first_bind(a)
        ws=self.tmp/'ws'; ws.mkdir()
        class B: pass
        b=B(); b.root=str(ws); b.relay='r'; b.relay_dir=str(self.tmp); b.channel=self.CHA; b.worker_endpoint='ep'; b.lane=None; b.project_id=None; b.bound_by='t'; b.force=False
        awrp.do_bind(b)
        class C: pass
        c=C(); c.binding_root=str(ws); c.task_id='task_bad'; c.run_id=None; c.branch='main'; c.remote='origin'
        with self.assertRaises(RuntimeError):
            awrp.do_plan_dispatch(c)
class TQ(unittest.TestCase):
    CHA='ch-qa'; CHB='ch-qb'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def mkctx(self,root):
        (Path(root)/'contexts').mkdir(exist_ok=True)
        awrp.write_new(Path(root)/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
    def mkproj(self,root,pid,channels=(),aliases=(),notion_page_id=None):
        return awrp.project_create(str(root),pid,'T-'+pid,channels,None,'chatgpt',aliases,notion_page_id)
    def mktask(self,root,tid,channel,project=None):
        class A: pass
        a=A(); a.root=str(root); a.context_id='c'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=channel; a.lane_id=None; a.worker_endpoint='ep'; a.project_id=project
        a.legacy=True
        awrp.create_task(a); return str(Path(root)/'tasks'/tid)
    def dis(self,td,rid,legacy=True):
        class A: pass
        a=A(); a.task_dir=td; a.type='DISPATCH'; a.actor_role='coordinator'; a.actor_id='chatgpt'; a.recipient_role='worker'; a.recipient_id='ep'; a.run_id=rid; a.new_run=False; a.state='working'; a.phase='x'; a.waiting_on='ep'; a.run_state='dispatched'; a.summary='go'; a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None; a.legacy_route=legacy
        awrp.emit(a)
    def out(self,fn,args):
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): fn(args)
        return json.loads(buf.getvalue())
    def attach(self,ws,relay,pid):
        class A: pass
        a=A(); a.root=str(ws); a.relay_dir=str(relay); a.project_id=pid; a.by='test'
        return self.out(awrp.do_attach,a)
    def switch(self,ws,relay,pid,tid=None,rid=None):
        class A: pass
        a=A(); a.root=str(ws); a.relay_dir=str(relay); a.project_id=pid; a.task_id=tid; a.run_id=rid
        return self.out(awrp.do_switch,a)
    def focus(self,ws,relay):
        class A: pass
        a=A(); a.root=str(ws); a.relay_dir=str(relay)
        return self.out(awrp.do_focus,a)
    def mkws(self,name='ws'):
        ws=self.tmp/name; ws.mkdir(exist_ok=True); return ws
    def resolve(self,**kw):
        class A: pass
        a=A(); a.root=str(self.tmp); a.project_id=kw.get('project_id'); a.alias=kw.get('alias'); a.title=kw.get('title')
        return self.out(awrp.do_resolve_project,a)
    def test_cross_field_deterministic(self):
        self.mkproj(self.tmp,'proj-a',(self.CHA,),aliases=('Shared',))
        self.mkproj(self.tmp,'proj-b',(self.CHB,))
        pb=Path(self.tmp)/'projects'/'proj-b.json'
        o=json.loads(pb.read_text()); o['title']='Shared'; pb.write_text(json.dumps(o))
        r=self.resolve(alias='Shared')
        self.assertEqual((r['status'],r['project']['project_id']),('RESOLVED','proj-a'))
        r=self.resolve(title='Shared')
        self.assertEqual((r['status'],r['project']['project_id']),('RESOLVED','proj-b'))
    def test_roundtrip_switch_aba(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CHA,)); self.mkproj(self.tmp,'proj-b',(self.CHB,))
        ws=self.mkws()
        self.attach(ws,self.tmp,'proj-a'); self.attach(ws,self.tmp,'proj-b')
        self.switch(ws,self.tmp,'proj-a')
        self.switch(ws,self.tmp,'proj-b')
        self.assertEqual(self.focus(ws,self.tmp)['current']['project_id'],'proj-b')
        self.switch(ws,self.tmp,'proj-a')
        f=self.focus(ws,self.tmp)
        self.assertEqual(f['current']['project_id'],'proj-a')
        self.assertEqual(f['status'],'FOCUS_PROJECT')
    def test_dispatch_bad_prev_link_rejected(self):
        self.mkctx(self.tmp)
        td=self.mktask(self.tmp,'task_l',self.CHA)
        self.dis(td,'run_l')
        p=sorted((Path(td)/'events').glob('*.json'))[-1]
        o=json.loads(p.read_text())
        o['integrity']['prev_event_hash']='sha256:'+'0'*64
        o['integrity']['event_hash']=awrp.eh(o)
        p.write_text(json.dumps(o))
        with self.assertRaises(RuntimeError):
            awrp.validate(td)
        self.assertEqual(awrp.select_for_resume(str(self.tmp),self.CHA,'ep',None,None)['status'],'INVALID_CANONICAL')
    def test_multi_association_ambiguity(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CHA,)); self.mkproj(self.tmp,'proj-b',(self.CHB,))
        td=self.mktask(self.tmp,'task_m',self.CHA); self.dis(td,'run_m')
        awrp.migration_associate(str(self.tmp),'proj-a','task_m','legit')
        mp=Path(self.tmp)/'projects'/'proj-b'/'migrations'; mp.mkdir(parents=True)
        (mp/'task_m.json').write_text(json.dumps({'protocol':'awrp/0.1','project_id':'proj-b','task_id':'task_m','channel_id':self.CHB,'created_at':awrp.now(),'created_by':'x','reason':'forged'}))
        ws=self.mkws()
        self.attach(ws,self.tmp,'proj-a')
        self.attach(ws,self.tmp,'proj-b')
        class A: pass
        a=A(); a.root=str(ws); a.relay_dir=str(self.tmp); a.project_id='proj-a'; a.task_id='task_m'; a.run_id=None
        with self.assertRaises(RuntimeError):
            self.out(awrp.do_check_lineage,a)
    def test_cli_cannot_emit_illegal_state(self):
        with self.assertRaises(SystemExit):
            awrp.parser().parse_args(['emit','--task-dir','x','--type','DISPATCH','--actor-role','coordinator','--actor-id','c','--state','ready','--phase','x','--summary','x'])
        self.mkctx(self.tmp)
        class A: pass
        a=A(); a.root=str(self.tmp); a.context_id='c'; a.task_id='task_born'; a.title='t'; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=None; a.lane_id=None; a.worker_endpoint=None; a.project_id=None
        a.legacy=True
        awrp.create_task(a)
        v=awrp.validate(str(self.tmp/'tasks'/'task_born'))
        self.assertEqual(v['head']['task_projection']['state'],'submitted')
    def test_snapshot_lists_invalid_separately(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',(self.CHA,))
        td=self.mktask(self.tmp,'task_bad',self.CHA,project='proj-a')
        p=sorted((Path(td)/'events').glob('*.json'))[0]
        o=json.loads(p.read_text()); o['task_projection']['state']='ready'
        o['integrity']['event_hash']=awrp.eh(o)
        p.write_text(json.dumps(o))
        class A: pass
        a=A(); a.root=str(self.tmp); a.project_id='proj-a'
        r=self.out(awrp.do_project_snapshot,a)
        self.assertEqual([t['task_id'] for t in r['tasks'] if t.get('valid',True)],[])
        self.assertEqual(r['invalid_tasks'],['task_bad'])
        self.assertEqual(r['actionable_candidates'],[])
        self.assertFalse(r['ambiguous'])
class TU(unittest.TestCase):
    CH='ch-plan-new'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def git(self,repo,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def mkctx(self,root):
        (Path(root)/'contexts').mkdir(exist_ok=True)
        awrp.write_new(Path(root)/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
    def mkproj(self,root,pid,channels=()):
        return awrp.project_create(str(root),pid,'T-'+pid,channels,None,'chatgpt')
    def mkrelay(self):
        remote=self.tmp/'r.git'; w=self.tmp/'w'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(self.tmp,'init','-b','main',str(w))
        self.git(w,'config','user.email','t@e'); self.git(w,'config','user.name','t')
        self.mkctx(w)
        self.git(w,'add','-A'); self.git(w,'commit','-m','base'); self.git(w,'remote','add','origin',str(remote))
        self.git(w,'push','-u','origin','main'); self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
        return remote,w,self.git(w,'rev-parse','main')
    def plan(self,w,tid,base,created='2026-09-09T11:00:00Z',project=None,channel=None,context='c'):
        import io, contextlib
        class A: pass
        a=A(); a.root=str(w); a.task_id=tid; a.context_id=context; a.title='T-'+tid; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=channel; a.lane_id=None; a.worker_endpoint='ep'; a.project_id=project; a.created_at=created
        a.repo=str(w); a.branch='main'; a.remote='origin'; a.expected_base=base
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_plan_task_create(a)
        return json.loads(buf.getvalue())
    def out(self,fn,args):
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): fn(args)
        return json.loads(buf.getvalue())
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_plan_deterministic_submitted(self):
        remote,w,base=self.mkrelay()
        self.mkproj(w,'proj-a',(self.CH,))
        p1=self.plan(w,'task_n',base,project='proj-a',channel=self.CH)
        p2=self.plan(w,'task_n',base,project='proj-a',channel=self.CH)
        self.assertEqual(p1,p2)
        self.assertEqual(p1['event']['task_projection'],{'state':'submitted','phase':'intake','waiting_on':'chatgpt'})
        self.assertEqual(p1['event_hash'],awrp.eh(p1['event']))
        self.assertEqual(p1['task_json']['project_id'],'proj-a')
        self.assertEqual(p1['paths']['event'],'tasks/task_n/events/000001_'+p1['event_id']+'.json')
    def test_no_state_knobs(self):
        import argparse
        found=None
        for act in awrp.parser()._actions:
            if isinstance(act,argparse._SubParsersAction):
                found=act.choices.get('plan-task-create')
        self.assertIsNotNone(found)
        flags={s for act in found._actions for s in act.option_strings}
        for banned in ['--state','--phase','--waiting-on','--run-state','--run-id','--new-run']:
            self.assertNotIn(banned,flags)
        with self.assertRaises(SystemExit):
            awrp.parser().parse_args(['plan-task-create','--root','x','--task-id','t','--context-id','c','--title','t','--goal','g','--expected-base','b','--state','ready'])
    def test_ownership_enforced(self):
        remote,w,base=self.mkrelay()
        with self.assertRaises(RuntimeError):
            self.plan(w,'task_x',base,project='proj-ghost',channel=self.CH)
        self.mkproj(w,'proj-a',('ch-owned',))
        with self.assertRaises(RuntimeError):
            self.plan(w,'task_x',base,project='proj-a',channel=self.CH)
        with self.assertRaises(RuntimeError):
            self.plan(w,'task_x',base,context='ghost')
        with self.assertRaises(RuntimeError):
            self.plan(w,'../evil',base)
        td=w/'tasks'/'task_dup'
        td.mkdir(parents=True); (td/'task.json').write_text('{}')
        with self.assertRaises(RuntimeError):
            self.plan(w,'task_dup',base)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_plan_applies_verbatim(self):
        remote,w,base=self.mkrelay()
        self.mkproj(w,'proj-a',(self.CH,))
        p=self.plan(w,'task_live',base,project='proj-a',channel=self.CH)
        (w/p['paths']['task_json']).parent.mkdir(parents=True,exist_ok=True)
        (w/p['paths']['event']).parent.mkdir(parents=True,exist_ok=True)
        (w/p['paths']['task_json']).write_text(json.dumps(p['task_json'],ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (w/p['paths']['event']).write_text(json.dumps(p['event'],ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (w/p['paths']['projection']).write_text(p['taskmd_projection'],encoding='utf-8')
        v=awrp.validate(str(w/'tasks'/'task_live'))
        self.assertEqual(v['head']['integrity']['event_hash'],p['event_hash'])
        self.assertEqual(v['head']['task_projection']['state'],'submitted')
        self.git(w,'add','-A'); self.git(w,'commit','-m','connector plan applied'); self.git(w,'push','origin','main')
        b=self.tmp/'wb'
        subprocess.run(['git','-C',str(self.tmp),'clone',str(remote),str(b)],check=True,capture_output=True)
        v2=awrp.validate(str(b/'tasks'/'task_live'))
        self.assertEqual(v2['head']['integrity']['event_hash'],p['event_hash'])
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_stale_base_fails_no_write(self):
        remote,w,base=self.mkrelay()
        self.mkproj(w,'proj-a',(self.CH,))
        b=self.tmp/'wb'
        subprocess.run(['git','-C',str(self.tmp),'clone',str(remote),str(b)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.email','t@e'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.name','t@e'],check=True,capture_output=True)
        (b/'rival.txt').write_text('rival\n')
        for args in (['add','-A'],['commit','-m','rival'],['push','origin','main']):
            subprocess.run(['git','-C',str(b),*args],check=True,capture_output=True)
        before=sorted(p.name for p in (w/'tasks').glob('*') if (w/'tasks').exists()) if (w/'tasks').exists() else []
        with self.assertRaises(RuntimeError):
            self.plan(w,'task_s',base,project='proj-a',channel=self.CH)
        after=sorted(p.name for p in (w/'tasks').glob('*') if (w/'tasks').exists()) if (w/'tasks').exists() else []
        self.assertEqual(before,after)
class TV(unittest.TestCase):
    CH='ch-e2e'; EP='ep-e2e'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def git(self,repo,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def gg(self,repo,env,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True,env=env)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def mkctx(self,root):
        (Path(root)/'contexts').mkdir(exist_ok=True)
        awrp.write_new(Path(root)/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
    def out(self,fn,args):
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): fn(args)
        return json.loads(buf.getvalue())
    def connector_publish_new_task(self,repo,remote,branch,plan,message):
        import tempfile as _tf
        paths=plan['paths']
        blobs={}
        tmps=[]
        try:
            for key,content in (('task_json',json.dumps(plan['task_json'],ensure_ascii=False,indent=2)+'\n'),('event',json.dumps(plan['event'],ensure_ascii=False,indent=2)+'\n'),('projection',plan['taskmd_projection'])):
                fd,nm=_tf.mkstemp(); tmps.append(nm)
                Path(nm).write_bytes(content.encode('utf-8'))
                blobs[key]=self.git(repo,'hash-object','-w',nm)
        finally:
            for nm in tmps:
                try: Path(nm).unlink()
                except OSError: pass
        base=plan['expected_base']
        self.assertEqual(plan['api_plan']['parents'],[base])
        base_tree=self.git(repo,'rev-parse',f'{base}^{{tree}}')
        self.assertEqual(plan['api_plan']['base_tree'],base_tree)
        idx=str(self.tmp/'idx-e2e')
        if Path(idx).exists(): Path(idx).unlink()
        env=dict(__import__('os').environ); env['GIT_INDEX_FILE']=idx
        try:
            self.gg(repo,env,'read-tree',base_tree)
            self.gg(repo,env,'update-index','--add','--cacheinfo',f"100644,{blobs['task_json']},{paths['task_json']}")
            self.gg(repo,env,'update-index','--add','--cacheinfo',f"100644,{blobs['event']},{paths['event']}")
            self.gg(repo,env,'update-index','--add','--cacheinfo',f"100644,{blobs['projection']},{paths['projection']}")
            tree=self.gg(repo,env,'write-tree')
            commit=self.gg(repo,env,'commit-tree',tree,'-p',base,'-m',message)
        finally:
            try: Path(idx).unlink()
            except OSError: pass
        cp=subprocess.run(['git','-C',str(repo),'push',remote,f'{commit}:refs/heads/{branch}'],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr)
        self.assertEqual(self.git(repo,'ls-remote',remote,branch).split()[0],commit)
        return commit
    def plan_new(self,w,tid,base,created='2026-09-09T15:00:00Z'):
        class A: pass
        a=A(); a.root=str(w); a.task_id=tid; a.context_id='c'; a.title='T-'+tid; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=self.CH; a.lane_id=None; a.worker_endpoint=self.EP; a.project_id='proj-e2e'; a.created_at=created
        a.repo=str(w); a.branch='main'; a.remote='origin'; a.expected_base=base
        return self.out(awrp.do_plan_task_create,a)
    def guarded(self,ws_or_none,w,task_id,run_id,head,plan_fp=None,publish=False,repo=None):
        class A: pass
        a=A()
        if ws_or_none is None:
            a.binding_root=None; a.no_binding=True; a.project_id='proj-e2e'; a.channel=self.CH; a.worker_endpoint=self.EP; a.lane=None
        else:
            a.binding_root=str(ws_or_none); a.no_binding=False
        a.task_id=task_id; a.branch='main'; a.remote='origin'; a.repo=repo; a.publish=publish; a.commit_message=None; a.expected_plan=plan_fp
        a.run_id=run_id; a.new_run=False
        a.actor_role='coordinator'; a.actor_id='chatgpt'; a.recipient_role='worker'; a.recipient_id='ep-e2e'; a.state='working'; a.phase='x'; a.waiting_on='ep-e2e'; a.run_state='dispatched'; a.summary='go'
        a.details_file=None; a.artifacts_file=None; a.approval_file=None; a.causation_id=None
        a.expected_head=head; a.expected_hash=None; a.claimant=None; a.fencing_generation=None
        return self.out(awrp.do_dispatch_guarded,a)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_capability_guard_connector_e2e_new_task_to_bound_discovery(self):
        remote=self.tmp/'r.git'; w=self.tmp/'w'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(self.tmp,'init','-b','main',str(w))
        self.git(w,'config','user.email','t@e'); self.git(w,'config','user.name','t')
        self.mkctx(w)
        awrp.project_create(str(w),'proj-e2e','E2E',(self.CH,),None,'chatgpt')
        self.git(w,'add','-A'); self.git(w,'commit','-m','seed'); self.git(w,'remote','add','origin',str(remote))
        self.git(w,'push','-u','origin','main'); self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
        base=self.git(w,'rev-parse','main')
        plan=self.plan_new(w,'task_e2e',base)
        self.connector_publish_new_task(w,'origin','main',plan,'connector: create task_e2e')
        b=self.tmp/'b-fresh'
        subprocess.run(['git','-C',str(self.tmp),'clone',str(remote),str(b)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.email','t@e'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.name','t@e'],check=True,capture_output=True)
        v=awrp.validate(str(b/'tasks'/'task_e2e'))
        self.assertEqual(v['head']['integrity']['event_hash'],plan['event_hash'])
        self.git(w,'fetch','origin'); self.git(w,'reset','--hard','origin/main')
        h=awrp.validate(str(w/'tasks'/'task_e2e'))['head']['event_id']
        d=self.guarded(None,w,'task_e2e','run_e2e',head=h,repo=str(w),publish=True)
        self.assertEqual(d['run_id'],'run_e2e')
        c=self.tmp/'c-fresh'
        subprocess.run(['git','-C',str(self.tmp),'clone',str(remote),str(c)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(c),'config','user.email','t@e'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(c),'config','user.name','t@e'],check=True,capture_output=True)
        ws=self.tmp/'ws'; ws.mkdir()
        class A: pass
        a=A(); a.root=str(ws); a.relay='Bruce-Yii/awrp'; a.relay_dir=str(c); a.channel=self.CH; a.worker_endpoint=self.EP; a.lane=None; a.project_id=None; a.bound_by='t'; a.force=False
        awrp.do_bind(a)
        r=awrp.select_for_resume(str(c),self.CH,self.EP,None,None)
        self.assertEqual((r['status'],r['task_id'],r['run_id']),('EXECUTE','task_e2e','run_e2e'))
class TS(unittest.TestCase):
    CH='ch-bridge'; EP='ep-bridge'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def git(self,repo,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def gg(self,repo,env,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True,env=env)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def mkctx(self,root):
        (Path(root)/'contexts').mkdir(exist_ok=True)
        awrp.write_new(Path(root)/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
    def out(self,fn,args):
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): fn(args)
        return json.loads(buf.getvalue())
    def compose(self,relay,intent,actor_id='chatgpt',base=None,repo=None,binding=None):
        import tempfile as _tf, os as _os
        fd,nm=_tf.mkstemp(suffix='.json',dir=str(self.tmp)); _os.close(fd)
        self.addCleanup(lambda: Path(nm).unlink(missing_ok=True))
        Path(nm).write_text(json.dumps(intent),encoding='utf-8')
        class A: pass
        a=A(); a.root=str(relay); a.intent_file=nm; a.actor_role='coordinator'; a.actor_id=actor_id
        a.repo=str(repo or relay); a.branch='main'; a.remote='origin'; a.expected_base=base; a.binding_root=str(binding) if binding else None
        return self.out(awrp.do_compose_intent,a)
    def ship(self,repo,remote,branch,blobs,base,message):
        idx=str(self.tmp/'idx-ts')
        if Path(idx).exists(): Path(idx).unlink()
        env=dict(__import__('os').environ); env['GIT_INDEX_FILE']=idx
        try:
            base_tree=self.git(repo,'rev-parse',f'{base}^{{tree}}')
            self.gg(repo,env,'read-tree',base_tree)
            for path,content in blobs.items():
                cp=subprocess.run(['git','-C',str(repo),'hash-object','-w','--stdin'],input=content,capture_output=True)
                self.assertEqual(cp.returncode,0,cp.stderr.decode())
                self.gg(repo,env,'update-index','--add','--cacheinfo',f"100644,{cp.stdout.decode().strip()},{path}")
            tree=self.gg(repo,env,'write-tree')
            commit=self.gg(repo,env,'commit-tree',tree,'-p',base,'-m',message)
        finally:
            try: Path(idx).unlink()
            except OSError: pass
        cp=subprocess.run(['git','-C',str(repo),'push',remote,f'{commit}:refs/heads/{branch}'],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr)
        self.assertEqual(self.git(repo,'ls-remote',remote,branch).split()[0],commit)
        return commit
    def mkrelay(self):
        remote=self.tmp/'r.git'; w=self.tmp/'w'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(self.tmp,'init','-b','main',str(w))
        self.git(w,'config','user.email','t@e'); self.git(w,'config','user.name','t')
        self.mkctx(w)
        awrp.project_create(str(w),'proj-b','B',(self.CH,),None,'chatgpt')
        self.git(w,'add','-A'); self.git(w,'commit','-m','seed'); self.git(w,'remote','add','origin',str(remote))
        self.git(w,'push','-u','origin','main'); self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
        return remote,w,self.git(w,'rev-parse','main')
    def test_intent_schema_closed(self):
        base_intent={"action":"dispatch","idempotency_key":"k1","params":{"task_id":"t","state":"working","phase":"x","summary":"s"}}
        bad=dict(base_intent); bad['params']=dict(base_intent['params']); bad['params']['event_id']='evt_forged'
        with self.assertRaises(RuntimeError):
            self.compose(self.tmp,bad)
        bad2=dict(base_intent); bad2['params']=dict(base_intent['params']); bad2['params']['fencing']={'generation':1}
        with self.assertRaises(RuntimeError):
            self.compose(self.tmp,bad2)
        bad3={"action":"dispatch","params":{"task_id":"t","state":"working","phase":"x","summary":"s"}}
        with self.assertRaises(RuntimeError):
            self.compose(self.tmp,bad3)
        bad4={"action":"teleport","idempotency_key":"k","params":{}}
        with self.assertRaises(RuntimeError):
            self.compose(self.tmp,bad4)
        bad5={"action":"create-task","idempotency_key":"k","params":{"task_id":"t","context_id":"c","title":"t","goal":"g","state":"ready"}}
        with self.assertRaises(RuntimeError):
            self.compose(self.tmp,bad5)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_bridge_create_dispatch_lifecycle(self):
        remote,w,base=self.mkrelay()
        r1=self.compose(w,{"action":"create-task","idempotency_key":"k-create","params":{"task_id":"task_ts","context_id":"c","title":"T","goal":"g","project_id":"proj-b","channel_id":self.CH,"worker_endpoint":self.EP,"created_at":"2026-09-09T15:00:00Z"}},base=base)
        self.assertEqual(r1['plan']['event']['task_projection']['state'],'submitted')
        self.assertEqual(r1['plan']['event_hash'],awrp.eh(r1['plan']['event']))
        blobs={p:content for p,content in [
            (r1['plan']['paths']['task_json'],json.dumps(r1['plan']['task_json'],ensure_ascii=False,indent=2)+'\n'),
            (r1['plan']['paths']['event'],json.dumps(r1['plan']['event'],ensure_ascii=False,indent=2)+'\n'),
            (r1['plan']['paths']['projection'],r1['plan']['taskmd_projection'])]}
        c1=self.ship(w,'origin','main',{k:v.encode() for k,v in blobs.items()},base,'bridge: create task_ts')
        self.git(w,'fetch','origin'); self.git(w,'reset','--hard','origin/main')
        v=awrp.validate(str(w/'tasks'/'task_ts'))
        self.assertEqual(v['head']['integrity']['event_hash'],r1['plan']['event_hash'])
        ws=self.tmp/'ws'; ws.mkdir()
        class A: pass
        a=A(); a.root=str(ws); a.relay='Bruce-Yii/awrp'; a.relay_dir=str(w); a.channel=self.CH; a.worker_endpoint=self.EP; a.lane=None; a.project_id='proj-b'; a.bound_by='t'; a.force=False
        awrp.do_bind(a)
        r2=self.compose(w,{"action":"dispatch","idempotency_key":"k-dis","params":{"task_id":"task_ts","run_id":"run_ts","recipient_role":"worker","recipient_id":self.EP,"state":"working","phase":"x","waiting_on":self.EP,"run_state":"dispatched","summary":"go","expected_head":v['head']['event_id']}},base=c1)
        self.assertEqual(r2['run_id'],'run_ts')
        ev=r2['plan']['event']
        blobs2={r2['plan']['api_plan']['event_path']:json.dumps(ev,ensure_ascii=False,indent=2)+'\n',r2['plan']['api_plan']['taskmd_path']:r2['plan']['taskmd_projection']}
        c2=self.ship(w,'origin','main',{k:v.encode() for k,v in blobs2.items()},c1,'bridge: dispatch run_ts')
        self.git(w,'fetch','origin'); self.git(w,'reset','--hard','origin/main')
        v2=awrp.validate(str(w/'tasks'/'task_ts'))
        self.assertEqual(v2['active_run_id'],'run_ts')
        r3=self.compose(w,{"action":"review","idempotency_key":"k-rev","params":{"task_id":"task_ts","run_id":"run_ts","state":"working","phase":"review","waiting_on":"chatgpt","run_state":"succeeded","summary":"ok"}},base=c2)
        ev3=r3['plan']['event']
        blobs3={r3['plan']['api_plan']['event_path']:json.dumps(ev3,ensure_ascii=False,indent=2)+'\n',r3['plan']['api_plan']['taskmd_path']:r3['plan']['taskmd_projection']}
        self.ship(w,'origin','main',{k:v.encode() for k,v in blobs3.items()},c2,'bridge: review run_ts')
        self.git(w,'fetch','origin'); self.git(w,'reset','--hard','origin/main')
        r4=self.compose(w,{"action":"approval","idempotency_key":"k-app","params":{"task_id":"task_ts","run_id":"run_ts","state":"completed","phase":"completed","waiting_on":"null","run_state":"succeeded","summary":"done","approval":{"authority":"coordinator","scope":"s"}}},base=self.git(w,'rev-parse','main'))
        ev4=r4['plan']['event']
        blobs4={r4['plan']['api_plan']['event_path']:json.dumps(ev4,ensure_ascii=False,indent=2)+'\n',r4['plan']['api_plan']['taskmd_path']:r4['plan']['taskmd_projection']}
        self.ship(w,'origin','main',{k:v.encode() for k,v in blobs4.items()},self.git(w,'rev-parse','main'),'bridge: approve run_ts')
        self.git(w,'fetch','origin'); self.git(w,'reset','--hard','origin/main')
        v3=awrp.validate(str(w/'tasks'/'task_ts'))
        self.assertEqual(v3['head']['task_projection']['state'],'completed')
        self.assertIsNone(v3.get('active_run_id'))
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_bridge_binding_route_enforced(self):
        remote,w,base=self.mkrelay()
        td=w/'tasks'/'task_bg'
        class A: pass
        a=A(); a.root=str(w); a.context_id='c'; a.task_id='task_bg'; a.title='t'; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id='ch-other'; a.lane_id=None; a.worker_endpoint=self.EP; a.project_id=None
        a.legacy=True
        awrp.create_task(a)
        self.git(w,'add','-A'); self.git(w,'commit','-m','task'); self.git(w,'push','-u','origin','main')
        ws=self.tmp/'ws'; ws.mkdir()
        class B: pass
        b=B(); b.root=str(ws); b.relay='x'; b.relay_dir=str(w); b.channel=self.CH; b.worker_endpoint=self.EP; b.lane=None; b.project_id=None; b.bound_by='t'; b.force=False
        awrp.do_bind(b)
        class C: pass
        c=C(); c.root=str(w); c.intent_file=None; c.actor_role='coordinator'; c.actor_id='chatgpt'; c.repo=str(w); c.branch='main'; c.remote='origin'; c.expected_base=base; c.binding_root=str(ws)
        import tempfile as _tf, os as _os
        fd,nm=_tf.mkstemp(suffix='.json',dir=str(self.tmp)); _os.close(fd); self.addCleanup(lambda: Path(nm).unlink(missing_ok=True))
        Path(nm).write_text(json.dumps({"action":"dispatch","idempotency_key":"k","params":{"task_id":"task_bg","run_id":"run_bg","state":"working","phase":"x","summary":"go"}}),encoding='utf-8')
        c.intent_file=nm
        with self.assertRaises(RuntimeError):
            awrp.do_compose_intent(c)
class TX(unittest.TestCase):
    CH='ch-bridge'; EP='ep-bridge'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def git(self,repo,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def mkctx(self,root):
        (Path(root)/'contexts').mkdir(exist_ok=True)
        awrp.write_new(Path(root)/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
    def out(self,fn,args):
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): fn(args)
        return json.loads(buf.getvalue())
    def bridge(self,w,rid):
        class A: pass
        a=A(); a.root=str(w); a.request=rid; a.repo=str(w); a.branch='main'; a.remote='origin'
        return self.out(awrp.do_bridge_process,a)
    def mkreq(self,w,rid,body):
        p=w/'bridge'/'requests'; p.mkdir(parents=True,exist_ok=True)
        (p/f'{rid}.json').write_text(body if isinstance(body,str) else json.dumps(body),encoding='utf-8')
    def mkrelay(self):
        remote=self.tmp/'r.git'; w=self.tmp/'w'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(self.tmp,'init','-b','main',str(w))
        self.git(w,'config','user.email','t@e'); self.git(w,'config','user.name','t')
        self.mkctx(w)
        awrp.project_create(str(w),'proj-b','B',(self.CH,),None,'chatgpt')
        awrp.acquire_claim(str(w),self.CH,'coord-A')
        self.git(w,'add','-A'); self.git(w,'commit','-m','seed'); self.git(w,'remote','add','origin',str(remote))
        self.git(w,'push','-u','origin','main'); self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
        return remote,w,self.git(w,'rev-parse','main')
    def fresh_clone(self,remote,name):
        b=self.tmp/name
        subprocess.run(['git','-C',str(self.tmp),'clone',str(remote),str(b)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.email','t@e'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.name','t@e'],check=True,capture_output=True)
        return b
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_malformed_request_rejected(self):
        remote,w,base=self.mkrelay()
        self.mkreq(w,'r-bad','{not json')
        r=self.bridge(w,'r-bad')
        self.assertEqual(r['status'],'rejected')
        self.assertFalse((w/'tasks'/'task_x').exists())
        self.assertEqual(self.git(w,'rev-parse','main'),self.git(remote,'rev-parse','main'))
        res=json.loads((w/'bridge'/'requests'/'r-bad.result.json').read_text())
        self.assertEqual(res['status'],'rejected')
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_forged_keys_rejected(self):
        remote,w,base=self.mkrelay()
        bad={"protocol":"awrp/0.1","request_id":"r-forge","action":"dispatch","idempotency_key":"k","expected_base":base,
             "params":{"task_id":"t","state":"working","phase":"x","summary":"s","event_id":"evt_forged","event_hash":"sha256:0"}}
        self.mkreq(w,'r-forge',bad)
        r=self.bridge(w,'r-forge')
        self.assertEqual(r['status'],'rejected')
        bad2={"protocol":"awrp/0.1","request_id":"r-forge2","action":"dispatch","idempotency_key":"k","expected_base":base,
              "fencing":{"generation":1},"params":{"task_id":"t","state":"working","phase":"x","summary":"s"}}
        self.mkreq(w,'r-forge2',bad2)
        r=self.bridge(w,'r-forge2')
        self.assertEqual(r['status'],'rejected')
        self.assertEqual(self.git(w,'rev-parse','main'),self.git(remote,'rev-parse','main'))
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_unrelated_file_drift_publishes(self):
        remote,w,base=self.mkrelay()
        b=self.tmp/'wb'
        subprocess.run(['git','-C',str(self.tmp),'clone',str(remote),str(b)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.email','t@e'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.name','t@e'],check=True,capture_output=True)
        (b/'rival.txt').write_text('rival\n')
        for args in (['add','-A'],['commit','-m','rival'],['push','origin','main']):
            subprocess.run(['git','-C',str(b),*args],check=True,capture_output=True)
        rival=self.git(remote,'rev-parse','main')
        self.mkreq(w,'r-fresh',{"protocol":"awrp/0.1","request_id":"r-fresh","action":"create-task","idempotency_key":"k","expected_base":base,
            "params":{"task_id":"task_s","context_id":"c","title":"T","goal":"g","project_id":"proj-b","channel_id":self.CH,"worker_endpoint":self.EP,"created_at":"2026-09-09T15:00:00Z"}})
        r=self.bridge(w,'r-fresh')
        self.assertEqual(r['status'],'published')
        self.assertTrue((w/'tasks'/'task_s'/'task.json').exists())
        awrp.validate(str(w/'tasks'/'task_s'))
        self.assertEqual(self.git(w,'rev-parse','main'),self.git(remote,'rev-parse','main'))
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_bridge_request_commit_gap_accepted_create(self):
        remote,w,base=self.mkrelay()
        self.mkreq(w,'r-live-create',{"protocol":"awrp/0.1","request_id":"r-live-create","action":"create-task","idempotency_key":"k-live-c","expected_base":base,
            "params":{"task_id":"task_gap","context_id":"c","title":"T","goal":"g","project_id":"proj-b","channel_id":self.CH,"worker_endpoint":self.EP,"created_at":"2026-09-09T15:00:00Z"}})
        self.git(w,'add','bridge/requests/r-live-create.json')
        self.git(w,'commit','-m','connector: request r-live-create')
        self.git(w,'push','origin','main')
        req_head=self.git(remote,'rev-parse','main')
        self.assertNotEqual(req_head,base)
        actions=self.fresh_clone(remote,'b-actions-create')
        r=self.bridge(actions,'r-live-create')
        self.assertEqual(r['status'],'published')
        self.assertIn('bridge/requests/r-live-create.json',r.get('transport_gap') or [])
        v=self.fresh_clone(remote,'b-verify-create')
        awrp.validate(str(v/'tasks'/'task_gap'))
        res=json.loads((v/'bridge'/'requests'/'r-live-create.result.json').read_text())
        self.assertEqual(res['status'],'published')
        self.assertIn('bridge/requests/r-live-create.json',res.get('transport_gap') or [])
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_bridge_request_commit_gap_accepted_dispatch(self):
        remote,w,base=self.mkrelay()
        self.mkreq(w,'r-c0',{"protocol":"awrp/0.1","request_id":"r-c0","action":"create-task","idempotency_key":"k-c0","expected_base":base,
            "params":{"task_id":"task_gap2","context_id":"c","title":"T","goal":"g","project_id":"proj-b","channel_id":self.CH,"worker_endpoint":self.EP,"created_at":"2026-09-09T15:00:00Z"}})
        r0=self.bridge(w,'r-c0')
        self.assertEqual(r0['status'],'published')
        base2=self.git(remote,'rev-parse','main')
        h=awrp.validate(str(w/'tasks'/'task_gap2'))['head']['event_id']
        self.mkreq(w,'r-live-dis',{"protocol":"awrp/0.1","request_id":"r-live-dis","action":"dispatch","idempotency_key":"k-live-d","expected_base":base2,
            "params":{"task_id":"task_gap2","run_id":"run_gap","recipient_role":"worker","recipient_id":self.EP,"state":"working","phase":"x","waiting_on":self.EP,"run_state":"dispatched","summary":"go","expected_head":h}})
        self.git(w,'add','bridge/requests/r-live-dis.json')
        self.git(w,'commit','-m','connector: request r-live-dis')
        self.git(w,'push','origin','main')
        self.assertNotEqual(self.git(remote,'rev-parse','main'),base2)
        actions=self.fresh_clone(remote,'b-actions-dis')
        r=self.bridge(actions,'r-live-dis')
        self.assertEqual(r['status'],'published')
        self.assertIn('bridge/requests/r-live-dis.json',r.get('transport_gap') or [])
        v=self.fresh_clone(remote,'b-verify-dis')
        ev=json.loads((v/'tasks'/'task_gap2'/'events'/sorted(p.name for p in (v/'tasks'/'task_gap2'/'events').glob('*.json'))[-1]).read_text())
        self.assertEqual(ev['actor'],{'role':'coordinator','id':'coord-A'})
        self.assertEqual(ev.get('fencing'),{'channel_id':self.CH,'generation':1,'owner':'coord-A'})
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_bridge_unrelated_canonical_race_publishes(self):
        remote,w,base=self.mkrelay()
        self.mkreq(w,'r-rival',{"protocol":"awrp/0.1","request_id":"r-rival","action":"create-task","idempotency_key":"k-rival","expected_base":base,
            "params":{"task_id":"task_rival","context_id":"c","title":"T","goal":"g","project_id":"proj-b","channel_id":self.CH,"worker_endpoint":self.EP,"created_at":"2026-09-09T15:00:00Z"}})
        rr=self.bridge(w,'r-rival')
        self.assertEqual(rr['status'],'published')
        self.mkreq(w,'r-live2',{"protocol":"awrp/0.1","request_id":"r-live2","action":"create-task","idempotency_key":"k-live2","expected_base":base,
            "params":{"task_id":"task_live2","context_id":"c","title":"T","goal":"g","project_id":"proj-b","channel_id":self.CH,"worker_endpoint":self.EP,"created_at":"2026-09-09T15:00:00Z"}})
        self.git(w,'add','bridge/requests/r-live2.json')
        self.git(w,'commit','-m','connector: request r-live2')
        self.git(w,'push','origin','main')
        actions=self.fresh_clone(remote,'b-actions-live2')
        r=self.bridge(actions,'r-live2')
        self.assertEqual(r['status'],'published')
        self.assertEqual(r.get('gap_kind'),'unrelated-canonical')
        v=self.fresh_clone(remote,'b-verify-live2')
        self.assertTrue((v/'tasks'/'task_live2'/'task.json').exists())
        awrp.validate(str(v/'tasks'/'task_live2'))
        res=json.loads((v/'bridge'/'requests'/'r-live2.result.json').read_text())
        self.assertEqual(res['status'],'published')
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_bridge_create_dispatch_lifecycle(self):
        remote,w,base=self.mkrelay()
        self.mkreq(w,'r-create',{"protocol":"awrp/0.1","request_id":"r-create","action":"create-task","idempotency_key":"k-c","expected_base":base,
            "params":{"task_id":"task_e2e","context_id":"c","title":"T","goal":"g","project_id":"proj-b","channel_id":self.CH,"worker_endpoint":self.EP,"created_at":"2026-09-09T15:00:00Z"}})
        r=self.bridge(w,'r-create')
        self.assertEqual(r['status'],'published')
        b=self.fresh_clone(remote,'b-fresh')
        v=awrp.validate(str(b/'tasks'/'task_e2e'))
        self.assertEqual(v['head']['task_projection']['state'],'submitted')
        h=v['head']['event_id']
        base2=self.git(remote,'rev-parse','main')
        self.mkreq(w,'r-dis',{"protocol":"awrp/0.1","request_id":"r-dis","action":"dispatch","idempotency_key":"k-d","expected_base":base2,
            "params":{"task_id":"task_e2e","run_id":"run_e2e","recipient_role":"worker","recipient_id":self.EP,"state":"working","phase":"x","waiting_on":self.EP,"run_state":"dispatched","summary":"go","expected_head":h}})
        r=self.bridge(w,'r-dis')
        self.assertEqual(r['status'],'published')
        ev=json.loads((w/'tasks'/'task_e2e'/'events'/sorted(p.name for p in (w/'tasks'/'task_e2e'/'events').glob('*.json'))[-1]).read_text())
        self.assertEqual(ev['actor'],{'role':'coordinator','id':'coord-A'})
        self.assertEqual(ev.get('fencing'),{'channel_id':self.CH,'generation':1,'owner':'coord-A'})
        c=self.fresh_clone(remote,'c-fresh')
        ws=self.tmp/'ws'; ws.mkdir()
        class A: pass
        a=A(); a.root=str(ws); a.relay='Bruce-Yii/awrp'; a.relay_dir=str(c); a.channel=self.CH; a.worker_endpoint=self.EP; a.lane=None; a.project_id=None; a.bound_by='t'; a.force=False
        awrp.do_bind(a)
        s=awrp.select_for_resume(str(c),self.CH,self.EP,None,None)
        self.assertEqual((s['status'],s['task_id'],s['run_id']),('EXECUTE','task_e2e','run_e2e'))
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_duplicate_replay_skipped(self):
        remote,w,base=self.mkrelay()
        self.mkreq(w,'r-dup',{"protocol":"awrp/0.1","request_id":"r-dup","action":"create-task","idempotency_key":"k","expected_base":base,
            "params":{"task_id":"task_d","context_id":"c","title":"T","goal":"g","project_id":"proj-b","channel_id":self.CH,"worker_endpoint":self.EP,"created_at":"2026-09-09T15:00:00Z"}})
        r1=self.bridge(w,'r-dup')
        self.assertEqual(r1['status'],'published')
        tip=self.git(remote,'rev-parse','main')
        r2=self.bridge(w,'r-dup')
        self.assertEqual(r2['status'],'skipped')
        self.assertEqual(self.git(remote,'rev-parse','main'),tip)
    def test_workflow_recursion_guard(self):
        wf=(Path(__file__).resolve().parents[1]/'.github'/'workflows'/'awrp-bridge.yml').read_text(encoding='utf-8')
        self.assertIn('bridge/requests/*.json',wf)
        self.assertIn('*.result.json',wf)
        self.assertNotIn('tasks/**',wf)
        self.assertIn('bridge-process',wf)
        self.assertIn('setup-python',wf)
        self.assertIn('contents: write',wf.replace('contents:write','contents: write'))
        self.assertIn('user.name',wf)
        self.assertIn('user.email',wf)
        for banned in ['"TASK_CREATED"','event_hash','fencing','commit-tree','create-blob']:
            self.assertNotIn(banned,wf)
class TY(unittest.TestCase):
    CH='ch-ty'; EP='ep-ty'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def git(self,repo,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def mkctx(self,root,ctx='c'):
        (Path(root)/'contexts').mkdir(exist_ok=True)
        awrp.write_new(Path(root)/'contexts'/f'{ctx}.json',{'protocol':'awrp/0.1','context_id':ctx,'title':'t','created_at':awrp.now(),'description':''})
    def mkproj(self,root,pid,channels=()):
        return awrp.project_create(str(root),pid,'T-'+pid,channels,None,'chatgpt')
    def mktask(self,root,tid,lane=None,project=None,endpoint=EP,channel=CH):
        class A: pass
        a=A(); a.root=str(root); a.context_id='c'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=channel; a.lane_id=lane; a.worker_endpoint=endpoint; a.project_id=project
        a.legacy=True
        awrp.create_task(a); return str(Path(root)/'tasks'/tid)
    def emit(self,td,typ,rid,actor_role='coordinator',actor_id='chatgpt',recipient_role='worker',recipient_id='opencode',state='working',phase='x',waiting_on='opencode',run_state=None,artifacts=None,details=None,key=None,fg=None):
        import os, tempfile as _tf
        if typ=='DISPATCH':
            _ep=(json.loads((Path(td)/'task.json').read_text(encoding='utf-8')).get('routing') or {}).get('worker_endpoint') or 'ep-ty'
            recipient_id=_ep; waiting_on=_ep
        class A: pass
        a=A(); a.task_dir=td; a.type=typ; a.actor_role=actor_role; a.actor_id=actor_id; a.recipient_role=recipient_role; a.recipient_id=recipient_id; a.run_id=rid; a.new_run=False; a.state=state; a.phase=phase; a.waiting_on=waiting_on; a.run_state=run_state; a.summary='s'
        a.details_file=None; a.artifacts_file=None; a.approval_file=None
        if details is not None:
            fd,nm=_tf.mkstemp(suffix='.md'); os.close(fd); Path(nm).write_text(details,encoding='utf-8'); a.details_file=nm
        if artifacts is not None:
            fd,nm=_tf.mkstemp(suffix='.json'); os.close(fd); Path(nm).write_text(json.dumps(artifacts),encoding='utf-8'); a.artifacts_file=nm
        a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=fg; a.idempotency_key=key; a.require_fresh=False; a.legacy_route=True
        try: awrp.emit(a)
        finally:
            for p in (a.details_file,a.artifacts_file):
                if p:
                    try: Path(p).unlink()
                    except OSError: pass
    def out(self,fn,*args):
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): fn(*args)
        return json.loads(buf.getvalue())
    def events(self,td): return sorted(p.name for p in (Path(td)/'events').glob('*.json'))
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_f1_float_artifact_leaves_zero_trace(self):
        self.mkctx(self.tmp); td=self.mktask(self.tmp,'task_f1')
        self.emit(td,'DISPATCH','run_1',run_state='dispatched')
        before=self.events(td); md_before=(Path(td)/'TASK.md').read_bytes()
        with self.assertRaises(RuntimeError):
            self.emit(td,'HANDOFF','run_1',actor_role='worker',actor_id='ep-ty',recipient_role='coordinator',recipient_id='chatgpt',run_state='succeeded',artifacts=[{'kind':'x','v':1.5}])
        self.assertEqual(self.events(td),before)
        self.assertEqual((Path(td)/'TASK.md').read_bytes(),md_before)
        awrp.validate(td)
    def test_f1_postwrite_failure_rolls_back(self):
        self.mkctx(self.tmp); td=self.mktask(self.tmp,'task_f1b')
        self.emit(td,'DISPATCH','run_1',run_state='dispatched')
        before=self.events(td); md_before=(Path(td)/'TASK.md').read_bytes()
        real=awrp.validate; seen=[]
        def boom(t):
            seen.append(str(t))
            if len(seen)>1: raise RuntimeError('simulated post-write validation failure')
            return real(t)
        awrp.validate=boom
        try:
            with self.assertRaises(RuntimeError):
                self.emit(td,'ACK','run_1',actor_role='worker',actor_id='ep-ty',recipient_role='coordinator',recipient_id='chatgpt',run_state='working')
        finally: awrp.validate=real
        self.assertEqual(self.events(td),before)
        self.assertEqual((Path(td)/'TASK.md').read_bytes(),md_before)
        awrp.validate(td)
    def test_f2_terminal_requires_coordinator(self):
        self.mkctx(self.tmp); td=self.mktask(self.tmp,'task_f2')
        self.emit(td,'DISPATCH','run_1',run_state='dispatched')
        self.emit(td,'ACK','run_1',actor_role='worker',actor_id='ep-ty',recipient_role='coordinator',recipient_id='chatgpt',run_state='working')
        with self.assertRaises(RuntimeError):
            self.emit(td,'HANDOFF','run_1',actor_role='worker',actor_id='ep-ty',recipient_role='coordinator',recipient_id='chatgpt',state='completed',phase='done',waiting_on='null',run_state='succeeded')
        with self.assertRaises(RuntimeError):
            self.emit(td,'ERROR','run_1',actor_role='worker',actor_id='ep-ty',recipient_role='coordinator',recipient_id='chatgpt',state='failed',phase='done',waiting_on='null',run_state='failed')
        self.emit(td,'HANDOFF','run_1',actor_role='worker',actor_id='ep-ty',recipient_role='coordinator',recipient_id='chatgpt',phase='review',waiting_on='chatgpt',run_state='succeeded')
        v=awrp.validate(td)
        self.assertEqual(v['head']['task_projection']['state'],'working')
        self.assertIsNone(v.get('active_run_id'))
    def test_f2_coordinator_may_accept(self):
        self.mkctx(self.tmp); td=self.mktask(self.tmp,'task_f2c')
        self.emit(td,'DISPATCH','run_1',run_state='dispatched')
        self.emit(td,'APPROVAL','run_1',state='completed',phase='done',waiting_on='null',run_state='succeeded')
        v=awrp.validate(td)
        self.assertEqual(v['head']['task_projection']['state'],'completed')
        self.assertIsNone(v.get('active_run_id'))
    def test_f2_worker_reconcile_refused(self):
        self.mkctx(self.tmp); td=self.mktask(self.tmp,'task_f2r')
        self.emit(td,'DISPATCH','run_1',run_state='dispatched')
        with self.assertRaises(RuntimeError):
            self.emit(td,'RECONCILE','run_1',actor_role='worker',actor_id='ep-ty',recipient_role=None,recipient_id=None,run_state=None)
        self.assertEqual(len(self.events(td)),2)
    def test_f3_foreign_handoff_refused(self):
        self.mkctx(self.tmp); td=self.mktask(self.tmp,'task_f3')
        self.emit(td,'DISPATCH','run_1',run_state='dispatched')
        self.emit(td,'ACK','run_1',actor_role='worker',actor_id='ep-ty',recipient_role='coordinator',recipient_id='chatgpt',run_state='working')
        with self.assertRaises(RuntimeError) as cm:
            self.emit(td,'HANDOFF','run_1',actor_role='worker',actor_id='worker-B',recipient_role='coordinator',recipient_id='chatgpt',phase='review',waiting_on='chatgpt',run_state='succeeded')
        self.assertIn('ep-ty',str(cm.exception))
        with self.assertRaises(RuntimeError):
            self.emit(td,'INPUT_REQUEST','run_1',actor_role='worker',actor_id='worker-B',recipient_role='coordinator',recipient_id='chatgpt',run_state='working')
        self.emit(td,'HANDOFF','run_1',actor_role='worker',actor_id='ep-ty',recipient_role='coordinator',recipient_id='chatgpt',phase='review',waiting_on='chatgpt',run_state='succeeded')
        v=awrp.validate(td)
        self.assertEqual(v['runs']['run_1']['state'],'succeeded')
    def test_f6_duplicate_key_names_outcome(self):
        self.mkctx(self.tmp); td=self.mktask(self.tmp,'task_f6')
        self.emit(td,'DISPATCH','run_1',run_state='dispatched',key='k-cmd-1')
        first=[n for n in self.events(td) if n.startswith('000002')][0]
        self.emit(td,'CANCEL',None,state='canceled',phase='x',waiting_on='null')
        with self.assertRaises(RuntimeError) as cm:
            self.emit(td,'DISPATCH','run_2',run_state='dispatched',key='k-cmd-1')
        ev1=json.loads((Path(td)/'events'/first).read_text())
        self.assertIn(ev1['event_id'],str(cm.exception))
        self.assertEqual(len(self.events(td)),3)
    def test_f6_replay_indexes_keys(self):
        self.mkctx(self.tmp); td=self.mktask(self.tmp,'task_f6r')
        self.emit(td,'DISPATCH','run_1',run_state='dispatched',key='k-dis')
        r=self.out(awrp.replay,type('A',(),{'task_dir':td})())
        self.assertIn('idempotency',r)
        ev1=[n for n in self.events(td) if n.startswith('000002')][0]
        ev1id=json.loads((Path(td)/'events'/ev1).read_text())['event_id']
        self.assertEqual(r['idempotency'].get('k-dis'),ev1id)
        self.assertIsNone(r['idempotency'].get('k-ghost'))
    def gitrepo(self):
        remote=self.tmp/'r.git'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(self.tmp,'init','-b','main')
        self.git(self.tmp,'config','user.email','t@e'); self.git(self.tmp,'config','user.name','t')
        self.git(self.tmp,'add','-A'); self.git(self.tmp,'commit','-m','seed')
        self.git(self.tmp,'remote','add','origin',str(remote))
        self.git(self.tmp,'push','-u','origin','main')
        return remote
    def attach(self,ws,pid):
        class A: pass
        a=A(); a.root=str(ws); a.relay_dir=str(self.tmp); a.project_id=pid; a.by='t'
        return self.out(awrp.do_attach,a)
    def switch(self,ws,pid,tid,rid):
        class A: pass
        a=A(); a.root=str(ws); a.relay_dir=str(self.tmp); a.project_id=pid; a.task_id=tid; a.run_id=rid
        return self.out(awrp.do_switch,a)
    def focus(self,ws):
        class A: pass
        a=A(); a.root=str(ws); a.relay_dir=str(self.tmp)
        return self.out(awrp.do_focus,a)
    def lineage(self,ws,pid,tid,rid):
        class A: pass
        a=A(); a.root=str(ws); a.relay_dir=str(self.tmp); a.project_id=pid; a.task_id=tid; a.run_id=rid
        return self.out(awrp.do_check_lineage,a)
    def test_lane_null_visible_to_pinned_binding(self):
        self.mkctx(self.tmp)
        td=self.mktask(self.tmp,'task_nolane')
        self.emit(td,'DISPATCH','run_n',run_state='dispatched')
        r=awrp.select_for_resume(str(self.tmp),self.CH,self.EP,'lane-x',None)
        self.assertEqual((r['status'],r['task_id'],r['run_id']),('EXECUTE','task_nolane','run_n'))
    def test_lane_set_tasks_stay_exclusive(self):
        self.mkctx(self.tmp)
        td=self.mktask(self.tmp,'task_yl',lane='lane-y')
        self.emit(td,'DISPATCH','run_y',run_state='dispatched')
        r=awrp.select_for_resume(str(self.tmp),self.CH,self.EP,'lane-x',None)
        self.assertEqual(r['status'],'NO_TASK')
        r=awrp.select_for_resume(str(self.tmp),self.CH,self.EP,'lane-y',None)
        self.assertEqual((r['status'],r['task_id']),('EXECUTE','task_yl'))
    def test_lane_null_plus_own_lane_is_ambiguous(self):
        self.mkctx(self.tmp)
        a=self.mktask(self.tmp,'task_nolane'); self.emit(a,'DISPATCH','run_n',run_state='dispatched')
        b=self.mktask(self.tmp,'task_x',lane='lane-x'); self.emit(b,'DISPATCH','run_x',run_state='dispatched')
        r=awrp.select_for_resume(str(self.tmp),self.CH,self.EP,'lane-x',None)
        self.assertEqual(r['status'],'AMBIGUOUS')
        self.assertEqual(sorted(r['candidates']),['task_nolane','task_x'])
    def test_f4_historical_lineage_attribution(self):
        self.mkctx(self.tmp); self.mkproj(self.tmp,'proj-l',(self.CH,))
        td=self.mktask(self.tmp,'task_l4',project='proj-l')
        self.emit(td,'DISPATCH','run_1',run_state='dispatched')
        self.emit(td,'ACK','run_1',actor_role='worker',actor_id='ep-ty',recipient_role='coordinator',recipient_id='chatgpt',run_state='working')
        self.emit(td,'HANDOFF','run_1',actor_role='worker',actor_id='ep-ty',recipient_role='coordinator',recipient_id='chatgpt',phase='review',waiting_on='chatgpt',run_state='succeeded')
        self.emit(td,'DISPATCH','run_2',run_state='dispatched')
        self.gitrepo()
        ws=self.tmp/'ws'; ws.mkdir()
        self.attach(ws,'proj-l'); self.switch(ws,'proj-l','task_l4','run_2')
        snap=(ws/'.awrp'/'session.json').read_bytes()
        live=self.lineage(ws,'proj-l','task_l4','run_2')
        self.assertEqual((live['match'],live['historical']),(True,False))
        hist=self.lineage(ws,'proj-l','task_l4','run_1')
        self.assertEqual((hist['match'],hist['historical']),(True,True))
        ghost=self.lineage(ws,'proj-l','task_l4','run_ghost')
        self.assertEqual(ghost['match'],False)
        self.assertEqual((ws/'.awrp'/'session.json').read_bytes(),snap)
    def test_takeover_dogfood_attach_switch_focus_ack(self):
        self.mkctx(self.tmp); self.mkproj(self.tmp,'proj-l',(self.CH,))
        td=self.mktask(self.tmp,'task_td',project='proj-l')
        self.emit(td,'DISPATCH','run_1',run_state='dispatched')
        self.gitrepo()
        ws=self.tmp/'ws'; ws.mkdir()
        self.attach(ws,'proj-l'); self.switch(ws,'proj-l','task_td','run_1')
        f=self.focus(ws)
        self.assertEqual(f['status'],'FOCUS_EXECUTE')
        v=awrp.validate(td)
        self.assertEqual((f['head_event_id'],f['head_hash']),(v['head']['event_id'],v['head']['integrity']['event_hash']))
        with self.assertRaises(RuntimeError):
            self.switch(ws,'proj-l','task_td','run_ghost')
        self.emit(td,'ACK','run_1',actor_role='worker',actor_id='ep-ty',recipient_role='coordinator',recipient_id='chatgpt',run_state='working')
        self.assertEqual(self.focus(ws)['status'],'FOCUS_OWNED')
    def test_authority_matrix(self):
        self.mkctx(self.tmp)
        rows=[
            ('worker','HANDOFF','working',True,'succeeded'),
            ('worker','HANDOFF','completed',False,'succeeded'),
            ('worker','ERROR','failed',False,'failed'),
            ('worker','INPUT_REQUEST','input_required',True,None),
            ('worker','INPUT_PROVIDED','working',True,None),
            ('coordinator','APPROVAL','completed',True,'succeeded'),
            ('coordinator','CANCEL','canceled',True,None),
            ('worker','RECONCILE','working',False,None),
            ('coordinator','RECONCILE','working',True,None),
        ]
        for i,(role,typ,state,ok,run_state) in enumerate(rows):
            td=self.mktask(self.tmp,f'task_m{i}')
            self.emit(td,'DISPATCH','run_1',run_state='dispatched')
            actor=role if role=='coordinator' else 'ep-ty'
            if typ in ('ACK','HANDOFF','INPUT_REQUEST','INPUT_PROVIDED','ERROR'):
                self.emit(td,'ACK','run_1',actor_role='worker',actor_id='ep-ty',recipient_role='coordinator',recipient_id='chatgpt',run_state='working')
            kw={'actor_role':role,'actor_id':('chatgpt' if role=='coordinator' else 'ep-ty')}
            if typ=='HANDOFF': kw.update(recipient_role='coordinator',recipient_id='chatgpt',phase='review',waiting_on='chatgpt')
            if role=='coordinator' and typ in ('APPROVAL','REVIEW'): kw.update(recipient_role=None,recipient_id=None)
            if ok:
                self.emit(td,typ,'run_1',state=state,run_state=run_state,**kw)
            else:
                with self.assertRaises(RuntimeError,msg=f'row {i} {role}/{typ}/{state}'):
                    self.emit(td,typ,'run_1',state=state,run_state=run_state,**kw)
    def test_project_name_recovery_chain(self):
        self.mkctx(self.tmp)
        awrp.project_create(str(self.tmp),'proj-r','Recovery Project',(self.CH,),None,'chatgpt',('rec-alias',))
        td=self.mktask(self.tmp,'task_rec',project='proj-r')
        self.emit(td,'DISPATCH','run_1',run_state='dispatched')
        r=self.out(awrp.do_resolve_project,type('A',(),{'root':str(self.tmp),'project_id':None,'alias':'rec-alias','title':None})())
        self.assertEqual((r['status'],r['project']['project_id']),('RESOLVED','proj-r'))
        s=self.out(awrp.do_project_snapshot,type('A',(),{'root':str(self.tmp),'project_id':'proj-r'})())
        self.assertIn('task_rec',s['actionable_candidates'])
    def test_beijing_display_keeps_canonical_utc(self):
        self.mkctx(self.tmp); td=self.mktask(self.tmp,'task_bj')
        self.emit(td,'DISPATCH','run_1',run_state='dispatched')
        md=(Path(td)/'TASK.md').read_text(encoding='utf-8')
        self.assertIn('UTC+08:00',md)
        ev=sorted((Path(td)/'events').glob('*.json'))[-1].read_text(encoding='utf-8')
        self.assertNotIn('+08:00',ev)
        self.assertIn('Z',ev)
        r=self.out(awrp.replay,type('A',(),{'task_dir':td})())
        self.assertIn('UTC+08:00',r.get('head_created_at_beijing',''))
    def test_concurrent_tasks_no_double_run(self):
        self.mkctx(self.tmp)
        a=self.mktask(self.tmp,'task_ca'); self.emit(a,'DISPATCH','run_a',run_state='dispatched')
        b=self.mktask(self.tmp,'task_cb'); self.emit(b,'DISPATCH','run_b',run_state='dispatched')
        self.emit(a,'ACK','run_a',actor_role='worker',actor_id='ep-ty',recipient_role='coordinator',recipient_id='chatgpt',run_state='working')
        self.emit(b,'ACK','run_b',actor_role='worker',actor_id='ep-ty',recipient_role='coordinator',recipient_id='chatgpt',run_state='working')
        self.emit(a,'HANDOFF','run_a',actor_role='worker',actor_id='ep-ty',recipient_role='coordinator',recipient_id='chatgpt',phase='review',waiting_on='chatgpt',run_state='succeeded')
        self.emit(b,'HANDOFF','run_b',actor_role='worker',actor_id='ep-ty',recipient_role='coordinator',recipient_id='chatgpt',phase='review',waiting_on='chatgpt',run_state='succeeded')
        va=awrp.validate(a); vb=awrp.validate(b)
        self.assertIsNone(va.get('active_run_id')); self.assertIsNone(vb.get('active_run_id'))
        self.assertEqual(va['runs']['run_a']['executor'],'ep-ty')
        self.assertEqual(vb['runs']['run_b']['executor'],'ep-ty')
        self.assertTrue(all(e.get('run_id')=='run_a' or e.get('run_id') is None for e in va['events'] if e['type']!='TASK_CREATED'))
    def mkbridge(self):
        remote=self.tmp/'r.git'; w=self.tmp/'w'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(self.tmp,'init','-b','main',str(w))
        self.git(w,'config','user.email','t@e'); self.git(w,'config','user.name','t')
        self.mkctx(w)
        awrp.project_create(str(w),'proj-b','T-proj-b',(self.CH,),None,'chatgpt')
        awrp.acquire_claim(str(w),self.CH,'coord-TY')
        (w/'relay.json').write_text(json.dumps({'protocol':'awrp/0.1','relay':'Bruce-Yii/awrp'}),encoding='utf-8')
        self.git(w,'add','-A'); self.git(w,'commit','-m','seed'); self.git(w,'remote','add','origin',str(remote))
        self.git(w,'push','-u','origin','main')
        return remote,w,self.git(w,'rev-parse','main')
    def mkreq(self,w,rid,body):
        p=w/'bridge'/'requests'; p.mkdir(parents=True,exist_ok=True)
        (p/f'{rid}.json').write_text(body if isinstance(body,str) else json.dumps(body),encoding='utf-8')
    def bridge(self,w,rid):
        class A: pass
        a=A(); a.root=str(w); a.request=rid; a.repo=str(w); a.branch='main'; a.remote='origin'
        buf=__import__('io').StringIO()
        import contextlib
        with contextlib.redirect_stdout(buf): awrp.do_bridge_process(a)
        return json.loads(buf.getvalue())
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_f5_formal_create_dispatch_render_bootstrap(self):
        remote,w,base=self.mkbridge()
        self.mkreq(w,'r-f5c',{"protocol":"awrp/0.1","request_id":"r-f5c","action":"create-task","idempotency_key":"k-f5c","expected_base":base,
            "params":{"task_id":"task_f5","context_id":"c","title":"T","goal":"g","project_id":"proj-b","channel_id":self.CH,"worker_endpoint":self.EP,"created_at":"2026-09-09T15:00:00Z"}})
        r=self.bridge(w,'r-f5c')
        self.assertEqual(r['status'],'published')
        self.assertEqual(json.loads((w/'tasks'/'task_f5'/'task.json').read_text())['transport'],{'relay_repo':'Bruce-Yii/awrp'})
        base2=self.git(remote,'rev-parse','main')
        h=awrp.validate(str(w/'tasks'/'task_f5'))['head']['event_id']
        self.mkreq(w,'r-f5d',{"protocol":"awrp/0.1","request_id":"r-f5d","action":"dispatch","idempotency_key":"k-f5d","expected_base":base2,
            "params":{"task_id":"task_f5","run_id":"run_f5","recipient_role":"worker","recipient_id":self.EP,"state":"working","phase":"x","waiting_on":self.EP,"run_state":"dispatched","summary":"go","expected_head":h}})
        r=self.bridge(w,'r-f5d')
        self.assertEqual(r['status'],'published')
        class A: pass
        a=A(); a.root=str(w); a.project_id='proj-b'; a.task_id='task_f5'; a.run_id=None
        rb=self.out(awrp.do_render_bootstrap,a)
        self.assertIn('first-bind',rb['command'])
        self.assertIn('task_f5',rb['command']); self.assertIn('run_f5',rb['command'])
        self.assertEqual(rb['relay'],'Bruce-Yii/awrp')
class TZ(unittest.TestCase):
    CH='ch-tz'; EP='ep-tz'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def mkctx(self,root,ctx='c'):
        (Path(root)/'contexts').mkdir(exist_ok=True)
        awrp.write_new(Path(root)/'contexts'/f'{ctx}.json',{'protocol':'awrp/0.1','context_id':ctx,'title':'t','created_at':awrp.now(),'description':''})
    def mkproj(self,root,pid,channels=()):
        return awrp.project_create(str(root),pid,'T-'+pid,channels,None,'chatgpt')
    def mktask(self,root,tid,lane=None,project=None,endpoint=EP,channel=CH,ctx='c'):
        import os
        class A: pass
        a=A(); a.root=str(root); a.context_id=ctx; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=channel; a.lane_id=lane; a.worker_endpoint=endpoint; a.project_id=project
        a.legacy=True
        awrp.create_task(a); return str(Path(root)/'tasks'/tid)
    def emit(self,td,typ,rid,actor_role='coordinator',actor_id='chatgpt',recipient_role='worker',recipient_id='opencode',state='working',phase='x',waiting_on='opencode',run_state=None):
        import os
        if typ=='DISPATCH':
            _ep=(json.loads((Path(td)/'task.json').read_text(encoding='utf-8')).get('routing') or {}).get('worker_endpoint') or 'ep-ty'
            recipient_id=_ep; waiting_on=_ep
        class A: pass
        a=A(); a.task_dir=td; a.type=typ; a.actor_role=actor_role; a.actor_id=actor_id; a.recipient_role=recipient_role; a.recipient_id=recipient_id; a.run_id=rid; a.new_run=False; a.state=state; a.phase=phase; a.waiting_on=waiting_on; a.run_state=run_state; a.summary='s'
        a.details_file=None; a.artifacts_file=None; a.approval_file=None
        a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None; a.idempotency_key=None; a.require_fresh=False; a.legacy_route=True
        awrp.emit(a)
    def dis(self,td,rid,recipient=EP):
        self.emit(td,'DISPATCH',rid,recipient_role='worker',recipient_id=recipient,waiting_on=recipient,run_state='dispatched')
    def test_cross_project_resume_isolation(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',('ch-a',)); self.mkproj(self.tmp,'proj-b',('ch-b',))
        a=self.mktask(self.tmp,'task_a',project='proj-a',endpoint='ep-a',channel='ch-a')
        b=self.mktask(self.tmp,'task_b',project='proj-b',endpoint='ep-b',channel='ch-b')
        self.dis(a,'run_a',recipient='ep-a'); self.dis(b,'run_b',recipient='ep-b')
        ra=awrp.select_for_resume(str(self.tmp),'ch-a','ep-a',None,None)
        rb=awrp.select_for_resume(str(self.tmp),'ch-b','ep-b',None,None)
        self.assertEqual((ra['status'],ra['task_id']),('EXECUTE','task_a'))
        self.assertEqual((rb['status'],rb['task_id']),('EXECUTE','task_b'))
        ia=awrp.scan_inbox(str(self.tmp),project='proj-a')
        ib=awrp.scan_inbox(str(self.tmp),project='proj-b')
        self.assertEqual([r['task_id'] for r in ia['actionable']],['task_a'])
        self.assertEqual([r['task_id'] for r in ib['actionable']],['task_b'])
    def test_route_compat_rejects_cross_project(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',('ch-a',)); self.mkproj(self.tmp,'proj-b',('ch-b',))
        td=self.mktask(self.tmp,'task_a',project='proj-a',endpoint='ep-a',channel='ch-a')
        t=json.loads((Path(td)/'task.json').read_text())
        bad={'channel_id':'ch-b','worker_endpoint':'ep-b','lane_id':None,'project_id':'proj-b'}
        self.assertTrue(awrp.route_compat_error(bad,t,str(self.tmp)))
        good={'channel_id':'ch-a','worker_endpoint':'ep-a','lane_id':None,'project_id':'proj-a'}
        self.assertIsNone(awrp.route_compat_error(good,t,str(self.tmp)))
    def test_ownership_mismatch_fails_validate(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-a',('ch-a',)); self.mkproj(self.tmp,'proj-b',('ch-b',))
        td=self.mktask(self.tmp,'task_x',channel='ch-a')
        tp=Path(td)/'task.json'; o=json.loads(tp.read_text()); o['project_id']='proj-b'; tp.write_text(json.dumps(o))
        with self.assertRaises(RuntimeError):
            awrp.validate(td)
    def test_broken_chain_excluded_not_actionable(self):
        self.mkctx(self.tmp)
        td=self.mktask(self.tmp,'task_brk')
        self.dis(td,'run_1')
        evp=sorted((Path(td)/'events').glob('*.json'))[-1]
        o=json.loads(evp.read_text()); o['summary']='tampered'; evp.write_text(json.dumps(o))
        with self.assertRaises(RuntimeError):
            awrp.validate(td)
        r=awrp.scan_inbox(str(self.tmp),channel=self.CH,worker_endpoint=self.EP)
        self.assertEqual(r['actionable'],[])
        self.assertEqual(len(r['invalid']),1)
    def test_stale_legacy_visible_only_unpinned(self):
        self.mkctx(self.tmp)
        td=self.mktask(self.tmp,'task_stale',lane='lane-legacy',endpoint='ep-legacy')
        self.dis(td,'run_s',recipient='ep-legacy')
        r=awrp.select_for_resume(str(self.tmp),self.CH,'ep-legacy',None,None)
        self.assertEqual((r['status'],r['task_id']),('EXECUTE','task_stale'))
        r2=awrp.select_for_resume(str(self.tmp),self.CH,'ep-legacy','lane-other',None)
        self.assertEqual(r2['status'],'NO_TASK')
    def test_migration_refusals(self):
        self.mkctx(self.tmp); self.mkproj(self.tmp,'proj-m',(self.CH,))
        td=self.mktask(self.tmp,'task_nc',endpoint=None,channel=None)
        with self.assertRaises(RuntimeError):
            awrp.migration_associate(str(self.tmp),'proj-m','task_nc')
        td2=self.mktask(self.tmp,'task_sc',project='proj-m')
        with self.assertRaises(RuntimeError):
            awrp.migration_associate(str(self.tmp),'proj-m','task_sc')
        td3=self.mktask(self.tmp,'task_or',channel='ch-orphan',endpoint='ep-o')
        with self.assertRaises(RuntimeError):
            awrp.migration_associate(str(self.tmp),'proj-m','task_or')
    def test_migration_success_path_deterministic(self):
        self.mkctx(self.tmp); self.mkproj(self.tmp,'proj-m',(self.CH,))
        td=self.mktask(self.tmp,'task_leg')
        m1=awrp.migration_associate(str(self.tmp),'proj-m','task_leg',reason='t')
        m2=awrp.read_migration(str(self.tmp),'proj-m','task_leg')
        self.assertEqual(m1,m2)
        s=self.out_snapshot('proj-m')
        self.assertIn('task_leg',[m['task_id'] for m in s['tasks']])
    def out_snapshot(self,pid):
        import io, contextlib
        buf=io.StringIO()
        class A: pass
        a=A(); a.root=str(self.tmp); a.project_id=pid
        with contextlib.redirect_stdout(buf): awrp.do_project_snapshot(a)
        return json.loads(buf.getvalue())
    def test_context_never_routes(self):
        self.mkctx(self.tmp,ctx='c'); self.mkctx(self.tmp,ctx='ctx_legacy')
        a=self.mktask(self.tmp,'task_c1',ctx='c')
        b=self.mktask(self.tmp,'task_c2',ctx='ctx_legacy')
        self.dis(a,'run_c1'); self.dis(b,'run_c2')
        r=awrp.scan_inbox(str(self.tmp),channel=self.CH,worker_endpoint=self.EP)
        self.assertEqual(sorted(x['task_id'] for x in r['actionable']),['task_c1','task_c2'])
    def test_render_needs_relay_identity(self):
        self.mkctx(self.tmp); self.mkproj(self.tmp,'proj-m',(self.CH,))
        td=self.mktask(self.tmp,'task_norelay',project='proj-m')
        self.dis(td,'run_1')
        class A: pass
        a=A(); a.root=str(self.tmp); a.project_id='proj-m'; a.task_id='task_norelay'; a.run_id=None
        with self.assertRaises(RuntimeError):
            awrp.do_render_bootstrap(a)
    def test_duplicate_alias_flagged(self):
        self.mkctx(self.tmp)
        awrp.project_create(str(self.tmp),'proj-1','T1',(self.CH,),None,'chatgpt',('same-alias',))
        awrp.project_create(str(self.tmp),'proj-2','T2',('ch-other',),None,'chatgpt',('same-alias',))
        r=awrp.audit_projects(str(self.tmp))
        self.assertFalse(r['ok'])
        self.assertTrue(any(v['type']=='ambiguous_alias' for v in r['violations']))
class TSC(unittest.TestCase):
    CH='ch-sc'; EP='ep-sc'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def git(self,repo,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def mkctx(self,root):
        (Path(root)/'contexts').mkdir(exist_ok=True)
        awrp.write_new(Path(root)/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
    def mkrelay2(self):
        remote=self.tmp/'r.git'; w=self.tmp/'w'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(self.tmp,'init','-b','main',str(w))
        self.git(w,'config','user.email','t@e'); self.git(w,'config','user.name','t')
        self.mkctx(w)
        awrp.project_create(str(w),'proj-s','S',(self.CH,),None,'chatgpt')
        awrp.acquire_claim(str(w),self.CH,'coord-S')
        (w/'relay.json').write_text(json.dumps({'protocol':'awrp/0.1','relay':'r'}),encoding='utf-8')
        self.git(w,'add','-A'); self.git(w,'commit','-m','seed'); self.git(w,'remote','add','origin',str(remote))
        self.git(w,'push','-u','origin','main'); self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
        for tid in ('task_a','task_b'):
            base=self.git(remote,'rev-parse','main')
            self.mkreq(w,'r-seed-'+tid,{"protocol":"awrp/0.1","request_id":'r-seed-'+tid,"action":"create-task","idempotency_key":'k-seed-'+tid,"expected_base":base,
                "params":{"task_id":tid,"context_id":"c","title":"T","goal":"g","project_id":"proj-s","channel_id":self.CH,"worker_endpoint":self.EP,"created_at":"2026-09-10T10:00:00Z"}})
            r=self.bridge(w,'r-seed-'+tid)
            assert r['status']=='published', r
        return remote,w,self.git(remote,'rev-parse','main')
    def mkreq(self,w,rid,body):
        p=w/'bridge'/'requests'; p.mkdir(parents=True,exist_ok=True)
        (p/f'{rid}.json').write_text(body if isinstance(body,str) else json.dumps(body),encoding='utf-8')
    def commit_req(self,w,rid,msg='connector: request'):
        self.git(w,'add',f'bridge/requests/{rid}.json')
        self.git(w,'commit','-m',f'{msg} {rid}')
        self.git(w,'push','origin','main')
    def bridge(self,w,rid):
        class A: pass
        a=A(); a.root=str(w); a.request=rid; a.repo=str(w); a.branch='main'; a.remote='origin'
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_bridge_process(a)
        return json.loads(buf.getvalue())
    def rival_clone(self,name='rival'):
        b=self.tmp/name
        subprocess.run(['git','-C',str(self.tmp),'clone',str(self.tmp/'r.git'),str(b)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.email','t@e'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.name','t@e'],check=True,capture_output=True)
        return b
    def emit(self,td,typ,rid,actor_role='coordinator',actor_id='coord-S',recipient_role='worker',recipient_id=None,state='working',phase='x',waiting_on=None,run_state=None,fg=None):
        class A: pass
        a=A(); a.task_dir=str(td); a.type=typ; a.actor_role=actor_role; a.actor_id=actor_id; a.recipient_role=recipient_role; a.recipient_id=self.EP if recipient_id is None else recipient_id; a.run_id=rid; a.new_run=False; a.state=state; a.phase=phase; a.waiting_on=self.EP if waiting_on is None else waiting_on; a.run_state=run_state; a.summary='s'
        a.details_file=None; a.artifacts_file=None; a.approval_file=None
        a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=fg; a.idempotency_key=None; a.require_fresh=False; a.legacy_route=True
        awrp.emit(a)
    def dispatch_req(self,w,rid,run,base,extra_params=None):
        params={"task_id":"task_a","run_id":run,"recipient_role":"worker","recipient_id":self.EP,"state":"working","phase":"x","waiting_on":self.EP,"run_state":"dispatched","summary":"go"}
        if extra_params: params.update(extra_params)
        self.mkreq(w,rid,{"protocol":"awrp/0.1","request_id":rid,"action":"dispatch","idempotency_key":'k-'+rid,"expected_base":base,"params":params})
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_unrelated_drift_publishes_without_resubmission(self):
        remote,w,base=self.mkrelay2()
        self.dispatch_req(w,'r-ab','run_ab',base)
        self.commit_req(w,'r-ab')
        rival=self.rival_clone()
        self.emit(rival/'tasks'/'task_b','REVIEW',None,phase='review',waiting_on='chatgpt',run_state=None,fg=1)
        self.git(rival,'add','-A'); self.git(rival,'commit','-m','rival review on B'); self.git(rival,'push','origin','main')
        r=self.bridge(w,'r-ab')
        self.assertEqual(r['status'],'published')
        self.assertEqual(r.get('gap_kind'),'unrelated-canonical')
        v=awrp.validate(str(w/'tasks'/'task_a'))
        self.assertEqual(len(v['events']),2)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_target_advance_rejects(self):
        remote,w,base=self.mkrelay2()
        self.dispatch_req(w,'r-t','run_t',base)
        self.commit_req(w,'r-t')
        rival=self.rival_clone()
        self.emit(rival/'tasks'/'task_a','REVIEW',None,phase='review',waiting_on='chatgpt',run_state=None,fg=1)
        self.git(rival,'add','-A'); self.git(rival,'commit','-m','rival review on A'); self.git(rival,'push','origin','main')
        r=self.bridge(w,'r-t')
        self.assertEqual(r['status'],'rejected')
        self.assertEqual(len(list((w/'tasks'/'task_a'/'events').glob('*.json'))),2)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_target_drift_matching_head_publishes(self):
        remote,w,base=self.mkrelay2()
        rival=self.rival_clone()
        self.emit(rival/'tasks'/'task_a','REVIEW',None,phase='review',waiting_on='chatgpt',run_state=None,fg=1)
        self.git(rival,'add','-A'); self.git(rival,'commit','-m','rival review on A'); self.git(rival,'push','origin','main')
        h=awrp.validate(str(rival/'tasks'/'task_a'))['head']
        self.dispatch_req(w,'r-tv','run_tv',base,extra_params={"expected_head":h['event_id'],"expected_hash":h['integrity']['event_hash']})
        self.git(w,'pull','--ff-only')
        self.commit_req(w,'r-tv')
        r=self.bridge(w,'r-tv')
        self.assertEqual(r['status'],'published')
        self.assertEqual(r.get('gap_kind'),'target-verified')
        self.assertEqual(len(list((w/'tasks'/'task_a'/'events').glob('*.json'))),3)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_claim_drift_rejects(self):
        remote,w,base=self.mkrelay2()
        self.dispatch_req(w,'r-c','run_c',base)
        self.commit_req(w,'r-c')
        rival=self.rival_clone()
        awrp.acquire_claim(str(rival),self.CH,'coord-R',expected_generation=1)
        self.git(rival,'add','-A'); self.git(rival,'commit','-m','rival takeover'); self.git(rival,'push','origin','main')
        r=self.bridge(w,'r-c')
        self.assertEqual(r['status'],'rejected')
        self.assertEqual(len(list((w/'tasks'/'task_a'/'events').glob('*.json'))),1)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_terminal_drift_rejects(self):
        remote,w,base=self.mkrelay2()
        self.dispatch_req(w,'r-k','run_k',base)
        self.commit_req(w,'r-k')
        rival=self.rival_clone()
        self.emit(rival/'tasks'/'task_a','CANCEL',None,actor_id='coord-S',state='canceled',phase='x',run_state=None,fg=1)
        self.git(rival,'add','-A'); self.git(rival,'commit','-m','rival cancel A'); self.git(rival,'push','origin','main')
        r=self.bridge(w,'r-k')
        self.assertEqual(r['status'],'rejected')
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_other_channel_claim_drift_ok(self):
        remote,w,base=self.mkrelay2()
        self.dispatch_req(w,'r-o','run_o',base)
        self.commit_req(w,'r-o')
        rival=self.rival_clone()
        awrp.acquire_claim(str(rival),'ch-other','someone')
        self.git(rival,'add','-A'); self.git(rival,'commit','-m','rival other claim'); self.git(rival,'push','origin','main')
        r=self.bridge(w,'r-o')
        self.assertEqual(r['status'],'published')
    def mktask_r(self,root,tid):
        class A: pass
        a=A(); a.root=str(root); a.context_id='c'; a.task_id=tid; a.title='t'; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=self.CH; a.lane_id=None; a.worker_endpoint=self.EP; a.project_id='proj-s'
        a.legacy=True
        awrp.create_task(a); return str(Path(root)/'tasks'/tid)
    def close_run_1(self,td):
        self.emit(td,'DISPATCH','run_1',run_state='dispatched')
        self.emit(td,'ACK','run_1',actor_role='worker',actor_id='ep-sc',recipient_role='coordinator',recipient_id='chatgpt',run_state='working')
        self.emit(td,'HANDOFF','run_1',actor_role='worker',actor_id='ep-sc',recipient_role='coordinator',recipient_id='chatgpt',phase='review',waiting_on='chatgpt',run_state='succeeded')
    def test_review_completed_run_accepts(self):
        self.mkctx(self.tmp)
        awrp.project_create(str(self.tmp),'proj-s','S',(self.CH,),None,'chatgpt')
        td=self.mktask_r(self.tmp,'task_r1')
        self.close_run_1(td)
        self.emit(td,'REVIEW','run_1',phase='review',waiting_on='chatgpt',run_state='succeeded')
        self.emit(td,'APPROVAL','run_1',state='completed',phase='done',waiting_on='null',run_state='succeeded')
        v=awrp.validate(td)
        self.assertEqual(v['head']['task_projection']['state'],'completed')
        self.assertIsNone(v.get('active_run_id'))
    def test_review_superseded_run_rejects(self):
        self.mkctx(self.tmp)
        awrp.project_create(str(self.tmp),'proj-s','S',(self.CH,),None,'chatgpt')
        td=self.mktask_r(self.tmp,'task_r2')
        self.close_run_1(td)
        self.emit(td,'DISPATCH','run_2',run_state='dispatched')
        with self.assertRaises(RuntimeError):
            self.emit(td,'REVIEW','run_1',phase='review',waiting_on='chatgpt',run_state='succeeded')
        with self.assertRaises(RuntimeError):
            self.emit(td,'APPROVAL','run_1',state='working',phase='x',waiting_on='chatgpt',run_state='succeeded')
        with self.assertRaises(RuntimeError):
            self.emit(td,'HANDOFF','run_1',actor_role='worker',actor_id='w1',recipient_role='coordinator',recipient_id='chatgpt',phase='review',waiting_on='chatgpt',run_state='succeeded')
        with self.assertRaises(RuntimeError):
            self.emit(td,'REVIEW','run_ghost',phase='review',waiting_on='chatgpt',run_state='succeeded')
        v=awrp.validate(td)
        self.assertEqual(v.get('active_run_id'),'run_2')
    def test_review_failed_canceled_latest_rejects(self):
        self.mkctx(self.tmp)
        awrp.project_create(str(self.tmp),'proj-s','S',(self.CH,),None,'chatgpt')
        td=self.mktask_r(self.tmp,'task_rf')
        self.emit(td,'DISPATCH','run_1',run_state='dispatched')
        self.emit(td,'ACK','run_1',actor_role='worker',actor_id='ep-sc',recipient_role='coordinator',recipient_id='chatgpt',run_state='working')
        self.emit(td,'HANDOFF','run_1',actor_role='worker',actor_id='ep-sc',recipient_role='coordinator',recipient_id='chatgpt',phase='review',waiting_on='chatgpt',run_state='failed')
        v=awrp.validate(td)
        self.assertIsNone(v.get('active_run_id'))
        self.assertEqual(v['runs']['run_1']['state'],'failed')
        with self.assertRaises(RuntimeError):
            self.emit(td,'REVIEW','run_1',phase='review',waiting_on='chatgpt',run_state='failed')
        with self.assertRaises(RuntimeError):
            self.emit(td,'APPROVAL','run_1',state='working',phase='x',waiting_on='chatgpt',run_state='failed')
        td2=self.mktask_r(self.tmp,'task_rc')
        self.emit(td2,'DISPATCH','run_1',run_state='dispatched')
        self.emit(td2,'CANCEL',None,state='canceled',phase='x',waiting_on='null')
        with self.assertRaises(RuntimeError):
            self.emit(td2,'REVIEW','run_1',phase='review',waiting_on='chatgpt',run_state='succeeded')
        self.assertEqual(len(list((Path(td2)/'events').glob('*.json'))),3)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_push_race_retries_and_publishes(self):
        import unittest.mock as mock
        remote,w,base=self.mkrelay2()
        self.dispatch_req(w,'r-race','run_race',base)
        self.commit_req(w,'r-race')
        rival=self.rival_clone()
        self.emit(rival/'tasks'/'task_b','REVIEW',None,phase='review',waiting_on='chatgpt',run_state=None,fg=1)
        self.git(rival,'add','-A'); self.git(rival,'commit','-m','rival review staged')
        repo_s=str(w); real=subprocess.run; state={'push':0}
        def flaky(argv,*a,**k):
            if len(argv)>=5 and argv[0]=='git' and argv[1]=='-C' and argv[2]==repo_s and argv[3]=='push':
                state['push']+=1
                if state['push']==1:
                    real(['git','-C',str(rival),'push','origin','main'],check=True,capture_output=True,text=True)
                    return subprocess.CompletedProcess(argv,1,'','error: failed to push some refs (non-fast-forward)')
            return real(argv,*a,**k)
        with mock.patch.object(awrp.subprocess,'run',new=flaky):
            r=self.bridge(w,'r-race')
        self.assertEqual(state['push'],2)
        self.assertEqual(r['status'],'published')
        self.assertEqual(r.get('attempts'),2)
        self.assertEqual(len(list((w/'tasks'/'task_a'/'events').glob('*.json'))),2)
        self.assertEqual(self.git(w,'rev-parse','main'),self.git(remote,'rev-parse','main'))
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_retry_exhaustion_rejects_clean(self):
        import unittest.mock as mock
        remote,w,base=self.mkrelay2()
        self.dispatch_req(w,'r-exh','run_exh',base)
        self.commit_req(w,'r-exh')
        repo_s=str(w); real=subprocess.run; state={'push':0}
        def always_fail(argv,*a,**k):
            if len(argv)>=5 and argv[0]=='git' and argv[1]=='-C' and argv[2]==repo_s and argv[3]=='push':
                state['push']+=1
                return subprocess.CompletedProcess(argv,1,'','error: failed to push some refs (non-fast-forward)')
            return real(argv,*a,**k)
        with mock.patch.object(awrp.subprocess,'run',new=always_fail):
            with self.assertRaises(RuntimeError):
                self.bridge(w,'r-exh')
        self.assertEqual(state['push'],3)
        self.assertEqual(self.git(w,'rev-parse','main'),self.git(remote,'rev-parse','main'))
        dirt=[l for l in self.git(w,'status','--porcelain').splitlines() if l.strip() and not (l.startswith('??') and 'bridge/requests/' in l)]
        self.assertEqual(dirt,[])
        self.assertEqual(len(list((w/'tasks'/'task_a'/'events').glob('*.json'))),1)
class TWD(unittest.TestCase):
    CH='ch-wd'; EP='ep-wd'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def git(self,repo,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def mkctx(self,root):
        (Path(root)/'contexts').mkdir(exist_ok=True)
        awrp.write_new(Path(root)/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
    def mkrelay2(self):
        remote=self.tmp/'r.git'; w=self.tmp/'w'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(self.tmp,'init','-b','main',str(w))
        self.git(w,'config','user.email','t@e'); self.git(w,'config','user.name','t')
        self.mkctx(w)
        awrp.project_create(str(w),'proj-w','W',(self.CH,),None,'chatgpt')
        awrp.acquire_claim(str(w),self.CH,'coord-W')
        (w/'relay.json').write_text(json.dumps({'protocol':'awrp/0.1','relay':'r'}),encoding='utf-8')
        self.git(w,'add','-A'); self.git(w,'commit','-m','seed'); self.git(w,'remote','add','origin',str(remote))
        self.git(w,'push','-u','origin','main'); self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
        for tid in ('task_a','task_b'):
            base=self.git(remote,'rev-parse','main')
            self.mkreq(w,'r-seed-'+tid,{"protocol":"awrp/0.1","request_id":'r-seed-'+tid,"action":"create-task","idempotency_key":'k-seed-'+tid,"expected_base":base,
                "params":{"task_id":tid,"context_id":"c","title":"T","goal":"g","project_id":"proj-w","channel_id":self.CH,"worker_endpoint":self.EP,"created_at":"2026-09-10T10:00:00Z"}})
            r=self.bridge(w,'r-seed-'+tid)
            assert r['status']=='published', r
        return remote,w,self.git(remote,'rev-parse','main')
    def mkreq(self,w,rid,body):
        p=w/'bridge'/'requests'; p.mkdir(parents=True,exist_ok=True)
        (p/f'{rid}.json').write_text(body if isinstance(body,str) else json.dumps(body),encoding='utf-8')
    def bridge(self,w,rid):
        class A: pass
        a=A(); a.root=str(w); a.request=rid; a.repo=str(w); a.branch='main'; a.remote='origin'
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_bridge_process(a)
        return json.loads(buf.getvalue())
    def rival_clone(self,name='rival'):
        b=self.tmp/name
        subprocess.run(['git','-C',str(self.tmp),'clone',str(self.tmp/'r.git'),str(b)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.email','t@e'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.name','t@e'],check=True,capture_output=True)
        return b
    def cemit(self,td,typ,rid,phase='x',waiting_on=None,run_state=None,fg=1,state='working'):
        class A: pass
        a=A(); a.task_dir=str(td); a.type=typ; a.actor_role='coordinator'; a.actor_id='coord-W'; a.recipient_role='worker'; a.recipient_id=self.EP; a.run_id=rid; a.new_run=False; a.state=state; a.phase=phase; a.waiting_on=self.EP if waiting_on is None else waiting_on; a.run_state=run_state; a.summary='s'
        a.details_file=None; a.artifacts_file=None; a.approval_file=None
        a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=fg; a.idempotency_key=None; a.require_fresh=False; a.legacy_route=True
        awrp.emit(a)
    def wemit(self,td,typ,rid,phase='x',waiting_on='chatgpt',run_state=None):
        class A: pass
        a=A(); a.task_dir=str(td); a.type=typ; a.actor_role='worker'; a.actor_id=self.EP; a.recipient_role='coordinator'; a.recipient_id='chatgpt'; a.run_id=rid; a.new_run=False; a.state='working'; a.phase=phase; a.waiting_on=waiting_on; a.run_state=run_state; a.summary='s'
        a.details_file=None; a.artifacts_file=None; a.approval_file=None
        a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None; a.idempotency_key=None; a.require_fresh=False; a.legacy_route=True
        awrp.emit(a)
    def dispatch_ack(self,w,tid,run):
        td=w/'tasks'/tid
        self.cemit(td,'DISPATCH',run,run_state='dispatched')
        self.wemit(td,'ACK',run,run_state='working')
        return td
    def head_of(self,td):
        h=awrp.validate(str(td))['head']; return (h['event_id'],h['integrity']['event_hash'])
    def wretrypush(self,w,td,run,exp_head,exp_hash,base,verify=(),max_attempts=3):
        class A: pass
        a=A(); a.task_dir=str(td); a.run_id=run; a.expected_head=exp_head; a.expected_hash=exp_hash; a.expected_base=base
        a.repo=str(w); a.branch='main'; a.remote='origin'; a.verify_cmd=list(verify); a.max_attempts=max_attempts
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_worker_retry_push(a)
        return json.loads(buf.getvalue())
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_worker_unrelated_drift_recovers_and_publishes(self):
        remote,w,base=self.mkrelay2()
        td=self.dispatch_ack(w,'task_a','run_w1')
        ack_file=sorted((td/'events').glob('*.json'))[-1]
        ack_bytes=ack_file.read_bytes()
        (w/'worker_note.txt').write_text('unrelated-main recovery\n',encoding='utf-8')
        self.git(w,'add','-A'); self.git(w,'commit','-m','worker: ACK run_w1 plus implementation note')
        rival=self.rival_clone()
        self.cemit(rival/'tasks'/'task_b','REVIEW',None,phase='review',waiting_on='chatgpt',run_state=None,fg=1)
        self.git(rival,'add','-A'); self.git(rival,'commit','-m','rival review on B'); self.git(rival,'push','origin','main')
        exp_head,exp_hash=self.head_of(td)
        r=self.wretrypush(w,td,'run_w1',exp_head,exp_hash,base,verify=('python -c "pass"',))
        self.assertEqual(r['status'],'published')
        self.assertEqual(r['attempts'],2)
        self.assertEqual(r.get('gap_kind'),'unrelated-canonical')
        self.assertEqual(self.git(w,'rev-parse','main'),self.git(remote,'rev-parse','main'))
        self.assertEqual(awrp.canonical_artifact_bytes(sorted((td/'events').glob('*.json'))[-1].read_bytes()),awrp.canonical_artifact_bytes(ack_bytes))
        v=awrp.validate(str(td)); self.assertEqual(v['head']['integrity']['event_hash'],exp_hash)
        self.assertEqual((w/'worker_note.txt').read_text(encoding='utf-8'),'unrelated-main recovery\n')
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_worker_overlap_refuses_and_preserves(self):
        remote,w,base=self.mkrelay2()
        td=self.dispatch_ack(w,'task_a','run_w2')
        (w/'worker_note.txt').write_text('v1\n',encoding='utf-8')
        self.git(w,'add','-A'); self.git(w,'commit','-m','worker: note v1')
        pre_head=self.git(w,'rev-parse','HEAD')
        rival=self.rival_clone()
        (rival/'worker_note.txt').write_text('rival\n',encoding='utf-8')
        self.git(rival,'add','-A'); self.git(rival,'commit','-m','rival touches same file'); self.git(rival,'push','origin','main')
        exp_head,exp_hash=self.head_of(td)
        with self.assertRaises(RuntimeError) as cm:
            self.wretrypush(w,td,'run_w2',exp_head,exp_hash,base)
        self.assertIn('overlap',str(cm.exception))
        self.assertEqual(self.git(w,'rev-parse','HEAD'),pre_head)
        self.assertEqual(self.git(remote,'rev-parse','main'),self.git(rival,'rev-parse','main'))
        self.assertEqual((w/'worker_note.txt').read_text(encoding='utf-8'),'v1\n')
        self.assertEqual(len(list((td/'events').glob('*.json'))),3)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_worker_same_task_advance_refuses(self):
        remote,w,base=self.mkrelay2()
        td=self.dispatch_ack(w,'task_a','run_w3')
        (w/'worker_note.txt').write_text('v3\n',encoding='utf-8')
        self.git(w,'add','-A'); self.git(w,'commit','-m','worker: note v3')
        pre_head=self.git(w,'rev-parse','HEAD')
        rival=self.rival_clone()
        self.cemit(rival/'tasks'/'task_a','REVIEW',None,phase='review',waiting_on='chatgpt',run_state=None,fg=1)
        self.git(rival,'add','-A'); self.git(rival,'commit','-m','rival review on A'); self.git(rival,'push','origin','main')
        exp_head,exp_hash=self.head_of(td)
        with self.assertRaises(RuntimeError) as cm:
            self.wretrypush(w,td,'run_w3',exp_head,exp_hash,base)
        self.assertIn('target task',str(cm.exception))
        self.assertEqual(self.git(w,'rev-parse','HEAD'),pre_head)
        self.assertEqual(len(list((td/'events').glob('*.json'))),3)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_worker_claim_drift_refuses(self):
        remote,w,base=self.mkrelay2()
        td=self.dispatch_ack(w,'task_a','run_w4')
        (w/'worker_note.txt').write_text('v4\n',encoding='utf-8')
        self.git(w,'add','-A'); self.git(w,'commit','-m','worker: note v4')
        pre_head=self.git(w,'rev-parse','HEAD')
        rival=self.rival_clone()
        awrp.acquire_claim(str(rival),self.CH,'coord-R',expected_generation=1)
        self.git(rival,'add','-A'); self.git(rival,'commit','-m','rival takeover'); self.git(rival,'push','origin','main')
        exp_head,exp_hash=self.head_of(td)
        with self.assertRaises(RuntimeError) as cm:
            self.wretrypush(w,td,'run_w4',exp_head,exp_hash,base)
        self.assertIn('claim',str(cm.exception))
        self.assertEqual(self.git(w,'rev-parse','HEAD'),pre_head)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_worker_verify_failure_blocks_publish(self):
        import sys
        remote,w,base=self.mkrelay2()
        td=self.dispatch_ack(w,'task_a','run_w5')
        (w/'worker_note.txt').write_text('v5\n',encoding='utf-8')
        self.git(w,'add','-A'); self.git(w,'commit','-m','worker: note v5')
        rival=self.rival_clone()
        self.cemit(rival/'tasks'/'task_b','REVIEW',None,phase='review',waiting_on='chatgpt',run_state=None,fg=1)
        self.git(rival,'add','-A'); self.git(rival,'commit','-m','rival review on B'); self.git(rival,'push','origin','main')
        rival_tip=self.git(remote,'rev-parse','main')
        exp_head,exp_hash=self.head_of(td)
        fail_cmd='python -c "import sys; sys.exit(1)"'
        with self.assertRaises(RuntimeError) as cm:
            self.wretrypush(w,td,'run_w5',exp_head,exp_hash,base,verify=(fail_cmd,))
        self.assertIn('verification failed',str(cm.exception))
        self.assertEqual(self.git(remote,'rev-parse','main'),rival_tip)
        self.assertEqual((w/'worker_note.txt').read_text(encoding='utf-8'),'v5\n')
        self.assertEqual(len(list((td/'events').glob('*.json'))),3)
        self.assertEqual(self.git(w,'rev-list','--count',f'{rival_tip}..HEAD'),'1')
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_worker_exhaustion_bounded_and_preserves(self):
        import unittest.mock as mock
        remote,w,base=self.mkrelay2()
        td=self.dispatch_ack(w,'task_a','run_w6')
        (w/'worker_note.txt').write_text('v6\n',encoding='utf-8')
        self.git(w,'add','-A'); self.git(w,'commit','-m','worker: note v6')
        n0=self.git(w,'rev-list','--count',f'{base}..HEAD')
        exp_head,exp_hash=self.head_of(td)
        repo_s=str(w); real=subprocess.run; state={'push':0}
        def always_fail(argv,*a,**k):
            if len(argv)>=5 and argv[0]=='git' and argv[1]=='-C' and argv[2]==repo_s and argv[3]=='push':
                state['push']+=1
                return subprocess.CompletedProcess(argv,1,'','error: failed to push some refs (non-fast-forward)')
            return real(argv,*a,**k)
        with mock.patch.object(awrp.subprocess,'run',new=always_fail):
            with self.assertRaises(RuntimeError) as cm:
                self.wretrypush(w,td,'run_w6',exp_head,exp_hash,base)
        self.assertIn('exhausted',str(cm.exception))
        self.assertEqual(state['push'],3)
        self.assertEqual(self.git(w,'rev-list','--count',f'{base}..HEAD'),n0)
        dirt=[l for l in self.git(w,'status','--porcelain').splitlines() if l.strip()]
        self.assertEqual(dirt,[])
        self.assertEqual((w/'worker_note.txt').read_text(encoding='utf-8'),'v6\n')
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_worker_closed_run_transports(self):
        remote,w,base=self.mkrelay2()
        td=self.dispatch_ack(w,'task_a','run_w7')
        self.wemit(td,'HANDOFF','run_w7',phase='review',waiting_on='chatgpt',run_state='succeeded')
        (w/'worker_note.txt').write_text('v7\n',encoding='utf-8')
        self.git(w,'add','-A'); self.git(w,'commit','-m','worker: close run_w7 plus note')
        v=awrp.validate(str(td)); self.assertIsNone(v.get('active_run_id'))
        rival=self.rival_clone()
        self.cemit(rival/'tasks'/'task_b','REVIEW',None,phase='review',waiting_on='chatgpt',run_state=None,fg=1)
        self.git(rival,'add','-A'); self.git(rival,'commit','-m','rival review on B'); self.git(rival,'push','origin','main')
        exp_head,exp_hash=self.head_of(td)
        r=self.wretrypush(w,td,'run_w7',exp_head,exp_hash,base)
        self.assertEqual(r['status'],'published')
        self.assertEqual(r['attempts'],2)
        self.assertEqual(r.get('gap_kind'),'unrelated-canonical')
        self.assertEqual(self.git(w,'rev-parse','main'),self.git(remote,'rev-parse','main'))
        self.assertEqual(awrp.validate(str(td))['head']['integrity']['event_hash'],exp_hash)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_worker_superseded_run_refuses(self):
        remote,w,base=self.mkrelay2()
        td=self.dispatch_ack(w,'task_a','run_old')
        self.wemit(td,'HANDOFF','run_old',phase='review',waiting_on='chatgpt',run_state='succeeded')
        self.cemit(td,'DISPATCH','run_new',run_state='dispatched')
        self.wemit(td,'ACK','run_new',run_state='working')
        (w/'worker_note.txt').write_text('v8\n',encoding='utf-8')
        self.git(w,'add','-A'); self.git(w,'commit','-m','worker: supersede test')
        pre_head=self.git(w,'rev-parse','HEAD')
        exp_head,exp_hash=self.head_of(td)
        with self.assertRaises(RuntimeError) as cm:
            self.wretrypush(w,td,'run_old',exp_head,exp_hash,base)
        self.assertIn('not transportable',str(cm.exception))
        self.assertEqual(self.git(w,'rev-parse','HEAD'),pre_head)
        self.assertEqual(self.git(remote,'rev-parse','main'),base)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_worker_post_close_coordinator_tip_refuses(self):
        remote,w,base=self.mkrelay2()
        td=self.dispatch_ack(w,'task_a','run_old9')
        self.wemit(td,'HANDOFF','run_old9',phase='review',waiting_on='chatgpt',run_state='succeeded')
        self.cemit(td,'REVIEW',None,phase='review',waiting_on='chatgpt',run_state=None,fg=1)
        (w/'worker_note.txt').write_text('v9\n',encoding='utf-8')
        self.git(w,'add','-A'); self.git(w,'commit','-m','worker: coordinator-tip test')
        pre_head=self.git(w,'rev-parse','HEAD')
        exp_head,exp_hash=self.head_of(td)
        with self.assertRaises(RuntimeError) as cm:
            self.wretrypush(w,td,'run_old9',exp_head,exp_hash,base)
        self.assertIn('no transport authority',str(cm.exception))
        self.assertEqual(self.git(w,'rev-parse','HEAD'),pre_head)
        self.assertEqual(self.git(remote,'rev-parse','main'),base)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_worker_wrong_run_refuses(self):
        remote,w,base=self.mkrelay2()
        td=self.dispatch_ack(w,'task_a','run_w10')
        self.wemit(td,'HANDOFF','run_w10',phase='review',waiting_on='chatgpt',run_state='succeeded')
        (w/'worker_note.txt').write_text('v10\n',encoding='utf-8')
        self.git(w,'add','-A'); self.git(w,'commit','-m','worker: wrong-run test')
        exp_head,exp_hash=self.head_of(td)
        with self.assertRaises(RuntimeError) as cm:
            self.wretrypush(w,td,'run_ghost',exp_head,exp_hash,base)
        self.assertIn('unknown locally',str(cm.exception))
        self.assertEqual(self.git(remote,'rev-parse','main'),base)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_worker_failed_close_tip_transports(self):
        remote,w,base=self.mkrelay2()
        td=self.dispatch_ack(w,'task_a','run_w11')
        self.wemit(td,'HANDOFF','run_w11',phase='review',waiting_on='chatgpt',run_state='failed')
        v=awrp.validate(str(td)); self.assertIsNone(v.get('active_run_id'))
        ack_files=sorted((td/'events').glob('*.json'))
        tip_bytes=ack_files[-1].read_bytes()
        (w/'worker_note.txt').write_text('v11\n',encoding='utf-8')
        self.git(w,'add','-A'); self.git(w,'commit','-m','worker: close run_w11 failed plus note')
        rival=self.rival_clone()
        self.cemit(rival/'tasks'/'task_b','REVIEW',None,phase='review',waiting_on='chatgpt',run_state=None,fg=1)
        self.git(rival,'add','-A'); self.git(rival,'commit','-m','rival review on B'); self.git(rival,'push','origin','main')
        exp_head,exp_hash=self.head_of(td)
        r=self.wretrypush(w,td,'run_w11',exp_head,exp_hash,base)
        self.assertEqual(r['status'],'published')
        self.assertEqual(r['attempts'],2)
        self.assertEqual(self.git(w,'rev-parse','main'),self.git(remote,'rev-parse','main'))
        self.assertEqual(awrp.canonical_artifact_bytes(sorted((td/'events').glob('*.json'))[-1].read_bytes()),awrp.canonical_artifact_bytes(tip_bytes))
        self.assertEqual(awrp.validate(str(td))['head']['integrity']['event_hash'],exp_hash)
class TBX(unittest.TestCase):
    CH='ch-bx'; EP='ep-bx'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def git(self,repo,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def mkrelay1(self):
        remote=self.tmp/'r.git'; w=self.tmp/'w'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(self.tmp,'init','-b','main',str(w))
        self.git(w,'config','user.email','t@e'); self.git(w,'config','user.name','t')
        (w/'contexts').mkdir(exist_ok=True)
        awrp.write_new(w/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        awrp.project_create(str(w),'proj-b','B',(self.CH,),None,'chatgpt')
        awrp.acquire_claim(str(w),self.CH,'coord-B')
        (w/'relay.json').write_text(json.dumps({'protocol':'awrp/0.1','relay':'r'}),encoding='utf-8')
        self.git(w,'add','-A'); self.git(w,'commit','-m','seed'); self.git(w,'remote','add','origin',str(remote))
        self.git(w,'push','-u','origin','main'); self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
        base=self.git(remote,'rev-parse','main')
        self.mkreq(w,'r-seed-t1',{"protocol":"awrp/0.1","request_id":'r-seed-t1',"action":"create-task","idempotency_key":'k-seed-t1',"expected_base":base,
            "params":{"task_id":'task_t1',"context_id":"c","title":"T","goal":"g","project_id":"proj-b","channel_id":self.CH,"worker_endpoint":self.EP,"created_at":"2026-09-10T10:00:00Z"}})
        r=self.bridge(w,'r-seed-t1')
        assert r['status']=='published', r
        return remote,w,self.git(remote,'rev-parse','main')
    def mkreq(self,w,rid,body):
        p=w/'bridge'/'requests'; p.mkdir(parents=True,exist_ok=True)
        (p/f'{rid}.json').write_text(body if isinstance(body,str) else json.dumps(body),encoding='utf-8')
    def bridge(self,w,rid):
        class A: pass
        a=A(); a.root=str(w); a.request=rid; a.repo=str(w); a.branch='main'; a.remote='origin'
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_bridge_process(a)
        return json.loads(buf.getvalue())
    def preflight(self,w,rid):
        class A: pass
        a=A(); a.root=str(w); a.request=rid; a.repo=str(w); a.branch='main'; a.remote='origin'
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_bridge_preflight(a)
        return json.loads(buf.getvalue())
    def snapshot(self,w):
        return (self.git(w,'status','--porcelain'),
                sorted(p.name for p in (w/'tasks'/'task_t1'/'events').glob('*.json')),
                sorted(p.name for p in (w/'bridge'/'requests').glob('*')))
    def dispatch_req(self,w,rid,run,base,extra_params=None):
        params={"task_id":"task_t1","run_id":run,"recipient_role":"worker","recipient_id":self.EP,"state":"working","phase":"x","waiting_on":self.EP,"run_state":"dispatched","summary":"go"}
        if extra_params: params.update(extra_params)
        self.mkreq(w,rid,{"protocol":"awrp/0.1","request_id":rid,"action":"dispatch","idempotency_key":'k-'+rid,"expected_base":base,"params":params})
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_preflight_valid_dispatch_plannable_and_writeless(self):
        remote,w,base=self.mkrelay1()
        self.dispatch_req(w,'r-ok','run_ok',base)
        before=self.snapshot(w)
        r=self.preflight(w,'r-ok')
        self.assertEqual(r['status'],'plannable')
        self.assertEqual(r['task_id'],'task_t1')
        self.assertEqual(len(r['planned_writes']),2)
        self.assertTrue(r['planned_writes'][0].startswith('tasks/task_t1/events/'))
        self.assertTrue(r['planned_writes'][1].endswith('tasks/task_t1/TASK.md'))
        self.assertEqual(self.snapshot(w),before)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_preflight_rejects_public_mutation_action(self):
        remote,w,base=self.mkrelay1()
        self.mkreq(w,'r-evil',{"protocol":"awrp/0.1","request_id":'r-evil',"action":"create_issue","idempotency_key":'k-evil',"expected_base":base,
            "params":{"task_id":"task_t1","title":"oops"}})
        before=self.snapshot(w)
        with self.assertRaises(RuntimeError) as cm:
            self.preflight(w,'r-evil')
        self.assertIn('ineligible',str(cm.exception))
        self.assertEqual(self.snapshot(w),before)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_preflight_rejects_public_mutation_params(self):
        remote,w,base=self.mkrelay1()
        self.dispatch_req(w,'r-lbl','run_lbl',base,extra_params={"labels":["p1"],"issue_number":7})
        before=self.snapshot(w)
        with self.assertRaises(RuntimeError) as cm:
            self.preflight(w,'r-lbl')
        self.assertIn('ineligible',str(cm.exception))
        self.assertEqual(self.snapshot(w),before)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_preflight_rejects_stale_base(self):
        remote,w,base=self.mkrelay1()
        self.dispatch_req(w,'r-stale','run_stale','0'*40)
        before=self.snapshot(w)
        with self.assertRaises(RuntimeError) as cm:
            self.preflight(w,'r-stale')
        self.assertIn('captured base',str(cm.exception))
        self.assertEqual(self.snapshot(w),before)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_preflight_rejects_unknown_target(self):
        remote,w,base=self.mkrelay1()
        self.mkreq(w,'r-ghost',{"protocol":"awrp/0.1","request_id":'r-ghost',"action":"dispatch","idempotency_key":'k-ghost',"expected_base":base,
            "params":{"task_id":"task_nope","state":"working","phase":"x","summary":"go"}})
        before=self.snapshot(w)
        with self.assertRaises(RuntimeError) as cm:
            self.preflight(w,'r-ghost')
        self.assertIn('not in the relay',str(cm.exception))
        self.assertEqual(self.snapshot(w),before)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_preflight_rejects_resubmission_writeless(self):
        remote,w,base=self.mkrelay1()
        self.dispatch_req(w,'r-first','run_dup',base)
        self.git(w,'add','bridge/requests/r-first.json'); self.git(w,'commit','-m','connector: request r-first'); self.git(w,'push','origin','main')
        r=self.bridge(w,'r-first')
        assert r['status']=='published', r
        self.dispatch_req(w,'r-second','run_other',self.git(remote,'rev-parse','main'))
        (w/'bridge'/'requests'/'r-second.json').write_text((w/'bridge'/'requests'/'r-second.json').read_text().replace('k-r-second','k-r-first'),encoding='utf-8')
        before=self.snapshot(w)
        with self.assertRaises(RuntimeError) as cm:
            self.preflight(w,'r-second')
        self.assertIn('duplicate command',str(cm.exception))
        self.assertEqual(self.snapshot(w),before)
    def test_intent_action_surface_pinned(self):
        self.assertEqual(set(awrp.INTENT_ACTIONS),{'create-task','dispatch','review','approval','reconcile','incident-create','incident-update'})
        self.assertFalse(set(awrp.INTENT_ACTIONS)&set(awrp.PUBLIC_MUTATION_ACTIONS))
    def test_compose_intent_rejects_public_action(self):
        import tempfile as _tf
        f=_tf.NamedTemporaryFile(delete=False,suffix='.json',mode='w',encoding='utf-8')
        try:
            f.write(json.dumps({"action":"create_pull_request","idempotency_key":"k-x","params":{"task_id":"t"}})); f.close()
            class A: pass
            a=A(); a.intent_file=f.name
            with self.assertRaises(RuntimeError) as cm:
                awrp.do_compose_intent(a)
            self.assertIn('ineligible',str(cm.exception))
        finally:
            Path(f.name).unlink(missing_ok=True)
class TBW(unittest.TestCase):
    def req(self,**over):
        base={"action_class":"transport_write","repository":"Bruce-Yii/awrp","path":"bridge/requests/r-t1.json",
            "contents":{"protocol":"awrp/0.1","request_id":"r-t1","action":"dispatch","idempotency_key":"k1","expected_base":"abc123",
                "params":{"task_id":"t","state":"working","phase":"x","summary":"go"}}}
        base.update(over); return base
    def test_valid_transport_single_delegated_call(self):
        import hashlib as _hl
        fake=awrp_transport.FakeTransport()
        out=awrp_transport.transport_write(self.req(),fake)
        self.assertEqual(out['status'],'delegated')
        self.assertEqual(len(fake.calls),1)
        want=(json.dumps(self.req()['contents'],ensure_ascii=False,indent=2,sort_keys=True)+'\n').encode()
        self.assertEqual(fake.calls[0]['path'],'bridge/requests/r-t1.json')
        self.assertEqual(out['sha256'],'sha256:'+_hl.sha256(want).hexdigest())
        self.assertEqual(out['size_bytes'],len(want))
    def test_create_issue_drift_blocked_zero_calls(self):
        drifts=[self.req(action_class='create_issue'),
                self.req(contents={**self.req()['contents'],'action':'create_issue'}),
                self.req(action_class='comment_issue')]
        for d in drifts:
            fake=awrp_transport.FakeTransport()
            with self.assertRaises(awrp_transport.IneligibleMutation):
                awrp_transport.transport_write(d,fake)
            self.assertEqual(fake.calls,[])
    def test_repo_mismatch_zero_calls(self):
        fake=awrp_transport.FakeTransport()
        with self.assertRaises(awrp_transport.IneligibleMutation):
            awrp_transport.transport_write(self.req(repository='other/repo'),fake)
        self.assertEqual(fake.calls,[])
    def test_path_mismatch_zero_calls(self):
        bad_paths=['issues/1.json','bridge/requests/r-t1.result.json','bridge/requests/../evil.json',
                   'bridge/requests/r-other.json','bridge/requests/.json','']
        for p in bad_paths:
            fake=awrp_transport.FakeTransport()
            with self.assertRaises(awrp_transport.IneligibleMutation,msg=p):
                awrp_transport.transport_write(self.req(path=p),fake)
            self.assertEqual(fake.calls,[])
    def test_public_params_zero_calls(self):
        for params in ({'task_id':'t','labels':['p1']},{'task_id':'t','issue_number':7},
                       {'task_id':'t','comment_body':'hi'},{'task_id':'t','merge_method':'squash'}):
            c=dict(self.req()['contents']); c['params']=params
            fake=awrp_transport.FakeTransport()
            with self.assertRaises(awrp_transport.IneligibleMutation):
                awrp_transport.transport_write(self.req(contents=c),fake)
            self.assertEqual(fake.calls,[])
    def test_envelope_strictness_zero_calls(self):
        bad=[self.req(action_class=None),{k:v for k,v in self.req().items() if k!='path'},
             {**self.req(),'extra':1},'not-a-dict',None,
             self.req(contents={k:v for k,v in self.req()['contents'].items() if k!='params'})]
        for b in bad:
            fake=awrp_transport.FakeTransport()
            with self.assertRaises(awrp_transport.IneligibleMutation):
                awrp_transport.transport_write(b,fake)
            self.assertEqual(fake.calls,[])
    def test_preflight_hook_gates_delegation(self):
        fake=awrp_transport.FakeTransport()
        with self.assertRaises(awrp_transport.IneligibleMutation):
            awrp_transport.transport_write(self.req(),fake,preflight=lambda r:{'status':'rejected','reason':'stale'})
        self.assertEqual(fake.calls,[])
        out=awrp_transport.transport_write(self.req(),fake,preflight=lambda r:{'status':'plannable'})
        self.assertEqual(out['status'],'delegated')
        self.assertEqual(len(fake.calls),1)
    def test_no_public_mutation_surface(self):
        from types import ModuleType as _MT
        names={n for n in dir(awrp_transport) if not n.startswith('_') and not isinstance(getattr(awrp_transport,n),_MT)}
        self.assertEqual(names,{'TRANSPORT_ACTION_CLASS','TRANSPORT_REPOSITORY','TRANSPORT_PATH_RE','TRANSPORT_REQUEST_KEYS',
            'TRANSPORT_ACTIONS','PUBLIC_MUTATION_ACTIONS','PUBLIC_MUTATION_PARAMS','CONTENTS_REQUIRED_KEYS',
            'IneligibleMutation','FakeTransport','transport_write','validate_transport_request','canonical_contents_bytes'})
        joined=' '.join(sorted(names)).lower()
        for frag in ('issue','pull','comment','label','merge','close_','release'):
            self.assertNotIn(frag,joined)
    def test_policy_mirrors_awrp(self):
        self.assertEqual(set(awrp_transport.PUBLIC_MUTATION_ACTIONS),set(awrp.PUBLIC_MUTATION_ACTIONS))
        self.assertEqual(set(awrp_transport.PUBLIC_MUTATION_PARAMS),set(awrp.PUBLIC_MUTATION_PARAMS))
        self.assertEqual(set(awrp_transport.TRANSPORT_ACTIONS),set(awrp.INTENT_ACTIONS))
    def test_contents_bytes_canonical(self):
        data=awrp_transport.canonical_contents_bytes({"b":1,"a":[1,2]})
        self.assertEqual(data,b'{\n  "a": [\n    1,\n    2\n  ],\n  "b": 1\n}\n')
class TBI(unittest.TestCase):
    CH='ch-bi'; EP='ep-bi'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def mklayout(self,lane='lane-a'):
        ws=self.tmp/'ws'; relay=self.tmp/'relay'
        (relay/'contexts').mkdir(parents=True)
        awrp.write_new(relay/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        awrp.project_create(str(relay),'proj-b','B',(self.CH,),None,'chatgpt')
        (ws/'.awrp').mkdir(parents=True)
        (ws/'.awrp'/'binding.json').write_text(json.dumps({'protocol':'awrp/0.1','relay':'r','relay_dir':str(relay),'channel_id':self.CH,'worker_endpoint':self.EP,'lane_id':lane}),encoding='utf-8')
        return ws,relay
    def mktask(self,relay,tid,lane=None,project='proj-b'):
        class A: pass
        a=A(); a.root=str(relay); a.context_id='c'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='w'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=self.CH; a.lane_id=lane; a.worker_endpoint=self.EP; a.project_id=project
        a.legacy=True
        awrp.create_task(a); return str(relay/'tasks'/tid)
    def dispatch(self,td,rid):
        class A: pass
        a=A(); a.task_dir=td; a.type='DISPATCH'; a.actor_role='coordinator'; a.actor_id='chatgpt'; a.recipient_role='worker'; a.recipient_id=self.EP; a.run_id=rid; a.new_run=False; a.state='working'; a.phase='x'; a.waiting_on=self.EP; a.run_state='dispatched'; a.summary='s'
        a.details_file=None; a.artifacts_file=None; a.approval_file=None
        a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None; a.idempotency_key=None; a.require_fresh=False; a.legacy_route=True
        awrp.emit(a)
    def inbox(self,root,channel=CH,endpoint=EP,task_id=None,project=None,legacy=False):
        class A: pass
        a=A(); a.root=str(root); a.channel=channel; a.worker_endpoint=endpoint; a.task_id=task_id; a.project=project; a.legacy=legacy
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_inbox(a)
        return json.loads(buf.getvalue())
    def test_bound_workspace_resolves_relay_and_agrees_with_resume(self):
        ws,relay=self.mklayout()
        td=self.mktask(relay,'task_one'); self.dispatch(td,'run_1')
        r=self.inbox(ws)
        self.assertEqual(r['root'],str(relay))
        self.assertEqual(r['workspace_root'],str(ws))
        self.assertEqual([c['task_id'] for c in r['actionable']],['task_one'])
        s=awrp.select_for_resume(str(relay),self.CH,self.EP,'lane-a',None)
        self.assertEqual(s['status'],'EXECUTE')
        self.assertEqual(s['task_id'],'task_one')
    def test_unbound_root_scans_cwd(self):
        ws,relay=self.mklayout()
        td=self.mktask(relay,'task_one'); self.dispatch(td,'run_1')
        r=self.inbox(relay)
        self.assertEqual(r['root'],str(relay))
        self.assertIsNone(r['workspace_root'])
        self.assertEqual([c['task_id'] for c in r['actionable']],['task_one'])
    def test_missing_relay_dir_fails_closed(self):
        ws,relay=self.mklayout()
        (ws/'.awrp'/'binding.json').write_text(json.dumps({'protocol':'awrp/0.1','relay':'r','relay_dir':str(self.tmp/'nope'),'channel_id':self.CH,'worker_endpoint':self.EP}),encoding='utf-8')
        with self.assertRaises(RuntimeError) as cm:
            self.inbox(ws)
        self.assertIn('relay_dir',str(cm.exception))
    def test_corrupt_binding_fails_closed(self):
        ws,relay=self.mklayout()
        (ws/'.awrp'/'binding.json').write_text('{oops',encoding='utf-8')
        with self.assertRaises(RuntimeError) as cm:
            self.inbox(ws)
        self.assertIn('binding',str(cm.exception))
    def test_task_id_exact_via_binding(self):
        ws,relay=self.mklayout()
        td=self.mktask(relay,'task_one'); self.dispatch(td,'run_1')
        r=self.inbox(ws,channel=None,endpoint=None,task_id='task_one')
        self.assertEqual(r['root'],str(relay))
        self.assertEqual(len(r['actionable']),1)
        self.assertTrue(r['actionable'][0]['actionable'])
    def test_project_filter_true_zero(self):
        ws,relay=self.mklayout()
        td=self.mktask(relay,'task_one'); self.dispatch(td,'run_1')
        r=self.inbox(ws,project='proj-other')
        self.assertEqual(r['root'],str(relay))
        self.assertEqual(r['actionable'],[])
        r=self.inbox(ws,project='proj-b')
        self.assertEqual([c['task_id'] for c in r['actionable']],['task_one'])
    def test_lane_visibility_preserved(self):
        ws,relay=self.mklayout()
        t1=self.mktask(relay,'task_nolane'); self.dispatch(t1,'run_n')
        t2=self.mktask(relay,'task_otherlane',lane='lane-other'); self.dispatch(t2,'run_o')
        r=self.inbox(ws)
        self.assertEqual(sorted(c['task_id'] for c in r['actionable']),['task_nolane','task_otherlane'])
        s=awrp.select_for_resume(str(relay),self.CH,self.EP,'lane-a',None)
        self.assertEqual(s['status'],'EXECUTE')
        self.assertEqual(s['task_id'],'task_nolane')
    def test_ambiguity_not_broadened(self):
        ws,relay=self.mklayout()
        for i,tid in enumerate(('task_a1','task_a2')):
            td=self.mktask(relay,tid); self.dispatch(td,f'run_{i}')
        r=self.inbox(ws)
        self.assertEqual(len(r['actionable']),2)
        s=awrp.select_for_resume(str(relay),self.CH,self.EP,'lane-a',None)
        self.assertEqual(s['status'],'AMBIGUOUS')
class TBM(unittest.TestCase):
    def setUp(self):
        import sys as _sys
        self.tmp=Path(tempfile.mkdtemp()); (self.tmp/'base').mkdir()
        self.py=_sys.executable
        self.server=Path(__file__).resolve().parents[1]/'tools'/'awrp_mcp_transport.py'
        self.proc=None
    def tearDown(self):
        import os, stat
        if self.proc is not None:
            try: self.proc.kill()
            except Exception: pass
            try: self.proc.wait(timeout=10)
            except Exception: pass
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def start(self,*extra):
        self.proc=subprocess.Popen([self.py,str(self.server),'--base-dir',str(self.tmp/'base'),*extra],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
        return self.proc
    def rpc(self,method,params=None,req_id=1):
        self.proc.stdin.write(json.dumps({'jsonrpc':'2.0','id':req_id,'method':method,**({'params':params} if params is not None else {})})+'\n')
        self.proc.stdin.flush()
        line=self.proc.stdout.readline()
        self.assertTrue(line,'server produced no output')
        return json.loads(line)
    def files(self):
        return sorted(str(p.relative_to(self.tmp/'base')).replace('\\','/') for p in (self.tmp/'base').rglob('*') if p.is_file())
    def args(self,**over):
        base={"action_class":"transport_write","repository":"Bruce-Yii/awrp","path":"bridge/requests/r-mcp1.json",
            "contents":{"protocol":"awrp/0.1","request_id":"r-mcp1","action":"dispatch","idempotency_key":"k1","expected_base":"abc123",
                "params":{"task_id":"t","state":"working","phase":"x","summary":"go"}}}
        base.update(over); return base
    def test_initialize_and_single_tool(self):
        self.start()
        r=self.rpc('initialize',{},req_id=1)
        self.assertIn('tools',r['result']['capabilities'])
        r=self.rpc('tools/list',{},req_id=2)
        self.assertEqual([t['name'] for t in r['result']['tools']],['awrp_transport_write'])
        schema=r['result']['tools'][0]['inputSchema']
        self.assertEqual(sorted(schema['required']),['action_class','contents','path','repository'])
    def test_valid_call_writes_exact_bytes(self):
        import hashlib as _hl
        self.start()
        self.rpc('initialize',{},req_id=1)
        r=self.rpc('tools/call',{'name':'awrp_transport_write','arguments':self.args()},req_id=2)
        body=json.loads(r['result']['content'][0]['text'])
        self.assertEqual(body['status'],'delegated')
        want=(json.dumps(self.args()['contents'],ensure_ascii=False,indent=2,sort_keys=True)+'\n').encode()
        self.assertEqual((self.tmp/'base'/'bridge'/'requests'/'r-mcp1.json').read_bytes(),want)
        self.assertEqual(body['sha256'],'sha256:'+_hl.sha256(want).hexdigest())
    def test_create_issue_drift_zero_writes(self):
        self.start()
        self.rpc('initialize',{},req_id=1)
        bad=self.args(action_class='create_issue')
        r=self.rpc('tools/call',{'name':'awrp_transport_write','arguments':bad},req_id=2)
        self.assertEqual(r['error']['code'],-32602)
        self.assertIn('ineligible',r['error']['message'])
        r=self.rpc('tools/call',{'name':'github_create_issue','arguments':bad},req_id=3)
        self.assertEqual(r['error']['code'],-32602)
        self.assertEqual(self.files(),[])
    def test_repo_drift_zero_writes(self):
        self.start()
        self.rpc('initialize',{},req_id=1)
        r=self.rpc('tools/call',{'name':'awrp_transport_write','arguments':self.args(repository='example/unrelated-repository')},req_id=2)
        self.assertEqual(r['error']['code'],-32602)
        self.assertEqual(self.files(),[])
    def test_repeated_drift_after_valid(self):
        self.start()
        self.rpc('initialize',{},req_id=1)
        r=self.rpc('tools/call',{'name':'awrp_transport_write','arguments':self.args()},req_id=2)
        self.assertIn('result',r)
        for i,bad in enumerate((self.args(action_class='create_issue'),
                                self.args(repository='Bruce-Yii/other'),
                                self.args(path='bridge/requests/../evil.json'))):
            r=self.rpc('tools/call',{'name':'awrp_transport_write','arguments':bad},req_id=10+i)
            self.assertIn('error',r,msg=bad)
        self.assertEqual(self.files(),['bridge/requests/r-mcp1.json'])
    def test_path_escape_zero_writes(self):
        self.start()
        self.rpc('initialize',{},req_id=1)
        r=self.rpc('tools/call',{'name':'awrp_transport_write','arguments':self.args(path='bridge/requests/x.result.json')},req_id=2)
        self.assertIn('error',r)
        self.assertEqual(self.files(),[])
    def test_preflight_cmd_gates(self):
        self.start('--preflight-cmd','python -c "import sys; sys.exit(3)"')
        self.rpc('initialize',{},req_id=1)
        r=self.rpc('tools/call',{'name':'awrp_transport_write','arguments':self.args()},req_id=2)
        self.assertIn('error',r)
        self.assertEqual(self.files(),[])
        self.proc.kill(); self.proc.wait(timeout=10); self.proc=None
        self.start('--preflight-cmd','python -c "pass"')
        self.rpc('initialize',{},req_id=1)
        r=self.rpc('tools/call',{'name':'awrp_transport_write','arguments':self.args()},req_id=2)
        self.assertIn('result',r)
        self.assertEqual(self.files(),['bridge/requests/r-mcp1.json'])
    def test_unknown_method_server_survives(self):
        self.start()
        self.rpc('initialize',{},req_id=1)
        r=self.rpc('github/createIssue',{'title':'THIS_SHOULD_NOT_EXIST'},req_id=2)
        self.assertEqual(r['error']['code'],-32601)
        r=self.rpc('tools/call',{'name':'awrp_transport_write','arguments':self.args()},req_id=3)
        self.assertIn('result',r)
        self.assertEqual(self.files(),['bridge/requests/r-mcp1.json'])
class TPE(unittest.TestCase):
    CH='ch-pe'; EP='ep-pe'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def git(self,repo,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def mkexec(self):
        remote=self.tmp/'r.git'; w=self.tmp/'w'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(self.tmp,'init','-b','main',str(w))
        self.git(w,'config','user.email','t@e'); self.git(w,'config','user.name','t')
        (w/'contexts').mkdir(exist_ok=True)
        awrp.write_new(w/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        awrp.project_create(str(w),'proj-p','P',(self.CH,),None,'chatgpt')
        self.git(w,'add','-A'); self.git(w,'commit','-m','seed'); self.git(w,'remote','add','origin',str(remote))
        self.git(w,'push','-u','origin','main'); self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
        return remote,w,self.git(remote,'rev-parse','main')
    def mktask(self,w,tid):
        class A: pass
        a=A(); a.root=str(w); a.context_id='c'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='w'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=self.CH; a.lane_id=None; a.worker_endpoint=self.EP; a.project_id='proj-p'
        a.legacy=True
        awrp.create_task(a); return w/'tasks'/tid
    def emit(self,td,typ,rid,**kw):
        class A: pass
        a=A(); a.task_dir=str(td); a.type=typ; a.run_id=rid; a.new_run=False; a.summary=kw.get('summary','s')
        a.actor_role=kw.get('actor_role','coordinator'); a.actor_id=kw.get('actor_id','chatgpt')
        a.recipient_role=kw.get('recipient_role','worker'); a.recipient_id=kw.get('recipient_id',self.EP)
        a.state=kw.get('state','working'); a.phase=kw.get('phase','x'); a.waiting_on=kw.get('waiting_on',self.EP)
        a.run_state=kw.get('run_state'); a.details_file=None; a.artifacts_file=None; a.approval_file=None
        a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None; a.idempotency_key=None; a.require_fresh=False; a.legacy_route=True
        awrp.emit(a)
    def close(self,td,run,phase='review'):
        self.emit(td,'DISPATCH',run,run_state='dispatched')
        self.emit(td,'ACK',run,actor_role='worker',actor_id='ep-pe',recipient_role='coordinator',recipient_id='chatgpt',run_state='working')
        self.emit(td,'HANDOFF',run,actor_role='worker',actor_id='ep-pe',recipient_role='coordinator',recipient_id='chatgpt',phase=phase,waiting_on='chatgpt',run_state='succeeded',summary='done')
    def push_task(self,w,tid):
        self.git(w,'add','--',f'tasks/{tid}'); self.git(w,'commit','-m',f'seed {tid}'); self.git(w,'push','origin','main')
    def evfiles(self,td):
        return sorted(str(p) for p in (td/'events').glob('*.json'))
    def pub(self,w,td,run,events,artifacts=(),max_attempts=3):
        class A: pass
        a=A(); a.task_dir=str(td); a.run_id=run; a.event_file=list(events); a.artifact=list(artifacts)
        a.repo=str(w); a.branch='main'; a.remote='origin'; a.commit_message=None; a.max_attempts=max_attempts
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_publish_ephemeral(a)
        return json.loads(buf.getvalue())
    def tree_files(self,repo,rev='HEAD'):
        out=self.git(repo,'ls-tree','-r','--name-only',rev)
        return sorted(l for l in out.splitlines() if l.strip())
    def rival(self,name='rival'):
        b=self.tmp/name
        subprocess.run(['git','-C',str(self.tmp),'clone',str(self.tmp/'r.git'),str(b)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.email','t@e'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.name','t@e'],check=True,capture_output=True)
        return b
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_ephemeral_publishes_with_dirty_workspace(self):
        remote,w,base=self.mkexec()
        td=self.mktask(w,'task_a')
        self.push_task(w,'task_a')
        self.close(td,'run_1')
        (w/'contexts'/'c.json').write_text((w/'contexts'/'c.json').read_text()+'\n',encoding='utf-8')
        (w/'stray.txt').write_text('dirty\n',encoding='utf-8')
        r=self.pub(w,td,'run_1',self.evfiles(td))
        self.assertEqual(r['status'],'published')
        self.assertEqual(r['attempts'],1)
        names=self.tree_files(remote)
        self.assertTrue(any(n.startswith('tasks/task_a/events/') for n in names))
        self.assertTrue((w/'stray.txt').exists())
        self.assertIn('M contexts/c.json',self.git(w,'status','--porcelain'))
        self.assertEqual(r['published_head'],self.git(remote,'rev-parse','main'))
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_ephemeral_e2e_5595_divergence(self):
        import unittest.mock as mock
        remote,w,base=self.mkexec()
        td=self.mktask(w,'task_a')
        self.push_task(w,'task_a')
        self.close(td,'run_1')
        other=self.mktask(w,'task_other')
        self.emit(other,'DISPATCH','run_o',run_state='dispatched')
        self.git(w,'add','--',f'tasks/task_other'); self.git(w,'commit','-m','worker: unrelated local task commit')
        (w/'dirty.txt').write_text('dirty\n',encoding='utf-8')
        rival=self.rival()
        (rival/'remote-only.txt').write_text('rival\n',encoding='utf-8')
        self.git(rival,'add','-A'); self.git(rival,'commit','-m','rival unrelated')
        real=subprocess.run; state={'push':0}
        def flaky(argv,*a,**k):
            if len(argv)>=5 and argv[0]=='git' and argv[1]=='-C' and argv[3]=='push':
                state['push']+=1
                if state['push']==1:
                    real(['git','-C',str(rival),'push','origin','main'],check=True,capture_output=True,text=True)
                    return subprocess.CompletedProcess(argv,1,'','error: failed to push some refs (non-fast-forward)')
            return real(argv,*a,**k)
        with mock.patch.object(awrp.subprocess,'run',new=flaky):
            r=self.pub(w,td,'run_1',self.evfiles(td))
        self.assertEqual(state['push'],2)
        self.assertEqual(r['status'],'published')
        self.assertEqual(r['attempts'],2)
        self.assertEqual(r.get('gap_kind'),'unrelated-canonical')
        names=self.tree_files(remote)
        self.assertTrue(any(n.startswith('tasks/task_a/events/') for n in names))
        self.assertFalse(any('task_other' in n for n in names))
        self.assertTrue(any(n=='remote-only.txt' for n in names))
        self.assertIn('task_other',self.git(w,'ls-tree','-r','--name-only','HEAD'))
        self.assertTrue((w/'dirty.txt').exists())
        v=awrp.validate(str(td)); self.assertEqual(v['head']['run_id'],'run_1')
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_ephemeral_same_task_staleness_refuses(self):
        remote,w,base=self.mkexec()
        td=self.mktask(w,'task_a')
        self.push_task(w,'task_a')
        self.close(td,'run_1')
        rival=self.rival()
        class A: pass
        a=A(); a.task_dir=str(rival/'tasks'/'task_a'); a.type='DISPATCH'; a.actor_role='coordinator'; a.actor_id='chatgpt'; a.recipient_role='worker'; a.recipient_id=self.EP; a.run_id='run_2'; a.new_run=False; a.state='working'; a.phase='x'; a.waiting_on=self.EP; a.run_state='dispatched'; a.summary='rival'
        a.details_file=None; a.artifacts_file=None; a.approval_file=None
        a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None; a.idempotency_key=None; a.require_fresh=False; a.legacy_route=True
        awrp.emit(a)
        self.git(rival,'add','-A'); self.git(rival,'commit','-m','rival dispatch'); self.git(rival,'push','origin','main')
        tip=self.git(remote,'rev-parse','main')
        with self.assertRaises(RuntimeError) as cm:
            self.pub(w,td,'run_1',self.evfiles(td))
        self.assertIn('semantic staleness',str(cm.exception))
        self.assertEqual(self.git(remote,'rev-parse','main'),tip)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_ephemeral_republish_is_idempotent(self):
        remote,w,base=self.mkexec()
        td=self.mktask(w,'task_a')
        self.push_task(w,'task_a')
        self.close(td,'run_1')
        r=self.pub(w,td,'run_1',self.evfiles(td))
        self.assertEqual(r['status'],'published')
        tip=self.git(remote,'rev-parse','main')
        r=self.pub(w,td,'run_1',self.evfiles(td))
        self.assertEqual(r['status'],'already_published')
        self.assertEqual(self.git(remote,'rev-parse','main'),tip)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_ephemeral_exhaustion_bounded(self):
        import unittest.mock as mock
        remote,w,base=self.mkexec()
        td=self.mktask(w,'task_a')
        self.push_task(w,'task_a')
        self.close(td,'run_1')
        real=subprocess.run; state={'push':0}
        def always_fail(argv,*a,**k):
            if len(argv)>=5 and argv[0]=='git' and argv[1]=='-C' and argv[3]=='push':
                state['push']+=1
                return subprocess.CompletedProcess(argv,1,'','error: failed to push some refs (non-fast-forward)')
            return real(argv,*a,**k)
        with mock.patch.object(awrp.subprocess,'run',new=always_fail):
            with self.assertRaises(RuntimeError) as cm:
                self.pub(w,td,'run_1',self.evfiles(td))
        self.assertIn('exhausted',str(cm.exception))
        self.assertEqual(state['push'],3)
        self.assertEqual(sum(1 for n in self.tree_files(remote) if n.startswith('tasks/task_a/events/')),1)
        self.assertEqual(len(list((td/'events').glob('*.json'))),4)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_ephemeral_artifact_import(self):
        remote,w,base=self.mkexec()
        td=self.mktask(w,'task_a')
        self.push_task(w,'task_a')
        self.close(td,'run_1')
        art=td/'artifacts'/'run_1'; art.mkdir(parents=True)
        (art/'note.diff').write_text('diff-bytes\n',encoding='utf-8')
        r=self.pub(w,td,'run_1',self.evfiles(td),artifacts=['artifacts/run_1/note.diff'])
        self.assertEqual(r['status'],'published')
        self.assertEqual(r['artifacts'],['tasks/task_a/artifacts/run_1/note.diff'])
        blob=self.git(remote,'show',f"{self.git(remote,'rev-parse','main')}:tasks/task_a/artifacts/run_1/note.diff")
        self.assertEqual(blob.strip(),'diff-bytes')
        self.assertEqual(r['events'][-1],awrp.validate(str(td))['head']['event_id'])
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_ephemeral_tampered_bytes_refused(self):
        remote,w,base=self.mkexec()
        td=self.mktask(w,'task_a')
        self.push_task(w,'task_a')
        self.close(td,'run_1')
        last=sorted((td/'events').glob('*.json'))[-1]
        o=json.loads(last.read_text(encoding='utf-8')); o['summary']='tampered'; last.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        tip=self.git(remote,'rev-parse','main')
        with self.assertRaises(RuntimeError):
            self.pub(w,td,'run_1',self.evfiles(td))
        self.assertEqual(self.git(remote,'rev-parse','main'),tip)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_ephemeral_wrong_run_refused(self):
        remote,w,base=self.mkexec()
        td=self.mktask(w,'task_a')
        self.push_task(w,'task_a')
        self.close(td,'run_1')
        with self.assertRaises(RuntimeError):
            self.pub(w,td,'run_ghost',self.evfiles(td))
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_ephemeral_concurrent_tasks_isolated(self):
        remote,w,base=self.mkexec()
        ta=self.mktask(w,'task_a')
        self.push_task(w,'task_a')
        self.close(ta,'run_a')
        tb=self.mktask(w,'task_b')
        self.close(tb,'run_b')
        r=self.pub(w,ta,'run_a',self.evfiles(ta))
        self.assertEqual(r['status'],'published')
        names=self.tree_files(remote)
        self.assertTrue(any(n.startswith('tasks/task_a/events/') for n in names))
        self.assertFalse(any(n.startswith('tasks/task_b/') for n in names))
class TDI(unittest.TestCase):
    CH='ch-di'; EP='ep-di'
    CH='ch-di'; EP='ep-di'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def mkroot(self):
        (self.tmp/'contexts').mkdir(exist_ok=True)
        awrp.write_new(self.tmp/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        awrp.project_create(str(self.tmp),'proj-d','D',(self.CH,),None,'chatgpt')
        return str(self.tmp)
    def mktask(self,root,tid,lane=None,channel=CH,endpoint=EP,project='proj-d'):
        class A: pass
        a=A(); a.root=root; a.context_id='c'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='w'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=channel; a.lane_id=lane; a.worker_endpoint=endpoint; a.project_id=project
        a.legacy=True
        awrp.create_task(a); return str(Path(root)/'tasks'/tid)
    def dispatch(self,td,rid,recipient_id=None,waiting_on=None,recipient_role='worker'):
        class A: pass
        a=A(); a.task_dir=td; a.type='DISPATCH'; a.actor_role='coordinator'; a.actor_id='chatgpt'; a.recipient_role=recipient_role; a.recipient_id=recipient_id or self.EP; a.run_id=rid; a.new_run=False; a.state='working'; a.phase='x'
        a.waiting_on=self.EP if waiting_on is None else waiting_on; a.run_state='dispatched'; a.summary='go'
        a.details_file=None; a.artifacts_file=None; a.approval_file=None
        a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None; a.idempotency_key=None; a.require_fresh=False; a.legacy_route=True
        awrp.emit(a)
    def _ns(self,root):
        class A: pass
        a=A(); a.root=root; a.channel=self.CH; a.worker_endpoint=self.EP; a.task_id=None; a.project=None; a.legacy=False
        return a
    def _hist_dispatch(self,td,tid):
        h=awrp.validate(td)['head']; t=json.loads((Path(td)/'task.json').read_text(encoding='utf-8'))
        e={'protocol':'awrp/0.1','event_id':awrp.newid('evt'),'seq':2,'context_id':t['context_id'],'task_id':tid,'run_id':'run_hist','type':'DISPATCH',
           'actor':{'role':'coordinator','id':'chatgpt'},'recipient':{'role':'worker','id':'opencode_legacy'},'causation_id':None,'created_at':awrp.now(),
           'task_projection':{'state':'working','phase':'x','waiting_on':'opencode_legacy'},'run':{'state':'dispatched'},
           'artifacts':[],'summary':'hist','details':None,'approval':None,
           'integrity':{'prev_event_id':h['event_id'],'prev_event_hash':h['integrity']['event_hash'],'event_hash':''}}
        e['integrity']['event_hash']=awrp.eh(e)
        (Path(td)/'events'/f"000002_{e['event_id']}.json").write_text(json.dumps(e,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def test_mismatch_recipient_refused(self):
        root=self.mkroot(); td=self.mktask(root,'task_d1')
        with self.assertRaises(RuntimeError) as cm:
            self.dispatch(td,'run_x',recipient_id='opencode_legacy',waiting_on='opencode_legacy')
        self.assertIn('identity refused',str(cm.exception))
        self.assertEqual(len(list((Path(td)/'events').glob('*.json'))),1)
    def test_wrong_role_refused(self):
        root=self.mkroot(); td=self.mktask(root,'task_d0')
        with self.assertRaises(RuntimeError) as cm:
            self.dispatch(td,'run_x',recipient_role='coordinator',recipient_id=self.EP,waiting_on=self.EP)
        self.assertIn('identity refused',str(cm.exception))
        self.assertIn('worker',str(cm.exception))
        self.assertEqual(len(list((Path(td)/'events').glob('*.json'))),1)
    def test_historical_wrong_role_flagged(self):
        import io, contextlib
        root=self.mkroot(); td=self.mktask(root,'task_d0h')
        h=awrp.validate(td)['head']; t=json.loads((Path(td)/'task.json').read_text(encoding='utf-8'))
        e={'protocol':'awrp/0.1','event_id':awrp.newid('evt'),'seq':2,'context_id':t['context_id'],'task_id':'task_d0h','run_id':'run_hist','type':'DISPATCH',
           'actor':{'role':'coordinator','id':'chatgpt'},'recipient':{'role':'coordinator','id':self.EP},'causation_id':None,'created_at':awrp.now(),
           'task_projection':{'state':'working','phase':'x','waiting_on':self.EP},'run':{'state':'dispatched'},
           'artifacts':[],'summary':'hist','details':None,'approval':None,
           'integrity':{'prev_event_id':h['event_id'],'prev_event_hash':h['integrity']['event_hash'],'event_hash':''}}
        e['integrity']['event_hash']=awrp.eh(e)
        (Path(td)/'events'/f"000002_{e['event_id']}.json").write_text(json.dumps(e,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        self.assertEqual(len(awrp.validate(td)['events']),2)
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_inbox(self._ns(root))
        r=json.loads(buf.getvalue())
        got=[c for c in r['actionable'] if c['task_id']=='task_d0h'][0]
        self.assertEqual(got['identity']['status'],'mismatch')
        self.assertIn('worker',got['identity']['reason'])
    def test_mismatch_waiting_on_refused(self):
        root=self.mkroot(); td=self.mktask(root,'task_d2')
        with self.assertRaises(RuntimeError) as cm:
            self.dispatch(td,'run_x',waiting_on='someone-else')
        self.assertIn('identity refused',str(cm.exception))
        self.assertEqual(len(list((Path(td)/'events').glob('*.json'))),1)
    def test_valid_accepted_and_flagged_consistent(self):
        import io, contextlib
        root=self.mkroot(); td=self.mktask(root,'task_d3',lane='lane-x')
        self.dispatch(td,'run_ok')
        self.assertEqual(len(list((Path(td)/'events').glob('*.json'))),2)
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_inbox(self._ns(root))
        r=json.loads(buf.getvalue())
        got=[c for c in r['actionable'] if c['task_id']=='task_d3'][0]
        self.assertEqual(got['identity']['status'],'consistent')
        buf=io.StringIO()
        class A: pass
        a=A(); a.task_dir=td
        with contextlib.redirect_stdout(buf): awrp.replay(a)
        self.assertEqual(json.loads(buf.getvalue())['dispatch_identity']['status'],'consistent')
    def test_legacy_compat_accepted(self):
        root=self.mkroot(); td=self.mktask(root,'task_d4',channel=None,endpoint=None,project=None)
        self.dispatch(td,'run_old',recipient_id='opencode_legacy',waiting_on='opencode_legacy')
        self.assertEqual(len(list((Path(td)/'events').glob('*.json'))),2)
        v=awrp.validate(td)
        d=next(e for e in v['events'] if e['type']=='DISPATCH')
        self.assertEqual(awrp.dispatch_identity(v['task'],d)['status'],'legacy_compat')
    def test_historical_mismatch_flagged(self):
        import io, contextlib
        root=self.mkroot(); td=self.mktask(root,'task_d5')
        self._hist_dispatch(td,'task_d5')
        v=awrp.validate(td)
        self.assertEqual(len(v['events']),2)
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_inbox(self._ns(root))
        r=json.loads(buf.getvalue())
        got=[c for c in r['actionable'] if c['task_id']=='task_d5'][0]
        self.assertEqual(got['identity']['status'],'mismatch')
        self.assertIn('opencode_legacy',got['identity']['reason'])
    def test_audit_command(self):
        import io, contextlib
        root=self.mkroot()
        td_ok=self.mktask(root,'task_d6'); self.dispatch(td_ok,'run_ok')
        td_bad=self.mktask(root,'task_d7'); self._hist_dispatch(td_bad,'task_d7')
        class A: pass
        a=A(); a.root=root; a.task_id=None
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_audit_dispatch_identity(a)
        out=json.loads(buf.getvalue())
        by={t['task_id']:t for t in out['tasks']}
        self.assertEqual(by['task_d6']['dispatches'][0]['identity']['status'],'consistent')
        self.assertEqual(by['task_d7']['dispatches'][0]['identity']['status'],'mismatch')
class TBN(unittest.TestCase):
    CH='ch-bn'; EP='ep-bn'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def mkroot(self):
        (self.tmp/'contexts').mkdir(exist_ok=True)
        awrp.write_new(self.tmp/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        awrp.project_create(str(self.tmp),'proj-n','N',(self.CH,),None,'chatgpt')
        return str(self.tmp)
    def mktask(self,root,tid):
        class A: pass
        a=A(); a.root=root; a.context_id='c'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='w'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id='ch'; a.lane_id=None; a.worker_endpoint='w'; a.project_id=None
        a.legacy=True
        awrp.create_task(a); return str(Path(root)/'tasks'/tid)
    def emit(self,td,typ,rid,**kw):
        class A: pass
        a=A(); a.task_dir=td; a.type=typ; a.run_id=rid; a.new_run=kw.get('new_run',False); a.summary=kw.get('summary','s')
        a.actor_role=kw.get('actor_role','coordinator'); a.actor_id=kw.get('actor_id','chatgpt')
        if typ=='DISPATCH':
            _ep=(json.loads((Path(td)/'task.json').read_text(encoding='utf-8')).get('routing') or {}).get('worker_endpoint') or 'ep-bn'
            a.recipient_role='worker'; a.recipient_id=_ep
        else:
            a.recipient_role=kw.get('recipient_role','worker'); a.recipient_id=kw.get('recipient_id',self.EP)
        a.state=kw.get('state','working'); a.phase=kw.get('phase','x'); a.waiting_on=kw.get('waiting_on',a.recipient_id if typ=='DISPATCH' else self.EP)
        a.run_state=kw.get('run_state'); a.details_file=None; a.artifacts_file=None; a.approval_file=None
        a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=kw.get('fencing_generation'); a.idempotency_key=kw.get('idempotency_key'); a.require_fresh=False; a.legacy_route=True
        awrp.emit(a)
    def close(self,td,run,run_state='succeeded'):
        self.emit(td,'DISPATCH',run,run_state='dispatched')
        self.emit(td,'ACK',run,actor_role='worker',actor_id='w',recipient_role='coordinator',recipient_id='chatgpt',run_state='working')
        self.emit(td,'HANDOFF',run,actor_role='worker',actor_id='w',recipient_role='coordinator',recipient_id='chatgpt',phase='review',waiting_on='chatgpt',run_state=run_state,summary='done')
    def note(self,td,rid,**kw):
        h=awrp.validate(td)['head']; p=h['task_projection']
        cur_rs=(awrp.validate(td).get('runs') or {}).get(rid,{}).get('state') if rid else None
        self.emit(td,'NOTE',rid,actor_role=kw.get('actor_role','worker'),actor_id=kw.get('actor_id','w'),
            recipient_role=kw.get('recipient_role','coordinator'),recipient_id=kw.get('recipient_id','chatgpt'),
            state=kw.get('state',p['state']),phase=kw.get('phase',p['phase']),
            waiting_on=kw.get('waiting_on',p['waiting_on']),
            run_state=kw.get('run_state',cur_rs),summary=kw.get('summary','evidence'),
            fencing_generation=kw.get('fencing_generation'),idempotency_key=kw.get('idempotency_key'),new_run=kw.get('new_run',False))
    def test_note_closed_run_succeeds_and_preserves_authority(self):
        root=self.mkroot(); td=self.mktask(root,'task_n1')
        self.close(td,'run_1')
        before=awrp.validate(td)
        self.note(td,'run_1',summary='post-run evidence block')
        v=awrp.validate(td)
        self.assertEqual(v['head']['type'],'NOTE')
        self.assertEqual(v['head']['summary'],'post-run evidence block')
        self.assertIsNone(v.get('active_run_id'))
        self.assertEqual(v['head']['task_projection'],before['head']['task_projection'])
        self.assertEqual(v['runs']['run_1']['executor'],'w')
        self.assertEqual(v['runs']['run_1']['state'],'succeeded')
        s=awrp.select_for_resume(root,self.CH,self.EP,None,None)
        self.assertEqual(s['status'],'NO_TASK')
    def test_note_task_level_null_run(self):
        root=self.mkroot(); td=self.mktask(root,'task_n2')
        self.close(td,'run_1')
        with self.assertRaises(RuntimeError) as cm:
            self.note(td,None,actor_id='w-other',summary='unattributed task note')
        self.assertIn('task worker identity',str(cm.exception))
        self.note(td,None,actor_id='w',summary='task-level note')
        v=awrp.validate(td)
        self.assertEqual(v['head']['type'],'NOTE')
        self.assertIsNone(v['head'].get('run_id'))
    def test_note_unknown_run_refused(self):
        root=self.mkroot(); td=self.mktask(root,'task_n3')
        self.close(td,'run_1')
        with self.assertRaises(RuntimeError) as cm:
            self.note(td,'run_ghost')
        self.assertIn('unknown run_id',str(cm.exception))
    def test_note_projection_drift_refused(self):
        root=self.mkroot(); td=self.mktask(root,'task_n4')
        self.close(td,'run_1')
        with self.assertRaises(RuntimeError):
            self.note(td,'run_1',state='completed')
        with self.assertRaises(RuntimeError):
            self.note(td,'run_1',phase='other-phase')
        with self.assertRaises(RuntimeError):
            self.note(td,'run_1',waiting_on='someone-else')
        self.assertEqual(len(list((Path(td)/'events').glob('*.json'))),4)
    def test_note_run_state_rules(self):
        root=self.mkroot(); td=self.mktask(root,'task_n5')
        self.close(td,'run_1')
        with self.assertRaises(RuntimeError) as cm:
            self.note(td,'run_1',run_state='working')
        self.assertIn('projection-neutral',str(cm.exception))
        self.note(td,'run_1',run_state=None,summary='stateless reference')
        self.assertEqual(awrp.validate(td)['head']['summary'],'stateless reference')
    def test_note_terminal_refused(self):
        root=self.mkroot(); td=self.mktask(root,'task_n6')
        self.close(td,'run_1')
        self.emit(td,'CANCEL',None,state='canceled',phase='x',waiting_on='null')
        with self.assertRaises(RuntimeError) as cm:
            self.note(td,'run_1')
        self.assertIn('terminal',str(cm.exception))
    def test_note_no_recipient_refused(self):
        root=self.mkroot(); td=self.mktask(root,'task_n7')
        self.close(td,'run_1')
        with self.assertRaises(RuntimeError) as cm:
            self.note(td,'run_1',recipient_role=None,recipient_id=None)
        self.assertIn('recipient',str(cm.exception))
    def test_note_fencing_refused(self):
        root=self.mkroot(); td=self.mktask(root,'task_n8')
        self.close(td,'run_1')
        with self.assertRaises(RuntimeError) as cm:
            self.note(td,'run_1',fencing_generation=1)
        self.assertIn('fencing',str(cm.exception))
    def test_note_wrong_role_and_new_run_refused(self):
        root=self.mkroot(); td=self.mktask(root,'task_n9')
        self.close(td,'run_1')
        with self.assertRaises(RuntimeError):
            self.note(td,'run_1',actor_role='admin',actor_id='x')
        with self.assertRaises(RuntimeError):
            self.note(td,'run_1',new_run=True)
        self.assertEqual(len(list((Path(td)/'events').glob('*.json'))),4)
    def test_note_coordinator_to_worker(self):
        root=self.mkroot(); td=self.mktask(root,'task_n10')
        self.close(td,'run_1')
        self.note(td,'run_1',actor_role='coordinator',actor_id='chatgpt',recipient_role='worker',recipient_id=self.EP,summary='coord follow-up')
        self.assertEqual(awrp.validate(td)['head']['summary'],'coord follow-up')
    def test_note_idempotency(self):
        root=self.mkroot(); td=self.mktask(root,'task_n11')
        self.close(td,'run_1')
        self.note(td,'run_1',summary='once',idempotency_key='k-note-1')
        with self.assertRaises(RuntimeError) as cm:
            self.note(td,'run_1',summary='twice',idempotency_key='k-note-1')
        self.assertIn('duplicate command',str(cm.exception))
    def test_note_confers_no_reviewability(self):
        root=self.mkroot(); td=self.mktask(root,'task_n12')
        self.close(td,'run_f',run_state='failed')
        self.note(td,'run_f',summary='failure evidence')
        with self.assertRaises(RuntimeError):
            self.emit(td,'REVIEW','run_f',phase='review',waiting_on='chatgpt',run_state='failed')
        td2=self.mktask(root,'task_n12b')
        self.close(td2,'run_s')
        self.note(td2,'run_s',summary='extra evidence')
        self.emit(td2,'REVIEW','run_s',phase='review',waiting_on='chatgpt',run_state='succeeded')
        self.assertEqual(awrp.validate(td2)['head']['type'],'REVIEW')
    def test_note_does_not_seat_executor(self):
        root=self.mkroot(); td=self.mktask(root,'task_n13')
        self.emit(td,'DISPATCH','run_x',run_state='dispatched')
        with self.assertRaises(RuntimeError) as cm:
            self.note(td,'run_x',actor_id='w-other',summary='bystander note')
        self.assertIn('dispatched recipient',str(cm.exception))
        self.note(td,'run_x',actor_id='w',summary='recipient note')
        v=awrp.validate(td)
        self.assertIsNone(v['runs']['run_x']['executor'])
        self.emit(td,'ACK','run_x',actor_role='worker',actor_id='w',recipient_role='coordinator',recipient_id='chatgpt',run_state='working')
        self.assertEqual(awrp.validate(td)['runs']['run_x']['executor'],'w')
    def test_note_run_reference_binds_executor(self):
        root=self.mkroot(); td=self.mktask(root,'task_n15')
        self.close(td,'run_1')
        with self.assertRaises(RuntimeError) as cm:
            self.note(td,'run_1',actor_id='w-other',summary='foreign evidence')
        self.assertIn('run executor',str(cm.exception))
        self.assertEqual(len(list((Path(td)/'events').glob('*.json'))),4)
    def test_note_coordinator_binds_coordinator(self):
        root=self.mkroot(); td=self.mktask(root,'task_n16')
        self.close(td,'run_1')
        with self.assertRaises(RuntimeError) as cm:
            self.note(td,'run_1',actor_role='coordinator',actor_id='mallory',recipient_role='worker',recipient_id=self.EP)
        self.assertIn('task coordinator',str(cm.exception))
        self.assertEqual(len(list((Path(td)/'events').glob('*.json'))),4)
    def test_note_selection_unaffected(self):
        root=self.mkroot(); td=self.mktask(root,'task_n14')
        self.close(td,'run_a')
        self.note(td,'run_a',summary='old evidence')
        self.emit(td,'DISPATCH','run_b',run_state='dispatched')
        s=awrp.select_for_resume(root,'ch','w',None,None)
        self.assertEqual(s['status'],'EXECUTE')
        self.assertEqual(s['run_id'],'run_b')
class TBP(unittest.TestCase):
    CH='ch-bp'; EP='ep-bp'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def git(self,repo,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def mkclone(self):
        remote=self.tmp/'r.git'; w=self.tmp/'w'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(self.tmp,'init','-b','main',str(w))
        self.git(w,'config','user.email','t@e'); self.git(w,'config','user.name','t')
        (w/'contexts').mkdir(exist_ok=True)
        awrp.write_new(w/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        awrp.project_create(str(w),'proj-p','P',(self.CH,),None,'chatgpt')
        self.git(w,'add','-A'); self.git(w,'commit','-m','seed'); self.git(w,'remote','add','origin',str(remote))
        self.git(w,'push','-u','origin','main'); self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
        return remote,w,self.git(remote,'rev-parse','main')
    def mktask(self,w,tid):
        class A: pass
        a=A(); a.root=str(w); a.context_id='c'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='w'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=self.CH; a.lane_id=None; a.worker_endpoint=self.EP; a.project_id='proj-p'
        a.legacy=True
        awrp.create_task(a); return w/'tasks'/tid
    def emit(self,td,typ,rid,**kw):
        class A: pass
        a=A(); a.task_dir=str(td); a.type=typ; a.run_id=rid; a.new_run=False; a.summary=kw.get('summary','s')
        a.actor_role=kw.get('actor_role','coordinator'); a.actor_id=kw.get('actor_id','chatgpt')
        a.recipient_role=kw.get('recipient_role','worker'); a.recipient_id=kw.get('recipient_id',self.EP)
        a.state=kw.get('state','working'); a.phase=kw.get('phase','x'); a.waiting_on=kw.get('waiting_on',self.EP)
        a.run_state=kw.get('run_state'); a.details_file=None; a.artifacts_file=None; a.approval_file=None
        a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None; a.idempotency_key=None; a.require_fresh=False; a.legacy_route=True
        awrp.emit(a)
    def close(self,td,run):
        self.emit(td,'DISPATCH',run,run_state='dispatched')
        self.emit(td,'ACK',run,actor_role='worker',actor_id='ep-bp',recipient_role='coordinator',recipient_id='chatgpt',run_state='working')
        self.emit(td,'HANDOFF',run,actor_role='worker',actor_id='ep-bp',recipient_role='coordinator',recipient_id='chatgpt',phase='review',waiting_on='chatgpt',run_state='succeeded',summary='done')
    def note(self,td,rid,**kw):
        h=awrp.validate(str(td))['head']; p=h['task_projection']
        cur_rs=(awrp.validate(str(td)).get('runs') or {}).get(rid,{}).get('state') if rid else None
        self.emit(td,'NOTE',rid,actor_role=kw.get('actor_role','worker'),actor_id=kw.get('actor_id','ep-bp'),
            recipient_role='coordinator',recipient_id='chatgpt',
            state=p['state'],phase=p['phase'],waiting_on=p['waiting_on'],
            run_state=cur_rs,summary=kw.get('summary','evidence'))
    def head_of(self,td):
        h=awrp.validate(str(td))['head']; return (h['event_id'],h['integrity']['event_hash'])
    def wretrypush(self,w,td,run,exp_head,exp_hash,base):
        class A: pass
        a=A(); a.task_dir=str(td); a.run_id=run; a.expected_head=exp_head; a.expected_hash=exp_hash; a.expected_base=base
        a.repo=str(w); a.branch='main'; a.remote='origin'; a.verify_cmd=[]; a.max_attempts=3
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_worker_retry_push(a)
        return json.loads(buf.getvalue())
    def rival_clone(self,name='rival'):
        b=self.tmp/name
        subprocess.run(['git','-C',str(self.tmp),'clone',str(self.tmp/'r.git'),str(b)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.email','t@e'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.name','t@e'],check=True,capture_output=True)
        return b
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_note_tip_publishes_across_drift(self):
        remote,w,base=self.mkclone()
        td=self.mktask(w,'task_p1')
        self.close(td,'run_1')
        self.git(w,'add','-A'); self.git(w,'commit','-m','worker: close run_1'); self.git(w,'push','origin','main')
        base2=self.git(w,'rev-parse','HEAD')
        self.note(td,'run_1',summary='post-run evidence')
        tip_bytes=sorted((td/'events').glob('*.json'))[-1].read_bytes()
        self.git(w,'add','-A'); self.git(w,'commit','-m','worker: evidence NOTE')
        rival=self.rival_clone()
        (rival/'unrelated.txt').write_text('rival\n',encoding='utf-8')
        self.git(rival,'add','-A'); self.git(rival,'commit','-m','rival unrelated'); self.git(rival,'push','origin','main')
        exp_head,exp_hash=self.head_of(td)
        r=self.wretrypush(w,td,'run_1',exp_head,exp_hash,base2)
        self.assertEqual(r['status'],'published')
        self.assertEqual(r['attempts'],2)
        self.assertEqual(r.get('gap_kind'),'unrelated-canonical')
        self.assertEqual(self.git(w,'rev-parse','main'),self.git(remote,'rev-parse','main'))
        self.assertEqual(awrp.canonical_artifact_bytes(sorted((td/'events').glob('*.json'))[-1].read_bytes()),awrp.canonical_artifact_bytes(tip_bytes))
        self.assertEqual(awrp.validate(str(td))['head']['integrity']['event_hash'],exp_hash)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_note_tip_refuses_after_governance(self):
        remote,w,base=self.mkclone()
        td=self.mktask(w,'task_p2')
        self.close(td,'run_1')
        self.emit(td,'REVIEW','run_1',phase='review',waiting_on='chatgpt',run_state='succeeded')
        self.note(td,'run_1',summary='late evidence')
        self.git(w,'add','-A'); self.git(w,'commit','-m','worker: governed chain')
        exp_head,exp_hash=self.head_of(td)
        with self.assertRaises(RuntimeError) as cm:
            self.wretrypush(w,td,'run_1',exp_head,exp_hash,base)
        self.assertIn('directly from its closing HANDOFF',str(cm.exception))
        self.assertEqual(self.git(remote,'rev-parse','main'),base)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_note_tip_refuses_superseded(self):
        remote,w,base=self.mkclone()
        td=self.mktask(w,'task_p3')
        self.close(td,'run_a')
        self.close(td,'run_b')
        self.note(td,'run_b',summary='b evidence')
        self.git(w,'add','-A'); self.git(w,'commit','-m','worker: b chain')
        exp_head,exp_hash=self.head_of(td)
        with self.assertRaises(RuntimeError) as cm:
            self.wretrypush(w,td,'run_a',exp_head,exp_hash,base)
        self.assertIn('not its NOTE chain',str(cm.exception))
        self.assertEqual(self.git(remote,'rev-parse','main'),base)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_task_level_note_tip_refuses(self):
        remote,w,base=self.mkclone()
        td=self.mktask(w,'task_p4')
        self.close(td,'run_1')
        h=awrp.validate(str(td))['head']; p=h['task_projection']
        self.emit(td,'NOTE',None,actor_role='worker',actor_id=self.EP,recipient_role='coordinator',recipient_id='chatgpt',
            state=p['state'],phase=p['phase'],waiting_on=p['waiting_on'],summary='task note')
        self.git(w,'add','-A'); self.git(w,'commit','-m','worker: task note')
        exp_head,exp_hash=self.head_of(td)
        with self.assertRaises(RuntimeError) as cm:
            self.wretrypush(w,td,'run_1',exp_head,exp_hash,base)
        self.assertIn('not its NOTE chain',str(cm.exception))
        self.assertEqual(self.git(remote,'rev-parse','main'),base)
    def test_note_lineage_wrong_actor_unit(self):
        ev_h={'type':'HANDOFF','run_id':'r','actor':{'role':'worker','id':'w1'},'run':{'state':'succeeded'},'event_id':'e1'}
        ev_n={'type':'NOTE','run_id':'r','actor':{'role':'worker','id':'wX'},'run':{'state':'succeeded'},'event_id':'e2'}
        v={'events':[ev_h,ev_n],'head':ev_n,'runs':{'r':{'executor':'w1','state':'succeeded'}}}
        with self.assertRaises(RuntimeError) as cm:
            awrp._worker_note_lineage(v,'r')
        self.assertIn('executor',str(cm.exception))
    def test_note_lineage_open_state_unit(self):
        ev_h={'type':'HANDOFF','run_id':'r','actor':{'role':'worker','id':'w1'},'run':{'state':'working'},'event_id':'e1'}
        ev_n={'type':'NOTE','run_id':'r','actor':{'role':'worker','id':'w1'},'run':{'state':'working'},'event_id':'e2'}
        v={'events':[ev_h,ev_n],'head':ev_n,'runs':{'r':{'executor':'w1','state':'working'}}}
        with self.assertRaises(RuntimeError) as cm:
            awrp._worker_note_lineage(v,'r')
        self.assertIn('not closed',str(cm.exception))
    def test_note_lineage_ok_unit(self):
        ev_h={'type':'HANDOFF','run_id':'r','actor':{'role':'worker','id':'w1'},'run':{'state':'failed'},'event_id':'e1'}
        ev_n={'type':'NOTE','run_id':'r','actor':{'role':'worker','id':'w1'},'run':{'state':'failed'},'event_id':'e2'}
        v={'events':[ev_h,ev_n],'head':ev_n,'runs':{'r':{'executor':'w1','state':'failed'}}}
        self.assertTrue(awrp._worker_note_lineage(v,'r'))
    def test_write_new_is_lf_stable(self):
        p=self.tmp/'lf.json'
        awrp.write_new(p,{'a':1})
        raw=p.read_bytes()
        self.assertNotIn(b'\r',raw)
        self.assertTrue(raw.endswith(b'\n'))
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_crlf_worktree_tolerated_across_recompose(self):
        remote,w,base=self.mkclone()
        (w/'.gitattributes').write_text('tasks/**/events/*.json text eol=lf\n',encoding='utf-8')
        self.git(w,'add','-A'); self.git(w,'commit','-m','attributes'); self.git(w,'push','origin','main')
        base2=self.git(w,'rev-parse','HEAD')
        td=self.mktask(w,'task_p5')
        self.close(td,'run_1')
        for f in (td/'events').glob('*.json'):
            f.write_bytes(f.read_bytes().replace(b'\n',b'\r\n'))
        self.git(w,'add','-A'); self.git(w,'commit','-m','worker: close run_1 (crlf worktree)'); self.git(w,'push','origin','main')
        base3=self.git(w,'rev-parse','HEAD')
        self.note(td,'run_1',summary='post-run evidence')
        self.git(w,'add','-A'); self.git(w,'commit','-m','worker: evidence NOTE')
        rival=self.rival_clone()
        (rival/'unrelated.txt').write_text('rival\n',encoding='utf-8')
        self.git(rival,'add','-A'); self.git(rival,'commit','-m','rival unrelated'); self.git(rival,'push','origin','main')
        exp_head,exp_hash=self.head_of(td)
        r=self.wretrypush(w,td,'run_1',exp_head,exp_hash,base3)
        self.assertEqual(r['status'],'published')
        self.assertEqual(r['attempts'],2)
        self.assertEqual(self.git(w,'rev-parse','main'),self.git(remote,'rev-parse','main'))
        self.assertEqual(awrp.validate(str(td))['head']['integrity']['event_hash'],exp_hash)
class TBC(unittest.TestCase):
    def schemas(self):
        d=Path(__file__).resolve().parents[1]/'schemas'
        return {p.stem.replace('.schema',''):json.loads(p.read_text(encoding='utf-8')) for p in sorted(d.glob('*.schema.json'))}
    def test_event_schema_matches_runtime(self):
        s=self.schemas()['event']
        self.assertEqual(set(s['properties']['type']['enum']),set(awrp.EVENT_TYPES))
        self.assertEqual(s['properties']['protocol'],{'const':awrp.PROTOCOL})
        for k in ('idempotency_key','claimant','fencing'):
            self.assertIn(k,s['properties'])
        self.assertEqual(set(s['required']),{'protocol','event_id','seq','context_id','task_id','type','actor','created_at','task_projection','summary','artifacts','integrity'})
    def test_state_run_enum_consistency(self):
        self.assertTrue(set(awrp.TERMINAL)<set(awrp.TASK_STATES))
        self.assertTrue(set(awrp.CLOSED_RUN_STATES)<set(awrp.RUN_STATES))
        self.assertTrue(set(awrp.ACTIVE_RUN_STATES)<set(awrp.RUN_STATES))
        self.assertTrue(set(awrp.EXECUTION_TYPES)<set(awrp.EVENT_TYPES))
        self.assertTrue(set(awrp.ALLOWED)-{None}<=set(awrp.TASK_STATES))
        for _from,_to in awrp.ALLOWED.items():
            if _from is not None: self.assertTrue(set(_to)<=set(awrp.TASK_STATES))
        doc=(Path(__file__).resolve().parents[1]/'protocol'/'AWRP-0.1.md').read_text(encoding='utf-8')
        for st in awrp.TASK_STATES: self.assertIn(f'`{st}`',doc)
        for rs in awrp.RUN_STATES: self.assertIn(f'`{rs}`',doc)
        for et in awrp.EVENT_TYPES: self.assertIn(f'`{et}`',doc)
    def test_manifest_schemas_match_creators(self):
        s=self.schemas()
        self.assertEqual({t['properties']['protocol']['const'] for t in s.values() if 'protocol' in t.get('properties',{})},{awrp.PROTOCOL})
        tmp=Path(tempfile.mkdtemp())
        try:
            (tmp/'contexts').mkdir()
            awrp.write_new(tmp/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
            class A: pass
            a=A(); a.root=str(tmp); a.context_id='c'; a.task_id='task_p'; a.title='t'; a.goal='g'; a.worker='w'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
            a.channel_id=None; a.lane_id=None; a.worker_endpoint=None; a.project_id=None
            a.legacy=True
            awrp.create_task(a)
            task=json.loads((tmp/'tasks'/'task_p'/'task.json').read_text(encoding='utf-8'))
            self.assertTrue(set(s['task']['required'])<=set(task))
            awrp.project_create(str(tmp),'proj-p','P',(),None,'chatgpt')
            proj=json.loads((tmp/'projects'/'proj-p.json').read_text(encoding='utf-8'))
            self.assertTrue(set(s['project']['required'])<=set(proj))
            self.assertEqual(set(s['project']['properties']['project_id']),{'type','pattern'})
            ctx=json.loads((tmp/'contexts'/'c.json').read_text(encoding='utf-8'))
            self.assertTrue(set(s['context']['required'])<=set(ctx))
        finally:
            import os, stat
            def ro(action,path,exc):
                try: os.chmod(path,stat.S_IWRITE); action(path)
                except Exception: pass
            shutil.rmtree(tmp,onerror=ro)
    def test_projection_keys_parity(self):
        s=self.schemas()['event']
        self.assertEqual(set(s['properties']['task_projection']['required']),{'state','phase','waiting_on'})
    def test_readiness_profile_contract(self):
        s=self.schemas()['readiness']
        self.assertEqual(set(s['required']),{'ok','missing','transport'})
        prof=s['x-ready-manifest']
        self.assertIn('routing.worker_endpoint',prof['required_manifest_fields'])
        self.assertIn('authority.coordinator',prof['required_authority_identities'])
        self.assertIn('merge',prof['required_policy_keys'])
        tmp=Path(tempfile.mkdtemp())
        try:
            (tmp/'contexts').mkdir()
            awrp.write_new(tmp/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
            awrp.project_create(str(tmp),'proj-r','R',('ch-r',),None,'chatgpt')
            class A: pass
            a=A(); a.root=str(tmp); a.context_id='c'; a.task_id='task_r'; a.title='t'; a.goal='g'; a.worker='w'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
            a.channel_id='ch-r'; a.lane_id=None; a.worker_endpoint='w'; a.project_id='proj-r'; a.legacy=False
            import io, contextlib
            buf=io.StringIO()
            with contextlib.redirect_stdout(buf): awrp.create_task(a)
            t=json.loads((tmp/'tasks'/'task_r'/'task.json').read_text(encoding='utf-8'))
            r=awrp.task_readiness(t,str(tmp))
            self.assertTrue(r['ok'])
            self.assertEqual(set(r),{'ok','missing','transport'})
            self.assertEqual(r['missing'],[])
        finally:
            import os, stat
            def ro(action,path,exc):
                try: os.chmod(path,stat.S_IWRITE); action(path)
                except Exception: pass
            shutil.rmtree(tmp,onerror=ro)
    def test_cli_surface_pinned(self):
        import io, contextlib
        cmds={'validate','replay','render-card','emit','publish-preflight','worker-retry-push','publish-ephemeral','artifact-hash','audit-chain','doctor','inbox','bind','resume','first-bind','project-create','recover-task','attach','switch','focus','check-lineage','plan-dispatch','dispatch-guarded','acquire-claim','read-claim','audit-history','audit-fencing','audit-dispatch-identity','bridge-process','bridge-preflight','compose-intent','publish-atomic','publish-connector'}
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.parser().print_help()
        h=buf.getvalue().replace('{',' ').replace('}', ' ').replace(',', ' ')
        for c in cmds: self.assertIn(f' {c} ',h)
    def test_artifact_hash_contract(self):
        import tempfile as _tf
        f=_tf.NamedTemporaryFile(delete=False,suffix='.diff'); f.close()
        try:
            Path(f.name).write_bytes(b'a\n')
            r=json.loads(json.dumps(awrp.artifact_fingerprint(f.name)))
            self.assertEqual(set(r),{'path','sha256','size_bytes','line_ending'})
            self.assertTrue(r['sha256'].startswith('sha256:'))
        finally:
            Path(f.name).unlink(missing_ok=True)
    def test_readiness_schema_contract(self):
        s=self.schemas()['readiness']
        self.assertEqual(set(s['required']),{'ok','missing','transport'})
        prof=s['x-ready-manifest']
        self.assertIn('routing.worker_endpoint',prof['required_manifest_fields'])
        self.assertIn('authority.coordinator',prof['required_authority_identities'])
        self.assertIn('merge',prof['required_policy_keys'])
        self.assertIn('human_approval',prof['recognized_policy_values'])
class TDC(unittest.TestCase):
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def mkroot(self):
        (self.tmp/'contexts').mkdir(exist_ok=True)
        awrp.write_new(self.tmp/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        return str(self.tmp)
    def mktask(self,root,tid):
        class A: pass
        a=A(); a.root=root; a.context_id='c'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='w'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=None; a.lane_id=None; a.worker_endpoint=None; a.project_id=None
        a.legacy=True
        awrp.create_task(a); return str(Path(root)/'tasks'/tid)
    def dispatch(self,td,rid):
        class A: pass
        a=A(); a.task_dir=td; a.type='DISPATCH'; a.actor_role='coordinator'; a.actor_id='chatgpt'; a.recipient_role='worker'; a.recipient_id='opencode'; a.run_id=rid; a.new_run=False; a.state='working'; a.phase='x'; a.waiting_on='opencode'; a.run_state='dispatched'; a.summary='go'
        a.details_file=None; a.artifacts_file=None; a.approval_file=None
        a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None; a.idempotency_key=None; a.require_fresh=False; a.legacy_route=True
        awrp.emit(a)
    def test_audit_chain_clean(self):
        root=self.mkroot(); td=self.mktask(root,'task_c1')
        self.dispatch(td,'run_1')
        r=awrp.audit_chain(td)
        self.assertTrue(r['ok'])
        self.assertTrue(all(e['ok'] for e in r['events']))
        self.assertIsNone(r['events'][0]['introduced_by'])
    def test_audit_chain_hash_mismatch(self):
        root=self.mkroot(); td=self.mktask(root,'task_c2')
        self.dispatch(td,'run_1')
        p=sorted((Path(td)/'events').glob('*.json'))[-1]
        o=json.loads(p.read_text(encoding='utf-8')); o['summary']='tampered'; p.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        r=awrp.audit_chain(td)
        self.assertFalse(r['ok'])
        last=r['events'][-1]
        self.assertFalse(last['ok'])
        self.assertFalse(last['checks']['event_hash']['ok'])
        self.assertTrue(last['checks']['prev_link']['ok'])
        self.assertTrue(last['checks']['sequence']['ok'])
    def test_audit_chain_link_break(self):
        root=self.mkroot(); td=self.mktask(root,'task_c3')
        self.dispatch(td,'run_1')
        p=sorted((Path(td)/'events').glob('*.json'))[-1]
        o=json.loads(p.read_text(encoding='utf-8')); o['integrity']['prev_event_id']='evt_bogus'; p.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        r=awrp.audit_chain(td)
        self.assertFalse(r['ok'])
        self.assertFalse(r['events'][-1]['checks']['prev_link']['ok'])
    def test_audit_chain_seq_gap(self):
        root=self.mkroot(); td=self.mktask(root,'task_c4')
        self.dispatch(td,'run_1')
        p=sorted((Path(td)/'events').glob('*.json'))[-1]
        o=json.loads(p.read_text(encoding='utf-8')); o['seq']=99; p.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        r=awrp.audit_chain(td)
        self.assertFalse(r['ok'])
        self.assertFalse(r['events'][-1]['checks']['sequence']['ok'])
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_audit_chain_producer_attribution(self):
        import subprocess as _sp
        root=self.mkroot()
        _sp.run(['git','-C',root,'init','-b','main'],check=True,capture_output=True)
        _sp.run(['git','-C',root,'config','user.email','t@e'],check=True,capture_output=True)
        _sp.run(['git','-C',root,'config','user.name','t'],check=True,capture_output=True)
        td=self.mktask(root,'task_c5')
        self.dispatch(td,'run_1')
        _sp.run(['git','-C',root,'add','-A'],check=True,capture_output=True)
        _sp.run(['git','-C',root,'commit','-m','seed'],check=True,capture_output=True)
        r=awrp.audit_chain(td,root)
        self.assertTrue(r['ok'])
        intro=r['events'][-1]['introduced_by']
        self.assertEqual(len(intro['commit']),40)
        self.assertEqual(intro['author_email'],'t@e')
        self.assertFalse(intro['single_file'])
    def test_remote_head_of_matches_inline(self):
        import subprocess as _sp
        d=Path(tempfile.mkdtemp())
        try:
            _sp.run(['git','-C',str(d),'init','--bare','r.git'],check=True,capture_output=True)
            _sp.run(['git','-C',str(d),'init','-b','main','w'],check=True,capture_output=True)
            _sp.run(['git','-C',str(d/'w'),'config','user.email','t@e'],check=True,capture_output=True)
            _sp.run(['git','-C',str(d/'w'),'config','user.name','t'],check=True,capture_output=True)
            (d/'w'/'f').write_text('x',encoding='utf-8')
            _sp.run(['git','-C',str(d/'w'),'add','-A'],check=True,capture_output=True)
            _sp.run(['git','-C',str(d/'w'),'commit','-m','s'],check=True,capture_output=True)
            _sp.run(['git','-C',str(d/'w'),'remote','add','origin',str(d/'r.git')],check=True,capture_output=True)
            _sp.run(['git','-C',str(d/'w'),'push','-u','origin','main'],check=True,capture_output=True)
            rh=awrp.git_out(str(d/'w'),'ls-remote','origin','main')
            self.assertEqual(awrp.remote_head_of(str(d/'w'),'origin','main'),rh.split()[0])
        finally:
            import os, stat
            def ro(action,path,exc):
                try: os.chmod(path,stat.S_IWRITE); action(path)
                except Exception: pass
            shutil.rmtree(d,onerror=ro)
class TCM(unittest.TestCase):
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def mkroot(self):
        (self.tmp/'contexts').mkdir(exist_ok=True)
        awrp.write_new(self.tmp/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        return str(self.tmp)
    def mktask(self,root,tid,channel=None,endpoint=None):
        class A: pass
        a=A(); a.root=root; a.context_id='c'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='w'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=channel; a.lane_id=None; a.worker_endpoint=endpoint; a.project_id=None
        a.legacy=True
        awrp.create_task(a); return str(Path(root)/'tasks'/tid)
    def intent(self,action='dispatch',params=None,**extra):
        import tempfile as _tf, os as _os
        body={"action":action,"idempotency_key":"k-m","params":params or {"task_id":"t","state":"working","phase":"x","summary":"s"}}
        body.update(extra)
        fd,nm=_tf.mkstemp(suffix='.json',dir=str(self.tmp)); _os.close(fd)
        self.addCleanup(lambda: Path(nm).unlink(missing_ok=True))
        Path(nm).write_text(json.dumps(body),encoding='utf-8')
        class A: pass
        a=A(); a.intent_file=nm; a.actor_role='coordinator'; a.actor_id='chatgpt'
        a.repo=str(self.tmp); a.branch='main'; a.remote='origin'; a.expected_base='0'*40; a.binding_root=None
        a.root=str(self.tmp)
        return a
    def test_intent_rejects_canonical_top_level(self):
        for bad in ({'event_id':'evt_forged'},{'seq':99},{'integrity':{}},{'event_hash':'sha256:0'},{'actor':{'role':'x','id':'y'}},{'fencing':{}}):
            with self.assertRaises(RuntimeError,msg=str(sorted(bad))):
                awrp.do_compose_intent(self.intent(**bad))
    def test_intent_rejects_canonical_params(self):
        for bad in ({'seq':99},{'prev_event_id':'x'},{'prev_event_hash':'x'},{'event_hash':'x'},{'event_id':'x'}):
            p={"task_id":"t","state":"working","phase":"x","summary":"s"}
            p.update(bad)
            with self.assertRaises(RuntimeError,msg=str(sorted(bad))):
                awrp.do_compose_intent(self.intent(params=p))
    def test_bridge_request_rejects_canonical_keys(self):
        (self.tmp/'bridge'/'requests').mkdir(parents=True)
        for bad in ({'event_id':'x'},{'seq':1},{'actor':{}},{'fencing':{}},{'integrity':{}}):
            body={"protocol":"awrp/0.1","request_id":"r-bad","action":"dispatch","idempotency_key":"k","expected_base":"b","params":{"task_id":"t"}}
            body.update(bad)
            (self.tmp/'bridge'/'requests'/'r-bad.json').write_text(json.dumps(body),encoding='utf-8')
            with self.assertRaises(RuntimeError,msg=str(sorted(bad))):
                awrp.read_bridge_request(str(self.tmp),'r-bad')
    def test_fencing_without_claim_refused(self):
        root=self.mkroot(); td=self.mktask(root,'task_f1')
        class A: pass
        a=A(); a.task_dir=td; a.type='REVIEW'; a.actor_role='coordinator'; a.actor_id='chatgpt'; a.recipient_role=None; a.recipient_id=None; a.run_id=None; a.new_run=False; a.state='working'; a.phase='x'; a.waiting_on='chatgpt'; a.run_state=None; a.summary='r'
        a.details_file=None; a.artifacts_file=None; a.approval_file=None
        a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=1; a.idempotency_key=None; a.require_fresh=False; a.legacy_route=True
        with self.assertRaises(RuntimeError) as cm:
            awrp.emit(a)
        self.assertIn('claim',str(cm.exception))
        self.assertEqual(len(list((Path(td)/'events').glob('*.json'))),1)
    def test_selection_ignores_wall_clock(self):
        root=self.mkroot()
        for tid in ('task_early','task_late'):
            self.mktask(root,tid,channel='ch',endpoint='w')
        import datetime as _dt
        real=awrp.now
        try:
            awrp.now=lambda: '2020-01-01T00:00:00Z'
            self._dispatch(root,'task_early','run_e')
            awrp.now=lambda: '2030-01-01T00:00:00Z'
            self._dispatch(root,'task_late','run_l')
        finally:
            awrp.now=real
        s=awrp.select_for_resume(root,'ch','w',None,None)
        self.assertEqual(s['status'],'AMBIGUOUS')
        self.assertEqual(sorted(s['candidates']),['task_early','task_late'])
    def _dispatch(self,root,tid,rid):
        class A: pass
        a=A(); a.task_dir=str(Path(root)/'tasks'/tid); a.type='DISPATCH'; a.actor_role='coordinator'; a.actor_id='chatgpt'; a.recipient_role='worker'; a.recipient_id='w'; a.run_id=rid; a.new_run=False; a.state='working'; a.phase='x'; a.waiting_on='w'; a.run_state='dispatched'; a.summary='go'
        a.details_file=None; a.artifacts_file=None; a.approval_file=None
        a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None; a.idempotency_key=None; a.require_fresh=False; a.legacy_route=True
        awrp.emit(a)
    def test_emit_cli_has_no_material_flags(self):
        with self.assertRaises(SystemExit):
            awrp.parser().parse_args(['emit','--task-dir','t','--type','DISPATCH','--actor-role','coordinator','--actor-id','c','--state','working','--phase','x','--summary','s','--event-id','evt_forged'])
    def test_invalid_canonical_verdict(self):
        root=self.mkroot()
        self.mktask(root,'task_bad',channel='ch',endpoint='w')
        self._dispatch(root,'task_bad','run_b')
        p=sorted((Path(root)/'tasks'/'task_bad'/'events').glob('*.json'))[-1]
        o=json.loads(p.read_text(encoding='utf-8')); o['summary']='tampered'; p.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        s=awrp.select_for_resume(root,'ch','w',None,None)
        self.assertEqual(s['status'],'INVALID_CANONICAL')
        self.assertIn('invalid_canonical',s)
        self.assertEqual(len(s['invalid_canonical']),1)
        inv=s['invalid_canonical'][0]
        self.assertEqual(inv['task_id'],'task_bad')
        self.assertIn('hash mismatch',inv['error'])
        fx=inv['forensics']
        self.assertFalse(fx['ok'])
        self.assertEqual(fx['last_valid']['seq'],1)
        bad=[e for e in fx['events'] if not e['ok']][0]
        self.assertIn('recorded',bad['checks']['event_hash']['detail'])
        self.assertIn('recomputed',bad['checks']['event_hash']['detail'])
    def test_true_no_task_has_empty_invalid(self):
        root=self.mkroot()
        s=awrp.select_for_resume(root,'ch','w',None,None)
        self.assertEqual(s['status'],'NO_TASK')
        self.assertEqual(s.get('invalid_canonical'),[])
    def test_recover_task_flow(self):
        import tempfile as _tf, os as _os
        root=self.mkroot()
        self.mktask(root,'task_pred',channel='ch',endpoint='w')
        self._dispatch(root,'task_pred','run_p')
        p=sorted((Path(root)/'tasks'/'task_pred'/'events').glob('*.json'))[-1]
        o=json.loads(p.read_text(encoding='utf-8')); o['summary']='tampered'; p.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        fd,nm=_tf.mkstemp(suffix='.md',dir=str(self.tmp)); _os.close(fd)
        self.addCleanup(lambda: Path(nm).unlink(missing_ok=True))
        Path(nm).write_text('human approves recovery of task_pred',encoding='utf-8')
        class A: pass
        a=A(); a.root=root; a.task_id='task_rec'; a.predecessor_task='task_pred'; a.context_id='c'; a.title='recovery'; a.goal='recover'; a.worker='w'; a.created_by='chatgpt'
        a.channel_id='ch'; a.lane_id=None; a.worker_endpoint='w'; a.project_id=None
        a.approval_file=nm; a.contract='recover at seq1 boundary; no event copy'
        awrp.recover_task(a)
        v=awrp.validate(str(Path(root)/'tasks'/'task_rec'))
        self.assertEqual(v['head']['type'],'TASK_CREATED')
        det=json.loads(v['head']['details'])
        self.assertEqual(det['recovery_of']['task_id'],'task_pred')
        self.assertEqual(det['recovery_of']['last_valid']['seq'],1)
        self.assertEqual(len(det['bad_events']),1)
        self.assertTrue(det['approval']['sha256'].startswith('sha256:'))
        self.assertEqual(len(list((Path(root)/'tasks'/'task_rec'/'events').glob('*.json'))),1)
        self.assertTrue((Path(root)/'tasks'/'task_rec'/'artifacts').exists())
    def test_recover_task_refuses_clean(self):
        import tempfile as _tf, os as _os
        root=self.mkroot()
        self.mktask(root,'task_ok',channel='ch',endpoint='w')
        self._dispatch(root,'task_ok','run_o')
        fd,nm=_tf.mkstemp(suffix='.md',dir=str(self.tmp)); _os.close(fd)
        self.addCleanup(lambda: Path(nm).unlink(missing_ok=True))
        Path(nm).write_text('approval',encoding='utf-8')
        class A: pass
        a=A(); a.root=root; a.task_id='task_rec2'; a.predecessor_task='task_ok'; a.context_id='c'; a.title='r'; a.goal='g'; a.worker='w'; a.created_by='chatgpt'
        a.channel_id='ch'; a.lane_id=None; a.worker_endpoint='w'; a.project_id=None
        a.approval_file=nm; a.contract='c'
        with self.assertRaises(RuntimeError) as cm:
            awrp.recover_task(a)
        self.assertIn('validates cleanly',str(cm.exception))
    def test_recover_task_requires_approval(self):
        root=self.mkroot()
        self.mktask(root,'task_pred2',channel='ch',endpoint='w')
        self._dispatch(root,'task_pred2','run_p')
        p=sorted((Path(root)/'tasks'/'task_pred2'/'events').glob('*.json'))[-1]
        o=json.loads(p.read_text(encoding='utf-8')); o['summary']='tampered'; p.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        class A: pass
        a=A(); a.root=root; a.task_id='task_rec3'; a.predecessor_task='task_pred2'; a.context_id='c'; a.title='r'; a.goal='g'; a.worker='w'; a.created_by='chatgpt'
        a.channel_id='ch'; a.lane_id=None; a.worker_endpoint='w'; a.project_id=None
        a.approval_file=None; a.contract='c'
        with self.assertRaises(RuntimeError) as cm:
            awrp.recover_task(a)
        self.assertIn('approval',str(cm.exception))
    def _approval(self,body='human approves'):
        import tempfile as _tf, os as _os
        fd,nm=_tf.mkstemp(suffix='.md',dir=str(self.tmp)); _os.close(fd)
        self.addCleanup(lambda: Path(nm).unlink(missing_ok=True))
        Path(nm).write_text(body,encoding='utf-8')
        return nm
    def _recover(self,root,tid,pred,run_id=None,**kw):
        class A: pass
        a=A(); a.root=root; a.task_id=tid; a.predecessor_task=pred; a.context_id='c'; a.title='r'; a.goal='g'; a.worker='w'; a.created_by='chatgpt'
        a.channel_id='ch'; a.lane_id=None; a.worker_endpoint='w'; a.project_id=None
        a.approval_file=kw.get('approval_file',self._approval()); a.contract=kw.get('contract','c')
        a.run_id=run_id; a.phase=kw.get('phase'); a.run_summary=kw.get('run_summary'); a.expected_head=kw.get('expected_head')
        a.fencing_generation=None; a.idempotency_key=kw.get('idempotency_key'); a.legacy_route=False
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.recover_task(a)
        return json.loads(buf.getvalue())
    def _corrupt(self,root,tid,rid='run_p'):
        self.mktask(root,tid,channel='ch',endpoint='w')
        self._dispatch(root,tid,rid)
        p=sorted((Path(root)/'tasks'/tid/'events').glob('*.json'))[-1]
        o=json.loads(p.read_text(encoding='utf-8')); o['summary']='tampered'; p.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def test_recover_dispatch_successor_linkage(self):
        root=self.mkroot()
        self._corrupt(root,'task_pred')
        out=self._recover(root,'task_rec','task_pred',run_id='run_s1')
        self.assertEqual(out['run_id'],'run_s1')
        self.assertEqual(out['seq'],2)
        td=str(Path(root)/'tasks'/'task_rec')
        v=awrp.validate(td)
        self.assertEqual(v.get('active_run_id'),'run_s1')
        self.assertEqual(v['head']['type'],'DISPATCH')
        self.assertEqual(len(list((Path(td)/'events').glob('*.json'))),2)
        arts=v['head']['artifacts']
        kinds={x['kind'] for x in arts}
        self.assertEqual(kinds,{'recovery_approval','recovery_provenance'})
        appr=[x for x in arts if x['kind']=='recovery_approval'][0]
        raw=(Path(td)/'artifacts'/Path(appr['path']).name).read_bytes()
        import hashlib as _hl
        self.assertEqual(appr['sha256'],'sha256:'+_hl.sha256(raw).hexdigest())
        det=json.loads(v['head']['details'])
        self.assertEqual(det['recovery_of']['task_id'],'task_pred')
        self.assertEqual(det['successor_run'],'run_s1')
    def test_recover_dispatch_duplicate_idempotency(self):
        root=self.mkroot()
        self._corrupt(root,'task_pred')
        self._recover(root,'task_rec','task_pred',run_id='run_s1')
        td=str(Path(root)/'tasks'/'task_rec')
        class A: pass
        a=A(); a.task_dir=td; a.type='DISPATCH'; a.actor_role='coordinator'; a.actor_id='chatgpt'; a.recipient_role='worker'; a.recipient_id='w'; a.run_id='run_s2'; a.new_run=False; a.state='working'; a.phase='x'; a.waiting_on='w'; a.run_state='dispatched'; a.summary='dup'
        a.details_file=None; a.artifacts_file=None; a.approval_file=None
        a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None
        a.idempotency_key='recovery-dispatch-task_pred-seq1-task_rec'; a.require_fresh=False; a.legacy_route=True
        with self.assertRaises(RuntimeError) as cm:
            awrp.emit(a)
        self.assertIn('duplicate command',str(cm.exception))
    def test_recover_dispatch_stale_head(self):
        root=self.mkroot()
        self._corrupt(root,'task_pred')
        with self.assertRaises(RuntimeError) as cm:
            self._recover(root,'task_rec','task_pred',run_id='run_s1',expected_head='evt_bogus')
        self.assertIn('stale',str(cm.exception))
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_post_push_verify_positive(self):
        import subprocess as _sp
        d=Path(tempfile.mkdtemp())
        try:
            _sp.run(['git','-C',str(d),'init','--bare','r.git'],check=True,capture_output=True)
            _sp.run(['git','-C',str(d),'init','-b','main','w'],check=True,capture_output=True)
            _sp.run(['git','-C',str(d/'w'),'config','user.email','t@e'],check=True,capture_output=True)
            _sp.run(['git','-C',str(d/'w'),'config','user.name','t'],check=True,capture_output=True)
            (d/'w'/'contexts').mkdir(exist_ok=True)
            awrp.write_new(d/'w'/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
            class A: pass
            a=A(); a.root=str(d/'w'); a.context_id='c'; a.task_id='task_v'; a.title='t'; a.goal='g'; a.worker='w'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
            a.channel_id=None; a.lane_id=None; a.worker_endpoint=None; a.project_id=None
            a.legacy=True
            awrp.create_task(a)
            _sp.run(['git','-C',str(d/'w'),'add','-A'],check=True,capture_output=True)
            _sp.run(['git','-C',str(d/'w'),'commit','-m','seed'],check=True,capture_output=True)
            _sp.run(['git','-C',str(d/'w'),'remote','add','origin',str(d/'r.git')],check=True,capture_output=True)
            _sp.run(['git','-C',str(d/'w'),'push','-u','origin','main'],check=True,capture_output=True)
            v=awrp.validate(str(d/'w'/'tasks'/'task_v')); h=v['head']
            tip=awrp.post_push_verify(str(d/'w'),'origin','main',str(d/'w'/'tasks'/'task_v'),h['event_id'],h['integrity']['event_hash'])
            self.assertEqual(tip,_sp.run(['git','-C',str(d/'w'),'rev-parse','main'],check=True,capture_output=True,text=True).stdout.strip())
        finally:
            import os, stat
            def ro(action,path,exc):
                try: os.chmod(path,stat.S_IWRITE); action(path)
                except Exception: pass
            shutil.rmtree(d,onerror=ro)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_post_push_verify_detects_divergence(self):
        import subprocess as _sp
        d=Path(tempfile.mkdtemp())
        try:
            _sp.run(['git','-C',str(d),'init','--bare','r.git'],check=True,capture_output=True)
            _sp.run(['git','-C',str(d),'init','-b','main','w'],check=True,capture_output=True)
            _sp.run(['git','-C',str(d/'w'),'config','user.email','t@e'],check=True,capture_output=True)
            _sp.run(['git','-C',str(d/'w'),'config','user.name','t'],check=True,capture_output=True)
            (d/'w'/'contexts').mkdir(exist_ok=True)
            awrp.write_new(d/'w'/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
            class A: pass
            a=A(); a.root=str(d/'w'); a.context_id='c'; a.task_id='task_v'; a.title='t'; a.goal='g'; a.worker='w'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
            a.channel_id=None; a.lane_id=None; a.worker_endpoint=None; a.project_id=None
            a.legacy=True
            awrp.create_task(a)
            _sp.run(['git','-C',str(d/'w'),'add','-A'],check=True,capture_output=True)
            _sp.run(['git','-C',str(d/'w'),'commit','-m','seed'],check=True,capture_output=True)
            _sp.run(['git','-C',str(d/'w'),'remote','add','origin',str(d/'r.git')],check=True,capture_output=True)
            _sp.run(['git','-C',str(d/'w'),'push','-u','origin','main'],check=True,capture_output=True)
            v=awrp.validate(str(d/'w'/'tasks'/'task_v')); h=v['head']
            with self.assertRaises(RuntimeError) as cm:
                awrp.post_push_verify(str(d/'w'),'origin','main',str(d/'w'/'tasks'/'task_v'),h['event_id'],'sha256:'+'0'*64)
            self.assertIn('recomputed',str(cm.exception))
        finally:
            import os, stat
            def ro(action,path,exc):
                try: os.chmod(path,stat.S_IWRITE); action(path)
                except Exception: pass
            shutil.rmtree(d,onerror=ro)
class TCR(unittest.TestCase):
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def mkroot(self):
        (self.tmp/'contexts').mkdir(exist_ok=True)
        awrp.write_new(self.tmp/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        return str(self.tmp)
    def args(self,root,tid,**kw):
        class A: pass
        a=A(); a.root=root; a.context_id='c'; a.task_id=tid; a.title='t'; a.goal='g'; a.worker='w'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=kw.get('channel_id'); a.lane_id=None; a.worker_endpoint=kw.get('worker_endpoint'); a.project_id=kw.get('project_id')
        a.legacy=kw.get('legacy',False)
        return a
    def test_strict_refuses_incomplete(self):
        root=self.mkroot()
        with self.assertRaises(RuntimeError) as cm:
            awrp.create_task(self.args(root,'t1'))
        self.assertIn('--project-id',str(cm.exception))
        with self.assertRaises(RuntimeError) as cm:
            awrp.create_task(self.args(root,'t2',project_id='p'))
        self.assertIn('--channel-id',str(cm.exception))
        self.assertFalse((Path(root)/'tasks'/'t2').exists())
    def test_strict_accepts_complete(self):
        root=self.mkroot()
        awrp.project_create(root,'proj-r','R',('ch-r',),None,'chatgpt')
        class A: pass
        a=self.args(root,'t3',project_id='proj-r',channel_id='ch-r',worker_endpoint='w-r')
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.create_task(a)
        self.assertEqual(buf.getvalue().strip(),'t3')
        self.assertTrue(awrp.task_readiness(json.loads((Path(root)/'tasks'/'t3'/'task.json').read_text(encoding='utf-8')),root)['ok'])
    def test_strict_refuses_ownership_mismatch(self):
        root=self.mkroot()
        awrp.project_create(root,'proj-a','A',('ch-a',),None,'chatgpt')
        awrp.project_create(root,'proj-b','B',('ch-b',),None,'chatgpt')
        with self.assertRaises(RuntimeError) as cm:
            awrp.create_task(self.args(root,'t4',project_id='proj-a',channel_id='ch-b',worker_endpoint='w'))
        self.assertIn('does not own',str(cm.exception))
    def test_legacy_accepts_bare_shape(self):
        root=self.mkroot()
        class A: pass
        a=self.args(root,'t5'); a.legacy=True
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.create_task(a)
        self.assertEqual(buf.getvalue().strip(),'t5')
        r=awrp.task_readiness(json.loads((Path(root)/'tasks'/'t5'/'task.json').read_text(encoding='utf-8')),root)
        self.assertFalse(r['ok'])
        self.assertIn('project_id',r['missing'])
    def test_readiness_reports_transport(self):
        root=self.mkroot()
        awrp.project_create(root,'proj-r','R',('ch-r',),None,'chatgpt')
        t={'protocol':'awrp/0.1','task_id':'x','project_id':'proj-r','routing':{'channel_id':'ch-r','lane_id':None,'worker_endpoint':'w'},'default_worker':'w','authority':{'coordinator':'chatgpt','final_authority':'human'},'side_effect_policy':{'local_read':'allow','local_write':'allow','local_commit':'allow','relay_write':'allow','push_user_fork':'dispatch_only','upstream_comment':'human_approval','upstream_pr_create':'human_approval','merge':'merge'}}
        r=awrp.task_readiness(t,root)
        self.assertFalse(r['ok'])
        self.assertTrue(any('merge' in m for m in r['missing']))
        t['side_effect_policy']['merge']='human_approval'
        r=awrp.task_readiness(t,root)
        self.assertTrue(r['ok'])
        self.assertIn('transport',r)
    def test_readiness_rejects_malformed(self):
        root=self.mkroot()
        t={'protocol':'awrp/0.1','task_id':'x','project_id':'p','routing':{'channel_id':'c','lane_id':None,'worker_endpoint':'w'},'default_worker':'w','authority':{},'side_effect_policy':{}}
        r=awrp.task_readiness(t,root)
        self.assertFalse(r['ok'])
        self.assertTrue(any('authority' in m for m in r['missing']))
        self.assertTrue(any('side_effect_policy' in m for m in r['missing']))
        t2=dict(t,authority={'coordinator':'','final_authority':'human'})
        r=awrp.task_readiness(t2,root)
        self.assertFalse(r['ok'])
class TAX(unittest.TestCase):
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def mkroot(self):
        (self.tmp/'contexts').mkdir(exist_ok=True)
        awrp.write_new(self.tmp/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        return str(self.tmp)
    def mktask(self,root,tid,channel='ch',endpoint='w'):
        class A: pass
        a=A(); a.root=root; a.context_id='c'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='w'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=channel; a.lane_id=None; a.worker_endpoint=endpoint; a.project_id=None
        a.legacy=True
        awrp.create_task(a); return str(Path(root)/'tasks'/tid)
    def _ns(self,**kw):
        class A: pass
        a=A()
        defaults={'task_dir':None,'type':'DISPATCH','actor_role':'coordinator','actor_id':'chatgpt','recipient_role':'worker','recipient_id':'w','run_id':None,'new_run':False,'state':'working','phase':'x','waiting_on':'w','run_state':None,'summary':'s','details_file':None,'artifacts_file':None,'approval_file':None,'causation_id':None,'expected_head':None,'expected_hash':None,'claimant':None,'fencing_generation':None,'idempotency_key':None,'require_fresh':False,'legacy_route':True}
        defaults.update(kw)
        for k,v in defaults.items(): setattr(a,k,v)
        return a
    def _dispatch(self,td,rid,**kw):
        a=self._ns(task_dir=td,type='DISPATCH',actor_role='coordinator',actor_id='chatgpt',recipient_role='worker',recipient_id=kw.get('recipient_id','w'),run_id=rid,state='working',phase='x',waiting_on=kw.get('waiting_on','w'),run_state='dispatched',summary='go')
        awrp.emit(a)
    def test_sibling_predecessor_second_refused(self):
        root=self.mkroot(); td=self.mktask(root,'task_s1')
        h1=awrp.validate(td)['head']
        self._dispatch(td,'run_a')
        v=awrp.validate(td)
        self.assertEqual(len(v['events']),2)
        sib=self._ns(task_dir=td,type='DISPATCH',actor_role='coordinator',actor_id='chatgpt',recipient_role='worker',recipient_id='w',run_id='run_b',state='working',phase='x',waiting_on='w',run_state='dispatched',summary='sibling',expected_head=h1['event_id'])
        with self.assertRaises(RuntimeError) as cm:
            awrp._prepare_event(Path(td),sib)
        self.assertIn('stale',str(cm.exception))
        self.assertEqual(len(awrp.validate(td)['events']),2)
    def _git_remote(self,root):
        import subprocess as _sp, tempfile as _tf2
        rd=_tf2.mkdtemp()
        self.addCleanup(lambda: __import__('shutil').rmtree(rd,ignore_errors=True))
        _sp.run(['git','init','--bare',rd],check=True,capture_output=True)
        return rd
    def test_preflight_run_authority(self):
        import subprocess as _sp
        root=self.mkroot(); td=self.mktask(root,'task_p1')
        self._dispatch(td,'run_1')
        _sp.run(['git','-C',root,'init','-b','main'],check=True,capture_output=True)
        _sp.run(['git','-C',root,'config','user.email','t@e'],check=True,capture_output=True)
        _sp.run(['git','-C',root,'config','user.name','t'],check=True,capture_output=True)
        _sp.run(['git','-C',root,'add','-A'],check=True,capture_output=True)
        _sp.run(['git','-C',root,'commit','-m','seed'],check=True,capture_output=True)
        _sp.run(['git','-C',root,'remote','add','origin',self._git_remote(root)],check=True,capture_output=True)
        _sp.run(['git','-C',root,'push','-u','origin','main'],check=True,capture_output=True)
        a=self._ns(task_dir=td,repo=root,remote='origin',branch='main',run_id='run_1')
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_preflight(a)
        r=json.loads(buf.getvalue())
        self.assertTrue(r['ok'])
        self.assertEqual(r['run_authority'],{'run_id':'run_1','active_run_id':'run_1'})
        b=self._ns(task_dir=td,repo=root,remote='origin',branch='main',run_id='run_ghost')
        with self.assertRaises(RuntimeError):
            awrp.do_preflight(b)
        self.emit_cancel(td)
        with self.assertRaises(RuntimeError) as cm:
            awrp.do_preflight(a)
        self.assertTrue('not transportable' in str(cm.exception) or 'no transport authority' in str(cm.exception))
    def emit_cancel(self,td):
        a=self._ns(task_dir=td,type='CANCEL',actor_role='coordinator',actor_id='chatgpt',recipient_role=None,recipient_id=None,run_id=None,state='canceled',phase='x',waiting_on='null',run_state=None)
        awrp.emit(a)
    def test_preflight_no_run_unchanged(self):
        import subprocess as _sp
        root=self.mkroot(); td=self.mktask(root,'task_p2')
        self._dispatch(td,'run_1')
        _sp.run(['git','-C',root,'init','-b','main'],check=True,capture_output=True)
        _sp.run(['git','-C',root,'config','user.email','t@e'],check=True,capture_output=True)
        _sp.run(['git','-C',root,'config','user.name','t'],check=True,capture_output=True)
        _sp.run(['git','-C',root,'add','-A'],check=True,capture_output=True)
        _sp.run(['git','-C',root,'commit','-m','seed'],check=True,capture_output=True)
        _sp.run(['git','-C',root,'remote','add','origin',self._git_remote(root)],check=True,capture_output=True)
        _sp.run(['git','-C',root,'push','-u','origin','main'],check=True,capture_output=True)
        a=self._ns(task_dir=td,repo=root,remote='origin',branch='main')
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_preflight(a)
        r=json.loads(buf.getvalue())
        self.assertTrue(r['ok'])
        self.assertIsNone(r['run_authority'])
    def test_doctor_healthy(self):
        root=self.mkroot(); td=self.mktask(root,'task_d1')
        self._dispatch(td,'run_1')
        a=self._ns(task_dir=td,repo=root,remote='origin',branch=None)
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_doctor(a)
        r=json.loads(buf.getvalue())
        for k in ('chain','readiness','integrity','identity','freshness'):
            self.assertIn(k,r['checks'])
        self.assertTrue(r['checks']['chain']['ok'])
        self.assertTrue(r['checks']['integrity']['ok'])
        self.assertEqual(r['checks']['identity']['status'],'consistent')
    def test_doctor_corrupt(self):
        root=self.mkroot(); td=self.mktask(root,'task_d2')
        self._dispatch(td,'run_1')
        n_before=len(list(Path(root).rglob('*')))
        p=sorted((Path(td)/'events').glob('*.json'))[-1]
        o=json.loads(p.read_text(encoding='utf-8')); o['summary']='tampered'; p.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        a=self._ns(task_dir=td,repo=root,remote='origin',branch=None)
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_doctor(a)
        r=json.loads(buf.getvalue())
        self.assertFalse(r['ok'])
        self.assertFalse(r['checks']['chain']['ok'])
        self.assertFalse(r['checks']['integrity']['ok'])
        self.assertEqual(n_before,len(list(Path(root).rglob('*'))))
    def test_capability_matrix(self):
        self.assertTrue(len(awrp.PUBLIC_MUTATION_ACTIONS)>0)
        self.assertTrue(len(awrp.PUBLIC_MUTATION_PARAMS)>0)
        self.assertFalse(set(awrp.INTENT_ACTIONS)&set(awrp.PUBLIC_MUTATION_ACTIONS))
        self.assertEqual(set(awrp_transport.PUBLIC_MUTATION_ACTIONS),set(awrp.PUBLIC_MUTATION_ACTIONS))
        self.assertTrue(awrp._is_transport_only_path('bridge/requests/r-1.json'))
        self.assertFalse(awrp._is_transport_only_path('bridge/requests/r-1.result.json'))
        self.assertFalse(awrp._is_transport_only_path('tasks/t/events/000001_x.json'))
        self.assertFalse(awrp._is_transport_only_path('issues/1.json'))
class TBF(unittest.TestCase):
    CH='ch-bf'; EP='ep-bf'
    def setUp(self):
        import sys as _sys
        self.tmp=Path(tempfile.mkdtemp())
        self.py=_sys.executable
        self.server=Path(__file__).resolve().parents[1]/'tools'/'awrp_mcp_transport.py'
        self.proc=None
    def tearDown(self):
        import os, stat
        if self.proc is not None:
            try: self.proc.kill()
            except Exception: pass
            try: self.proc.wait(timeout=10)
            except Exception: pass
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def git(self,repo,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def mkrelay(self):
        remote=self.tmp/'r.git'; w=self.tmp/'w'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(self.tmp,'init','-b','main',str(w))
        self.git(w,'config','user.email','t@e'); self.git(w,'config','user.name','t')
        (w/'contexts').mkdir(exist_ok=True)
        awrp.write_new(w/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        awrp.project_create(str(w),'proj-b','B',(self.CH,),None,'chatgpt')
        awrp.acquire_claim(str(w),self.CH,'coord-B')
        (w/'relay.json').write_text(json.dumps({'protocol':'awrp/0.1','relay':'Bruce-Yii/awrp'}),encoding='utf-8')
        self.git(w,'add','-A'); self.git(w,'commit','-m','seed'); self.git(w,'remote','add','origin',str(remote))
        self.git(w,'push','-u','origin','main'); self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
        return remote,w
    def mkdispatch_task(self,w,tid):
        class A: pass
        a=A(); a.root=str(w); a.context_id='c'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='w'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=self.CH; a.lane_id=None; a.worker_endpoint=self.EP; a.project_id='proj-b'; a.legacy=False
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.create_task(a)
        self.git(w,'add','-A'); self.git(w,'commit','-m',f'seed {tid}'); self.git(w,'push','origin','main')
    def start(self):
        self.proc=subprocess.Popen([self.py,str(self.server),'--base-dir',str(self.tmp/'w')],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
        return self.proc
    def rpc(self,method,params=None,req_id=1):
        self.proc.stdin.write(json.dumps({'jsonrpc':'2.0','id':req_id,'method':method,**({'params':params} if params is not None else {})})+'\n')
        self.proc.stdin.flush()
        line=self.proc.stdout.readline()
        self.assertTrue(line,'server produced no output')
        return json.loads(line)
    def req(self,rid,action='dispatch',params=None):
        base=self.git(self.tmp/'w','rev-parse','main') if (self.tmp/'w').exists() else '0'*40
        return {"action_class":"transport_write","repository":"Bruce-Yii/awrp","path":f"bridge/requests/{rid}.json",
            "contents":{"protocol":"awrp/0.1","request_id":rid,"action":action,"idempotency_key":f"k-{rid}","expected_base":base,
                "params":params or {"task_id":"task_e2e","run_id":"run_e2e","recipient_role":"worker","recipient_id":self.EP,"state":"working","phase":"x","waiting_on":self.EP,"run_state":"dispatched","summary":"go"}}}
    def bridge(self,rid):
        class A: pass
        a=A(); a.root=str(self.tmp/'w'); a.request=rid; a.repo=str(self.tmp/'w'); a.branch='main'; a.remote='origin'
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_bridge_process(a)
        return json.loads(buf.getvalue())
    def preflight(self,rid):
        class A: pass
        a=A(); a.root=str(self.tmp/'w'); a.request=rid; a.repo=str(self.tmp/'w'); a.branch='main'; a.remote='origin'
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_bridge_preflight(a)
        return json.loads(buf.getvalue())
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_facade_to_bridge_dispatch_e2e(self):
        remote,w=self.mkrelay()
        self.mkdispatch_task(w,'task_e2e')
        self.start()
        self.rpc('initialize',{},req_id=1)
        r=self.rpc('tools/call',{'name':'awrp_transport_write','arguments':self.req('r-e2e')},req_id=2)
        self.assertIn('result',r)
        body=json.loads(r['result']['content'][0]['text'])
        self.assertEqual(body['status'],'delegated')
        self.assertTrue((w/'bridge'/'requests'/'r-e2e.json').exists())
        pf=self.preflight('r-e2e')
        self.assertEqual(pf['status'],'plannable')
        b=self.bridge('r-e2e')
        self.assertEqual(b['status'],'published')
        v=awrp.validate(str(w/'tasks'/'task_e2e'))
        self.assertEqual(v['head']['run_id'],'run_e2e')
        res=json.loads((w/'bridge'/'requests'/'r-e2e.result.json').read_text(encoding='utf-8'))
        self.assertEqual(res['status'],'published')
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_facade_create_issue_drift_zero_side_effects(self):
        remote,w=self.mkrelay()
        self.mkdispatch_task(w,'task_e2e')
        before=self.git(w,'rev-parse','main')
        self.start()
        self.rpc('initialize',{},req_id=1)
        bad=self.req('r-evil'); bad['action_class']='create_issue'
        r=self.rpc('tools/call',{'name':'awrp_transport_write','arguments':bad},req_id=2)
        self.assertIn('error',r)
        self.assertEqual(self.git(w,'rev-parse','main'),before)
        self.assertFalse((w/'bridge'/'requests'/'r-evil.json').exists())
        self.assertEqual(len(list((w/'tasks'/'task_e2e'/'events').glob('*.json'))),1)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_facade_repo_drift_zero_side_effects(self):
        remote,w=self.mkrelay()
        self.mkdispatch_task(w,'task_e2e')
        before=self.git(w,'rev-parse','main')
        self.start()
        self.rpc('initialize',{},req_id=1)
        bad=self.req('r-rogue'); bad['repository']='example/unrelated-repository'
        r=self.rpc('tools/call',{'name':'awrp_transport_write','arguments':bad},req_id=2)
        self.assertIn('error',r)
        self.assertEqual(self.git(w,'rev-parse','main'),before)
        self.assertFalse((w/'bridge'/'requests'/'r-rogue.json').exists())
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_facade_unknown_tool_zero_side_effects(self):
        remote,w=self.mkrelay()
        self.mkdispatch_task(w,'task_e2e')
        before=self.git(w,'rev-parse','main')
        self.start()
        self.rpc('initialize',{},req_id=1)
        r=self.rpc('tools/call',{'name':'github_create_issue','arguments':self.req('r-x')},req_id=2)
        self.assertIn('error',r)
        self.assertEqual(self.git(w,'rev-parse','main'),before)
class TUJ(unittest.TestCase):
    CH='ch-uj'; EP='ep-uj'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def git(self,repo,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def mkrelay(self):
        remote=self.tmp/'r.git'; w=self.tmp/'w'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(self.tmp,'init','-b','main',str(w))
        self.git(w,'config','user.email','t@e'); self.git(w,'config','user.name','t')
        (w/'contexts').mkdir(exist_ok=True)
        awrp.write_new(w/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        awrp.project_create(str(w),'proj-u','U',(self.CH,),None,'chatgpt')
        self.git(w,'add','-A'); self.git(w,'commit','-m','seed'); self.git(w,'remote','add','origin',str(remote))
        self.git(w,'push','-u','origin','main'); self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
        return remote,w
    def mktask(self,w,tid):
        class A: pass
        a=A(); a.root=str(w); a.context_id='c'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='w'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=self.CH; a.lane_id=None; a.worker_endpoint=self.EP; a.project_id='proj-u'; a.legacy=False
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.create_task(a)
        return w/'tasks'/tid
    def out(self,fn,args):
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): fn(args)
        return json.loads(buf.getvalue())
    def ns(self,**kw):
        class A: pass
        a=A()
        for k,v in kw.items(): setattr(a,k,v)
        return a
    def emit(self,td,typ,rid,**kw):
        a=self.ns(task_dir=str(td),type=typ,run_id=rid,new_run=False,summary=kw.get('summary','s'),
            actor_role=kw.get('actor_role','coordinator'),actor_id=kw.get('actor_id','chatgpt'),
            recipient_role=kw.get('recipient_role','worker'),recipient_id=kw.get('recipient_id',self.EP),
            state=kw.get('state','working'),phase=kw.get('phase','x'),waiting_on=kw.get('waiting_on',self.EP),
            run_state=kw.get('run_state'),details_file=None,artifacts_file=None,approval_file=None,
            causation_id=None,expected_head=None,expected_hash=None,claimant=None,fencing_generation=None,
            idempotency_key=None,require_fresh=False,legacy_route=True)
        awrp.emit(a)
    def bind(self,ws,w):
        ws.mkdir(exist_ok=True)
        return self.out(awrp.do_bind,self.ns(root=str(ws),relay='r',relay_dir=str(w),channel=self.CH,worker_endpoint=self.EP,lane=None,project_id='proj-u',bound_by='t',force=False))
    def test_enable_project_and_first_bind(self):
        remote,w=self.mkrelay()
        td=self.mktask(w,'task_j1')
        self.git(w,'add','-A'); self.git(w,'commit','-m',f'seed task_j1'); self.git(w,'push','origin','main')
        dg=self.out(awrp.do_dispatch_guarded,self.ns(binding_root=None,no_binding=True,project_id='proj-u',channel=self.CH,worker_endpoint=self.EP,lane=None,task_id='task_j1',branch='main',remote='origin',repo=str(w),publish=False,commit_message=None,expected_plan=None,run_id='run_1',new_run=False,actor_role='coordinator',actor_id='chatgpt',recipient_role='worker',recipient_id=self.EP,state='working',phase='x',waiting_on=self.EP,run_state='dispatched',summary='go',details_file=None,artifacts_file=None,approval_file=None,causation_id=None,expected_head=None,expected_hash=None,claimant=None,fencing_generation=None,idempotency_key=None))
        self.assertIn('plan_fingerprint',dg)
        ws=self.tmp/'ws'
        self.bind(ws,w)
        fb=self.out(awrp.do_first_bind,self.ns(root=str(ws),relay='r',relay_dir=str(w),project_id='proj-u',channel=self.CH,worker_endpoint=self.EP,task_id='task_j1',run_id=None,lane=None,bound_by='t'))
        self.assertEqual(fb['status'],'EXECUTE')
        self.assertEqual(fb['run_id'],'run_1')
    def test_bound_continue_needs_no_ids(self):
        remote,w=self.mkrelay()
        td=self.mktask(w,'task_j2')
        self.emit(td,'DISPATCH','run_1',run_state='dispatched')
        self.git(w,'add','-A'); self.git(w,'commit','-m','x'); self.git(w,'push','origin','main')
        ws=self.tmp/'ws'
        self.bind(ws,w)
        r=self.out(awrp.do_resume,self.ns(root=str(ws),channel=None,worker_endpoint=None,lane=None))
        self.assertEqual((r['status'],r['run_id']),('EXECUTE','run_1'))
        self.emit(td,'ACK','run_1',actor_role='worker',actor_id=self.EP,recipient_role='coordinator',recipient_id='chatgpt',run_state='working')
        r=self.out(awrp.do_resume,self.ns(root=str(ws),channel=None,worker_endpoint=None,lane=None))
        self.assertEqual(r['status'],'OWNED')
    def test_two_tasks_independent(self):
        remote,w=self.mkrelay()
        ta=self.mktask(w,'task_ja'); tb=self.mktask(w,'task_jb')
        self.emit(ta,'DISPATCH','run_a',run_state='dispatched')
        self.emit(tb,'DISPATCH','run_b',run_state='dispatched')
        self.emit(ta,'ACK','run_a',actor_role='worker',actor_id=self.EP,recipient_role='coordinator',recipient_id='chatgpt',run_state='working')
        self.emit(ta,'HANDOFF','run_a',actor_role='worker',actor_id=self.EP,recipient_role='coordinator',recipient_id='chatgpt',phase='review',waiting_on='chatgpt',run_state='succeeded')
        s=awrp.select_for_resume(str(w),self.CH,self.EP,None,None)
        self.assertEqual(s['status'],'EXECUTE')
        self.assertEqual(s['task_id'],'task_jb')
    def test_session_switches_projects(self):
        remote,w=self.mkrelay()
        awrp.project_create(str(w),'proj-v','V',('ch-v',),None,'chatgpt')
        ta=self.mktask(w,'task_ju')
        ws=self.tmp/'ws'; ws.mkdir(exist_ok=True)
        self.out(awrp.do_attach,self.ns(root=str(ws),relay_dir=str(w),project_id='proj-u',by='t'))
        self.out(awrp.do_attach,self.ns(root=str(ws),relay_dir=str(w),project_id='proj-v',by='t'))
        self.out(awrp.do_switch,self.ns(root=str(ws),relay_dir=str(w),project_id='proj-u',task_id=None,run_id=None))
        f=self.out(awrp.do_focus,self.ns(root=str(ws),relay_dir=str(w)))
        self.assertEqual(f['current']['project_id'],'proj-u')
        self.out(awrp.do_switch,self.ns(root=str(ws),relay_dir=str(w),project_id='proj-v',task_id=None,run_id=None))
        f=self.out(awrp.do_focus,self.ns(root=str(ws),relay_dir=str(w)))
        self.assertEqual(f['current']['project_id'],'proj-v')
    def test_wrong_window_lineage_verified(self):
        remote,w=self.mkrelay()
        td=self.mktask(w,'task_jw')
        self.emit(td,'DISPATCH','run_1',run_state='dispatched')
        ws=self.tmp/'ws'; ws.mkdir(exist_ok=True)
        self.out(awrp.do_attach,self.ns(root=str(ws),relay_dir=str(w),project_id='proj-u',by='t'))
        before=(ws/'.awrp'/'session.json').read_bytes() if (ws/'.awrp'/'session.json').exists() else None
        r=self.out(awrp.do_check_lineage,self.ns(root=str(ws),relay_dir=str(w),project_id='proj-nope',task_id='task_jw',run_id='run_1'))
        self.assertFalse(r.get('match',True))
        after=(ws/'.awrp'/'session.json').read_bytes() if (ws/'.awrp'/'session.json').exists() else None
        self.assertEqual(before,after)
    def test_takeover_revokes_stale_run(self):
        remote,w=self.mkrelay()
        td=self.mktask(w,'task_jt')
        self.emit(td,'DISPATCH','run_old',run_state='dispatched')
        self.emit(td,'ACK','run_old',actor_role='worker',actor_id=self.EP,recipient_role='coordinator',recipient_id='chatgpt',run_state='working')
        self.emit(td,'CANCEL',None,actor_role='coordinator',actor_id='chatgpt',state='working',phase='x',waiting_on=self.EP)
        self.emit(td,'DISPATCH','run_new',run_state='dispatched')
        h=awrp.validate(str(td))['head']
        with self.assertRaises(RuntimeError):
            awrp.do_preflight(self.ns(task_dir=str(td),repo=str(w),branch='main',remote='origin',expected_base=None,expected_head=h['event_id'],expected_hash=h['integrity']['event_hash'],run_id='run_old'))
    def test_interruption_then_safe_recovery(self):
        remote,w=self.mkrelay()
        td=self.mktask(w,'task_jr')
        self.emit(td,'DISPATCH','run_1',run_state='dispatched')
        self.emit(td,'ACK','run_1',actor_role='worker',actor_id=self.EP,recipient_role='coordinator',recipient_id='chatgpt',run_state='working')
        n_before=len(list((td/'events').glob('*.json')))
        ws=self.tmp/'ws'
        self.bind(ws,w)
        r=self.out(awrp.do_resume,self.ns(root=str(ws),channel=None,worker_endpoint=None,lane=None))
        self.assertEqual(r['status'],'OWNED')
        self.assertEqual(len(list((td/'events').glob('*.json'))),n_before)
        self.emit(td,'HANDOFF','run_1',actor_role='worker',actor_id=self.EP,recipient_role='coordinator',recipient_id='chatgpt',phase='review',waiting_on='chatgpt',run_state='succeeded')
        self.assertIsNone(awrp.validate(str(td)).get('active_run_id'))
    def test_human_names_resolve_to_ids(self):
        remote,w=self.mkrelay()
        awrp.project_create(str(w),'proj-n','Nice Name',('ch-n',),None,'chatgpt',('nick',))
        r=self.out(awrp.do_resolve_project,self.ns(root=str(w),project_id=None,alias='nick',title=None))
        self.assertEqual(r['status'],'RESOLVED')
        self.assertEqual(r['project']['project_id'],'proj-n')
class TQS(unittest.TestCase):
    def setUp(self):
        import sys as _sys
        self.tmp=Path(tempfile.mkdtemp())
        self.py=_sys.executable
        self.cli_path=str(Path(__file__).resolve().parents[1]/'tools'/'awrp.py')
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def cli(self,*args):
        cp=subprocess.run([self.py,self.cli_path,*args],capture_output=True,text=True,cwd=str(self.tmp))
        self.assertEqual(cp.returncode,0,cp.stderr)
        return cp.stdout.strip()
    def test_readme_quick_start_executes(self):
        import io
        self.cli('init-context','--root','.', '--context-id','ctx_alpha','--title','Example Project')
        self.cli('project-create','--root','.', '--project-id','project_alpha','--title','Example Project','--channel','channel_alpha_contrib')
        tid=self.cli('create-task','--root','.', '--context-id','ctx_alpha','--project-id','project_alpha','--channel-id','channel_alpha_contrib','--worker-endpoint','codex_alpha','--title','Fix example issue','--goal','Reproduce and fix.','--worker','codex_alpha')
        out=self.cli('dispatch-guarded','--no-binding','--project-id','project_alpha','--channel','channel_alpha_contrib','--worker-endpoint','codex_alpha','--repo','.', '--task-id',tid,'--run-id','run_01','--actor-role','coordinator','--actor-id','chatgpt','--recipient-role','worker','--recipient-id','codex_alpha','--state','working','--phase','implementation','--waiting-on','codex_alpha','--run-state','dispatched','--summary','Implement the approved execution pack.')
        self.assertIn('plan_fingerprint',json.loads(out))
        self.cli('emit','--task-dir',f'tasks/{tid}','--type','ACK','--actor-role','worker','--actor-id','codex_alpha','--recipient-role','coordinator','--recipient-id','chatgpt','--run-id','run_01','--state','working','--phase','implementation','--waiting-on','codex_alpha','--run-state','working','--summary','Accepted.')
        self.cli('emit','--task-dir',f'tasks/{tid}','--type','HANDOFF','--actor-role','worker','--actor-id','codex_alpha','--recipient-role','coordinator','--recipient-id','chatgpt','--run-id','run_01','--state','working','--phase','review','--waiting-on','chatgpt','--run-state','succeeded','--summary','Done.')
        v=json.loads(self.cli('validate','--task-dir',f'tasks/{tid}'))
        self.assertTrue(v['ok'])
        r=json.loads(self.cli('replay','--task-dir',f'tasks/{tid}'))
        self.assertIsNone(r['active_run_id'])
        self.assertEqual(r['runs']['run_01']['state'],'succeeded')
        self.assertEqual(r['runs']['run_01']['executor'],'codex_alpha')
    def test_readme_matches_supported_commands(self):
        doc=(Path(__file__).resolve().parents[1]/'README.md').read_text(encoding='utf-8')
        for needle in ('--project-id project_alpha','--channel-id channel_alpha_contrib','--worker-endpoint codex_alpha','dispatch-guarded','--no-binding','--legacy'):
            self.assertIn(needle,doc)
class TN(unittest.TestCase):
    CH='ch-tn'; EP='ep-tn'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def mkctx(self,root,ctx='c'):
        (Path(root)/'contexts').mkdir(exist_ok=True)
        awrp.write_new(Path(root)/'contexts'/f'{ctx}.json',{'protocol':'awrp/0.1','context_id':ctx,'title':'t','created_at':awrp.now(),'description':''})
    def mktask(self,root,tid):
        class A: pass
        a=A(); a.root=str(root); a.context_id='c'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=self.CH; a.lane_id=None; a.worker_endpoint=self.EP; a.project_id=None
        a.legacy=True
        awrp.create_task(a); return str(Path(root)/'tasks'/tid)
    def emit(self,td,typ,rid,**kw):
        import os
        class A: pass
        a=A(); a.task_dir=td; a.type=typ; a.run_id=rid; a.new_run=False; a.summary='s'
        a.actor_role=kw.get('actor_role','coordinator'); a.actor_id=kw.get('actor_id','chatgpt')
        a.recipient_role=kw.get('recipient_role','worker'); a.recipient_id=kw.get('recipient_id',self.EP)
        a.state=kw.get('state','working'); a.phase=kw.get('phase','x'); a.waiting_on=kw.get('waiting_on',self.EP)
        a.run_state=kw.get('run_state'); a.details_file=None; a.artifacts_file=None; a.approval_file=None
        a.causation_id=None; a.expected_head=kw.get('expected_head'); a.expected_hash=None; a.claimant=None
        a.fencing_generation=None; a.idempotency_key=None; a.require_fresh=False; a.legacy_route=True
        awrp.emit(a)
    def test_execute_auto_ack_golden_path_no_human_turn(self):
        self.mkctx(self.tmp)
        td=self.mktask(self.tmp,'task_g')
        self.emit(td,'DISPATCH','run_g',run_state='dispatched')
        r=awrp.select_for_resume(str(self.tmp),self.CH,self.EP,None,None)
        self.assertEqual(r['status'],'EXECUTE')
        self.emit(td,'ACK','run_g',actor_role='worker',actor_id='ep-tn',recipient_role='coordinator',recipient_id='chatgpt',run_state='working',expected_head=r['head_event_id'])
        self.emit(td,'HANDOFF','run_g',actor_role='worker',actor_id='ep-tn',recipient_role='coordinator',recipient_id='chatgpt',phase='review',waiting_on='chatgpt',run_state='succeeded')
        v=awrp.validate(td)
        kinds=[e['type'] for e in v['events']]
        self.assertEqual(kinds,['TASK_CREATED','DISPATCH','ACK','HANDOFF'])
        self.assertNotIn('INPUT_REQUEST',kinds)
        self.assertEqual((v['head']['task_projection']['state'],v['head']['task_projection']['waiting_on']),('working','chatgpt'))
        self.assertEqual(v['runs']['run_g']['state'],'succeeded')
    def test_stale_head_emit_refuses_without_trace(self):
        self.mkctx(self.tmp)
        td=self.mktask(self.tmp,'task_s')
        self.emit(td,'DISPATCH','run_1',run_state='dispatched')
        before=sorted(p.name for p in (Path(td)/'events').glob('*.json'))
        with self.assertRaises(RuntimeError):
            self.emit(td,'ACK','run_1',actor_role='worker',actor_id='ep-tn',recipient_role='coordinator',recipient_id='chatgpt',run_state='working',expected_head='evt_bogus_head')
        self.assertEqual(sorted(p.name for p in (Path(td)/'events').glob('*.json')),before)
    def test_execute_means_act_wording_pinned(self):
        root=Path(__file__).resolve().parents[1]
        contract=(root/'protocol'/'WORKER-CONTRACT.md').read_text(encoding='utf-8')
        self.assertIn('### EXECUTE means act (no redundant human confirmation)',contract)
        self.assertIn('MUST immediately emit `ACK`',contract)
        self.assertIn('MUST NOT ask the',contract)
        self.assertIn('to confirm the ACK',contract)
        adapter=(root/'templates'/'AGENTS_AWRP.md').read_text(encoding='utf-8')
        self.assertIn('never ask the human to confirm the ACK',adapter)
        snippet=(root/'templates'/'AGENT_INSTRUCTIONS_SNIPPET.md').read_text(encoding='utf-8')
        self.assertIn('never ask the human to confirm the ACK',snippet)
        bootstrap=(root/'AWRP-BOOTSTRAP.md').read_text(encoding='utf-8')
        self.assertIn('never ask the human to confirm the ACK',bootstrap)
class TFencingPositiveProof(unittest.TestCase):
    CH='ch-fp'; EP='ep-fp'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def mkctx(self,root,ctx='c'):
        (Path(root)/'contexts').mkdir(exist_ok=True)
        awrp.write_new(Path(root)/'contexts'/f'{ctx}.json',{'protocol':'awrp/0.1','context_id':ctx,'title':'t','created_at':awrp.now(),'description':''})
    def mkproj(self,root,pid,channels=()):
        return awrp.project_create(str(root),pid,'T-'+pid,channels,None,'chatgpt')
    def mktask(self,root,tid,channel=CH,endpoint=EP,project=None):
        class A: pass
        a=A(); a.root=str(root); a.context_id='c'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=channel; a.lane_id=None; a.worker_endpoint=endpoint; a.project_id=project
        a.legacy=True
        awrp.create_task(a); return str(Path(root)/'tasks'/tid)
    def emit(self,td,typ,rid,actor_role='coordinator',actor_id='chatgpt',recipient_role='worker',recipient_id=None,state='working',phase='x',waiting_on=None,run_state=None,fg=None):
        class A: pass
        a=A(); a.task_dir=td; a.type=typ; a.actor_role=actor_role; a.actor_id=actor_id; a.recipient_role=recipient_role; a.recipient_id=recipient_id or self.EP; a.run_id=rid; a.new_run=False; a.state=state; a.phase=phase; a.waiting_on=waiting_on if waiting_on is not None else self.EP; a.run_state=run_state; a.summary='s'
        a.details_file=None; a.artifacts_file=None; a.approval_file=None
        a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=fg; a.idempotency_key=None; a.require_fresh=False; a.legacy_route=True
        awrp.emit(a)
    def write_claim_only(self,root,channel,owner='chatgpt',gen=1):
        obj={'protocol':'awrp/0.1','channel_id':channel,'generation':gen,'owner':owner,'updated_at':awrp.now(),'prev_owner':None,'takeover':False,'note':'hand-planted claim-only fixture'}
        p=Path(root)/'channels'/channel/'claim.json'; p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        return obj
    def events(self,td): return sorted(p.name for p in (Path(td)/'events').glob('*.json'))
    def out(self,fn,args):
        import io, contextlib
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): fn(args)
        return json.loads(buf.getvalue())
    def test_strict_claim_only_blocks_fenced_dispatch_without_trace(self):
        self.mkctx(self.tmp); self.mkproj(self.tmp,'proj-fp',(self.CH,))
        td=self.mktask(self.tmp,'task_o',project='proj-fp')
        self.write_claim_only(self.tmp,self.CH)
        before=self.events(td)
        with self.assertRaises(RuntimeError) as cm:
            self.emit(td,'DISPATCH','run_o',run_state='dispatched',fg=1)
        self.assertIn('inconsistent',str(cm.exception))
        self.assertEqual(self.events(td),before)
        auth=awrp.fencing_authority(str(self.tmp),self.CH)
        self.assertEqual((auth['status'],auth['strict'],auth['generation'],auth['owner']),('inconsistent',True,1,'chatgpt'))
    def test_strict_claim_only_ack_refuses_fenced_run(self):
        self.mkctx(self.tmp); self.mkproj(self.tmp,'proj-fp',(self.CH,))
        td=self.mktask(self.tmp,'task_a',project='proj-fp')
        awrp.acquire_claim(str(self.tmp),self.CH,'chatgpt')
        self.emit(td,'DISPATCH','run_a',run_state='dispatched',fg=1)
        (Path(self.tmp)/'channels'/self.CH/'claim.log.jsonl').unlink()
        auth=awrp.fencing_authority(str(self.tmp),self.CH)
        self.assertEqual(auth['status'],'inconsistent')
        before=self.events(td)
        with self.assertRaises(RuntimeError) as cm:
            self.emit(td,'ACK','run_a',actor_role='worker',actor_id=self.EP,recipient_role='coordinator',recipient_id='chatgpt',run_state='working')
        self.assertIn('claim-log',str(cm.exception))
        self.assertEqual(self.events(td),before)
    def test_legacy_claim_authorizes_no_new_fenced_mutation(self):
        self.mkctx(self.tmp)
        td=self.mktask(self.tmp,'task_l')
        self.write_claim_only(self.tmp,self.CH)
        auth=awrp.fencing_authority(str(self.tmp),self.CH)
        self.assertEqual((auth['status'],auth['strict']),('legacy-claim',False))
        before=self.events(td)
        with self.assertRaises(RuntimeError) as cm:
            self.emit(td,'DISPATCH','run_l',run_state='dispatched',fg=1)
        self.assertIn('migrate-claim',str(cm.exception))
        self.assertEqual(self.events(td),before)
        awrp.migrate_claim(str(self.tmp),self.CH)
        self.emit(td,'DISPATCH','run_l',run_state='dispatched',fg=1)
        v=awrp.validate(td)
        d=[x for x in v['events'] if x['type']=='DISPATCH'][0]
        self.assertEqual(d.get('fencing'),{'channel_id':self.CH,'generation':1,'owner':'chatgpt'})
        self.emit(td,'ACK','run_l',actor_role='worker',actor_id=self.EP,recipient_role='coordinator',recipient_id='chatgpt',run_state='working')
        self.assertEqual(awrp.validate(td)['active_run_id'],'run_l')
    def test_no_channel_class_publishes_unseatable_fenced_dispatch(self):
        self.mkctx(self.tmp)
        self.mkproj(self.tmp,'proj-fp',(self.CH,))
        strict_td=self.mktask(self.tmp,'task_s',project='proj-fp')
        self.write_claim_only(self.tmp,self.CH)
        with self.assertRaises(RuntimeError):
            self.emit(strict_td,'DISPATCH','run_s',run_state='dispatched',fg=1)
        awrp.migrate_claim(str(self.tmp),self.CH)
        self.emit(strict_td,'DISPATCH','run_s',run_state='dispatched',fg=1)
        self.emit(strict_td,'ACK','run_s',actor_role='worker',actor_id=self.EP,recipient_role='coordinator',recipient_id='chatgpt',run_state='working')
        self.assertEqual(awrp.validate(strict_td)['active_run_id'],'run_s')
        (Path(self.tmp)/'channels'/self.CH/'claim.log.jsonl').unlink()
        (Path(self.tmp)/'channels'/self.CH/'claim.json').unlink()
        self.assertEqual(awrp.fencing_authority(str(self.tmp),self.CH)['status'],'unclaimed')
        plain_td=self.mktask(self.tmp,'task_p',project='proj-fp')
        with self.assertRaises(RuntimeError):
            self.emit(plain_td,'DISPATCH','run_p',run_state='dispatched',fg=1)
        self.emit(plain_td,'DISPATCH','run_p',run_state='dispatched')
        self.emit(plain_td,'ACK','run_p',actor_role='worker',actor_id=self.EP,recipient_role='coordinator',recipient_id='chatgpt',run_state='working')
        self.assertEqual(awrp.validate(plain_td)['active_run_id'],'run_p')
    def test_historical_generation_ack_survives_rotation(self):
        self.mkctx(self.tmp); self.mkproj(self.tmp,'proj-fp',(self.CH,))
        td=self.mktask(self.tmp,'task_h',project='proj-fp')
        awrp.acquire_claim(str(self.tmp),self.CH,'chatgpt')
        self.emit(td,'DISPATCH','run_h',run_state='dispatched',fg=1)
        awrp.acquire_claim(str(self.tmp),self.CH,'chatgpt',expected_generation=1)
        self.emit(td,'ACK','run_h',actor_role='worker',actor_id=self.EP,recipient_role='coordinator',recipient_id='chatgpt',run_state='working')
        self.assertEqual(awrp.validate(td)['active_run_id'],'run_h')
    def test_forged_fencing_ack_refuses(self):
        self.mkctx(self.tmp)
        td=self.mktask(self.tmp,'task_f')
        awrp.acquire_claim(str(self.tmp),self.CH,'chatgpt')
        self.emit(td,'DISPATCH','run_f',run_state='dispatched',fg=1)
        v=awrp.validate(td); t=v['task']; h=v['head']
        e={'protocol':'awrp/0.1','event_id':awrp.newid('evt'),'seq':h['seq']+1,'context_id':t['context_id'],'task_id':t['task_id'],'run_id':'run_ghost','type':'DISPATCH','actor':{'role':'coordinator','id':'chatgpt'},'recipient':{'role':'worker','id':self.EP},'causation_id':None,'created_at':awrp.now(),'task_projection':{'state':'working','phase':'x','waiting_on':self.EP},'run':{'state':'dispatched'},'artifacts':[],'summary':'forged','details':None,'approval':None,'fencing':{'channel_id':self.CH,'generation':1,'owner':'impostor'},'integrity':{'prev_event_id':h['event_id'],'prev_event_hash':h['integrity']['event_hash'],'event_hash':''}}
        e['integrity']['event_hash']=awrp.eh(e)
        awrp.write_new(Path(td)/'events'/f"{e['seq']:06d}_{e['event_id']}.json",e)
        with self.assertRaises(RuntimeError) as cm:
            self.emit(td,'ACK','run_ghost',actor_role='worker',actor_id=self.EP,recipient_role='coordinator',recipient_id='chatgpt',run_state='working')
        self.assertIn('claim-log',str(cm.exception))
    def test_migrate_claim_proves_old_channel_without_new_generation(self):
        self.mkctx(self.tmp); self.mkproj(self.tmp,'proj-fp',(self.CH,))
        td=self.mktask(self.tmp,'task_m',project='proj-fp')
        self.emit(td,'DISPATCH','run_m',run_state='dispatched')
        cur=self.write_claim_only(self.tmp,self.CH)
        cp=Path(self.tmp)/'channels'/self.CH/'claim.json'
        o=json.loads(cp.read_text(encoding='utf-8')); o['updated_at']='2030-01-01T00:00:00Z'
        cp.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        r=awrp.migrate_claim(str(self.tmp),self.CH,note='adopt pre-claim history',by='chatgpt')
        self.assertEqual((r['generation'],r['owner'],r['migrated'],r['history_entries']),(1,'chatgpt',True,1))
        auth=awrp.fencing_authority(str(self.tmp),self.CH)
        self.assertEqual((auth['status'],auth['generation'],auth['owner']),('proven',1,'chatgpt'))
        with self.assertRaises(RuntimeError):
            awrp.migrate_claim(str(self.tmp),self.CH)
        with self.assertRaises(RuntimeError):
            awrp.repair_claim(str(self.tmp),self.CH+'-ghost')
        a=awrp.audit_fencing(td)
        self.assertTrue(a['ok']); self.assertTrue(a['fenced']); self.assertEqual(a['authority']['status'],'proven')
    def test_repair_claim_restores_history_ahead_and_unblocks_acquire(self):
        self.mkctx(self.tmp)
        awrp.acquire_claim(str(self.tmp),self.CH,'chatgpt')
        tip={'protocol':'awrp/0.1','channel_id':self.CH,'generation':2,'owner':'chatgpt','updated_at':awrp.now(),'prev_owner':'chatgpt','takeover':False,'note':'crashed between log and claim.json'}
        lp=Path(self.tmp)/'channels'/self.CH/'claim.log.jsonl'
        with open(lp,'a',encoding='utf-8') as fh: fh.write(json.dumps(tip,ensure_ascii=False,sort_keys=True)+'\n')
        self.assertEqual(awrp.fencing_authority(str(self.tmp),self.CH)['status'],'inconsistent')
        with self.assertRaises(RuntimeError) as cm:
            awrp.acquire_claim(str(self.tmp),self.CH,'chatgpt',expected_generation=1)
        self.assertIn('repair-claim',str(cm.exception))
        r=awrp.repair_claim(str(self.tmp),self.CH)
        self.assertEqual((r['repaired'],r['generation']),(True,2))
        self.assertEqual(awrp.fencing_authority(str(self.tmp),self.CH)['status'],'proven')
        c3=awrp.acquire_claim(str(self.tmp),self.CH,'chatgpt',expected_generation=2)
        self.assertEqual(c3['generation'],3)
    def test_acquire_refuses_over_diverged_claim_ahead(self):
        self.mkctx(self.tmp)
        awrp.acquire_claim(str(self.tmp),self.CH,'chatgpt')
        cp=Path(self.tmp)/'channels'/self.CH/'claim.json'
        o=json.loads(cp.read_text(encoding='utf-8')); o['generation']=2; o['note']='unproven claim-ahead artifact'
        cp.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        self.assertEqual(awrp.fencing_authority(str(self.tmp),self.CH)['status'],'inconsistent')
        with self.assertRaises(RuntimeError):
            awrp.acquire_claim(str(self.tmp),self.CH,'chatgpt',expected_generation=2)
        with self.assertRaises(RuntimeError) as cm:
            awrp.repair_claim(str(self.tmp),self.CH)
        self.assertIn('ahead of history',str(cm.exception))
    def test_unclaimed_channel_dispatch_stays_unfenced(self):
        self.mkctx(self.tmp)
        td=self.mktask(self.tmp,'task_u')
        self.assertEqual(awrp.fencing_authority(str(self.tmp),self.CH)['status'],'unclaimed')
        self.emit(td,'DISPATCH','run_u',run_state='dispatched')
        d=[x for x in awrp.validate(td)['events'] if x['type']=='DISPATCH'][0]
        self.assertNotIn('fencing',d)
    def test_doctor_reports_orphan_with_remediation(self):
        self.mkctx(self.tmp); self.mkproj(self.tmp,'proj-fp',(self.CH,))
        td=self.mktask(self.tmp,'task_d',project='proj-fp')
        self.emit(td,'DISPATCH','run_d',run_state='dispatched')
        self.write_claim_only(self.tmp,self.CH)
        import io, contextlib
        class A: pass
        a=A(); a.task_dir=td; a.repo=str(self.tmp); a.remote='origin'; a.branch=None
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_doctor(a)
        r=json.loads(buf.getvalue())
        self.assertEqual(r['checks']['claim']['authority'],'inconsistent')
        self.assertIn('migrate-claim',r['checks']['claim']['remediation'])
        self.assertFalse(r['ok'])
    def test_bridge_gate_refuses_inconsistent_channel(self):
        self.mkctx(self.tmp); self.mkproj(self.tmp,'proj-fp',(self.CH,))
        self.write_claim_only(self.tmp,self.CH)
        with self.assertRaises(RuntimeError) as cm:
            awrp._bridge_claim_owner(str(self.tmp),self.CH)
        self.assertIn('inconsistent',str(cm.exception))
        awrp.migrate_claim(str(self.tmp),self.CH)
        self.assertEqual(awrp._bridge_claim_owner(str(self.tmp),self.CH)['owner'],'chatgpt')
    def test_audit_fencing_flags_strict_orphan(self):
        self.mkctx(self.tmp); self.mkproj(self.tmp,'proj-fp',(self.CH,))
        td=self.mktask(self.tmp,'task_af',project='proj-fp')
        self.emit(td,'DISPATCH','run_af',run_state='dispatched')
        self.write_claim_only(self.tmp,self.CH)
        r=awrp.audit_fencing(td)
        self.assertFalse(r['ok']); self.assertTrue(r['fenced'])
        self.assertEqual(r['authority']['status'],'inconsistent')
        self.assertEqual(r['violations'][0]['type'],'orphaned_authority')
    def test_history_view_validates_full_triple_and_fails_closed(self):
        self.mkctx(self.tmp)
        awrp.acquire_claim(str(self.tmp),self.CH,'chatgpt')
        self.assertTrue(awrp.claim_history_contains(str(self.tmp),self.CH,1,'chatgpt'))
        self.assertFalse(awrp.claim_history_contains(str(self.tmp),self.CH,1,'impostor'))
        self.assertFalse(awrp.claim_history_contains(str(self.tmp),'ch-other',1,'chatgpt'))
        lp=Path(self.tmp)/'channels'/self.CH/'claim.log.jsonl'
        with open(lp,'a',encoding='utf-8') as fh:
            fh.write(json.dumps({'protocol':'awrp/0.1','channel_id':'ch-other','generation':1,'owner':'chatgpt','updated_at':awrp.now(),'prev_owner':None,'takeover':False})+'\n')
        view=awrp.claim_history_view(str(self.tmp),self.CH)
        self.assertEqual([p['type'] for p in view['problems']],['channel_mismatch'])
        self.assertFalse(awrp.claim_history_contains(str(self.tmp),self.CH,1,'chatgpt'))
        self.assertEqual(awrp.fencing_authority(str(self.tmp),self.CH)['status'],'inconsistent')
    def test_generation_conflict_proves_nothing(self):
        self.mkctx(self.tmp)
        awrp.acquire_claim(str(self.tmp),self.CH,'chatgpt')
        awrp.acquire_claim(str(self.tmp),self.CH,'chatgpt',expected_generation=1)
        lp=Path(self.tmp)/'channels'/self.CH/'claim.log.jsonl'
        with open(lp,'a',encoding='utf-8') as fh:
            fh.write(json.dumps({'protocol':'awrp/0.1','channel_id':self.CH,'generation':2,'owner':'rival','updated_at':awrp.now(),'prev_owner':'chatgpt','takeover':True})+'\n')
        view=awrp.claim_history_view(str(self.tmp),self.CH)
        self.assertEqual([p['type'] for p in view['problems']],['generation_conflict'])
        self.assertFalse(awrp.claim_history_contains(str(self.tmp),self.CH,2,'chatgpt'))
        self.assertFalse(awrp.claim_history_contains(str(self.tmp),self.CH,1,'chatgpt'))
        auth=awrp.fencing_authority(str(self.tmp),self.CH)
        self.assertEqual(auth['status'],'inconsistent')
    def test_doctor_rejects_claim_only_legacy_channel(self):
        self.mkctx(self.tmp)
        td=self.mktask(self.tmp,'task_dl')
        self.emit(td,'DISPATCH','run_dl',run_state='dispatched')
        self.write_claim_only(self.tmp,self.CH)
        import io, contextlib
        class A: pass
        a=A(); a.task_dir=td; a.repo=str(self.tmp); a.remote='origin'; a.branch=None
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_doctor(a)
        r=json.loads(buf.getvalue())
        self.assertEqual(r['checks']['claim']['authority'],'legacy-claim')
        self.assertIn('migrate-claim',r['checks']['claim']['remediation'])
        self.assertFalse(r['ok'])
    def test_audit_fencing_flags_unproven_fenced_event_on_legacy_claim(self):
        self.mkctx(self.tmp)
        td=self.mktask(self.tmp,'task_al')
        self.write_claim_only(self.tmp,self.CH)
        v=awrp.validate(td); t=v['task']; h=v['head']
        e={'protocol':'awrp/0.1','event_id':awrp.newid('evt'),'seq':h['seq']+1,'context_id':t['context_id'],'task_id':t['task_id'],'run_id':'run_al','type':'DISPATCH','actor':{'role':'coordinator','id':'chatgpt'},'recipient':{'role':'worker','id':self.EP},'causation_id':None,'created_at':awrp.now(),'task_projection':{'state':'working','phase':'x','waiting_on':self.EP},'run':{'state':'dispatched'},'artifacts':[],'summary':'pre-revision fenced dispatch','details':None,'approval':None,'fencing':{'channel_id':self.CH,'generation':1,'owner':'chatgpt'},'integrity':{'prev_event_id':h['event_id'],'prev_event_hash':h['integrity']['event_hash'],'event_hash':''}}
        e['integrity']['event_hash']=awrp.eh(e)
        awrp.write_new(Path(td)/'events'/f"{e['seq']:06d}_{e['event_id']}.json",e)
        r=awrp.audit_fencing(td)
        self.assertFalse(r['ok']); self.assertTrue(r['fenced'])
        self.assertEqual(r['authority']['status'],'legacy-claim')
        self.assertEqual([x['type'] for x in r['violations']],['unfenced_or_mismatch'])
    def test_event_replacement_is_detected_by_append_only_audit(self):
        import subprocess as _sp
        remote=self.tmp/'r.git'; w=self.tmp/'w'
        def git(repo,*args):
            cp=_sp.run(['git','-C',str(repo),*args],capture_output=True,text=True)
            self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
        git(self.tmp,'init','--bare',str(remote))
        git(self.tmp,'init','-b','main',str(w))
        git(w,'config','user.email','t@e'); git(w,'config','user.name','t')
        self.mkctx(w)
        td=self.mktask(w,'task_r')
        self.dis(w,td,'run_r')
        git(w,'add','-A'); git(w,'commit','-m','base'); git(w,'remote','add','origin',str(remote)); git(w,'push','-u','origin','main')
        base=git(w,'rev-parse','main')
        old=sorted((Path(td)/'events').glob('*.json'))[-1]
        o=json.loads(old.read_text(encoding='utf-8'))
        o['event_id']=awrp.newid('evt'); o['summary']='replacement with fresh identity'
        o['integrity']['event_hash']=awrp.eh({k:v for k,v in o.items() if k!='integrity'} | {'integrity':{k:v for k,v in o['integrity'].items() if k!='event_hash'}})
        new_name=f"{o['seq']:06d}_{o['event_id']}.json"
        old.unlink(); (Path(td)/'events'/new_name).write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        awrp.validate(td)
        git(w,'add','-A'); git(w,'commit','-m','replacement')
        r=awrp.audit_append_only(str(w),'task_r',ref=base)
        self.assertFalse(r['ok'])
        kinds={x['type'] for x in r['violations']}
        self.assertTrue(kinds & {'deleted','renamed','modified'},
                        f'replacement must never be silent, got {kinds}')
    def dis(self,w,td,rid,recipient=None):
        recipient=recipient or self.EP
        class A: pass
        a=A(); a.task_dir=td; a.type='DISPATCH'; a.actor_role='coordinator'; a.actor_id='chatgpt'; a.recipient_role='worker'; a.recipient_id=recipient; a.run_id=rid; a.new_run=False; a.state='working'; a.phase='x'; a.waiting_on=recipient; a.run_state='dispatched'; a.summary='d'
        a.details_file=None; a.artifacts_file=None; a.approval_file=None
        a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None; a.idempotency_key=None; a.require_fresh=False; a.legacy_route=True
        awrp.emit(a)
class TFastPath(unittest.TestCase):
    CH='ch-fx'; EP='ep-fx'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def mkctx(self,root,ctx='c'):
        (Path(root)/'contexts').mkdir(exist_ok=True)
        awrp.write_new(Path(root)/'contexts'/f'{ctx}.json',{'protocol':'awrp/0.1','context_id':ctx,'title':'t','created_at':awrp.now(),'description':''})
    def mktask(self,root,tid,channel=CH,endpoint=EP,project=None):
        class A: pass
        a=A(); a.root=str(root); a.context_id='c'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=channel; a.lane_id=None; a.worker_endpoint=endpoint; a.project_id=project
        a.legacy=True
        awrp.create_task(a); return str(Path(root)/'tasks'/tid)
    def dis(self,td,rid,recipient=EP):
        class A: pass
        a=A(); a.task_dir=td; a.type='DISPATCH'; a.actor_role='coordinator'; a.actor_id='chatgpt'; a.recipient_role='worker'; a.recipient_id=recipient; a.run_id=rid; a.new_run=False; a.state='working'; a.phase='x'; a.waiting_on=recipient; a.run_state='dispatched'; a.summary='d'
        a.details_file=None; a.artifacts_file=None; a.approval_file=None
        a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=None; a.idempotency_key=None; a.require_fresh=False; a.legacy_route=True
        awrp.emit(a)
    def count_validations(self):
        calls=[]
        real=awrp.validate
        def counting(td,*a,**k):
            calls.append(Path(td).name); return real(td,*a,**k)
        awrp.validate=counting
        self.addCleanup(setattr,awrp,'validate',real)
        return calls
    def test_resume_validates_only_routing_candidates(self):
        self.mkctx(self.tmp)
        for i in range(6):
            td=self.mktask(self.tmp,f'task_other_{i}',channel=f'ch-else-{i}',endpoint=f'ep-else-{i}')
            self.dis(td,f'run_other_{i}',recipient=f'ep-else-{i}')
        td=self.mktask(self.tmp,'task_hit')
        self.dis(td,'run_hit')
        calls=self.count_validations()
        r=awrp.select_for_resume(str(self.tmp),self.CH,self.EP,None,None)
        self.assertEqual((r['status'],r['task_id']),('EXECUTE','task_hit'))
        self.assertEqual(calls,['task_hit'])
    def test_select_reuses_candidate_snapshot_without_revalidation(self):
        self.mkctx(self.tmp)
        td=self.mktask(self.tmp,'task_one')
        self.dis(td,'run_one')
        calls=self.count_validations()
        r=awrp.select_for_resume(str(self.tmp),self.CH,self.EP,None,None)
        self.assertEqual(r['status'],'EXECUTE')
        self.assertEqual(len(calls),1)
    def test_unrelated_corruption_no_longer_blocks_resume(self):
        self.mkctx(self.tmp)
        bad=self.mktask(self.tmp,'task_bad',channel='ch-else',endpoint='ep-else')
        self.dis(bad,'run_bad',recipient='ep-else')
        p=sorted((Path(bad)/'events').glob('*.json'))[-1]
        o=json.loads(p.read_text(encoding='utf-8')); o['summary']='tampered'; p.write_text(json.dumps(o))
        good=self.mktask(self.tmp,'task_good')
        self.dis(good,'run_good')
        r=awrp.select_for_resume(str(self.tmp),self.CH,self.EP,None,None)
        self.assertEqual((r['status'],r['task_id']),('EXECUTE','task_good'))
        r2=awrp.select_for_resume(str(self.tmp),'ch-else','ep-else',None,None)
        self.assertEqual(r2['status'],'INVALID_CANONICAL')
    def test_no_candidate_reports_no_task_not_invalid(self):
        self.mkctx(self.tmp)
        bad=self.mktask(self.tmp,'task_bad',channel='ch-else',endpoint='ep-else')
        self.dis(bad,'run_bad',recipient='ep-else')
        p=sorted((Path(bad)/'events').glob('*.json'))[-1]
        o=json.loads(p.read_text(encoding='utf-8')); o['summary']='tampered'; p.write_text(json.dumps(o))
        r=awrp.select_for_resume(str(self.tmp),self.CH,self.EP,None,None)
        self.assertEqual(r['status'],'NO_TASK')
        self.assertEqual(r.get('invalid_canonical'),[])
    def test_unreadable_manifest_still_fails_closed(self):
        self.mkctx(self.tmp)
        td=self.mktask(self.tmp,'task_broken')
        (Path(td)/'task.json').write_text('{not json',encoding='utf-8')
        r=awrp.select_for_resume(str(self.tmp),self.CH,self.EP,None,None)
        self.assertEqual(r['status'],'INVALID_CANONICAL')
        self.assertEqual(len(r['invalid_canonical']),1)
    def test_preflight_shares_validation_snapshot(self):
        import subprocess as _sp
        remote=self.tmp/'r.git'; w=self.tmp/'w'
        def git(repo,*args):
            cp=_sp.run(['git','-C',str(repo),*args],capture_output=True,text=True)
            self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
        git(self.tmp,'init','--bare',str(remote))
        git(self.tmp,'init','-b','main',str(w))
        git(w,'config','user.email','t@e'); git(w,'config','user.name','t')
        self.mkctx(w)
        td=self.mktask(w,'task_p')
        self.dis(td,'run_p')
        git(w,'add','-A'); git(w,'commit','-m','seed'); git(w,'remote','add','origin',str(remote)); git(w,'push','-u','origin','main')
        v=awrp.validate(td); h=v['head']
        calls=self.count_validations()
        import io, contextlib
        class A: pass
        a=A(); a.task_dir=td; a.repo=str(w); a.branch='main'; a.remote='origin'; a.expected_base=None; a.expected_head=None; a.expected_hash=None; a.run_id='run_p'
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_preflight(a)
        r=json.loads(buf.getvalue())
        self.assertTrue(r['ok'])
        self.assertEqual(len(calls),1)
    def test_bridge_batch_sweep_bounded_single_process(self):
        import subprocess as _sp
        remote=self.tmp/'r.git'; w=self.tmp/'w'
        def git(repo,*args):
            cp=_sp.run(['git','-C',str(repo),*args],capture_output=True,text=True)
            self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
        git(self.tmp,'init','--bare',str(remote))
        git(self.tmp,'init','-b','main',str(w))
        git(w,'config','user.email','t@e'); git(w,'config','user.name','t')
        self.mkctx(w)
        awrp.project_create(str(w),'proj-b','B',(self.CH,),None,'chatgpt')
        awrp.acquire_claim(str(w),self.CH,'chatgpt')
        git(w,'add','-A'); git(w,'commit','-m','seed'); git(w,'remote','add','origin',str(remote)); git(w,'push','-u','origin','main')
        base=git(w,'rev-parse','main')
        def mkreq(rid,body):
            p=w/'bridge'/'requests'; p.mkdir(parents=True,exist_ok=True)
            (p/f'{rid}.json').write_text(body if isinstance(body,str) else json.dumps(body),encoding='utf-8')
        mkreq('r-new-1',{"protocol":"awrp/0.1","request_id":"r-new-1","action":"create-task","idempotency_key":"k1","expected_base":base,
            "params":{"task_id":"task_b1","context_id":"c","title":"B1","goal":"g","project_id":"proj-b","channel_id":self.CH,"worker_endpoint":self.EP,"created_at":"2026-09-09T15:00:00Z"}})
        mkreq('r-new-2',{"protocol":"awrp/0.1","request_id":"r-new-2","action":"create-task","idempotency_key":"k2","expected_base":base,
            "params":{"task_id":"task_b2","context_id":"c","title":"B2","goal":"g","project_id":"proj-b","channel_id":self.CH,"worker_endpoint":self.EP,"created_at":"2026-09-09T15:00:00Z"}})
        for i in range(5):
            mkreq(f'r-old-{i}',{"protocol":"awrp/0.1","request_id":f'r-old-{i}',"action":"create-task","idempotency_key":f'k-old-{i}',"expected_base":base,
                "params":{"task_id":f"task_old_{i}","context_id":"c","title":"O","goal":"g","project_id":"proj-b","channel_id":self.CH,"worker_endpoint":self.EP,"created_at":"2026-09-09T15:00:00Z"}})
            (w/'bridge'/'requests'/f'r-old-{i}.result.json').write_text(json.dumps({"protocol":"awrp/0.1","request_id":f'r-old-{i}',"status":"published"}),encoding='utf-8')
        composes=[]
        real=awrp._bridge_compose_once
        def counting(*a,**k):
            composes.append(a[4] if len(a)>4 else 'kw'); return real(*a,**k)
        awrp._bridge_compose_once=counting
        self.addCleanup(setattr,awrp,'_bridge_compose_once',real)
        import io, contextlib
        class A: pass
        a=A(); a.root=str(w); a.request='r-new-2'; a.all_pending=True; a.repo=str(w); a.branch='main'; a.remote='origin'
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_bridge_process(a)
        r=json.loads(buf.getvalue())
        self.assertEqual(r['mode'],'all-pending')
        self.assertEqual(r['processed'],['r-new-2','r-new-1'])
        self.assertEqual(sorted(r['results']),['r-new-1','r-new-2'])
        self.assertEqual({v['status'] for v in r['results'].values()},{'published'})
        self.assertTrue((w/'tasks'/'task_b1'/'task.json').exists())
        self.assertTrue((w/'tasks'/'task_b2'/'task.json').exists())
        self.assertEqual(len(composes),2)
        self.assertEqual(git(remote,'rev-parse','main'),git(w,'rev-parse','main'))
    def test_benchmark_work_counts_scale_with_candidates_not_history(self):
        self.mkctx(self.tmp)
        for i in range(40):
            td=self.mktask(self.tmp,f'task_noise_{i:02d}',channel=f'ch-noise-{i}',endpoint=f'ep-noise-{i}')
            self.dis(td,f'run_noise_{i}',recipient=f'ep-noise-{i}')
        for tid in ('task_c1','task_c2'):
            td=self.mktask(self.tmp,tid)
            self.dis(td,'run_'+tid)
        calls=self.count_validations()
        r=awrp.select_for_resume(str(self.tmp),self.CH,self.EP,None,None)
        self.assertEqual(r['status'],'AMBIGUOUS')
        self.assertEqual(sorted(r['candidates']),['task_c1','task_c2'])
        self.assertEqual(sorted(calls),['task_c1','task_c2'])
        print(f'BENCHMARK resume: 42 histories present, full validations performed: {len(calls)} (candidates only; unrelated: 0)')
class TIncidentCore(unittest.TestCase):
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def create(self,iid='inc_20260917_core',**kw):
        d={'title':'t','summary':'s','severity':'high','category':'fencing','reporter_role':'worker','reporter_id':'opencode_awrp','symptom':'sym','impact':'imp','evidence':'concrete evidence'}
        d.update(kw)
        return awrp.incident_create(str(self.tmp),iid,**d)
    def update(self,iid,actor_role='worker',actor_id='opencode_awrp',**kw):
        return awrp.incident_update(str(self.tmp),iid,actor_role,actor_id,**kw)
    def idir(self,iid): return self.tmp/'incidents'/iid
    def test_create_show_list_audit_happy_path(self):
        o=self.create()
        self.assertEqual(o['status'],'open')
        self.assertTrue(o['discovery_hash'].startswith('sha256:'))
        s=awrp.incident_show(str(self.tmp),'inc_20260917_core')
        self.assertEqual((s['status'],s['head_seq']),( 'open',0))
        lst=awrp.incident_list(str(self.tmp))
        self.assertEqual([i['incident_id'] for i in lst['incidents']],['inc_20260917_core'])
        self.assertEqual(lst['invalid'],[])
        a=awrp.incident_audit(str(self.tmp))
        self.assertTrue(a['ok'])
        self.assertTrue((self.idir('inc_20260917_core')/'INCIDENT.md').exists())
        self.assertTrue((self.tmp/'incidents'/'INDEX.md').exists())
    def test_duplicate_create_refused(self):
        self.create()
        with self.assertRaises(RuntimeError):
            self.create()
    def test_discovery_immutable(self):
        self.create()
        p=self.idir('inc_20260917_core')/'incident.json'
        o=json.loads(p.read_text(encoding='utf-8')); o['summary']='rewritten'
        p.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        with self.assertRaises(RuntimeError) as cm:
            awrp.incident_validate(self.idir('inc_20260917_core'))
        self.assertIn('immutable',str(cm.exception))
    def test_tampered_update_detected(self):
        self.create()
        self.update('inc_20260917_core',status='mitigated',note='holding')
        p=sorted((self.idir('inc_20260917_core')/'events').glob('*.json'))[-1]
        o=json.loads(p.read_text(encoding='utf-8')); o['note']='tampered'
        p.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        with self.assertRaises(RuntimeError):
            awrp.incident_validate(self.idir('inc_20260917_core'))
    def test_illegal_transitions_refused(self):
        self.create()
        with self.assertRaises(RuntimeError):
            self.update('inc_20260917_core',status='duplicate',note='x')
        with self.assertRaises(RuntimeError):
            self.update('inc_20260917_core',status='bogus',note='x')
        with self.assertRaises(RuntimeError):
            self.update('inc_20260917_core',status='accepted_risk')
        self.update('inc_20260917_core',status='mitigated',note='holding')
        with self.assertRaises(RuntimeError):
            self.update('inc_20260917_core',status='duplicate',note='x')
    def test_lifecycle_with_resolved_at_and_reopen(self):
        self.create()
        self.update('inc_20260917_core',status='mitigated',note='holding')
        e=self.update('inc_20260917_core',status='resolved',resolution_evidence='fix verified')
        s=awrp.incident_show(str(self.tmp),'inc_20260917_core')
        self.assertEqual(s['status'],'resolved')
        self.assertEqual(s['resolved_at'],e['created_at'])
        self.update('inc_20260917_core',status='open',note='recurred')
        s2=awrp.incident_show(str(self.tmp),'inc_20260917_core')
        self.assertEqual((s2['status'],s2['resolved_at']),('open',None))
    def test_empty_update_and_bad_fields_refused(self):
        self.create()
        with self.assertRaises(RuntimeError):
            self.update('inc_20260917_core')
        with self.assertRaises(RuntimeError):
            self.create('inc_20260917_bad',severity='cosmic')
        with self.assertRaises(RuntimeError):
            self.create('inc_20260917_bad',category='gossip')
        with self.assertRaises(RuntimeError):
            self.create('inc_20260917_bad',evidence='  ')
        with self.assertRaises(RuntimeError):
            self.create('inc_20260917_bad',refs={'issue_number':'1'})
        with self.assertRaises(RuntimeError):
            self.create('bad-id!')
    def test_links_must_resolve(self):
        self.create('inc_20260917_a')
        with self.assertRaises(RuntimeError):
            self.create('inc_20260917_b',related_incidents=['inc_20260917_ghost'])
        with self.assertRaises(RuntimeError):
            self.update('inc_20260917_a',related_add=['inc_20260917_ghost'])
        self.create('inc_20260917_b')
        self.update('inc_20260917_a',related_add=['inc_20260917_b'])
        self.update('inc_20260917_b',status='duplicate',duplicate_of='inc_20260917_a',note='same root cause')
        s=awrp.incident_show(str(self.tmp),'inc_20260917_b')
        self.assertEqual(s['status'],'duplicate')
        with self.assertRaises(RuntimeError):
            self.update('inc_20260917_b',status='open',note='nope')
        self.update('inc_20260917_b',note='post-close evidence still appends')
    def test_idempotency_key_replay_refused(self):
        self.create()
        self.update('inc_20260917_core',note='first',idempotency_key='k1')
        with self.assertRaises(RuntimeError) as cm:
            self.update('inc_20260917_core',note='retry',idempotency_key='k1')
        self.assertIn('already recorded',str(cm.exception))
    def test_projection_rebuild_is_byte_identical(self):
        self.create()
        self.update('inc_20260917_core',status='mitigated',note='holding')
        inc=self.idir('inc_20260917_core')
        before={p.name:awrp.artifact_fingerprint(str(p))['sha256'] for p in [inc/'INCIDENT.md',self.tmp/'incidents'/'INDEX.md']}
        (inc/'INCIDENT.md').unlink(); (self.tmp/'incidents'/'INDEX.md').unlink()
        awrp.do_incident_rebuild(type('A',(),{'root':str(self.tmp),'incident_id':None})())
        after={p.name:awrp.artifact_fingerprint(str(p))['sha256'] for p in [inc/'INCIDENT.md',self.tmp/'incidents'/'INDEX.md']}
        self.assertEqual(before,after)
    def test_strict_schema_rejects_unknown_keys(self):
        self.create()
        p=self.idir('inc_20260917_core')/'incident.json'
        o=json.loads(p.read_text(encoding='utf-8')); o['surprise']='x'
        o['discovery_hash']=awrp.incident_discovery_hash(o)
        p.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        with self.assertRaises(RuntimeError) as cm:
            awrp.incident_validate(self.idir('inc_20260917_core'))
        self.assertIn('unknown discovery keys',str(cm.exception))
    def test_list_filters(self):
        self.create('inc_20260917_x',severity='low',category='docs')
        self.create('inc_20260917_y',severity='critical',category='protocol')
        self.update('inc_20260917_y',status='mitigated',note='holding')
        self.assertEqual([i['incident_id'] for i in awrp.incident_list(str(self.tmp),status='mitigated')['incidents']],['inc_20260917_y'])
        self.assertEqual([i['incident_id'] for i in awrp.incident_list(str(self.tmp),severity='low')['incidents']],['inc_20260917_x'])
        self.assertEqual([i['incident_id'] for i in awrp.incident_list(str(self.tmp),category='protocol')['incidents']],['inc_20260917_y'])
class TIncidentBridge(unittest.TestCase):
    CH='ch-ib'; EP='ep-ib'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def git(self,repo,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def mkrelay(self):
        remote=self.tmp/'r.git'; w=self.tmp/'w'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(self.tmp,'init','-b','main',str(w))
        self.git(w,'config','user.email','t@e'); self.git(w,'config','user.name','t')
        (w/'contexts').mkdir(exist_ok=True)
        awrp.write_new(w/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        self.git(w,'add','-A'); self.git(w,'commit','-m','seed'); self.git(w,'remote','add','origin',str(remote))
        self.git(w,'push','-u','origin','main'); self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
        return remote,w,self.git(w,'rev-parse','main')
    def mkreq(self,w,rid,body):
        p=w/'bridge'/'requests'; p.mkdir(parents=True,exist_ok=True)
        (p/f'{rid}.json').write_text(body if isinstance(body,str) else json.dumps(body),encoding='utf-8')
    def bridge(self,w,rid,all_pending=False):
        import io, contextlib
        class A: pass
        a=A(); a.root=str(w); a.request=rid; a.all_pending=all_pending; a.repo=str(w); a.branch='main'; a.remote='origin'
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_bridge_process(a)
        return json.loads(buf.getvalue())
    def ireq(self,rid,action,iid,params,base,key='k'):
        return {"protocol":"awrp/0.1","request_id":rid,"action":action,"idempotency_key":key,"expected_base":base,"params":{"incident_id":iid,**params}}
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_bridge_incident_create_and_update(self):
        remote,w,base=self.mkrelay()
        self.mkreq(w,'r-inc-c1',self.ireq('r-inc-c1','incident-create','inc_20260917_b1',{"title":"T","summary":"s","severity":"high","category":"protocol","reporter_role":"coordinator","reporter_id":"chatgpt","symptom":"sym","impact":"imp","evidence":"concrete evidence"},base,key='k1'))
        out=self.bridge(w,'r-inc-c1')
        self.assertEqual(out['status'],'published')
        self.assertEqual(out['incident_id'],'inc_20260917_b1')
        self.assertTrue((w/'incidents'/'inc_20260917_b1'/'incident.json').exists())
        self.assertTrue((w/'incidents'/'INDEX.md').exists())
        v=awrp.incident_validate(w/'incidents'/'inc_20260917_b1')
        self.assertEqual(v['head_status'],'open')
        self.mkreq(w,'r-inc-u1',self.ireq('r-inc-u1','incident-update','inc_20260917_b1',{"reporter_role":"coordinator","reporter_id":"chatgpt","status":"mitigated","note":"holding"},base,key='k2'))
        out2=self.bridge(w,'r-inc-u1')
        self.assertEqual((out2['status'],out2['incident_id']),('published','inc_20260917_b1'))
        v2=awrp.incident_validate(w/'incidents'/'inc_20260917_b1')
        self.assertEqual((v2['head_status'],v2['update_count']),('mitigated',1))
        self.assertEqual(self.git(remote,'rev-parse','main'),self.git(w,'rev-parse','main'))
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_bridge_incident_rejections_leave_no_trace(self):
        remote,w,base=self.mkrelay()
        self.mkreq(w,'r-inc-bad',self.ireq('r-inc-bad','incident-create','inc_20260917_bad',{"title":"T","summary":"s","severity":"high","category":"protocol","reporter_role":"coordinator","reporter_id":"chatgpt","symptom":"sym","impact":"imp"},base))
        out=self.bridge(w,'r-inc-bad')
        self.assertEqual(out['status'],'rejected')
        self.assertFalse((w/'incidents').exists())
        self.mkreq(w,'r-inc-worker',self.ireq('r-inc-worker','incident-create','inc_20260917_w',{"title":"T","summary":"s","severity":"high","category":"protocol","reporter_role":"worker","reporter_id":"opencode_awrp","symptom":"sym","impact":"imp","evidence":"e"},base))
        out2=self.bridge(w,'r-inc-worker')
        self.assertEqual(out2['status'],'rejected')
        self.assertFalse((w/'incidents'/'inc_20260917_w').exists())
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_bridge_incident_preflight_and_replay(self):
        remote,w,base=self.mkrelay()
        import io, contextlib
        self.mkreq(w,'r-inc-p1',self.ireq('r-inc-p1','incident-create','inc_20260917_p1',{"title":"T","summary":"s","severity":"medium","category":"transport","reporter_role":"coordinator","reporter_id":"chatgpt","symptom":"sym","impact":"imp","evidence":"concrete evidence"},base))
        class A: pass
        a=A(); a.root=str(w); a.request='r-inc-p1'; a.repo=str(w); a.branch='main'; a.remote='origin'
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_bridge_preflight(a)
        pf=json.loads(buf.getvalue())
        self.assertEqual((pf['status'],pf['incident_id']),('plannable','inc_20260917_p1'))
        r1=self.bridge(w,'r-inc-p1')
        self.assertEqual(r1['status'],'published')
        r2=self.bridge(w,'r-inc-p1')
        self.assertEqual(r2['status'],'skipped')
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_bridge_incident_survives_unrelated_drift(self):
        remote,w,base=self.mkrelay()
        b=self.tmp/'wb'
        subprocess.run(['git','-C',str(self.tmp),'clone',str(remote),str(b)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.email','t@e'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'config','user.name','t@e'],check=True,capture_output=True)
        class A: pass
        a=A(); a.root=str(b); a.context_id='c'; a.task_id='task_rival'; a.title='t'; a.goal='g'; a.worker='w'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id='ch-r'; a.lane_id=None; a.worker_endpoint='ep-r'; a.project_id=None; a.legacy=True
        awrp.create_task(a)
        subprocess.run(['git','-C',str(b),'add','-A'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'commit','-m','rival'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(b),'push','origin','main'],check=True,capture_output=True)
        self.mkreq(w,'r-inc-d1',self.ireq('r-inc-d1','incident-create','inc_20260917_d1',{"title":"T","summary":"s","severity":"low","category":"docs","reporter_role":"coordinator","reporter_id":"chatgpt","symptom":"sym","impact":"imp","evidence":"concrete evidence"},base))
        out=self.bridge(w,'r-inc-d1')
        self.assertEqual(out['status'],'published')
        self.assertEqual(awrp.incident_validate(w/'incidents'/'inc_20260917_d1')['head_status'],'open')
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_bridge_incident_batch_sweep(self):
        remote,w,base=self.mkrelay()
        self.mkreq(w,'r-inc-s1',self.ireq('r-inc-s1','incident-create','inc_20260917_s1',{"title":"T1","summary":"s","severity":"low","category":"docs","reporter_role":"coordinator","reporter_id":"chatgpt","symptom":"sym","impact":"imp","evidence":"concrete evidence"},base,key='ks1'))
        self.mkreq(w,'r-inc-s2',self.ireq('r-inc-s2','incident-create','inc_20260917_s2',{"title":"T2","summary":"s","severity":"low","category":"docs","reporter_role":"coordinator","reporter_id":"chatgpt","symptom":"sym","impact":"imp","evidence":"concrete evidence"},base,key='ks2'))
        out=self.bridge(w,'r-inc-s1',all_pending=True)
        self.assertEqual(out['mode'],'all-pending')
        self.assertEqual(sorted(out['processed']),['r-inc-s1','r-inc-s2'])
        self.assertEqual({v['status'] for v in out['results'].values()},{'published'})
        self.assertTrue((w/'incidents'/'INDEX.md').exists())
        rows=[l for l in (w/'incidents'/'INDEX.md').read_text(encoding='utf-8').splitlines() if l.startswith('| `inc_')]
        self.assertEqual(len(rows),2)
class TIncidentConcurrency(unittest.TestCase):
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def test_independent_creates_and_interleaved_updates(self):
        ids=[f'inc_20260917_p{i:02d}' for i in range(8)]
        for iid in ids:
            awrp.incident_create(str(self.tmp),iid,title='t',summary='s',severity='medium',category='recovery',reporter_role='worker',reporter_id='opencode_awrp',symptom='sym',impact='imp',evidence='concrete evidence')
        for rnd in range(3):
            for iid in ids:
                awrp.incident_update(str(self.tmp),iid,'worker','opencode_awrp',note=f'observation {rnd} for {iid}')
        for iid in ids:
            v=awrp.incident_validate(self.tmp/'incidents'/iid)
            self.assertEqual((v['head_status'],v['update_count']),('open',3))
        lst=awrp.incident_list(str(self.tmp))
        self.assertEqual(sorted(i['incident_id'] for i in lst['incidents']),ids)
        self.assertEqual(lst['invalid'],[])
        idx=(self.tmp/'incidents'/'INDEX.md').read_text(encoding='utf-8')
        for iid in ids: self.assertIn(iid,idx)
    def test_same_id_create_races_one_winner(self):
        awrp.incident_create(str(self.tmp),'inc_20260917_race',title='t',summary='s',severity='low',category='other',reporter_role='human',reporter_id='u',symptom='sym',impact='imp',evidence='concrete evidence')
        with self.assertRaises(RuntimeError):
            awrp.incident_create(str(self.tmp),'inc_20260917_race',title='t2',summary='s2',severity='low',category='other',reporter_role='human',reporter_id='u',symptom='sym',impact='imp',evidence='concrete evidence')
        v=awrp.incident_validate(self.tmp/'incidents'/'inc_20260917_race')
        self.assertEqual(v['incident']['title'],'t')
    def test_same_incident_sequential_updates_serialize(self):
        awrp.incident_create(str(self.tmp),'inc_20260917_ser',title='t',summary='s',severity='high',category='transport',reporter_role='coordinator',reporter_id='chatgpt',symptom='sym',impact='imp',evidence='concrete evidence')
        e1=awrp.incident_update(str(self.tmp),'inc_20260917_ser','coordinator','chatgpt',status='mitigated',note='first')
        e2=awrp.incident_update(str(self.tmp),'inc_20260917_ser','coordinator','chatgpt',evidence_add='second observation')
        self.assertEqual((e1['seq'],e2['seq']),(1,2))
        self.assertEqual(e2['integrity']['prev_event_id'],e1['event_id'])
        v=awrp.incident_validate(self.tmp/'incidents'/'inc_20260917_ser')
        self.assertEqual(v['head_status'],'mitigated')
class TFirstBindOverride(unittest.TestCase):
    CH='ch-fb'; EP='ep-fb'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def git(self,repo,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def mkseed(self):
        remote=self.tmp/'r.git'; w0=self.tmp/'seed'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(self.tmp,'init','-b','main',str(w0))
        self.git(w0,'config','user.email','t@e'); self.git(w0,'config','user.name','t')
        (w0/'contexts').mkdir(exist_ok=True)
        awrp.write_new(w0/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        awrp.project_create(str(w0),'proj-fb','FB',(self.CH,),None,'chatgpt')
        awrp.acquire_claim(str(w0),self.CH,'chatgpt')
        class A: pass
        a=A(); a.root=str(w0); a.context_id='c'; a.task_id='task_fb'; a.title='t'; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=self.CH; a.lane_id=None; a.worker_endpoint=self.EP; a.project_id='proj-fb'
        a.legacy=True
        awrp.create_task(a)
        class E: pass
        e=E(); e.task_dir=str(w0/'tasks'/'task_fb'); e.type='DISPATCH'; e.actor_role='coordinator'; e.actor_id='chatgpt'; e.recipient_role='worker'; e.recipient_id=self.EP; e.run_id='run_fb'; e.new_run=False; e.state='working'; e.phase='x'; e.waiting_on=self.EP; e.run_state='dispatched'; e.summary='d'; e.details_file=None; e.artifacts_file=None; e.approval_file=None; e.causation_id=None; e.expected_head=None; e.expected_hash=None; e.claimant=None; e.fencing_generation=1; e.idempotency_key=None; e.require_fresh=False; e.legacy_route=True
        awrp.emit(e)
        self.git(w0,'add','-A'); self.git(w0,'commit','-m','seed'); self.git(w0,'remote','add','origin',str(remote)); self.git(w0,'push','-u','origin','main'); self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
        return remote
    def clone(self,remote,name):
        d=self.tmp/name
        subprocess.run(['git','-C',str(self.tmp),'clone',str(remote),str(d)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(d),'config','user.email','t@e'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(d),'config','user.name','t@e'],check=True,capture_output=True)
        return d
    def bind(self,ws,relaydir,task_id='task_fb',run_id='run_fb'):
        import io, contextlib
        class A: pass
        a=A(); a.root=str(ws); a.relay='Bruce-Yii/awrp'; a.relay_dir=str(relaydir); a.project_id='proj-fb'; a.channel=self.CH; a.worker_endpoint=self.EP; a.task_id=task_id; a.run_id=run_id; a.lane=None; a.bound_by='t'
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_first_bind(a)
        return json.loads(buf.getvalue())
    def mkws(self,name='ws'):
        ws=self.tmp/name; ws.mkdir(exist_ok=True); return ws
    def dirty_bound_clone(self,bound,remote):
        rival=self.clone(remote,'rival')
        (rival/'tasks'/'task_fb'/'TASK.md').write_text('# rival projection\n',encoding='utf-8')
        subprocess.run(['git','-C',str(rival),'add','-A'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(rival),'commit','-m','rival'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(rival),'push','origin','main'],check=True,capture_output=True)
        (bound/'tasks'/'task_fb'/'TASK.md').write_text('# my divergent projection\n',encoding='utf-8')
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_override_succeeds_on_dirty_bound_clone_without_mutating_binding(self):
        remote=self.mkseed()
        bound=self.clone(remote,'bound'); clean=self.clone(remote,'clean')
        ws=self.mkws()
        r1=self.bind(ws,bound)
        self.assertEqual(r1['status'],'EXECUTE')
        self.assertFalse(r1['binding'].get('override'))
        bpath=ws/'.awrp'/'binding.json'
        before=awrp.artifact_fingerprint(str(bpath))['sha256']
        self.dirty_bound_clone(bound,remote)
        with self.assertRaises(RuntimeError):
            self.bind(ws,bound)
        r2=self.bind(ws,clean)
        self.assertEqual(r2['status'],'EXECUTE')
        self.assertTrue(r2['binding'].get('override'))
        self.assertEqual(r2['binding']['relay_dir'],str(clean.resolve()))
        self.assertEqual(r2['task_id'],'task_fb'); self.assertEqual(r2['run_id'],'run_fb')
        self.assertEqual(awrp.artifact_fingerprint(str(bpath))['sha256'],before)
        v=awrp.validate(clean/'tasks'/'task_fb')
        self.assertEqual(r2['head_event_id'],v['head']['event_id'])
        self.assertEqual(r2['run_id'],v.get('active_run_id'))
        self.assertEqual(r2['fencing_authority']['status'],'proven')
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_override_wrong_relay_refused(self):
        remote=self.mkseed()
        bound=self.clone(remote,'bound'); other=self.clone(remote,'other')
        ws=self.mkws()
        self.bind(ws,bound)
        (other/'relay.json').write_text(json.dumps({'protocol':'awrp/0.1','relay':'someone-else/repo'}),encoding='utf-8')
        with self.assertRaises(RuntimeError) as cm:
            self.bind(ws,other)
        self.assertIn('wrong repo',str(cm.exception))
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_override_unpullable_refused(self):
        remote=self.mkseed()
        bound=self.clone(remote,'bound'); nopull=self.clone(remote,'nopull')
        ws=self.mkws()
        self.bind(ws,bound)
        subprocess.run(['git','-C',str(nopull),'remote','remove','origin'],check=True,capture_output=True)
        with self.assertRaises(RuntimeError):
            self.bind(ws,nopull)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_no_override_path_unchanged_on_dirty_clone(self):
        remote=self.mkseed()
        bound=self.clone(remote,'bound')
        ws=self.mkws()
        self.bind(ws,bound)
        self.dirty_bound_clone(bound,remote)
        import io, contextlib
        class A: pass
        a=A(); a.root=str(ws); a.relay='Bruce-Yii/awrp'; a.relay_dir=None; a.project_id='proj-fb'; a.channel=self.CH; a.worker_endpoint=self.EP; a.task_id='task_fb'; a.run_id='run_fb'; a.lane=None; a.bound_by='t'
        buf=io.StringIO()
        with self.assertRaises(RuntimeError):
            with contextlib.redirect_stdout(buf): awrp.do_first_bind(a)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_override_absent_dir_refused(self):
        remote=self.mkseed()
        bound=self.clone(remote,'bound')
        ws=self.mkws()
        self.bind(ws,bound)
        with self.assertRaises(RuntimeError) as cm:
            self.bind(ws,self.tmp/'nope')
        self.assertIn('absent',str(cm.exception))
class TExecutionView(unittest.TestCase):
    CH='ch-ev'; EP='ep-ev'
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self):
        import os, stat
        def ro(action,path,exc):
            try: os.chmod(path,stat.S_IWRITE); action(path)
            except Exception: pass
        shutil.rmtree(self.tmp,onerror=ro)
    def git(self,repo,*args):
        cp=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr); return cp.stdout.strip()
    def mkrelay(self):
        remote=self.tmp/'r.git'; w=self.tmp/'w'
        self.git(self.tmp,'init','--bare',str(remote))
        self.git(self.tmp,'init','-b','main',str(w))
        self.git(w,'config','user.email','t@e'); self.git(w,'config','user.name','t')
        (w/'contexts').mkdir(exist_ok=True)
        awrp.write_new(w/'contexts'/'c.json',{'protocol':'awrp/0.1','context_id':'c','title':'t','created_at':awrp.now(),'description':''})
        awrp.write_new(w/'relay.json',{'protocol':'awrp/0.1','relay':'Bruce-Yii/awrp'})
        awrp.project_create(str(w),'proj-ev','EV',(self.CH,),None,'chatgpt')
        awrp.acquire_claim(str(w),self.CH,'chatgpt')
        self.git(w,'add','-A'); self.git(w,'commit','-m','seed'); self.git(w,'remote','add','origin',str(remote))
        self.git(w,'push','-u','origin','main'); self.git(remote,'symbolic-ref','HEAD','refs/heads/main')
        return remote
    def mktask(self,root,tid,project='proj-ev'):
        class A: pass
        a=A(); a.root=str(root); a.context_id='c'; a.task_id=tid; a.title=tid; a.goal='g'; a.worker='opencode'; a.created_by='chatgpt'; a.source_repo=None; a.source_issue=None
        a.channel_id=self.CH; a.lane_id=None; a.worker_endpoint=self.EP; a.project_id=project
        a.legacy=True
        awrp.create_task(a); return str(Path(root)/'tasks'/tid)
    def ev(self,td,typ,rid,run_state=None,phase='x',waiting_on=None,actor_role='coordinator',actor_id='chatgpt',fg=None):
        class A: pass
        a=A(); a.task_dir=td; a.type=typ; a.actor_role=actor_role; a.actor_id=actor_id
        a.recipient_role='worker'; a.recipient_id=self.EP; a.run_id=rid; a.new_run=False; a.state='working'; a.phase=phase
        a.waiting_on=waiting_on if waiting_on is not None else self.EP; a.run_state=run_state; a.summary='s'
        a.details_file=None; a.artifacts_file=None; a.approval_file=None
        a.causation_id=None; a.expected_head=None; a.expected_hash=None; a.claimant=None; a.fencing_generation=fg; a.idempotency_key=None; a.require_fresh=False; a.legacy_route=True
        awrp.emit(a)
    def dis(self,td,rid):
        self.ev(td,'DISPATCH',rid,run_state='dispatched',fg=1)
    def sess(self,name='s'):
        d=self.tmp/name; d.mkdir(exist_ok=True); return str(d)
    def acquire(self,root,remote):
        return awrp.execution_view_acquire(root,'Bruce-Yii/awrp',origin_url=str(remote))
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_acquire_creates_reuses_and_binds_end_to_end(self):
        remote=self.mkrelay()
        r1=self.acquire(self.sess('s1'),remote)
        self.assertTrue(r1['created']); self.assertTrue(r1['fresh'])
        self.assertEqual(Path(r1['relay_dir']).name,'relay')
        r2=self.acquire(self.sess('s1'),remote)
        self.assertFalse(r2['created'])
        self.assertEqual(r2['relay_dir'],r1['relay_dir'])
        td=self.mktask(r1['relay_dir'],'task_e2e')
        self.dis(td,'run_e2e')
        import io, contextlib
        class A: pass
        a=A(); a.root=self.sess('s1'); a.relay='Bruce-Yii/awrp'; a.relay_dir=r1['relay_dir']; a.project_id='proj-ev'; a.channel=self.CH; a.worker_endpoint=self.EP; a.task_id='task_e2e'; a.run_id='run_e2e'; a.lane=None; a.bound_by='t'
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): awrp.do_first_bind(a)
        r=json.loads(buf.getvalue())
        self.assertEqual(r['status'],'EXECUTE')
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_acquire_refuses_dirty_or_foreign_view_untouched(self):
        remote=self.mkrelay()
        s=self.sess('s2')
        r=self.acquire(s,remote)
        vd=Path(r['relay_dir'])
        (vd/'tasks'/'task_x'/'events'/'000001_ghost.json').parent.mkdir(parents=True,exist_ok=True)
        (vd/'tasks'/'task_x'/'events'/'000001_ghost.json').write_text('{"foreign":true}\n',encoding='utf-8')
        with self.assertRaises(RuntimeError) as cm:
            self.acquire(s,remote)
        self.assertIn('uncommitted bytes',str(cm.exception))
        self.assertTrue((vd/'tasks'/'task_x'/'events'/'000001_ghost.json').exists())
        shutil.rmtree(vd/'tasks'/'task_x')
        other=self.tmp/'other.git'
        self.git(self.tmp,'init','--bare',str(other))
        ow=self.tmp/'ow'; self.git(self.tmp,'init','-b','main',str(ow))
        self.git(ow,'config','user.email','t@e'); self.git(ow,'config','user.name','t')
        awrp.write_new(ow/'relay.json',{'protocol':'awrp/0.1','relay':'someone-else/repo'})
        s3=self.sess('s3')
        (Path(s3)/'relay').mkdir(parents=True)
        self.git(Path(s3)/'relay','init','-b','main')
        self.git(Path(s3)/'relay','config','user.email','t@e'); self.git(Path(s3)/'relay','config','user.name','t')
        (Path(s3)/'relay'/'relay.json').write_text(json.dumps({'protocol':'awrp/0.1','relay':'someone-else/repo'}),encoding='utf-8')
        self.git(Path(s3)/'relay','add','-A'); self.git(Path(s3)/'relay','commit','-m','x'); self.git(Path(s3)/'relay','remote','add','origin',str(other))
        with self.assertRaises(RuntimeError) as cm2:
            awrp.execution_view_acquire(s3,'Bruce-Yii/awrp',origin_url=str(other))
        self.assertIn('refusing a wrong repo',str(cm2.exception))
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_parallel_runs_progress_while_one_view_stale(self):
        remote=self.mkrelay()
        ra=self.acquire(self.sess('sa'),remote)
        tda=self.mktask(ra['relay_dir'],'task_a')
        self.dis(tda,'run_a')
        wa=Path(ra['relay_dir'])
        self.git(wa,'add','-A'); self.git(wa,'commit','-m','A dispatch'); self.git(wa,'push','origin','main')
        rival=self.tmp/'rival'; self.git(self.tmp,'clone',str(remote),str(rival))
        self.git(rival,'config','user.email','t@e'); self.git(rival,'config','user.name','t')
        (rival/'tasks'/'task_a'/'TASK.md').write_text('# rival projection\n',encoding='utf-8')
        self.git(rival,'add','-A'); self.git(rival,'commit','-m','rival'); self.git(rival,'push','origin','main')
        self.ev(tda,'ACK','run_a',run_state='working',phase='x',actor_role='worker',actor_id=self.EP)
        self.git(wa,'add','-A'); self.git(wa,'commit','-m','A unpublished ack')
        cp=subprocess.run(['git','-C',str(wa),'pull','--ff-only'],capture_output=True,text=True)
        self.assertNotEqual(cp.returncode,0)
        rb=self.acquire(self.sess('sb'),remote)
        tdb=self.mktask(rb['relay_dir'],'task_b')
        self.dis(tdb,'run_b')
        self.ev(tdb,'ACK','run_b',run_state='working',phase='x',actor_role='worker',actor_id=self.EP)
        self.ev(tdb,'HANDOFF','run_b',run_state='succeeded',phase='review',waiting_on='chatgpt',actor_role='worker',actor_id=self.EP)
        wb=Path(rb['relay_dir'])
        self.git(wb,'add','-A'); self.git(wb,'commit','-m','B handoff')
        self.git(wb,'push','origin','main')
        self.assertEqual(awrp.validate(tdb)['active_run_id'],None)
        self.assertEqual(awrp.audit_fencing(tdb)['authority']['status'],'proven')
        fresh=self.tmp/'fresh'
        self.git(self.tmp,'clone',str(remote),str(fresh))
        self.assertEqual(awrp.validate(fresh/'tasks'/'task_b')['runs']['run_b']['state'],'succeeded')
        before={p.name:awrp.artifact_fingerprint(str(p))['sha256'] for p in sorted((wa/'tasks'/'task_a'/'events').glob('*.json'))}
        self.assertIn('task_a',awrp.validate(wa/'tasks'/'task_a')['task']['task_id'])
        after={p.name:awrp.artifact_fingerprint(str(p))['sha256'] for p in sorted((wa/'tasks'/'task_a'/'events').glob('*.json'))}
        self.assertEqual(before,after)
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_release_gate(self):
        remote=self.mkrelay()
        r=self.acquire(self.sess('sr'),remote)
        vd=Path(r['relay_dir'])
        td=self.mktask(r['relay_dir'],'task_r')
        self.dis(td,'run_r')
        self.ev(td,'ACK','run_r',run_state='working',phase='x',actor_role='worker',actor_id=self.EP)
        self.git(vd,'add','-A'); self.git(vd,'commit','-m','unpublished ack')
        with self.assertRaises(RuntimeError) as cm:
            awrp.execution_view_release(self.sess('sr'),'task_r','run_r')
        self.assertIn('unpublished',str(cm.exception))
        self.assertTrue(vd.exists())
        self.git(vd,'push','origin','main')
        with self.assertRaises(RuntimeError) as cm2:
            awrp.execution_view_release(self.sess('sr'),'task_r','run_r')
        self.assertIn('not closed',str(cm2.exception))
        self.ev(td,'HANDOFF','run_r',run_state='succeeded',phase='review',waiting_on='chatgpt',actor_role='worker',actor_id=self.EP)
        self.git(vd,'add','-A'); self.git(vd,'commit','-m','handoff'); self.git(vd,'push','origin','main')
        out=awrp.execution_view_release(self.sess('sr'),'task_r','run_r')
        self.assertTrue(out['released'])
        self.assertFalse(vd.exists())
if __name__=='__main__': unittest.main()
