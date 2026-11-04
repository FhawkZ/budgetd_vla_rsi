"""Prepare exact approved author resources. No LLM or generated code execution."""
import hashlib,json
from pathlib import Path
from skill_rsi_development_packet import ensure_safe
CASES={'move_can_pot': {'skill': 'move_can_pot_d885e5', 'run': 'skill-rsi-twotask-dev4-20261104-1515', 'feedback_sha256': '975dd71ad858294516df7e676eaea89f7a4e28fd3e2ec275928a6cdbd2e47002', 'source_sha256': {'SKILL.md': '668252bb9e47635117e29e6ca4cac778453f6e08fdd41f4582bc75cb9d2ecb1a', 'skills.py': 'b433f9bed65023d53857530ef2e2a78c96f1de06b49c1a23451f7c054cfe6e7c', 'perception.py': '72d962b585a1e2df4c4beadb4d91d9c405c6532d06854fb8d2f4d2aee437f8d0'}}, 'stack_bowls_two': {'skill': 'stack_bowls_two_79dfa1', 'run': 'skill-rsi-no-denoiser-dev1-20261104-0610', 'feedback_sha256': '9d27996a27677326b3670b28bf6e9def0c700916e4f55f4a8a0bc8a85097249e', 'source_sha256': {'SKILL.md': '9dd35fb312ba8d6d1b1b7cbdffdb11b801e0c31aefe2d72dc57e24d345105b86', 'skills.py': '19677c6ad2ec85a05c6f2df48a2dc0e2aa5a03196a24808a09c831e4c2c8f325', 'perception.py': 'f30e469ab5a78b31f9784dc32273561305bc90078f15583436093f556fea954a'}}}
API_SHA='cf8774e60c14c674ea01d1f32e2f19cdd13054ccc416455dd9f6248c2424267c'

def sha(b):return hashlib.sha256(b).hexdigest()
def prepare(task,runtime,repo,destination):
    if task not in CASES:raise ValueError('unapproved task')
    case=CASES[task];dest=Path(destination)
    if dest.exists():raise FileExistsError(dest)
    vendor=Path(runtime)/'vendor/Skill-RSI-3483ea128ba432730f135aac326da1b768b671e4/frozen_skills'/case['skill']
    packet=Path(runtime)/'outputs/skill-rsi-twotask-prepare-20261104-1515/author-input-staging'/case['run']/'feedback.json'
    feedback=packet.read_bytes()
    if sha(feedback)!=case['feedback_sha256']:raise ValueError('approved packet changed')
    parsed=json.loads(feedback);ensure_safe(parsed)
    if parsed['classification']!='valid_development_feedback_not_evaluation' or parsed['task']!=task:raise ValueError('feedback identity')
    api=(Path(repo)/'docs/skill-rsi-author-api-v1.md').read_bytes()
    if sha(api)!=API_SHA:raise ValueError('public API contract changed')
    resources={'api_doc':api,'development_feedback':feedback}
    for name,rid in [('SKILL.md','skill_doc'),('skills.py','inherited_skills'),('perception.py','inherited_perception')]:
        b=(vendor/name).read_bytes()
        if sha(b)!=case['source_sha256'][name]:raise ValueError('published source changed')
        resources[rid]=b
    # Paths are owner-managed snapshots, never chosen by a model.
    dest.mkdir(parents=True,exist_ok=False);grants=[]
    for rid,b in resources.items():
        if len(b)>300000:raise ValueError('resource cap')
        p=dest/(rid+'.txt');p.write_bytes(b);grants.append({'id':rid,'path':str(p.resolve()),'sha256':sha(b)})
    manifest={'status':'FROZEN_AUTHOR_INPUT','purpose':'PREPARATION_NOT_MODEL_OR_ROLLOUT_AUTHORIZATION','task':task,'resources':grants,'author_calls':0,'image_attachments':0,'outputs':['SKILL.md','skills.py','perception.py','rationale.md'],'limitations':['text feedback only; referenced images not attached','two successful development examples are not evidence of a binding fault','no evaluation labels or scorer source supplied']}
    (dest/'manifest.json').write_text(json.dumps(manifest,indent=2));return manifest
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--task',required=True);p.add_argument('--runtime',required=True);p.add_argument('--repo',required=True);p.add_argument('--out',required=True);a=p.parse_args();print(json.dumps(prepare(a.task,a.runtime,a.repo,a.out),indent=2))
