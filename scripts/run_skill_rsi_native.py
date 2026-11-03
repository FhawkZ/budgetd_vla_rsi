"""Bounded, single-initialization Skill-RSI frozen fallback development.

Uses unmodified upstream API, skill/perception loaders, budgets, atom logger,
monitor, settling and scorer. Unlike native episode.run, does NOT perform an
extra materialization/reset/replay. Initial layout is evaluator-only evidence.
No author/caller/LLM, policy edit, hidden retry or privileged skill observation.
"""
import argparse
import fcntl
import hashlib
import importlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def dump(p,x):
    Path(p).parent.mkdir(parents=True,exist_ok=True)
    Path(p).write_text(json.dumps(x,indent=2,ensure_ascii=False))

def append(p,x):
    with Path(p).open('a') as f:f.write(json.dumps(x)+'\n');f.flush();os.fsync(f.fileno())

def classify(official,klass,infra):
    terminal=klass is not None and klass.split(':')[0] in ('safety_stop','timeout','budget_exhausted','infra')
    success=official is True and not terminal
    label=klass or ('success' if success else 'finished_but_failed')
    if klass is not None and success:label='success_after_'+klass
    return dict(success=None if infra else success, official_success=official,
                failure_class=label,
                infrastructure_error=infra is not None, infra_reason=infra)

def pin_render(pci):
    # Explicit deployment selection only: retain upstream RT/OptiX configuration.
    import sapien
    device=sapien.Device('cuda:0')
    assert device.pci_string.lower()[-7:]==pci.lower()[-7:]
    engine=importlib.import_module('sapien.wrapper.engine')
    old=engine.Scene
    engine.Scene=lambda:old([sapien.physx.PhysxCpuSystem(),sapien.render.RenderSystem(device)])
    import sapien.core as core
    class Renderer(sapien.pysapien.render.SapienRenderer):
        def __init__(self,**kwargs):super().__init__(device)
        def create_material(self):return sapien.render.RenderMaterial()
    sapien.SapienRenderer=core.SapienRenderer=Renderer
    return device.pci_string

