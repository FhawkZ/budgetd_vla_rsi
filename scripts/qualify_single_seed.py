"""One-reset, zero-model single-seed deployment qualification. Never a task score."""
import argparse
import fcntl
import json
import os
import signal
import socket
import subprocess
import sys
import time
import traceback
from pathlib import Path
from run_paired_patch_validation import (ROOT, RENDER_BOOTSTRAP, save, digest,
                                        gpu_snapshot, proc_identity, append, cleanup_owned)


def canonical(value):
    return json.dumps(value,sort_keys=True,default=lambda x:x.tolist(),allow_nan=False)


def check(cfg, path, expected_sha):
    runtime=Path(os.environ['RSI_RUNTIME_ROOT'])
    assert digest(path)==expected_sha and cfg['status']=='frozen'
    assert socket.gethostname()==cfg['hostname']
    assert cfg['gpu']==1 and cfg['max_resets']==1 and cfg['max_native_setup_attempts']==2
    assert cfg['model_calls']==cfg['vla_inferences']==cfg['policy_actions']==0
    assert cfg['seed']==100006 and cfg['task']=='stack_blocks_two' and cfg['worker_wall_seconds']==300
    for rel,h in cfg['code_sha256'].items():assert digest(ROOT/rel)==h,rel
    for rel,h in cfg['source_sha256'].items():assert digest(runtime/rel)==h,rel
    assert digest(runtime/cfg['initial_reference'])==cfg['initial_reference_sha256']
    return runtime


def worker(cfg,out):
    import numpy as np
    from PIL import Image
    from rpent.utils.daemon import ProcessDaemon
    from rpent.dashboard.events import NullDashboardEventSink
    from robots.robotwin.robot_spec import _init_runtime
    from robots.robotwin.primitives import RoboTwinPrimitives
    from robots.robotwin.env_client import RoboTwinEnvClient
    runtime=Path(os.environ['RSI_RUNTIME_ROOT']);source=runtime/cfg['source'];daemons=[]
    original_start=ProcessDaemon.start;original_reset=RoboTwinEnvClient.reset
    report=dict(status='running',resets=0,model_calls=0,vla_inferences=0,policy_actions=0)
    def spawn(d):
        assert d.name=='robotwin_env_server','No model service allowed'
        assert Path(d.cmd[1]).name=='env_server.py'
        bootstrap=out/'bootstrap';bootstrap.mkdir()
        (bootstrap/'sitecustomize.py').write_text(RENDER_BOOTSTRAP)
        d.cwd=str(runtime/cfg['assets'])
        d.cmd[1]=str(ROOT/'scripts/run_single_seed_env_server.py')
        d.subprocess_env.update(PYTHONPATH=str(bootstrap)+os.pathsep+str(ROOT/'scripts')+os.pathsep+str(source),
                               RSI_VLA_RENDER_CHILD='1',RSI_EXPECTED_GPU_PCI=os.environ['RSI_EXPECTED_GPU_PCI'],
                               ROBOTWIN_ASSETS_ROOT=d.cwd,ASSETS_PATH=d.cwd,RSI_SINGLE_SEED_LAUNCH='single_seed_v1',
                               RSI_OWNER_AUDIT_FILE=str(out/'owner-audit.json'),
                               RSI_SEED_ATTEMPTS_FILE=str(out/'seed-attempts.jsonl'))
        original_start(d);daemons.append(d)
        ident=proc_identity(d._proc.pid);append(out/'owned.jsonl',dict(pid=d._proc.pid,starttime=ident[0],name=d.name))
    ProcessDaemon.start=spawn
    def once(env):
        report['resets']+=1
        assert report['resets']==1,'Reset retry prohibited'
        return original_reset(env)
    RoboTwinEnvClient.reset=once
    try:
        args=argparse.Namespace(task_name=cfg['task'],seed=cfg['seed'],task_config='demo_randomized',
                               max_episode_steps=1200,env_endpoint=None,vla_endpoint=None,
                               robotwin_assets_path=str(runtime/cfg['assets']),vla_model_path=None,
                               lingbot_robot_config=None,cuda_device='1',env_cuda_device=None,vla_cuda_device=None)
        _,kw=_init_runtime(args,out,NullDashboardEventSink(),{'env'})
        env=kw['env'];primitives=RoboTwinPrimitives(**kw,model=None,check_cancelled=lambda:None)
        obs=primitives._build_lingbot_observation()
        assert env.last_info['episode_status']['actual_seed']==cfg['seed']
        assert env.last_info['episode_status']['take_action_cnt']==0
        images={}
        for name,view in obs['views'].items():
            file=out/(name+'.png');Image.fromarray(np.asarray(view['rgb'])).save(file);images[name]=digest(file)
        actual=dict(initial_robot_state=obs['robot_state'],initial_image_sha256=images,native_task_language=obs['task_language'])
        ref=json.loads((runtime/cfg['initial_reference']).read_text())
        for key in actual:assert canonical(actual[key])==canonical(ref[key]),'Initial reference mismatch: '+key
        report.update(status='completed',initial=actual,native_status=env.last_info['episode_status'],historical_reference_equal=True)
    except BaseException as exc:
        report.update(status='failed',error=repr(exc),traceback=traceback.format_exc())
    finally:
        report['daemon_before_cleanup']=[dict(pid=d._proc.pid,returncode=d.poll()) for d in daemons]
        for d in reversed(daemons):
            try:d.stop(timeout=15)
            except Exception as exc:report.setdefault('cleanup_errors',[]).append(repr(exc))
        report['daemon_after_cleanup']=[dict(pid=d._proc.pid,returncode=d.poll()) for d in daemons]
        report['cleanup']=cleanup_owned(out/'owned.jsonl');save(out/'result.json',report)
    if report['status']!='completed' or any(d['returncode']!=0 for d in report['daemon_after_cleanup']):
        raise RuntimeError('Single-seed qualification failed; no retry')


