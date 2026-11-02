"""Finite CPU metadata/source audit and fake-transport probes. Never loads weights.
Only the fixed DEVELOPMENT panel is read; no validation or test trajectories.
"""
import argparse,ast,copy,hashlib,json
from pathlib import Path
import numpy as np
import yaml

RPENT='a744bd5f128ebef3cb8c6736cf7cd98adff681f1'
MODEL_REV='e727b46cd220b66981ea4d2fd9ba84adc189e2cc'
DEV='official-owner-fixed50-dev10-20261101-0300'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def method(path,name):
    text=path.read_text(); found=[n for n in ast.walk(ast.parse(text)) if isinstance(n,ast.FunctionDef) and n.name==name]
    assert len(found)==1,(str(path),name)
    return found[0],ast.get_source_segment(text,found[0])
def payload_digest(p):
    return hashlib.sha256(json.dumps(p,sort_keys=True,default=lambda x:x.tolist()).encode()).hexdigest()

def audit(runtime,output):
    repo=Path(__file__).resolve().parents[1];vendor=runtime/'vendor'/('RPent-'+RPENT)
    site=runtime/'software/envs/robotwin/lib/python3.11/site-packages'
    model=runtime/'models/LingBot-VLA-RoboTwin-EEF-e727b46c'
    manifest=load(repo/'configs/lingbot-model-manifest.json');assert manifest['sha']==MODEL_REV
    entries={x['rfilename']:x for x in manifest['siblings']}
    names=['README.md','config.json','lingbotvla_cli.yaml','configs/robot_configs/robotwin_eef.yaml','norm_stats/robotwin_eef.json']
    meta=[]
    for name in names:
        path=model/name;raw=path.read_bytes();entry=entries[name]
        assert len(raw)==entry['size']
        assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==entry['blobId']
        meta.append(dict(path=str(path),bytes=len(raw),sha256=sha(path),git_blob=entry['blobId']))
    cfg=yaml.safe_load((model/'lingbotvla_cli.yaml').read_text());norm=load(model/'norm_stats/robotwin_eef.json')
    panel=load(vendor/'robots/robotwin/eval/demo_randomized.json')
    notes=load(vendor/'docs/_static/leaderboard/results.json')
    note=next(x for x in notes['footer_notes'] if x['id']=='vla-robotwin')
    source_specs=[(vendor/'robots/robotwin/vla_client.py',['infer']),
        (vendor/'robots/robotwin/primitives.py',['_build_lingbot_observation','lingbot_act','set_gripper']),
        (vendor/'robots/robotwin/rlinf_env.py',['_robot_state','_episode_status','get_task_language']),
        (site/'robotwin/envs/robot/robot.py',['_trans_endpose','get_left_arm_real_jointState','get_left_gripper_val','get_normal_real_gripper_val','set_gripper']),
        (site/'deploy/lingbot_vla_policy.py',['infer']),
        (repo/'scripts/bounded_vla.py',['status','_observation','dispatch']),
        (repo/'scripts/bounded_controller.py',['image_parts','feedback']),
        (repo/'scripts/run_model_bounded_vla.py',[])]
    sources=[]
    for p,fnames in source_specs:
        snippets=[]
        for name in fnames:
            n,text=method(p,name);snippets.append(dict(name=name,line=n.lineno,end_line=n.end_lineno,source=text))
        sources.append(dict(path=str(p),sha256=sha(p),snippets=snippets))
    # Execute exactly the upstream payload-building method with an inert base.
    n,_=method(vendor/'robots/robotwin/vla_client.py','infer')
    class Capture:
        def predict(self,payload):
            self.payload=copy.deepcopy(payload)
            return {'action':np.zeros((50,16),dtype=np.float64)}
    cls=ast.ClassDef(name='ProbeClient',bases=[ast.Name(id='Capture',ctx=ast.Load())],keywords=[],body=[n],decorator_list=[])
    tree=ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[]))
    scope={'Capture':Capture,'np':np,'Any':object};exec(compile(tree,'<exact-native-infer>','exec'),scope)
    client=scope['ProbeClient']()
    observation={'views':{k:{'rgb':np.zeros((2,2,3),dtype=np.uint8),'depth':np.zeros((2,2))} for k in ['head','left_wrist','right_wrist']},'robot_state':{'left_eef_pose':[1.,2.,3.,1.,0.,0.,0.],'right_eef_pose':[4.,5.,6.,1.,0.,0.,0.],'left_gripper':0.,'right_gripper':1.,'qpos_target14':[0.]*14,'arm_qpos_real12':[0.]*12},'task_language':'native synthetic task','episode_status':{'eval_success':False},'object_pose':[9.,9.,9.]}
    def transport(obs):
        out=client.infer(copy.deepcopy(obs));assert out.shape==(50,16)
        return copy.deepcopy(client.payload)
    base=transport(observation);assert set(base)=={'observation.state','task','observation.images.cam_high','observation.images.cam_left_wrist','observation.images.cam_right_wrist'}
    probes=[]
    variants=[]
    x=copy.deepcopy(observation);x['robot_state']['left_gripper']=.25;variants.append(('cached_gripper_command',x,True))
    x=copy.deepcopy(observation);x['robot_state']['left_eef_pose'][0]+=.1;variants.append(('measured_eef',x,True))
    x=copy.deepcopy(observation);x['robot_state']['arm_qpos_real12']=[.5]*12;x['robot_state']['qpos_target14']=[.3]*14;variants.append(('arm_joint_and_target_fields',x,False))
    x=copy.deepcopy(observation);x['robot_state']['synthetic_actual_finger_qpos']=[.2,.2];variants.append(('unpublished_actual_finger_field',x,False))
    x=copy.deepcopy(observation);x['views']['head']['depth'][:]=5;x['object_pose']=[1.,1.,1.];x['episode_status']['eval_success']=True;variants.append(('depth_object_oracle_and_score',x,False))
    x=copy.deepcopy(observation);x['views']['head']['rgb'][:]=128;variants.append(('rgb',x,True))
    x=copy.deepcopy(observation);x['task_language']='another synthetic task';variants.append(('native_language',x,True))
    for name,obs,expected in variants:
        payload=transport(obs);changed=payload_digest(payload)!=payload_digest(base);assert changed==expected
        probes.append(dict(name=name,payload_changed=changed,payload_sha256=payload_digest(payload),expected=expected))
    # Only predeclared existing development episodes; no model generation or physics.
    dev=runtime/'outputs'/DEV;devcfg=load(dev/'protocol.json');report=load(dev/'report.json')
    assert len(devcfg['cases'])==10 and report['status']=='completed'
    cases=[];observations=0;input_manifest=[]
    for i,case in enumerate(devcfg['cases']):
        d=dev/f"{i:02d}-{case['task']}-s{case['seed']}";ep=load(d/'episode.json')
        assert ep['status']=='completed' and ep['seed']==case['seed']
        rms=[];maxabs=[]
        for p in sorted(d.glob('inference-*.json')):
            x=load(p);s=x['robot_state'];target=np.delete(np.asarray(s['qpos_target14']),[6,13]);real=np.asarray(s['arm_qpos_real12'])
            assert target.shape==real.shape==(12,)
            err=target-real;rms.append(float(np.sqrt(np.mean(err**2))));maxabs.append(float(np.max(np.abs(err))));observations+=1
            input_manifest.append(dict(path=str(p),sha256=sha(p)))
        assert len(rms)==ep['vla_inferences']
        cases.append(dict(task=case['task'],seed=case['seed'],success=ep['native_eval_success'],observations=len(rms),joint_target_actual_RMS_rad_median=float(np.median(rms)),joint_target_actual_RMS_rad_max=max(rms),joint_target_actual_absolute_rad_max=max(maxabs)))
    assert observations==report['total_vla_inferences']==186
    fields=[
      dict(field='three RGB cameras',source='render_camera',kind='rendered sensor evidence',vla=True,controller='initial or explicit observe',contact_truth=False),
      dict(field='left/right_eef_pose',source='articulation link global_pose transformed into EEF frame',kind='measured simulator robot pose',vla=True,controller='full robot_state when observed',contact_truth=False),
      dict(field='left/right_tcp_pose',source='same link pose with TCP offset',kind='measured simulator robot pose',vla=False,controller='full robot_state when observed',contact_truth=False),
      dict(field='left/right_gripper',source='cached requested command',kind='command, not measured aperture',vla=True,controller='full robot_state when observed',contact_truth=False),
      dict(field='qpos_target14',source='joint drive targets + cached gripper command',kind='command',vla=False,controller='full robot_state when observed',contact_truth=False),
      dict(field='arm_qpos_real12',source='articulation get_qpos excluding gripper',kind='measured simulator arm joints',vla=False,controller='full robot_state when observed',contact_truth=False),
      dict(field='depth',source='available native rendering helper',kind='rendered sensor; excluded by RGB-only builder',vla=False,controller=False,contact_truth=False),
      dict(field='actual finger aperture/contact/object pose',source='not exposed by current bounded observation',kind='unavailable; object/contact simulator truth would be privileged',vla=False,controller=False,contact_truth=False),
      dict(field='eval_success',source='native task scorer',kind='privileged task outcome',vla=False,controller='external termination only in reduced runner',contact_truth=False),
      dict(field='submitted_waypoints/native_action_counter_delta',source='execution receipts',kind='submission/count feedback, not measured execution success',vla=False,controller='automatic tool feedback after execution',contact_truth=False)]
    result=dict(classification='finite_CPU_checkpoint_and_feedback_contract_audit',status='completed',model_calls=0,vla_calls=0,new_simulation_episodes=0,new_physics_steps=0,gpu_used=False,checkpoint=dict(repo=manifest['id'],revision=MODEL_REV,metadata_verified=meta,declared_training=note['text']['en'],train_path=cfg['data']['train_path'],configured_train_size=cfg['data']['train_size'],configured_max_steps=cfg['train']['max_steps'],training_task_list=None,training_episode_seed_split=None,training_camera_command_measurement_contract=None,model_index=manifest.get('model-index'),normalization_keys=list(norm),coverage_conclusion='RoboTwin SFT is documented. Exact task/scene membership and clean/randomized training mixture are not established by the inspected release metadata. Evaluation membership is not training coverage.'),evaluation_panel=dict(num_tasks=panel['num_tasks'],num_episodes=panel['num_episodes'],focal_tasks={k:panel['tasks'][k] for k in ['stack_blocks_two','handover_block']}),source_manifest=sources,payload_probes=probes,observation_fields=fields,development_only=dict(run=DEV,cases=cases,total_saved_observations=observations,interpretation='Observed command/arm-measurement differences are descriptive tracking signals, not verified cause of task failures or grasp labels.'),read_validation_trajectories=False,accepted_updates=0,strict_rsi_rounds=0,limitations=['No neural forward pass or actual motor action in this audit.','A configured train_size or max_steps is not an independently verified training count.','No population performance inference from the ten development cases.','Do not substitute measured fingers into the frozen command-conditioned VLA state without a new explicit shared contract and independent justification.'])
    output.mkdir(parents=True,exist_ok=False)
    (output/'report.json').write_text(json.dumps(result,indent=2)+'\n');(output/'development-input-manifest.json').write_text(json.dumps(input_manifest,indent=2)+'\n')
    print(json.dumps(dict(status=result['status'],metadata_verified=len(meta),source_files=len(sources),payload_probes=len(probes),development_cases=len(cases),saved_observations=observations,new_model_calls=0,new_episodes=0,case_tracking=cases)))
if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--runtime',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();audit(a.runtime,a.output)