def worker(cfg,index,out):
    case=cfg['cases'][index];runtime=Path(os.environ['RSI_RUNTIME_ROOT'])
    vendor=runtime/cfg['vendor'];native=runtime/cfg['native']
    out.mkdir(parents=True,exist_ok=False)
    started=time.time();row={'status':'running',**case,'qwen_calls':0,'vla_calls':0,
       'setup_attempts':0,'setup_completed':0,'clip_assignments':0,'clip_seconds':0.0,
       'accepted_updates':0,'classification':'frozen_published_skill_development'}
    dump(out/'episode.json',row)
    # Runtime path-only override occurs before perception_frozen imports CLIP_PATH.
    sys.path.insert(0,str(vendor/'runtime'))
    os.environ['RSI_REMOTE_ROOT']=str(out/'site')
    import common
    common.CLIP_PATH=str(runtime/cfg['clip_weight'])
    import episode as up
    import envadapter as env
    import perception_frozen as pf
    import observe
    import validate
    from api import API
    campaign=out/'campaign';campaign.mkdir();(campaign/'official').symlink_to(native,target_is_directory=True)
    camp={'campaign_id':cfg['id']+'-'+str(index),'task':case['task'],'scene':{'name':'clutter'},
          'limits':cfg['limits'],'monitor':cfg['monitor']}
    dump(campaign/'campaign.json',camp)
    # Goal/role vocabulary fixed before outcomes. Criterion is retained only for
    # this released code-only API (which upstream exposes); no author receives it.
    card=cfg['task_cards'][case['task']]
    pkg=vendor/'frozen_skills'/case['skill']
    lim,mon=common.limits_of(camp),common.monitor_of(camp)
    t=monitor=api=atom_log=None;wall=None;in_setup=True
    klass=infra=trace=result=official=None;settled=0;cleanup_error=None
    old_assign=pf.assign_roles
    def audited_assign(crops,roles):
        t0=time.perf_counter();rec={'roles':roles,'crops_sha256':[hashlib.sha256(c.tobytes()).hexdigest() for c in crops]}
        try:
            ans=old_assign(crops,roles);rec['output']=ans;return ans
        except BaseException as e:rec['error']=type(e).__name__+':'+str(e);raise
        finally:
            dt=time.perf_counter()-t0;rec['seconds']=dt;row['clip_assignments']+=1;row['clip_seconds']+=dt
            append(out/'clip.jsonl',rec)
    pf.assign_roles=audited_assign
    try:
        row['render_pci']=pin_render(os.environ['RSI_EXPECTED_GPU_PCI'])
        wall=up.Wall(lim['wall_seconds']);lines=up.LineBudget(lim['code_lines']);wall.start()
        row['setup_attempts']=1;append(out/'setup.jsonl',{'event':'enter','seed':case['seed'],'time':time.time()})
        t=env.setup(campaign,case['task'],case['seed'])
        row['setup_completed']=1;append(out/'setup.jsonl',{'event':'return','seed':case['seed'],'time':time.time()})
        lay=env.layout(t);common.dump(out/'initial-layout-evaluator-only.json',lay)
        row['layout_sha256']=env.layout_hash(lay);row['layout_replay_match']=None
        spec=env.task_spec(t,card);common.dump(out/'task-spec.json',spec)
        ns,atoms=validate.load_skills((pkg/'skills.py').read_text())
        detect=validate.load_perception((pkg/'perception.py').read_text(),pf.world_points)
        monitor=env.attach_monitor(t,lim,mon);api=API(t,out,lim,detect,spec)
        atom_log=up.AtomLog(ns,atoms,api,t,out);in_setup=False
        common.dump(out/'initial-proprioception.json',api._state())
        try:
            result=lines.run(ns['fallback'],api)
        except (env.SafetyStop,env.SimTimeout,env.BudgetExhausted,up.WallTimeout,common.InfraFailure):raise
        except Exception as e:
            result={'status':'error','failure_code':type(e).__name__+':'+str(e)[:300]};klass='atom_error';trace=traceback.format_exc()
        if klass is None and not (isinstance(result,dict) and 'status' in result and 'failure_code' in result):klass='atom_error'
        try:json.dumps(result)
        except Exception:result={'status':'error','failure_code':'return value not JSON'};klass='atom_error'
        wall.pause();settled=env.settle(t,lim['settle_seconds']);official=bool(t.check_success())
    except env.SafetyStop as e:klass='safety_stop:'+str(e);trace=traceback.format_exc()
    except env.SimTimeout:klass='timeout:sim';trace=traceback.format_exc()
    except env.BudgetExhausted as e:klass='budget_exhausted:'+str(e);trace=traceback.format_exc()
    except up.WallTimeout:
        klass='infra:setup_timeout' if in_setup else 'timeout:wall';infra='setup_timeout' if in_setup else None;trace=traceback.format_exc()
    except BaseException as e:
        infra=('setup:' if in_setup else 'runtime:')+type(e).__name__+':'+str(e)[:300]
        klass='infra:'+infra;trace=traceback.format_exc()
        if in_setup:append(out/'setup.jsonl',{'event':'raised','seed':case['seed'],'error':infra,'time':time.time()})
    finally:
        if wall:wall.pause()
        signal.setitimer(signal.ITIMER_REAL,0)
        if official is None and t is not None and infra is None:
            try:official=bool(t.check_success())
            except Exception:pass
        if t is not None:
            try:t.close_env()
            except BaseException as e:cleanup_error=type(e).__name__+':'+str(e)
        pf.assign_roles=old_assign
    if cleanup_error:infra='cleanup:'+cleanup_error;klass='infra:'+infra
    row.update(**classify(official,klass,infra),status='infrastructure_error' if infra else 'completed',
       self_report=result,traceback=trace,cleanup_error=cleanup_error,
       primitive_calls=api._calls_used() if api else 0,recorded_primitive_calls=len(api._trace) if api else 0,
       monitor_steps=monitor.steps if monitor else 0,dt=monitor.dt if monitor else None,
       sim_seconds=(monitor.steps-settled)*monitor.dt if monitor else None,
       settle_seconds=settled*monitor.dt if monitor else 0,
       safety_events=monitor.events if monitor else [],
       code_lines=lines.n if 'lines' in locals() else 0,
       wall_seconds=wall.spent if wall else None,process_seconds=time.time()-started,
       atom_evidence=atom_log.row() if atom_log else None)
    common.dump(out/'episode.json',row)
    return row

def verify(cfg):
    assert cfg['status']=='FROZEN' and cfg['qwen_max']==cfg['vla_max']==0
    assert cfg['attempts_max']==len(cfg['cases'])==4
    assert cfg['limits']['primitive_budget']==90 and cfg['limits']['sim_seconds']==90
    assert cfg['limits']['wall_seconds']==240 and cfg['limits']['code_lines']==30000
    assert cfg['limits']['settle_seconds']==2
    assert len({x['seed'] for x in cfg['cases']})==4
    for p,h in cfg['source_files'].items():assert sha(p)==h,p
    assert sha(Path(os.environ['RSI_RUNTIME_ROOT'])/cfg['clip_weight'])==cfg['clip_sha256']

