"""Once-only two-observation deployment equivalence check. No rollout, CLIP or LLM."""
import argparse,hashlib,json,os,time
from pathlib import Path

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(path):
    cfg=json.loads(Path(path).read_text());assert cfg['status']=='FROZEN' and cfg['detect_calls_max']==4 and len(cfg['cases'])==2
    for p,h in cfg['files'].items():assert sha(p)==h,p
    out=Path(cfg['output']);out.mkdir(parents=True,exist_ok=False);(out/'protocol.json').write_bytes(Path(path).read_bytes())
    report={'status':'running','protocol_sha256':sha(path),'cases':[],'detect_calls':0,'qwen_calls':0,'clip_calls':0,'vla_calls':0,'new_rollouts':0,'robot_actions':0,'accepted_updates':0};started=time.monotonic()
    try:
        import numpy as np
        from PIL import Image
        from skill_rsi_perception_worker import dependencies,plain
        from skill_rsi_perception_ipc import run_perception
        np,_,_,world_points,v=dependencies(cfg['upstream'])
        for i,c in enumerate(cfg['cases']):
            if time.monotonic()-started>cfg['total_wall_seconds']:raise TimeoutError('total CPU wall')
            case=out/f'case-{i:02d}';case.mkdir();source=Path(c['source']).read_text()
            packet=json.loads(Path(c['packet']).read_text());assert packet['classification']=='valid_development_feedback_not_evaluation'
            rgb=np.array(Image.open(c['rgb']).convert('RGB'));depth=np.load(c['depth'],allow_pickle=False);cal=json.loads(Path(c['calibration']).read_text())
            assert rgb.min()>0 or rgb.max()>0
            fn=v['load_perception'](source,world_points) # Only pinned published source, never author candidate.
            t=time.monotonic();report['detect_calls']+=1;reference=plain(fn(rgb,depth,cal),np);reference_seconds=time.monotonic()-t
            (case/'reference.json').write_text(json.dumps(reference,allow_nan=False))
            report['detect_calls']+=1;isolated=run_perception(source,rgb,depth,cal,cfg['upstream'],case/'isolated',timeout=15)
            row={'task':c['task'],'seed':packet['seed'],'reference_seconds':reference_seconds,'isolated_status':isolated['status'],'isolated_seconds':isolated['seconds'],'exit_code':isolated.get('exit_code'),'input_hashes':{k:sha(c[k]) for k in ['source','packet','rgb','depth','calibration']}}
            if isolated['status']!='result':row['comparison']='not_available';report['cases'].append(row);raise RuntimeError('isolated perception failed')
            actual=isolated['response']['result'];row.update(exact_equal=reference==actual,reference_sha256=sha(case/'reference.json'),components=len(reference[0]),table_z=reference[1])
            (case/'comparison.json').write_text(json.dumps(row,indent=2));report['cases'].append(row)
            if not row['exact_equal']:raise ValueError('output difference; no tuning/retry in this protocol')
        report['status']='completed_exact_development_equivalence'
    except Exception as e:report.update(status='closed_error',error=type(e).__name__+':'+str(e))
    finally:
        report.update(seconds=time.monotonic()-started,unused_detect_calls_cancelled=4-report['detect_calls'])
        (out/'report.json').write_text(json.dumps(report,indent=2));(out/'CLOSE.json').write_text(json.dumps({'state':'CLOSED','status':report['status'],'unused_cancelled':report['unused_detect_calls_cancelled']}))
    return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--protocol',required=True);a=p.parse_args();print(json.dumps(run(a.protocol),indent=2))
