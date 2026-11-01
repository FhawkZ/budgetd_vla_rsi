import json,os,hashlib,copy
from pathlib import Path
from PIL import Image,ImageDraw
from hcl_robotwin_adapter import load_official, pair_metrics, screening_contract
R=Path(os.environ['RSI_RUNTIME_ROOT']);repo=Path.cwd();out=R/'outputs/hcl-feedback-prepare-20261101-1200';out.mkdir(exist_ok=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
save=lambda p,d:p.write_text(json.dumps(d,indent=2,ensure_ascii=False)+'\n')
Optimizer,Pipeline,settings=load_official(R)
panel=R/'outputs/official-owner-fixed50-dev10-20261101-0300';report=json.loads((panel/'report.json').read_text());rows=[e['result'] for e in report['episodes']];keys=[(x['task'],x['seed']) for x in rows]
reference,nochange=pair_metrics(rows,rows,'handover_block',['stack_blocks_two'],keys,behavior_changed=False)
optim=Optimizer(record_dir=out/'hcl-official-gate',**settings)
assert optim.select_best_candidate([{'candidate_id':'unchanged','validation_errors':[]}],{'unchanged':nochange},reference) is None
# Manufactured outcomes solely for gate mapping verification, never task performance.
synthetic=copy.deepcopy(rows)
first=next(x for x in synthetic if x['task']=='handover_block' and not x['native_eval_success']);first['native_eval_success']=True
ref,gain=pair_metrics(rows,synthetic,'handover_block',['stack_blocks_two'],keys,behavior_changed=True)
assert optim.select_best_candidate([{'candidate_id':'fixture_gain','validation_errors':[]}],{'fixture_gain':gain},ref)
next(x for x in synthetic if x['task']=='stack_blocks_two' and x['native_eval_success'])['native_eval_success']=False
_,harm=pair_metrics(rows,synthetic,'handover_block',['stack_blocks_two'],keys,behavior_changed=True)
assert optim.select_best_candidate([{'candidate_id':'fixture_loss','validation_errors':[]}],{'fixture_loss':harm},ref) is None
cur=[{'task_id':str(x['seed'])+'handover','task_name':'handover_block'} for x in rows if x['task']=='handover_block'];old=[{'task_id':str(x['seed'])+'stack','task_name':'stack_blocks_two'} for x in rows if x['task']=='stack_blocks_two']
sc=screening_contract(R,optim,cur,old)
balanced=Optimizer(record_dir=out/'balanced-check',selection_objective='balanced');bc=screening_contract(R,balanced,cur,old)
assert sc['total_selected']==bc['total_selected']==10 and not bc['active_for_multiple_candidates']
save(out/'hcl-audit.json',{'classification':'CPU official gate mapping, real incumbent no-op and labeled synthetic outcomes; not policy results','paper_profile':settings,'official_profile_screening':sc,'balanced_small_panel_screening':bc,'gate_checks':{'real_incumbent_noop_rejected':True,'synthetic_gain_accepted':True,'synthetic_gain_old_loss_rejected':True},'paper_result_reproduction':False,'important':'Cheap screening branch is balanced-only in upstream pipeline; main stability/plasticity paper profile uses plasticity with historical budget. At5new+5old default minima select all10, no screening savings.'})
# Fixed, outcome-independent extraction: all ten cases, first/middle/last inference observation.
feedback={'classification':'development executed feedback only; no candidate validation or final test','selection_rule':'all ten frozen cases; first, floor((n-1)/2), last inference observations; no outcome-based selection','cases':[]};canvases=[Image.new('RGB',(5*224,2*252),'white') for _ in range(3)];provenance=[]
for i,e in enumerate(report['episodes']):
 row=e['result'];ep=panel/f"{i:02d}-{row['task']}-s{row['seed']}";frames=sorted(ep.glob('inference-*.json'));assert frames
 ids=[0,(len(frames)-1)//2,len(frames)-1];item={'task':row['task'],'seed':row['seed'],'instruction':row['native_task_language'],'native_success':row['native_eval_success'],'native_actions':row['native_actions'],'vla_inferences':row['vla_inferences'],'observations':[]}
 for stage,k in enumerate(ids):
  f=frames[k];d=json.loads(f.read_text());png=f.with_name(f.stem+'-head.png');im=Image.open(png).convert('RGB');im=im.resize((224,224));canvas=canvases[stage];x=(i%5)*224;y=(i//5)*252;canvas.paste(im,(x,y));ImageDraw.Draw(canvas).text((x+3,y+226),f"case {i}: {row['task']} s{row['seed']}",fill='black')
  state=d['robot_state'];item['observations'].append({'stage':stage,'inference_index':d['index'],'state':{a:state[a] for a in ('left_eef_pose','right_eef_pose','left_gripper','right_gripper')}})
  provenance.append({'path':str(png.relative_to(R)),'sha256':sha(png),'json_path':str(f.relative_to(R)),'json_sha256':sha(f),'case_index':i,'stage':stage})
 feedback['cases'].append(item)
save(out/'feedback.json',feedback);save(out/'source-provenance.json',provenance)
for j,canvas in enumerate(canvases):canvas.save(out/f'stage{j}.png')
print(json.dumps({'out':str(out),'screening':bc,'feedback_chars':len((out/'feedback.json').read_text())}))
