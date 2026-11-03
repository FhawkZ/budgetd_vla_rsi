"""Read-only audit of the frozen stage-program development experiment."""
import argparse, base64, hashlib, io, json, os
from pathlib import Path
import numpy as np
from PIL import Image
from stage_program import visible_frame, StageProgram

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_text())
def lines(p): return [json.loads(s) for s in Path(p).read_text().splitlines()]
def audit(root, repo, runtime):
    root, repo, runtime = map(Path, (root, repo, runtime))
    report, cfg, close = [read(root/n) for n in ('report.json','protocol.json','CLOSE.json')]
    assert report['status']=='completed' and close['status']=='CLOSED'
    assert sha(root/'protocol.json')==report['protocol_sha256']
    files={}
    def check(p, expected=None):
        h=sha(p)
        if expected is not None: assert h==expected,str(p)
        files[str(p)]={'path':str(p),'sha256':h,'bytes':p.stat().st_size}
        return h
    for rel,h in cfg['code_sha256'].items():
        check(repo/rel,h);check(root/'code'/Path(rel).name,h)
    progpath=runtime/cfg['stage_program']['path'];check(progpath,cfg['stage_program']['sha256']);program=read(progpath)
    totals=dict(vla_calls=0,prefixes=0,images=0,native_actions=0,setup_entries=0,resets=0,daemon_exit0=0,boundary_calls=0,stage_advances=0,collector_interval_seconds=0.0)
    episodes=[];pairdata={};requests=[]
    for i,case in enumerate(cfg['cases']):
        d=root/f"{i:02d}-{case['task']}-s{case['seed']}";e=read(d/'episode.json')
        assert e['status']=='completed' and all(e[k]==case[k] for k in ('task','seed','role','pair_index'))
        assert e['native_skill_attempts']==e['native_skill_actions']==0 and e['patch_attempts']==[]
        assert e['environment_reset_rpc']==1 and e['initial_reference_matches']
        assert e['native_task_language']==e['policy_task_language'] and e['native_episode_status']['actual_seed']==case['seed']
        for cam,h in e['initial_image_sha256'].items():check(d/f'initial-{cam}.png',h)
        attempt=lines(d/'seed-attempts.jsonl');beg=[x for x in attempt if x['event']=='setup_begin'];end=[x for x in attempt if x['event']=='setup_return']
        assert len(beg)==len(end)==2 and {x['phase'] for x in beg}=={'setup_task','reset'}
        assert all(x['requested_seed']==x['actual_argument_seed']==case['seed'] for x in beg+end)
        assert len(e['daemon_after_cleanup'])==2 and all(x['returncode']==0 for x in e['daemon_after_cleanup'])
        trace=lines(d/'language-trace.jsonl');start=[x for x in trace if x['status']=='started'];done=[x for x in trace if x['status']=='completed'];chunks=lines(d/'chunks.jsonl')
        assert len(trace)==2*len(done) and len(start)==len(done)==len(chunks)==e['vla_inferences']
        mode='native' if case['role']=='baseline' else 'successor_aware'
        ctrl=StageProgram(program,case['task'],e['native_task_language'],mode)
        bindex=0;prior=0
        for j,(st,tr,ch) in enumerate(zip(start,done,chunks),1):
            r=read(d/f'inference-{j:03d}.json');assert r['index']==j and r['status']=='completed'
            assert r['task_language']==e['native_task_language']
            obs={'robot_state':r['robot_state'],'task_language':r['task_language'],'views':{}}
            for cam,im in r['images'].items():
                check(d/im['path'],im['sha256']);obs['views'][cam]={'rgb':np.asarray(Image.open(d/im['path']).convert('RGB'))};totals['images']+=1
            frame=visible_frame(obs)
            if mode!='native' and j>1 and (j-1)%2==0 and ctrl.stage_index<len(ctrl.route['stages'])-1:
                bindex+=1;b=read(d/f'boundary-{bindex:03d}.json');req=d/f'boundary-{bindex:03d}-request.json';reply=d/f'boundary-{bindex:03d}-response.json'
                assert b['status']=='completed' and b['frame']==frame and b['vla_calls_completed']==j-1
                check(req,b['request_sha256']);body=read(req);ctx=json.loads(body['messages'][1]['content'][0]['text'])
                assert ctx==ctrl.decision_context(frame,j-1)
                imgs=[x['image_url']['url'] for x in body['messages'][1]['content'] if x['type']=='image_url'];assert len(imgs)==3
                for cam,u in zip(('head','left_wrist','right_wrist'),imgs):
                    a=np.asarray(Image.open(io.BytesIO(base64.b64decode(u.split(',',1)[1]))).convert('RGB'))
                    np.testing.assert_array_equal(a,obs['views'][cam]['rgb'])
                decision=json.loads(read(reply)['choices'][0]['message']['tool_calls'][0]['function']['arguments'])
                assert decision==b['decision'] and read(reply)['usage']==b['usage']
                event=ctrl.apply_decision(decision,frame,j-1);assert event==b['event'];totals['stage_advances']+=int(event['advanced'])
                requests.append((req,reply));totals['boundary_calls']+=1
            assert st['index']==tr['index']==j and st['program_mode']==tr['program_mode']==mode
            for t in (st,tr):
                assert all(t[k]==v for k,v in frame.items())
                assert t['native_language']==e['native_task_language'] and t['effective_language']==ctrl.effective_language() and t['stage_index']==ctrl.stage_index
            ctrl.complete_vla_call()
            pred=d/f'inference-{j:03d}.npy';check(pred,r['actions_sha256']);x=np.load(pred)
            prefix=d/f'executed-prefix-{j:03d}.npy';check(prefix,ch['result']['selected_actions_sha256'])
            np.testing.assert_array_equal(np.load(prefix),x[:min(50,cfg['horizon']-prior)])
            status=ch['result']['native_episode_status'];count=status['take_action_cnt']
            assert status['actual_seed']==case['seed'] and prior<count<=min(prior+50,cfg['horizon'])
            prior=count;totals['collector_interval_seconds']+=r['elapsed_seconds']
        assert bindex==e['qwen_calls'] and ctrl.events==e['stage_events'] and prior==e['native_actions']
        totals['vla_calls']+=len(done);totals['prefixes']+=len(chunks);totals['native_actions']+=prior;totals['setup_entries']+=2;totals['resets']+=1;totals['daemon_exit0']+=2
        row={k:e[k] for k in ('task','seed','role','vla_inferences','native_actions','native_eval_success','qwen_calls','wall_seconds')};row['final_stage']=ctrl.stage_index;episodes.append(row)
        pairdata.setdefault(case['pair_index'],{})[case['role']]=(e,d)
        for f in d.rglob('*'):
            if f.is_file() and not f.is_symlink():check(f)
    pairs=[]
    for idx,roles in sorted(pairdata.items()):
        a,ad=roles['baseline'];b,bd=roles['candidate']
        for key in ('initial_robot_state','initial_image_sha256','native_task_language'):assert a[key]==b[key]
        pairs.append(dict(pair=idx,task=a['task'],seed=a['seed'],baseline=a['native_eval_success'],candidate=b['native_eval_success'],gain=not a['native_eval_success'] and b['native_eval_success'],loss=a['native_eval_success'] and not b['native_eval_success'],initial_inputs_equal=True,first_prediction_equal=bool(np.array_equal(np.load(ad/'inference-001.npy'),np.load(bd/'inference-001.npy')))))
    qr=root.with_name(root.name+'-qwen');qual=root.with_name(root.name+'-qualification');qreport=read(qr/'report.json');requests.insert(0,(qual/'boundary-001-request.json',qual/'boundary-001-response.json'))
    usage=dict(generations=0,prompt_tokens=0,completion_tokens=0,generation_seconds=0.0)
    for n,(req,reply) in enumerate(requests,1):
        incoming=qr/'ledger'/f'{n:03d}-incoming.json';forwarded=qr/'ledger'/f'{n:03d}-forwarded.json';server=qr/'server'/f'{n:04d}-request.json'
        assert read(req)==read(incoming) and read(forwarded)==read(server)
        pa=read(qr/'ledger'/f'{n:03d}-audit.json');g=read(qr/'server'/f'{n:04d}-generation.json');sr=read(qr/'server'/f'{n:04d}-audit.json');response=read(qr/'ledger'/f'{n:03d}-response.json')
        assert pa['adaptation']['images_before']==pa['adaptation']['images_after']==g['image_count']==3
        assert g['usage']==pa['usage']==sr['usage']==response['usage']==read(reply)['usage']
        assert response==read(reply)
        usage['generations']+=1;usage['generation_seconds']+=g['generation_seconds']
        for k in ('prompt_tokens','completion_tokens'):usage[k]+=g['usage'][k]
    assert usage==qreport['usage'] and usage['generations']==totals['boundary_calls']+1
    assert totals['vla_calls']==report['total_vla_inferences']==close['used_vla']
    assert totals['native_actions']==report['native_actions'] and totals['boundary_calls']==report['qwen_calls']
    for f in qr.rglob('*'):
        if f.is_file() and not f.is_symlink():check(f)
    return dict(status='passed_evidence_audit_candidate_rejected',protocol_sha256=report['protocol_sha256'],program_sha256=cfg['stage_program']['sha256'],planned=12,completed=len(episodes),invalid=0,unstarted=0,pairs=pairs,episodes=episodes,totals=totals,qwen_usage=usage,gpu0_allocation_seconds=qreport['gpu_allocation_seconds'],gpu1_allocation_seconds=report['gpu1_lock_interval_seconds'],unused_vla_canceled=close['unused_canceled'],unused_qwen_canceled=qreport['unused_allowance_canceled'],verified_file_count=len(files),files=list(files.values()),accepted_updates=0,forgetting_after_update=None,strict_rsi=0,decision='Reject first B candidate: old success lost and no stage transition. Close candidate; no validation, rescue or budget refill. Explore concrete alternative.',limitations=['Development6pairs, not stable rates or independent validation','All candidate trajectories retained first-stage focus; no evidence of transition-mechanism benefit','Qwen descriptions are not contact ground truth; earlier boundary no vs later task success does not establish contemporaneous false negative','collector intervals include Qwen latency; not pure VLA RPC/kernel time','native counters not physics ticks;1200 horizon differs from official10000','No new model calls or simulation in this audit'])

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',required=True,type=Path);ap.add_argument('--output',required=True,type=Path);args=ap.parse_args()
    result=audit(args.root,Path(__file__).resolve().parents[1],os.environ['RSI_RUNTIME_ROOT'])
    args.output.mkdir(exist_ok=False);(args.output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('files','episodes')},indent=2))