def run(cfg,path,expected_sha,runtime):
    out=runtime/'outputs'/cfg['run_id'];assert not out.exists()
    v=os.statvfs(runtime);free=v.f_bavail*v.f_frsize;capacity=v.f_blocks*v.f_frsize
    reserve=max(100*2**30,.2*capacity)
    assert free>=reserve+cfg['projected_output_bytes'] and v.f_favail>100000
    lock=(runtime/'locks/gpu1.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    gpu=gpu_snapshot(1);assert gpu['memory_mib']<100 and not gpu['compute_pids']
    out.mkdir();save(out/'protocol.json',cfg);folder=out/'single-seed';folder.mkdir()
    import shutil
    code=out/'code';code.mkdir()
    for rel in cfg['code_sha256']:shutil.copy2(ROOT/rel,code/Path(rel).name)
    started=time.time();active=None
    report=dict(status='running',classification='initialization qualification only; not Agent score',
                protocol_sha256=expected_sha,started_unix=started,gpu_before=gpu,
                storage=dict(free_bytes=free,capacity_bytes=capacity,free_inodes=v.f_favail,reserve_bytes=reserve,
                             projected_output_bytes=cfg['projected_output_bytes']),model_calls=0,vla_inferences=0,policy_actions=0)
    save(out/'report.json',report)
    try:
        env=dict(os.environ,PYTHONPATH=str(runtime/cfg['source']),RPENT_REPO_ROOT=str(runtime/cfg['source']),
                 RPENT_RLINF_ROOT=str(runtime/cfg['rlinf']),CUDA_VISIBLE_DEVICES='1',CUDA_DEVICE_ORDER='PCI_BUS_ID',
                 RSI_EXPECTED_GPU_PCI=gpu['pci_bus_id'],NO_PROXY='127.0.0.1,localhost',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
        for key in ('OPENAI_API_KEY','ANTHROPIC_API_KEY','OPENAI_BASE_URL','ANTHROPIC_BASE_URL'):env.pop(key,None)
        with (folder/'worker.log').open('w') as log:
            active=subprocess.Popen([sys.executable,__file__,'--protocol',str(path),'--sha',expected_sha,'--worker','--out',str(folder)],
                                    env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            try:rc=active.wait(timeout=cfg['worker_wall_seconds'])
            except subprocess.TimeoutExpired:
                os.killpg(active.pid,signal.SIGTERM)
                try:active.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(active.pid,signal.SIGKILL);active.wait(timeout=5)
                rc=124
        report['worker_returncode']=rc
        report['result']=json.loads((folder/'result.json').read_text()) if (folder/'result.json').exists() else {'status':'missing'}
        assert rc==0,'Worker failed; no retry'
        rows=[json.loads(s) for s in (folder/'seed-attempts.jsonl').read_text().splitlines()]
        starts=[x for x in rows if x['event']=='setup_begin'];ends=[x for x in rows if x['event']=='setup_return']
        assert len(starts)==len(ends)==2
        assert [x['phase'] for x in starts]==['setup_task','reset']
        assert all(x['requested_seed']==x['actual_argument_seed']==cfg['seed'] for x in starts)
        assert not any(x['event'] in ('setup_error','failure_cleanup_error') for x in rows)
        audit=json.loads((folder/'owner-audit.json').read_text())
        assert audit['phase_counts']['_init_task_env_']==2 and audit['phase_counts'].get('take_action',0)==0
        report.update(status='passed_initialization_only',seed_attempts=rows,owner_audit=audit)
    except BaseException as exc:
        report.update(status='closed_failed',error=repr(exc),traceback=traceback.format_exc())
    finally:
        if active is not None and active.poll() is None:
            os.killpg(active.pid,signal.SIGKILL);active.wait(timeout=5)
        report['final_cleanup']=cleanup_owned(folder/'owned.jsonl')
        report.update(finished_unix=time.time(),gpu_allocation_seconds=time.time()-started,gpu_after=gpu_snapshot(1),accepted_updates=0,strict_rsi_rounds=0)
        save(out/'report.json',report);save(out/'CLOSE.json',dict(status=report['status'],unused_allowance='canceled; no retry',not_agent_score=True))
        lock.close()
    print(json.dumps({k:report[k] for k in ('status','gpu_allocation_seconds','model_calls','policy_actions','accepted_updates')}))


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--protocol',type=Path,required=True);p.add_argument('--sha',required=True)
    p.add_argument('--worker',action='store_true');p.add_argument('--out',type=Path);p.add_argument('--check',action='store_true')
    a=p.parse_args();path=a.protocol.resolve();cfg=json.loads(path.read_text());runtime=check(cfg,path,a.sha)
    if a.worker:worker(cfg,a.out)
    elif a.check:print('CPU protocol/source checks passed; no GPU used')
    else:run(cfg,path,a.sha,runtime)
