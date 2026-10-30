"""Freeze two explicit deployment-contract fixtures; no autonomous task grading."""
import hashlib,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];R=Path(os.environ['RSI_RUNTIME_ROOT'])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
prior=R/'outputs/qwen30b-qual3-20261031-0640';assert (prior/'CLOSE.json').exists();old=json.loads((prior/'protocol.json').read_text())
out=R/'outputs/qwen30b-contract2-prepare-20261031-0650';out.mkdir(exist_ok=False)
body=json.loads((R/old['inputs'][0]['path']).read_text());tool=next(t for t in body['tools'] if t['function']['name']=='sample_world_xyz')
print(json.dumps(tool,indent=2))
body['messages']=[{'role':'user','content':'This is a tool argument serialization qualification, not a robot task. Call sample_world_xyz once with view="head" and pixels=[[16,24],[32,48]]. The numbers are synthetic fixture inputs, not inferred coordinates. Do not execute a different tool. No robot tool will be executed.'}]
body['max_tokens']=1024;body['stream']=False
fixture=out/'nested-array.json';save(fixture,body)
source=ROOT/'scripts/qualify_qwen30b.py';s=source.read_text().replace("cfg['max_calls']==3", "cfg['max_calls']==2").replace("model_calls_cap=3", "model_calls_cap=2").replace("'--max-calls','3'", "'--max-calls','2'").replace("budget allowed fourth request", "budget allowed third request")
s=s.replace("valid=True\n   else:", "assert json.loads(value['arguments'])=={'view':'head','pixels':[[16,24],[32,48]]},'explicit serialization fixture mismatch'\n    valid=True\n   else:")
runner=ROOT/'scripts/qualify_qwen30b_contract2.py';assert not runner.exists();runner.write_text(s)
cfg=json.loads(json.dumps(old));cfg.update(run_id='qwen30b-contract2-20261031-0700',max_calls=2,classification='explicit_serialization_and_capacity_qualification_not_autonomous_score',closed_predecessor='qwen30b-qual3-20261031-0640',canceled_predecessor_allowance_not_reused=True,protocol_scope='Independent2call budget:31744input-token canary, then explicit synthetic nested-array serialization using original14tool schemas. All tools remain auto-selected, zero executed. Thirdrequest rejected. Stop after first failure; no prompt tuning.')
cfg['inputs']=[old['inputs'][2],dict(kind='historical_schema_boundary',path=str(fixture.relative_to(R)),sha256=sha(fixture),classification='explicit synthetic argument serialization; not historical autonomous input')]
cfg['code_sha256'].pop('scripts/qualify_qwen30b.py');cfg['code_sha256']['scripts/qualify_qwen30b_contract2.py']=sha(runner)
p=ROOT/'configs/qwen30b-contract2-20261031-0700.json';assert not p.exists();save(p,cfg);print('PROTOCOL_SHA',sha(p))
