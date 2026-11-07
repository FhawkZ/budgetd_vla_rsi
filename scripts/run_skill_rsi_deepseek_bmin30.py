"""B-min reduced-scale complete reuse panel: five fresh seeds per each of three tasks.

Twelve decisions per caller as in executed B-min, 30 planned attempts.
Not the published 50 seeds per task, nor an author-learning experiment.

All prior runners/configs remain unchanged. No generated Python is executed.
Explicit no-denoiser/single-init deployment differences remain in the protocol.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import run_skill_rsi_caller as caller
import run_skill_rsi_native_v2 as fallback
from run_phone_coherent_pair import (DURABLE, durable_dump, resources, tree_bytes)
from skill_rsi_owner_process import OwnedSession
from run_native_owner_pair import descendants, cleanup_known

SELF = Path(__file__).resolve()


def verify(cfg):
    assert cfg['status'] == 'FROZEN_DEEPSEEK_BMIN30'
    assert cfg['gpu'] == 3 and cfg['attempts_max'] == len(cfg['cases']) == 30
    assert cfg['max_api_calls'] == 180 and cfg['api_usd_cap'] == 8
    assert cfg['limits'] == dict(cfg['released_limits'], decisions_max=12)
    assert cfg['process_wall_seconds'] == 2520 and cfg['total_wall_seconds'] == 21600
    assert cfg['denoiser'] == 'none' and cfg['vla_max'] == 0
    for path,h in cfg['source_files'].items():
        assert fallback.sha(path) == h, path
    assert fallback.sha(Path(os.environ['RSI_RUNTIME_ROOT'])/cfg['clip_weight']) == cfg['clip_sha256']
    assert Path(cfg['output']).parent == DURABLE and Path(cfg['output']).resolve().parent == DURABLE.resolve()
    for i in range(0,30,2):
        a,b = cfg['cases'][i:i+2]
        assert all(a[k] == b[k] for k in ('task','skill','seed'))
        assert [a['mode'],b['mode']] == (['fallback','caller'] if i//2 % 2 == 0 else ['caller','fallback'])
    assert len({c['seed'] for c in cfg['cases']}) == 15
    assert sorted(sum(c['task']==task for c in cfg['cases']) for task in {c['task'] for c in cfg['cases']}) == [10,10,10]


def worker(cfg,index,out):
    if cfg['cases'][index]['mode'] == 'fallback':
        r = fallback.worker(cfg,index,out)
        r['deepseek_calls'] = 0
    else:
        import skill_rsi_caller_bridge as bridge
        from skill_rsi_deepseek_reuse_bridge import DeepSeekReuseBroker
        bridge.LocalQwenBroker = DeepSeekReuseBroker
        r = caller.worker(cfg,index,out)
        r['deepseek_calls'] = r.pop('qwen_calls')
        r['deepseek_usage'] = r.pop('qwen_usage')
        r['provider_note'] = 'official released deepseek_flash Adapter and native full task_spec; old worker field renamed'
    r['qwen_calls'] = 0
    r['accepted_updates'] = 0
    durable_dump(out/'episode.json',r)
    return r


def invalid(r,ep,exit_code,errors):
    if exit_code != 0 or errors or r.get('cleanup_error'):
        return False
    if not str(r.get('infra_reason','')).startswith('setup:UnStableError:'):
        return False
    if r.get('setup_attempts') != 1 or r.get('setup_completed') != 0:
        return False
    if any(r.get(k,0) != 0 for k in ('primitive_calls','deepseek_calls','vla_calls','clip_assignments')):
        return False
    rows = [json.loads(x) for x in (ep/'setup.jsonl').read_text().splitlines()]
    return [x['event'] for x in rows] == ['enter','raised'] and all(x['seed']==r['seed'] for x in rows)


def run(cfg,path):
    out=Path(cfg['output']); out.mkdir(exist_ok=False)
    t0=time.monotonic(); locks=[]
    report=dict(status='running',planned=30,attempted=0,completed=0,scene_invalid=0,
                unstarted=30,episodes=[],accepted_updates=0,qwen_calls=0,vla_calls=0,
                protocol_sha256=fallback.sha(path),started_unix=time.time())
    durable_dump(out/'protocol.json',cfg)
    try:
        runtime=Path(os.environ['RSI_RUNTIME_ROOT'])
        for name in ('deepseek-alignment.lock','gpu3.lock'):
            f=(runtime/'locks'/name).open('a');locks.append(f);fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        os.environ['RSI_DEEPSEEK_LEDGER']=str(out/'api-reservations.jsonl')
        os.environ['RSI_DEEPSEEK_MAX_CALLS']=str(cfg['max_api_calls'])
        os.environ['RSI_DEEPSEEK_USD_CAP']=str(cfg['api_usd_cap'])
        credential=Path(os.environ['RSI_DEEPSEEK_KEY_FILE'])
        assert credential.stat().st_mode & 0o077 == 0
        key=credential.read_text().strip();assert key.startswith('sk-') and '\n' not in key
        os.environ['DEEPSEEK_API_KEY']=key
        credential.unlink()  # credential survives only in this owned process tree
        for i,case in enumerate(cfg['cases']):
            if time.monotonic()-t0+cfg['process_wall_seconds'] > cfg['total_wall_seconds']:
                report['status']='stopped_wall';break
            gpu=resources(out,cfg['expected_output_bytes'])
            ep=out/f'case-{i:02d}';log=out/f'case-{i:02d}.log';known={};errors=[]
            env=dict(os.environ,CUDA_VISIBLE_DEVICES='3',CUDA_DEVICE_ORDER='PCI_BUS_ID',
                     RSI_EXPECTED_GPU_PCI=gpu['pci'],PYTHONPATH='',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
            started=time.monotonic()
            with log.open('xb') as f:
                p=subprocess.Popen([sys.executable,str(SELF),'--protocol',str(path),'--sha256',fallback.sha(path),
                                    '--worker',str(i),'--output',str(ep)],env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
                owned=OwnedSession(p)
                report.update(active={'index':i,'identity':owned.receipt},attempted=i+1,unstarted=29-i)
                durable_dump(out/'report.json',report)
                try:
                    while p.poll() is None:
                        for x in descendants(p.pid):known[(x['pid'],x['starttime'])]=x
                        if fallback.render_log_error(log.read_text(errors='replace')):raise RuntimeError('render_error')
                        if time.monotonic()-started>cfg['process_wall_seconds']:raise TimeoutError('process_wall')
                        time.sleep(.2)
                except BaseException as e:errors.append(type(e).__name__+':'+str(e))
                finally:
                    exit_before=p.poll();cleanup=owned.cleanup();extra=cleanup_known(known)
            if cleanup.get('live_remaining') or extra:errors.append('owned_residual')
            if any(x['state']!='Z' for x in cleanup.get('before',[])):errors.append('live_children_before_cleanup')
            if fallback.render_log_error(log.read_text(errors='replace')):errors.append('render_error')
            r=json.loads((ep/'episode.json').read_text()) if (ep/'episode.json').exists() else {}
            row=dict(case=case,result=r,exit_before_cleanup=exit_before,exit_code=p.returncode,
                     cleanup=cleanup,descendant_cleanup=extra,errors=errors,
                     process_interval_seconds=time.monotonic()-started)
            if not errors and p.returncode==0 and r.get('status')=='completed':
                row['classification']='policy_completed';report['completed']+=1
            elif invalid(r,ep,p.returncode,errors):
                row['classification']='scene_invalid';report['scene_invalid']+=1
            else:
                row['classification']='infrastructure_or_api_error';report['status']='stopped_infrastructure'
            report['episodes'].append(row);report['active']=None
            durable_dump(out/'report.json',report)
            if report['status']=='stopped_infrastructure':break
            if tree_bytes(out)>cfg['expected_output_bytes']:report['status']='stopped_output_cap';break
        else:report['status']='completed_with_censored' if report['scene_invalid'] else 'completed'
    except BaseException as e:
        report.update(status='owner_error',error=type(e).__name__+':'+str(e))
    finally:
        os.environ.pop('DEEPSEEK_API_KEY',None)
        report.update(finished_unix=time.time(),owner_interval_seconds=time.monotonic()-t0,
                      remaining_attempts_canceled=report['unstarted'],active=None)
        report['deepseek_calls']=sum(x['result'].get('deepseek_calls',0) for x in report['episodes'])
        report['remaining_api_calls_canceled']=cfg['max_api_calls']-report['deepseek_calls']
        durable_dump(out/'report.json',report)
        durable_dump(out/'CLOSE.json',dict(status='CLOSED',report_sha256=fallback.sha(out/'report.json')))
        for f in reversed(locks):f.close()
    return report


def main():
    a=argparse.ArgumentParser();a.add_argument('--protocol',type=Path,required=True)
    a.add_argument('--sha256',required=True);a.add_argument('--check',action='store_true')
    a.add_argument('--worker',type=int);a.add_argument('--output',type=Path);args=a.parse_args()
    assert fallback.sha(args.protocol)==args.sha256
    cfg=json.loads(args.protocol.read_text());verify(cfg)
    if args.check:print('frozen pins and paired budget verified');return
    if args.worker is not None:worker(cfg,args.worker,args.output)
    else:print(json.dumps({k:v for k,v in run(cfg,args.protocol.resolve()).items() if k not in ('episodes',)}))


if __name__=='__main__':main()
