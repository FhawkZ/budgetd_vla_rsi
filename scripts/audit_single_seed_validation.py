"""Read-only evidence audit of a CLOSED single-seed panel; never runs policies."""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from audit_paired_validation import load, sha, lines, selection_status
from scene_validity import native_scene_invalid


def promotion_gate(expected, episodes, pairs):
    state = selection_status(expected, episodes)
    old = [p for p in pairs if p['task'] == 'stack_blocks_two']
    new = [p for p in pairs if p['task'] == 'handover_block']
    checks = {
        'all_policy_episodes_completed': state == 'complete_requires_full_predeclared_gate',
        'all_pairs_verified': len(pairs)*2 == len(expected) and all(p['initial_inputs_equal'] for p in pairs),
        'new_task_strict_gain': bool(new) and sum(p['candidate'] for p in new) > sum(p['baseline'] for p in new),
        'no_old_success_lost': bool(old) and not any(p['baseline'] and not p['candidate'] for p in old),
        'nonvacuous_old_baseline': any(p['baseline'] for p in old),
    }
    return {'checks': checks, 'promotable': all(checks.values()),
            'complete_case_descriptive_only': not checks['all_policy_episodes_completed']}


def audit(root, output):
    report, cfg, close = (load(root/n) for n in ('report.json','protocol.json','CLOSE.json'))
    assert report['status'] in ('completed','completed_with_censored')
    assert close['status'] == report['status'] and close['unused_allowance'] == 'canceled'
    assert sha(root/'protocol.json') == report['protocol_sha256']
    runtime, repo = root.parent.parent, Path(__file__).resolve().parents[1]
    for name, digest in cfg['new_code_sha256'].items():
        assert sha(root/'code'/Path(name).name) == sha(repo/name) == digest
    for patch in cfg['role_patches'].values():
        assert sha(runtime/patch['path']) == patch['sha256']
    patch = load(runtime/cfg['role_patches']['candidate']['path'])
    native = runtime/'software/envs/robotwin/lib/python3.11/site-packages/robotwin/envs/vector_env.py'
    native_sha = sha(native)
    episodes = [x['result'] for x in report['episodes']]
    selection_status(cfg['cases'], episodes)
    assert len(episodes) == len(cfg['cases'])
    totals = defaultdict(lambda:dict(attempted=0, completed=0, invalid=0, successes=0,
        vla=0,native_actions=0,skill_actions=0,rpc_seconds=0.,worker_seconds=0.))
    members, raw, skills, censored, seeds = defaultdict(dict), [], [], [], []
    prefixes = images = setup_count = reset_count = 0
    exits = Counter()
    for i,(entry,case) in enumerate(zip(report['episodes'],cfg['cases'])):
        ep = entry['result']; d = root/f"{i:02d}-{case['task']}-s{case['seed']}"
        assert load(d/'episode.json') == ep and entry['case'] == case
        assert all(ep[k] == case[k] for k in ('task','seed','role','pair_index'))
        assert ep['qwen_calls'] == ep['skill_updates'] == ep['strict_rsi_rounds'] == 0
        assert not any(x['live'] for x in entry['cleanup'])
        t = totals[ep['task']+'/'+ep['role']]
        t['attempted'] += 1; t['worker_seconds'] += ep['wall_seconds']
        rows = lines(d/'seed-attempts.jsonl')
        assert rows[0] == dict(event='adapter_installed',source_sha256=native_sha,max_native_setup_attempts=2,auto_resample=False)
        starts = [x for x in rows if x['event']=='setup_begin']
        assert len(starts) <= 2 and all(x['requested_seed']==x['actual_argument_seed']==ep['seed'] for x in starts)
        assert [x['attempt'] for x in starts] == list(range(1,len(starts)+1))
        owner = load(d/'owner-audit.json')
        assert owner['status']=='process_exit' and owner['phase_counts']['_init_task_env_']==len(starts)
        setup_count += len(starts); reset_count += ep['environment_reset_rpc']
        seeds.append(dict(index=i,task=ep['task'],seed=ep['seed'],role=ep['role'],status=ep['status'],attempts=len(starts),receipt_sha256=sha(d/'seed-attempts.jsonl')))
        exits.update(x['returncode'] for x in ep['daemon_after_cleanup'])
        if ep['status']=='scene_invalid':
            assert native_scene_invalid(ep, rows)
            assert ep['environment_reset_rpc']==0 and not list(d.glob('inference-*.json'))
            assert not lines(d/'chunks.jsonl') and not lines(d/'native-skills.jsonl')
            t['invalid']+=1
            censored.append(dict(index=i,task=ep['task'],seed=ep['seed'],role=ep['role'],native_error=rows[-1],success=None,worker_seconds=ep['wall_seconds']))
        else:
            assert ep['status']=='completed' and type(ep['native_eval_success']) is bool
            assert ep['environment_reset_rpc']==1 and len(starts)==2
            assert [x['phase'] for x in starts]==['setup_task','reset']
            assert [x['event'] for x in rows]==['adapter_installed','setup_begin','setup_return','setup_begin','setup_return']
            assert all(x['returncode']==0 for x in ep['daemon_after_cleanup'])
            assert ep['native_episode_status']['actual_seed']==ep['seed']
            assert ep['policy_task_language']==ep['native_task_language']
            t['completed']+=1; t['successes']+=ep['native_eval_success']
            t['vla']+=ep['vla_inferences']; t['native_actions']+=ep['native_actions']
            members[ep['pair_index']][ep['role']] = (ep,d)
            for camera,digest in ep['initial_image_sha256'].items():
                assert sha(d/f'initial-{camera}.png')==digest
            meta, chunks = sorted(d.glob('inference-*.json')), lines(d/'chunks.jsonl')
            assert len(meta)==len(chunks)==ep['vla_inferences'] <= cfg['max_vla_inferences_per_episode']
            chunk_actions=0
            for p,chunk in zip(meta,chunks):
                m=load(p); pred=p.with_suffix('.npy'); selected=d/f"executed-prefix-{m['index']:03d}.npy"
                assert m['status']=='completed' and m['task_language']==ep['native_task_language']
                assert sha(pred)==m['actions_sha256'] and sha(selected)==chunk['result']['selected_actions_sha256']
                a,b=np.load(selected),np.load(pred)
                assert chunk['result']['request']['use_length']==50
                assert len(a)==min(50,cfg['horizon']-chunk['result']['before']['native_actions'])
                assert np.array_equal(a,b[:len(a)])
                assert chunk['result']['native_episode_status']['actual_seed']==ep['seed']
                prefixes+=1; chunk_actions+=chunk['result']['executed_actions'];t['rpc_seconds']+=m['elapsed_seconds']
                for view in m['images'].values():
                    assert sha(d/view['path'])==view['sha256'];images+=1
            seen=set()
            for s in lines(d/'native-skills.jsonl'):
                assert ep['role']=='candidate' and s['rule_index'] not in seen
                seen.add(s['rule_index']); rule=s['rule'];arm=rule['arm']
                assert rule==patch['rules'][s['rule_index']] and rule['operation']=='set_gripper'
                before,after=s['before']['robot_state'],s['after']['robot_state']
                assert rule['gripper_min']<=before[arm+'_gripper']<=rule['gripper_max']
                assert s['result']['episode_status']['actual_seed']==ep['seed']
                assert s['after']['episode_status']['take_action_cnt']-s['before']['episode_status']['take_action_cnt']==s['native_actions']==10
                assert s['result']['gripper_val']==rule['gripper_target']==after[arm+'_gripper']==0
                before_q,after_q=np.array(before['qpos_target14']),np.array(after['qpos_target14'])
                idx=6 if arm=='left' else 13
                assert np.array_equal(np.delete(before_q,idx),np.delete(after_q,idx)) and after_q[idx]==0
                t['skill_actions']+=s['native_actions']
                skills.append(dict(task=ep['task'],seed=ep['seed'],arm=arm,gripper_before=before[arm+'_gripper'],gripper_after=after[arm+'_gripper'],already_at_target=before[arm+'_gripper']==0,native_actions=s['native_actions'],eef_translation_m=float(np.linalg.norm(np.array(after[arm+'_eef_pose'][:3])-np.array(before[arm+'_eef_pose'][:3])))))
            assert t['skill_actions']>=0 and len(seen)==ep['native_skill_attempts']==ep['patch_attempts']
            assert sum(s['native_actions'] for s in lines(d/'native-skills.jsonl'))==ep['native_skill_actions']
            assert chunk_actions+ep['native_skill_actions']==ep['native_actions']<=cfg['horizon']
        for p in sorted(d.rglob('*')):
            if p.is_file():raw.append(dict(path=str(p.relative_to(root)),bytes=p.stat().st_size,sha256=sha(p)))
    pairs=[]
    for idx,m in sorted(members.items()):
        assert set(m)=={'baseline','candidate'}
        b,bp=m['baseline'];c,cp=m['candidate']
        keys=('initial_robot_state','initial_image_sha256','native_task_language')
        ref=load(root/f'paired-inputs/pair-{idx:02d}.json')
        assert set(ref)==set(keys) and all(b[k]==c[k]==ref[k] for k in keys)
        assert {b['initial_reference_mode'],c['initial_reference_mode']}=={'recorded_first_member','matched_second_member'}
        assert np.array_equal(np.load(bp/'inference-001.npy'),np.load(cp/'inference-001.npy'))
        pairs.append(dict(pair_index=idx,task=b['task'],seed=b['seed'],baseline=b['native_eval_success'],candidate=c['native_eval_success'],initial_inputs_equal=True,first_predictions_equal=True))
    assert sum(t['vla'] for t in totals.values())==report['total_vla_inferences']==close['inferences']
    assert sum(t['native_actions'] for t in totals.values())==report['total_native_actions']
    from hcl_robotwin_adapter import pair_metrics
    rejected=None
    try:
        pair_metrics([e for e in episodes if e['role']=='baseline'],[e for e in episodes if e['role']=='candidate'],'handover_block',['stack_blocks_two'],[(c['task'],c['seed']) for c in cfg['cases'] if c['role']=='baseline'],behavior_changed=True)
    except ValueError as exc:rejected=str(exc)
    gate=promotion_gate(cfg['cases'],episodes,pairs)
    if censored:assert rejected is not None and not gate['promotable']
    result=dict(protocol_status=report['status'],protocol_sha256=report['protocol_sha256'],candidate_sha256=cfg['role_patches']['candidate']['sha256'],planned=len(cfg['cases']),attempted=len(episodes),completed=sum(e['status']=='completed' for e in episodes),scene_invalid=len(censored),unstarted=len(cfg['cases'])-len(episodes),planned_pairs=len(cfg['cases'])//2,complete_pairs=len(pairs),paired_results=pairs,by_task_role=dict(totals),censored=censored,promotion_gate=gate,hcl_adapter_rejection=rejected,initialization_receipts=seeds,native_setup_entries=setup_count,environment_reset_rpc=reset_count,daemon_exit_codes=dict(exits),vla_inferences=close['inferences'],canceled_vla=close['maximum']-close['inferences'],native_actions=report['total_native_actions'],gpu1_allocation_seconds=report['GPU_allocation_seconds'],qwen_calls=0,prediction_prefixes_verified=prefixes,inference_images_verified=images,source_hashes_verified=len(cfg['new_code_sha256'])+1,raw_files_hashed=len(raw),raw_bytes=sum(x['bytes'] for x in raw),skill_audit=skills,skills_already_at_target=sum(s['already_at_target'] for s in skills),accepted_shared_updates=0,forgetting_after_update=None,strict_rsi_rounds=0,decision='No promotion; end finite candidate pilot without replacements or new calls.',limitations=['Complete-case outcomes are descriptive; missing pairs cannot be removed to satisfy the frozen gate.','A tie on nine pairs does not establish statistical equivalence or population inefficacy.','No terminal-stability evaluation, causal settling control, or full paper numerical reproduction.','Native action counts are not physics ticks. Worker seconds include initialization and invalid attempts; GPU allocation is a process interval, not kernel time.'])
    output.mkdir(parents=True,exist_ok=False)
    (output/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'raw-manifest.json').write_text(json.dumps(raw,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('initialization_receipts','skill_audit','limitations','paired_results')}))


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();audit(a.root,a.output)
