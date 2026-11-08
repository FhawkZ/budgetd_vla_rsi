"""Bounded native RPent CLI; only provider, deployment and evidence adapters."""
import argparse, fcntl, hashlib, json, os, shutil, signal, subprocess, sys, time, traceback
from pathlib import Path
from run_single_seed_panel import save,append,digest,proc_identity,cleanup_owned,gpu_snapshot,RENDER_BOOTSTRAP
ROOT=Path(__file__).resolve().parents[1]
def worker(cfg,index,out):
    from rpent.utils.rpc.http_rpc import HttpRpcClient
    from rpent_action_wait import install
    install(HttpRpcClient)
    import numpy as np
    from PIL import Image
    from rpent.utils.daemon import ProcessDaemon
    from robots.robotwin.env_client import RoboTwinEnvClient
    from robots.robotwin.vla_client import LingBotVLAClient
    import rpent.planner.base as planner_base
    from deepseek_audited_provider_v2 import build_model
    case=cfg['cases'][index]; runtime=Path(os.environ['RSI_RUNTIME_ROOT']); parent=out.parent
    key=Path(cfg['key_path']).read_text().strip()
    planner_base.build_api_model=lambda *a,**k:build_model(key,out/'api',parent/'reservations.jsonl',cfg['api_calls_total'],cfg['api_usd_cap'],8192)
    report=dict(status='running',case=case,vla_inferences=0,reset_rpc=0,started=time.time());save(out/'episode.json',report)
    daemons=[]; original_start=ProcessDaemon.start
    def start(d):
        for k in list(d.subprocess_env):
            if any(x in k.upper() for x in ('API_KEY','TOKEN','SECRET')):d.subprocess_env.pop(k)
        if d.name=='robotwin_env_server':
            d.cmd[1]=str(ROOT/'scripts/run_explore_single_seed_env_server.py');d.cwd=str(runtime/cfg['assets'])
            boot=out/'bootstrap';boot.mkdir();(boot/'sitecustomize.py').write_text(RENDER_BOOTSTRAP)
            d.subprocess_env.update(RSI_SINGLE_SEED_LAUNCH='single_seed_v1',RSI_OWNER_AUDIT_FILE=str(out/'owner-audit.json'),RSI_SEED_ATTEMPTS_FILE=str(out/'seed-attempts.jsonl'),RSI_VLA_RENDER_CHILD='1',ROBOTWIN_ASSETS_ROOT=d.cwd,ASSETS_PATH=d.cwd)
            d.subprocess_env['PYTHONPATH']=str(boot)+os.pathsep+str(ROOT/'scripts')+os.pathsep+d.subprocess_env.get('PYTHONPATH','')
        original_start(d);daemons.append(d)
        append(out/'owned-daemons.jsonl',dict(pid=d._proc.pid,starttime=proc_identity(d._proc.pid)[0],name=d.name))
    ProcessDaemon.start=start
    orig_reset=RoboTwinEnvClient.reset
    def reset(env,*a,**k):
        report['reset_rpc']+=1;assert report['reset_rpc']<=(2 if case['role']=='explore' else 1)
        value=orig_reset(env,*a,**k);s=env.last_info['episode_status'];assert s['actual_seed']==case['seed'];assert s['step_lim']==10000
        save(out/f"reset-{report['reset_rpc']}.json",{k:env.last_info[k] for k in ('episode_status','robot_state')});save(out/'episode.json',report);return value
    RoboTwinEnvClient.reset=reset
    orig_infer=LingBotVLAClient.infer
    def infer(model,obs):
        report['vla_inferences']+=1;assert report['vla_inferences']<=200;save(out/'episode.json',report)
        stem=out/f"infer-{report['vla_inferences']:04d}";images={}
        for camera,view in obs['views'].items():
            f=stem.with_name(stem.name+'-'+camera+'.png');Image.fromarray(np.asarray(view['rgb'])).save(f);images[camera]=digest(f)
        save(stem.with_suffix('.json'),dict(task_language=obs['task_language'],robot_state=obs['robot_state'],images=images))
        result=orig_infer(model,obs);np.save(stem.with_suffix('.npy'),result);return result
    LingBotVLAClient.infer=infer
    memory=parent/('memory-explore' if case['role']=='explore' else 'memory-'+case['role'])
    memory.mkdir(exist_ok=True)
    sys.argv=['rpent','--robot','robotwin','--planner','api','--model','deepseek:deepseek-flash','--max-tokens','8192','--reasoning-effort','high','--max-turns','100','--planner-timeout-s','1500','--task-name',case['task'],'--seed',str(case['seed']),'--task-config','demo_randomized','--max-episode-steps','10000','--robotwin-assets-path',str(runtime/cfg['assets']),'--vla-model-path',str(runtime/cfg['model']),'--cuda-device','0','--memory-profile','local','--memory-dir',str(memory),'--output-dir',str(out/'native')]
    if case['role']=='explore':sys.argv+=['--explore','--explore-attempts-per-session','1','--explore-sessions','1','--auto-merge-memory']
    try:
        from rpent.cli.main import main
        rc=main();report.update(status='completed' if rc in (None,0) else 'native_error',native_exit=rc)
    except BaseException as e:
        report.update(status='error',error=repr(e));traceback.print_exc()
    finally:
        report['daemon_exits_before']=[dict(name=d.name,pid=d._proc.pid,exit=d.poll()) for d in daemons]
        for d in daemons:d.stop()
        report['daemon_exits_after']=[dict(name=d.name,pid=d._proc.pid,exit=d.poll()) for d in daemons]
        report['finished']=time.time();save(out/'episode.json',report)
    return 0 if report['status']=='completed' and all(d.poll()==0 for d in daemons) else 1

