"""Export explicitly allowlisted valid DEVELOPMENT feedback, never scorer/layout.
This is an author-input staging artifact, not an author call or a skill update.
"""
import argparse,hashlib,json,shutil
from pathlib import Path

ALLOWED={
 "skill-rsi-no-denoiser-dev1-20261104-0610":{0},
 "skill-rsi-twotask-dev4-20261104-1515":{0},
}
FORBIDDEN={"criterion_source","official_success","success","layout","layout_sha256","object_pose","check_success","scorer","initial-layout-evaluator-only"}

def ensure_safe(value):
 if isinstance(value,dict):
  if set(value)&FORBIDDEN:raise ValueError("forbidden evaluator field")
  for v in value.values():ensure_safe(v)
 elif isinstance(value,list):
  for v in value:ensure_safe(v)

def lines(p):return [json.loads(s) for s in p.read_text().splitlines() if s.strip()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def export(runtime,run,index,dest):
 if index not in ALLOWED.get(run,set()):raise ValueError("not explicitly allowlisted development case")
 case=runtime/"outputs"/run/f"case-{index:02d}"
 episode=json.loads((case/"episode.json").read_text())
 if episode.get("status")!="completed" or episode.get("infrastructure_error") or episode.get("cleanup_error"):raise ValueError("invalid episode")
 health=lines(case/"render-health.jsonl")
 if not health or any(x.get("error") or x["rgb_max"]==0 for x in health):raise ValueError("invalid render")
 calls=lines(case/"calls.jsonl")
 if len(calls)!=episode["primitive_calls"]:raise ValueError("incomplete primitive receipts")
 for c in calls:
  if c["method"] not in {"observe","move_pose","gripper","wait"}:raise ValueError("unreviewed primitive")
 ensure_safe(calls)
 proprio=json.loads((case/"initial-proprioception.json").read_text());ensure_safe(proprio)
 # No episode scoring, task_spec, evaluator layout, log or atom success label is exported.
 packet={"classification":"valid_development_feedback_not_evaluation", "task":episode["task"],"seed":episode["seed"],"initial_proprioception":proprio,"primitive_calls":calls,"images":[],"limitations":["primitive booleans are API returns, not grasp/task truth", "initial proprioception only; no measured-state trajectory recorded", "no author request made"]}
 assets=[]
 for obs in sorted(case.glob("observation_*")):
  for name in ["rgb.png","depth_mm.npy","calibration.json"]:
   src=obs/name
   if not src.is_file():raise ValueError("missing observation asset")
   rel=Path(obs.name)/name;assets.append((src,rel));packet["images"].append({"path":str(rel),"sha256":sha(src)})
 if len(assets)!=3*sum(c["method"]=="observe" for c in calls) or not assets:raise ValueError("observation count mismatch")
 ensure_safe(packet)
 dest.mkdir(parents=True,exist_ok=False)
 for src,rel in assets:
  (dest/rel).parent.mkdir(exist_ok=True);shutil.copyfile(src,dest/rel)
 (dest/"feedback.json").write_text(json.dumps(packet,indent=2))
 return {"packet_sha256":sha(dest/"feedback.json"),"primitive_receipts":len(calls),"observation_assets":len(assets),"author_calls":0}
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--runtime",type=Path,required=True);p.add_argument("--run",required=True);p.add_argument("--case",type=int,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args();print(json.dumps(export(a.runtime,a.run,a.case,a.out)))
