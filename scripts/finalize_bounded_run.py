"""One-shot CPU finalizer for an already launched bounded run. Never launches episodes."""
import argparse,fcntl,json,os,subprocess,sys,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
r=Path(a.output).resolve();runtime=Path(os.environ['RSI_RUNTIME_ROOT']).resolve();assert r.parent==runtime/'outputs' and (r/'protocol.json').exists()
lock=(r/'finalizer.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
owner=json.loads((r/'report.json').read_text());deadline=owner['started_unix']+4900
while not (r/'CLOSE.json').exists() and time.time()<deadline:time.sleep(5)
report={'started_for':r.name,'model_calls':0,'simulator_episodes':0,'time':time.time()}
if not (r/'CLOSE.json').exists():report.update(status='timed_out_without_close',note='Do not assume owner completed or restart anything.')
else:
 result=subprocess.run([sys.executable,str(Path(__file__).with_name('summarize_bounded_vla.py')),str(r)],capture_output=True,text=True,timeout=60)
 (r/'summary-finalizer.log').write_text(result.stdout+result.stderr)
 report.update(status='summarized' if result.returncode==0 else 'summary_failed',returncode=result.returncode)
(r/'finalizer-status.json').write_text(json.dumps(report,indent=2)+'\n')
