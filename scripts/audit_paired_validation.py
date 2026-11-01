"""Read-only audit of the frozen paired validation. No rollout or model calls."""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lines(path):
    return [json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []


def selection_status(expected, episodes):
    """A censored panel cannot become an efficacy failure or pass by dropping rows."""
    keys = [(x['task'], x['seed'], x['role']) for x in episodes]
    want = [(x['task'], x['seed'], x['role']) for x in expected]
    if len(keys) != len(set(keys)) or keys != want[:len(keys)]:
        raise ValueError('duplicate, reordered, or foreign episode')
    if len(keys) != len(want) or any(x['status'] != 'completed' for x in episodes):
        return 'inconclusive_incomplete_panel_no_promotion'
    return 'complete_requires_full_predeclared_gate'


def audit(root, output):
    report = load(root/'report.json')
    cfg = load(root/'protocol.json')
    close = load(root/'CLOSE.json')
    assert report['status'] in ('completed', 'closed_failed')
    assert close['status'] == report['status']
    assert sha(root/'protocol.json') == report['protocol_sha256']
    assert sha(root/'code/run_paired_patch_validation.py') == cfg['runner_sha256']
    runtime = root.parent.parent
    for patch in cfg['role_patches'].values():
        assert sha(runtime/patch['path']) == patch['sha256']
    episodes = [row['result'] for row in report['episodes']]
    status = selection_status(cfg['cases'], episodes)
    totals = defaultdict(lambda: dict(episodes_completed=0, successes=0, vla=0,
                                     native_actions=0, skill_actions=0, rpc_seconds=0., worker_seconds=0.))
    pairs = defaultdict(dict)
    skills, rows, raw, censored = [], [], [], []
    prefixes = images = exits = 0
    initializations = 0
    for i, ep in enumerate(episodes):
        case = cfg['cases'][i]
        d = root/f"{i:02d}-{case['task']}-s{case['seed']}"
        assert load(d/'episode.json') == ep
        assert all(ep[k] == case[k] for k in ('task', 'seed', 'role', 'pair_index'))
        assert ep['qwen_calls'] == ep['skill_updates'] == ep['strict_rsi_rounds'] == 0
        assert ep['environment_reset_rpc'] == 1
        assert all(x['returncode'] == 0 for x in ep['daemon_after_cleanup'])
        exits += len(ep['daemon_after_cleanup'])
        oa = load(d/'owner-audit.json')
        initializations += oa['phase_counts']['_init_task_env_']
        if ep['status'] != 'completed':
            assert ep['native_eval_success'] is None
            censored.append(dict(index=i, task=ep['task'], seed=ep['seed'], role=ep['role'],
                                 native_actions=ep['native_actions'], vla=ep['vla_inferences'],
                                 error=ep['error'], worker_seconds=ep['wall_seconds'],
                                 construction_entries=oa['phase_counts']['_init_task_env_']))
            assert not list(d.glob('inference-*.json'))
        else:
            assert type(ep['native_eval_success']) is bool
            pairs[ep['pair_index']][ep['role']] = (ep, d)
            t = totals[ep['role']]
            t['episodes_completed'] += 1
            t['successes'] += ep['native_eval_success']
            t['vla'] += ep['vla_inferences']
            t['native_actions'] += ep['native_actions']
            t['worker_seconds'] += ep['wall_seconds']
            for camera, digest in ep['initial_image_sha256'].items():
                assert sha(d/f'initial-{camera}.png') == digest
            meta = sorted(d.glob('inference-*.json'))
            chunks = lines(d/'chunks.jsonl')
            assert len(meta) == len(chunks) == ep['vla_inferences']
            chunk_actions = 0
            for p, chunk in zip(meta, chunks):
                x = load(p)
                assert x['status'] == 'completed' and x['task_language'] == ep['native_task_language']
                predpath = p.with_suffix('.npy')
                assert sha(predpath) == x['actions_sha256']
                selected_path = d/f"executed-prefix-{x['index']:03d}.npy"
                assert sha(selected_path) == chunk['result']['selected_actions_sha256']
                selected, pred = np.load(selected_path), np.load(predpath)
                assert np.array_equal(selected, pred[:len(selected)])
                assert chunk['result']['native_episode_status']['actual_seed'] == ep['seed']
                prefixes += 1
                chunk_actions += chunk['result']['executed_actions']
                t['rpc_seconds'] += x['elapsed_seconds']
                for view in x['images'].values():
                    assert sha(d/view['path']) == view['sha256']
                    images += 1
            for x in lines(d/'native-skills.jsonl'):
                arm = x['rule']['arm']
                before, after = x['before']['robot_state'], x['after']['robot_state']
                assert x['result']['episode_status']['actual_seed'] == ep['seed']
                assert x['after']['episode_status']['take_action_cnt'] - x['before']['episode_status']['take_action_cnt'] == x['native_actions']
                t['skill_actions'] += x['native_actions']
                skills.append(dict(task=ep['task'], seed=ep['seed'], arm=arm,
                                   gripper_before=before[arm+'_gripper'], gripper_after=after[arm+'_gripper'],
                                   target=x['rule']['gripper_target'], native_actions=x['native_actions'],
                                   eef_translation_m=float(np.linalg.norm(np.array(after[arm+'_eef_pose'][:3])-np.array(before[arm+'_eef_pose'][:3])))))
            assert chunk_actions + ep['native_skill_actions'] == ep['native_actions']
        for p in sorted(d.rglob('*')):
            if p.is_file():
                raw.append(dict(path=str(p.relative_to(root)), bytes=p.stat().st_size, sha256=sha(p)))
    for idx, members in sorted(pairs.items()):
        if set(members) != {'baseline', 'candidate'}:
            continue
        b, bp = members['baseline']; c, cp = members['candidate']
        for key in ('initial_robot_state', 'initial_image_sha256', 'native_task_language'):
            assert b[key] == c[key], (idx, key)
        assert {b['initial_reference_mode'], c['initial_reference_mode']} == {'recorded_first_member', 'matched_second_member'}
        ref = load(root/f'paired-inputs/pair-{idx:02d}.json')
        assert 'native_eval_success' not in ref
        assert np.array_equal(np.load(bp/'inference-001.npy'), np.load(cp/'inference-001.npy'))
        rows.append(dict(pair_index=idx, task=b['task'], seed=b['seed'],
                         baseline=b['native_eval_success'], candidate=c['native_eval_success'],
                         initial_inputs_equal=True, first_predictions_equal=True))
    assert sum(t['vla'] for t in totals.values()) == report['total_vla_inferences'] == close['inferences']
    assert sum(t['native_actions'] for t in totals.values()) == report['total_native_actions']
    from hcl_robotwin_adapter import pair_metrics
    hcl_rejection = None
    if status.startswith('inconclusive'):
        try:
            pair_metrics([e for e in episodes if e['role']=='baseline'],
                         [e for e in episodes if e['role']=='candidate'],
                         'handover_block', ['stack_blocks_two'],
                         [(c['task'], c['seed']) for c in cfg['cases'] if c['role']=='baseline'],
                         behavior_changed=True)
        except ValueError as exc:
            hcl_rejection = str(exc)
        assert hcl_rejection is not None, 'Incomplete panel reached selection gate'
    result = dict(status=status, protocol_status=report['status'], protocol_sha256=report['protocol_sha256'],
                  completed_episodes=sum(e['status']=='completed' for e in episodes),
                  censored_episodes=len(censored), unstarted_episodes=len(cfg['cases'])-len(episodes),
                  paired_results=rows, by_role=dict(totals), censored=censored,
                  vla_inferences=report['total_vla_inferences'], qwen_calls=0,
                  native_actions=report['total_native_actions'], gpu1_allocation_seconds=report['GPU_allocation_seconds'],
                  canceled_vla=close['maximum']-close['inferences'],
                  one_reset_rpc_per_started_episode=True, native_initialization_entries=initializations,
                  initialization_entry_caveat='Includes construction preflight and hidden retries; not evaluated episodes or motor-step count.',
                  prediction_prefixes_verified=prefixes, inference_image_hashes_verified=images,
                  clean_daemon_exits=exits, raw_files_hashed=len(raw), raw_bytes=sum(x['bytes'] for x in raw),
                  skill_audit=skills, hcl_adapter_rejected_incomplete_panel=hcl_rejection,
                  accepted_shared_updates=0, forgetting_after_accepted_update=None, strict_rsi_rounds=0,
                  decision='Do not promote; efficacy unresolved due to scene-construction censoring. No refill or replacement.',
                  limitations=['Only three old-task pairs completed; both 1/3. No new-task validation outcome.',
                               'No terminal stability evaluation, significance claim, or full paper reproduction.',
                               'Native actions are not physical simulation ticks; one reset RPC can contain multiple setup attempts.',
                               'Partial tie cannot establish full candidate failure; invalid case is not policy failure.'])
    output.mkdir(parents=True, exist_ok=False)
    (output/'report.json').write_text(json.dumps(result, indent=2)+'\n')
    (output/'raw-manifest.json').write_text(json.dumps(raw, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('censored','skill_audit','limitations')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    audit(args.root, args.output)
