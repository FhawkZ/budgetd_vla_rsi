"""Explicit evidence-path deployment adaptation, not learned RSI or task replay."""
import json, shutil
from pathlib import Path
import run_roborsi_native_pilot as pilot

def inventory(root):
 root=Path(root).resolve(strict=True)
 rows=[]
 for p in sorted(root.rglob('*')):
  if not p.is_file() or not (p.name in ('plan.md','summary.md','trace.json') or p.suffix.lower() in ('.jpg','.png')):continue
  if p.is_symlink() or not p.resolve().is_relative_to(root):raise ValueError('symlink evidence')
  rows.append({'path':str(p),'sha256':pilot.sha(p),'bytes':p.stat().st_size,'reader':'read_image' if p.suffix.lower() in ('.jpg','.png') else 'read_text'})
 return rows

def prepare(state,closed_run):
 closed=Path(closed_run).resolve(strict=True);assert (closed/'CLOSE.json').exists()
 roots=list((closed/'roborsi-home/workspaces').iterdir());assert len(roots)==1
 source=roots[0];dest=Path(state['workspace'])/'episode-evidence';dest.mkdir()
 originals=inventory(source)
 for row in originals:
  src=Path(row['path']);target=dest/src.relative_to(source);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
 # Deliberately excludes episode_result, review, scoring and historical verdicts.
 pilot.write(Path(state['run_root'])/'evidence-source-manifest.json',originals)
 pilot.write(Path(state['run_root'])/'evidence-inventory.json',inventory(dest))
 state['review_evidence']=str(dest);state['closed_development_source']=str(closed)
 state['script_hashes']['scripts/reviewer_contract.py']=pilot.sha(__file__)
 pilot.write(Path(state['run_root'])/'state.json',state)

def guidance(root):
 root=Path(root);traces=sorted(root.rglob('trace.json'));frames=sorted(root.rglob('tick_*.jpg'))
 finals=sorted(root.glob('rollout/round_*/final_view_*.jpg'))
 lines=['Explicit deployment evidence contract: use only existing exact paths below. Images require read_image, never read_text. Use list_files to discover other paths; never guess tick names. The execution chain above already summarizes all trace steps.','Trace paths:']+[str(p) for p in traces]
 lines+=['Final camera paths (read_image):']+[str(p) for p in finals]
 if frames:lines += [f'{len(frames)} tick images exist, first={frames[0]}, last={frames[-1]}.']
 return '\n'.join(lines)

def child(state):
 pilot.clean_environment(state)
 from roborsi.agents.sessions import persistent_agent as pa
 from roborsi.agents.roles.reviewer import Reviewer, _parse_review_json
 from roborsi.agents.memory.workspace import Workspace
 pa._REPO=Path(state['workspace']);root=Path(state['review_evidence']);run=Path(state['run_root'])
 report={'classification':'Reviewer-only deployment qualification on CLOSED development evidence; not an additional task, baseline score or RSI update','status':'failed','model_call_cap':4,'accepted_updates':0}
 orig=pa.run_role
 def routed(role,task,prompt,**kwargs):
  assert role=='reviewer'
  extra=guidance(root)
  if state.get('tool_profile')=='role-evidence':
   extra+='\nExact registered tools: mcp__role_evidence__read_image({"path": absolute_image_path}), mcp__role_evidence__read_text, mcp__role_evidence__list_files, mcp__role_evidence__search_text. No generic MCP resource server is available.'
  prompt+='\n\n'+extra+'\nIndependent diagnostic budget: at most 3 evidence tool calls then one final JSON response. Read at least one final camera with read_image. Do not propose edits or execute robot actions.'
  pilot.write(run/'reviewer-prompt.json',{'role':role,'task':task,'prompt':prompt,'system_prompt':kwargs.get('system_prompt'),'images':kwargs.get('images')})
  answer=orig(role,task,prompt,**kwargs);(run/'reviewer-raw.txt').write_text(answer)
  parsed=_parse_review_json(answer)
  assert parsed.get('verdict') in ('done','continue','blocked'),'no valid original JSON verdict'
  assert parsed.get('proposal_decision')=='NO_PROPOSAL'
  assert parsed.get('root_cause') and parsed.get('review_md'),'missing evidence diagnosis'
  return answer
 pa.run_role=routed
 before={x['path']:x['sha256'] for x in inventory(root)}
 try:
  traces=sorted(root.rglob('trace.json'));assert len(traces)==1
  trace=json.loads(traces[0].read_text())
  result=Reviewer(model=pilot.ROLE_MODEL,allow_evolution=False).review(workspace=Workspace(task='stack_blocks_two',run_id='closed-evidence-diagnostic',root=root),engineer_result={'trace':trace,'tool_calls':len(trace),'rollout_meta':{}},in_episode=True,task_instruction='Stack the two blocks (red and green) on top of each other.',budget_left=0,rounds_left=0)
  rows=[json.loads(x) for x in (run/'mcp-audit.jsonl').read_text().splitlines()]
  assert any(x['tool']=='read_image' and 'final_view_' in x['path'] for x in rows),'no final image read'
  assert before=={x['path']:x['sha256'] for x in inventory(root)},'evidence changed'
  report.update(status='passed',review=result,evidence_reads=rows)
 except Exception as e:report['error']=repr(e)
 finally:pa.run_role=orig
 pilot.write(run/'reviewer-report.json',report)
 return 0 if report['status']=='passed' else 1

def install_native_contract(state, pa):
 """Expose actual paths at each review; preserve original scoring and verdict."""
 original=pa.run_role
 def run_role(role,task,prompt,**kwargs):
  if role=='reviewer':
   import re
   match=re.search(r'Episode workspace: ([^\n]+)',prompt)
   if not match:raise ValueError('missing explicit episode workspace')
   root=Path(match.group(1)).resolve(strict=True)
   if not root.is_relative_to(Path(state['run_root'])/'roborsi-home/workspaces'):raise ValueError('review root outside current run')
   prompt+='\n\n'+guidance(root)+'\nExact tools: mcp__role_evidence__read_image, mcp__role_evidence__read_text, mcp__role_evidence__list_files, mcp__role_evidence__search_text. No generic MCP resource server exists. At most 3 evidence tool calls before a final JSON verdict; do not infer task completion from a tool success alone.'
  return original(role,task,prompt,**kwargs)
 pa.run_role=run_role