def owner(cfg,protocol):
    root=Path(cfg['output']);root.mkdir(exist_ok=False,parents=True);shutil.copy2(protocol,root/'protocol.json')
    report=dict(status='running',started=time.time(),cases=[],protocol_sha256=digest(protocol));save(root/'report.json',report)
    lock=None
    try:
        for rel,sha in cfg['source_pins'].items():assert digest(rel)==sha,rel
        lock=open(cfg['lock'],'a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        snap=gpu_snapshot(0);assert not snap['compute_pids'] and snap['memory_mib']<128 and snap['utilization_percent']==0,snap
        disk=os.statvfs(root);assert disk.f_bavail*disk.f_frsize>max(100*2**30,disk.f_blocks*disk.f_frsize*.2)+cfg['expected_output_bytes'];assert disk.f_favail>100000
        os.environ['RSI_EXPECTED_GPU_PCI']=snap['pci_bus_id'];save(root/'preflight.json',dict(gpu=snap,free_bytes=disk.f_bavail*disk.f_frsize))
        for i,case in enumerate(cfg['cases']):
            if i==1:
                mem=root/'memory-explore';files=[p for sub in ('global','task-family','task-specific') for p in (mem/sub).rglob('*') if p.is_file()]
                save(root/'memory-publication.json',dict(files={str(p.relative_to(mem)):digest(p) for p in files},accepted_update=False))
                if not files:report['status']='closed_no_published_memory';break
                shutil.copytree(mem,root/'memory-reuse');(root/'memory-control').mkdir()
            out=root/f"{i:02d}-{case['role']}";out.mkdir();start=time.time()
            with (out/'worker.log').open('wb') as log:
                child=subprocess.Popen([sys.executable,__file__,'--protocol',str(protocol),'--worker',str(i),'--out',str(out)],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                save(out/'launch.json',dict(pid=child.pid,starttime=proc_identity(child.pid)[0]))
                exceeded=False
                while child.poll() is None and time.time()-start<1800:
                    if sum(p.stat().st_size for p in root.rglob('*') if p.is_file())>cfg['expected_output_bytes']:exceeded=True;break
                    time.sleep(2)
                if child.poll() is None:
                    os.killpg(child.pid,signal.SIGTERM)
                    try:child.wait(timeout=10)
                    except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
                cleanup=cleanup_owned(out/'owned-daemons.jsonl')
            row=dict(index=i,case=case,exit=child.returncode,elapsed=time.time()-start,cleanup=cleanup,output_cap_exceeded=exceeded)
            report['cases'].append(row);save(root/'report.json',report)
            if child.returncode or any(x['live'] for x in cleanup) or exceeded:report['status']='stopped_error';break
        else:report['status']='completed'
    except BaseException as e:report.update(status='owner_error',error=repr(e));traceback.print_exc()
    finally:
        Path(cfg['key_path']).unlink(missing_ok=True)
        report.update(finished=time.time(),cancelled=len(cfg['cases'])-len(report['cases']),accepted_update=False,strict_rsi=0)
        save(root/'report.json',report);save(root/'CLOSE.json',report)
        if lock:lock.close()
    return 0
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--protocol',required=True);p.add_argument('--worker',type=int);p.add_argument('--out');args=p.parse_args();protocol=Path(args.protocol).resolve();cfg=json.loads(protocol.read_text());assert cfg['status']=='FROZEN'
    sys.exit(worker(cfg,args.worker,Path(args.out)) if args.worker is not None else owner(cfg,protocol))
