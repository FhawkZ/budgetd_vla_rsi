"""Read-only audit of closed official fixed50 panel; no simulator/model imports."""
import argparse, hashlib, json
from pathlib import Path
import numpy as np

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_text())
def save(p,x): Path(p).write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def audit(repo, runtime, source, output):
    output.mkdir(exist_ok=False,parents=True)
    cfg_path=repo/'configs/official-owner-fixed50-dev10-20261101-0300.json'
    cfg=read(cfg_path); report=read(source/'report.json'); closed=read(source/'CLOSE.json')
    assert sha(cfg_path)==report['protocol_sha256']=='8dd38f6cfa550af2b88ff3744c5c4796701d95e081f88e94ec1485bb3405ae2e'
    assert read(source/'protocol.json')==cfg
    assert report['status']==closed['status']=='completed'
    assert closed['unused_allowance']=='canceled'
    checked={}
    for rel,digest in cfg['source_sha256'].items():
        p=runtime/('vendor/RPent-'+cfg['rpent_commit'])/rel
        assert sha(p)==digest; checked[str(p)]=digest
    for rel,digest in cfg['native_runtime_sha256'].items():
        p=runtime/rel; assert sha(p)==digest; checked[str(p)]=digest
    for rel,digest in {**cfg['owner_adapter_sha256'],'scripts/run_official_owner_panel.py':cfg['runner_sha256'],'scripts/bounded_vla.py':cfg['interface_sha256']}.items():
        assert sha(repo/rel)==sha(source/'code'/Path(rel).name)==digest; checked[rel]=digest
    expected=[('stack_blocks_two',s) for s in range(100000,100005)]+[('handover_block',s) for s in range(100001,100006)]
    assert [(c['task'],c['seed']) for c in cfg['cases']]==expected
    assert len(report['episodes'])==10
    rows=[]; initial=[]; raw_manifest={}; rpc_seconds=0.; image_count=0; chunk_count=0
    for index,case in enumerate(cfg['cases']):
        folder=source/f"{index:02d}-{case['task']}-s{case['seed']}"
        ep=read(folder/'episode.json'); owner=read(folder/'owner-audit.json')
        assert ep==report['episodes'][index]['result']
        assert ep['status']=='completed' and ep['environment_reset_rpc']==1
        assert ep['qwen_calls']==ep['skill_updates']==ep['strict_rsi_rounds']==0
        assert all(x['returncode']==0 for x in ep['daemon_after_cleanup'])
        assert all(not x['live'] for x in report['episodes'][index]['cleanup'])
        assert ep['native_task_language']==ep['policy_task_language']==case['instruction']
        assert owner['status']=='process_exit'
        assert owner['phase_counts']['take_action']==ep['native_actions']
        chunks=[json.loads(l) for l in (folder/'chunks.jsonl').read_text().splitlines()]
        assert 1<=len(chunks)==ep['vla_inferences']<=24
        assert len(list(folder.glob('inference-*.json')))==len(chunks)
        last=0
        for i,chunk in enumerate(chunks,1):
            predfile=folder/f'inference-{i:03d}.npy'; rec=read(folder/f'inference-{i:03d}.json')
            selectedfile=folder/f'executed-prefix-{i:03d}.npy'
            pred=np.load(predfile,allow_pickle=False); selected=np.load(selectedfile,allow_pickle=False)
            r=chunk['result']; status=r['native_episode_status']
            assert rec['status']=='completed' and rec['index']==i and rec['task_language']==case['instruction']
            assert pred.shape==(50,16) and np.isfinite(pred).all()
            assert rec['actions_sha256']==sha(predfile)
            assert r['selected_actions_sha256']==sha(selectedfile)
            assert np.array_equal(selected,pred[:min(50,1200-last)])
            assert r['request']=={'action':'execute_vla_chunk','use_length':50}
            assert r['before']['native_actions']==last and r['before']['inferences']==i-1
            delta=r['after']['native_actions']-last
            assert 0<delta<=len(selected) and delta==r['executed_actions']
            assert status['take_action_cnt']==r['after']['native_actions'] and status['actual_seed']==case['seed'] and status['step_lim']==1200
            assert r['after']['inferences']==i
            assert rec['robot_state']==(ep['initial_robot_state'] if i==1 else chunks[i-2]['robot_state'])
            for camera,im in rec['images'].items():
                assert sha(folder/im['path'])==im['sha256'];image_count+=1
            if i==1: assert {k:v['sha256'] for k,v in rec['images'].items()}==ep['initial_image_sha256']
            last=r['after']['native_actions'];rpc_seconds+=rec['elapsed_seconds'];chunk_count+=1
        assert last==ep['native_actions']<=1200
        assert ep['native_eval_success']==chunks[-1]['result']['native_episode_status']['eval_success']
        assert ep['termination']==('native_success' if ep['native_eval_success'] else 'bounded_horizon')
        # Exact evidence index protects all raw files without copying images into Git.
        for p in sorted(folder.rglob('*')):
            if p.is_file():raw_manifest[str(p.relative_to(source))]={'sha256':sha(p),'bytes':p.stat().st_size}
        initial.append(dict(task=case['task'],seed=case['seed'],instruction=case['instruction'],initial_robot_state=ep['initial_robot_state'],initial_image_sha256=ep['initial_image_sha256']))
        rows.append(dict(task=case['task'],seed=case['seed'],native_success=ep['native_eval_success'],vla_inferences=ep['vla_inferences'],native_actions=last,wall_seconds=ep['wall_seconds'],status=ep['status'],termination=ep['termination'],daemon_exit_codes=[x['returncode'] for x in ep['daemon_after_cleanup']]))
    assert chunk_count==report['total_vla_inferences']==closed['inferences']==186
    assert sum(r['native_actions'] for r in rows)==report['total_native_actions']==9243
    summary=dict(status='passed',classification='closed_development_panel_evidence_audit',source=str(source),protocol_sha256=sha(cfg_path),cases=rows,aggregate={t:dict(success=sum(r['native_success'] for r in rows if r['task']==t),total=5) for t in ('stack_blocks_two','handover_block')},vla_inferences=chunk_count,native_actions=9243,qwen_calls=0,unused_inferences_canceled=240-chunk_count,inference_rpc_seconds=rpc_seconds,gpu_allocation_seconds=report['GPU_allocation_seconds'],verified_rgb_files=image_count,verified_prefixes=chunk_count,verified_raw_files=len(raw_manifest),raw_bytes=sum(x['bytes'] for x in raw_manifest.values()),accepted_updates=0,forgetting=None,strict_rsi=0,
      documentation_findings=['Frozen JSON retained stale inherited limitations/initialization/contrast/paired_reference text describing prior 4-case and language-only protocols. Executed cases, caps, scope, official suite assertion and receipts establish this 10-case fixed50 protocol. Frozen JSON preserved; do not interpret obsolete narratives as executed comparisons.','One RPC reset per episode; native owner phase counters include internal construction/reset calls, not extra evaluated episodes.'],limitations=['Development observed fractions only; all 10 cases excluded from final test.','No post-terminal stability evaluation; native counter not physical ticks or planner successes.','10 clean completions support this deployment on this panel, not causal proof of original RPC root cause or universal stability.','Fixed50 is a controller baseline, not an accepted learning update or adapted full paper algorithm.'])
    save(output/'report.json',summary);save(output/'raw-evidence-manifest.json',raw_manifest)
    save(output/'paired-input-references.json',dict(classification='development_input_only_no_outcomes',cases=initial))
    save(output/'fixed50-incumbent.json',dict(version='fixed50-owner-v1',source_protocol_sha256=sha(cfg_path),source_run=str(source),controller={'use_length':50,'horizon':1200,'max_vla_inferences':24},weights_frozen=True,source_sha256=checked,qualification='10 development completions; no universal stability claim',accepted_learning_update=False))
    print(json.dumps({k:v for k,v in summary.items() if k not in ('cases','limitations','documentation_findings')},indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--runtime',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();audit(a.repo,a.runtime,a.source,a.output)
