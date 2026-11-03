"""Verify released Skill-RSI packages with the pinned upstream validators (CPU)."""
import argparse, hashlib, importlib.util, json, sys
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--vendor',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    manifest=json.loads(a.manifest.read_text())
    assert manifest['revision']=='3483ea128ba432730f135aac326da1b768b671e4'
    for r in manifest['files']:
        b=(a.vendor/r['path']).read_bytes()
        assert hashlib.sha256(b).hexdigest()==r['sha256'],r['path']
    sys.path.insert(0,str(a.vendor/'runtime'))
    spec=importlib.util.spec_from_file_location('skill_rsi_validate',a.vendor/'runtime/validate.py')
    v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
    rows=[]
    for d in sorted((a.vendor/'frozen_skills').iterdir()):
        m=json.loads((d/'MANIFEST.json').read_text())
        hashes={n:hashlib.sha256((d/n).read_bytes()).hexdigest()==h for n,h in m['files'].items()}
        se,atoms=v.validate_skills((d/'skills.py').read_text());pe=v.validate_perception((d/'perception.py').read_text())
        me=v.validate_skill_md((d/'SKILL.md').read_text(),atoms,m.get('task',d.name.rsplit('_',1)[0]))
        rows.append(dict(package=d.name,hashes=hashes,skills_errors=se,perception_errors=pe,description_errors=me,atoms=atoms))
    result={'classification':'official package CPU contract checks, not robot scores','revision':manifest['revision'],'packages':rows,'passed':all(all(r['hashes'].values()) and not (r['skills_errors'] or r['perception_errors'] or r['description_errors']) for r in rows),'new_model_calls':0,'new_simulation_episodes':0}
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='packages'}));return 0 if result['passed'] else 1
if __name__=='__main__':sys.exit(main())