def gpu_check(gpu):
    p=subprocess.run(['nvidia-smi','--query-gpu=index,uuid,pci.bus_id,memory.used,utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,check=True)
    rows=[x.strip().split(', ') for x in p.stdout.splitlines()];g=next(x for x in rows if int(x[0])==gpu)
    apps=subprocess.run(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader'],capture_output=True,text=True,check=True).stdout
    assert int(g[3])<128 and int(g[4])==0 and g[1] not in apps,(g,apps)
    return {'index':gpu,'uuid':g[1],'pci':g[2],'memory_mib':int(g[3])}

def parent(cfg,path):
    runtime=Path(os.environ['RSI_RUNTIME_ROOT']);out=runtime/'outputs'/cfg['id']
    assert not out.exists(),'one-shot output already exists'
    verify(cfg)
    lock=(runtime/f"locks/gpu{cfg['gpu']}.lock").open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    gpu=gpu_check(cfg['gpu']);disk=os.statvfs(runtime)
    assert disk.f_bavail*disk.f_frsize>max(100*2**30,.2*disk.f_blocks*disk.f_frsize)+cfg['expected_output_bytes'] and disk.f_favail>100000
    out.mkdir();dump(out/'protocol.json',cfg)
    report={'status':'running','protocol_sha256':sha(path),'planned':4,'attempted':0,'completed':0,'infrastructure_errors':0,'unstarted':4,'episodes':[],'gpu':gpu,'started_unix':time.time(),'qwen_calls':0,'vla_calls':0}
    dump(out/'report.json',report)
    try:
        for i,case in enumerate(cfg['cases']):
            if time.time()-report['started_unix']>cfg['total_wall_seconds']:raise TimeoutError('total wall cap')
            gpu_check(cfg['gpu'])
            env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(cfg['gpu']),CUDA_DEVICE_ORDER='PCI_BUS_ID',RSI_EXPECTED_GPU_PCI=gpu['pci'],PYTHONPATH='',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
            ep=out/f'case-{i:02d}'
            with (out/f'case-{i:02d}.log').open('w') as log:
                p=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--protocol',str(path),'--worker',str(i),'--output',str(ep)],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                report['attempted']+=1;report['unstarted']-=1;report['active_pid']=p.pid;dump(out/'report.json',report)
                timeout=False
                try:p.wait(timeout=min(cfg['process_wall_seconds'],max(1,cfg['total_wall_seconds']-(time.time()-report['started_unix']))))
                except subprocess.TimeoutExpired:
                    timeout=True;os.killpg(p.pid,signal.SIGTERM)
                    try:p.wait(timeout=8)
                    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=8)
            lingering=False
            try:os.killpg(p.pid,0);lingering=True
            except ProcessLookupError:pass
            if lingering:
                os.killpg(p.pid,signal.SIGTERM)
                time.sleep(0.2)
                try:os.killpg(p.pid,signal.SIGKILL)
                except ProcessLookupError:pass
            result=json.loads((ep/'episode.json').read_text()) if (ep/'episode.json').exists() else {}
            ok=p.returncode==0 and result.get('status')=='completed' and not timeout and not lingering
            report['episodes'].append({'case':case,'exit_code':p.returncode,'external_timeout':timeout,'lingering_owned_group':lingering,'result':result})
            report['active_pid']=None
            if ok:report['completed']+=1
            else:report['infrastructure_errors']+=1;report['status']='stopped_infrastructure';break
            dump(out/'report.json',report)
        else:report['status']='completed'
    except BaseException as e:
        report['status']='owner_error';report['error']=type(e).__name__+':'+str(e);report['traceback']=traceback.format_exc()
    finally:
        report['finished_unix']=time.time();report['GPU_allocation_seconds']=report['finished_unix']-report['started_unix']
        report['remaining_attempts_canceled']=4-report['attempted']
        dump(out/'report.json',report);dump(out/'CLOSE.json',{'status':'CLOSED','report_sha256':sha(out/'report.json'),'remaining_attempts_canceled':report['remaining_attempts_canceled']})
        fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
    return report

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--protocol',required=True,type=Path);ap.add_argument('--worker',type=int);ap.add_argument('--output',type=Path);ap.add_argument('--check',action='store_true');a=ap.parse_args();cfg=json.loads(a.protocol.read_text())
    if a.check:verify(cfg);print('frozen_sources_verified')
    elif a.worker is not None:worker(cfg,a.worker,a.output)
    else:parent(cfg,a.protocol.resolve())
