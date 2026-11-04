import sys,pathlib,unittest,tempfile,json
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/"scripts"))
from skill_rsi_development_packet import ensure_safe,export,ALLOWED
class Packet(unittest.TestCase):
 def test_nested_scorer_refused(self):
  with self.assertRaises(ValueError):ensure_safe({'roles':[{'criterion_source':'secret'}]})
 def test_observation_kept(self):ensure_safe({'roles':{'bowl':{'position_world':[0,0,1],'clip_score':.5}},'result':True})
 def test_sealed_or_unknown_not_read(self):
  with self.assertRaises(ValueError):export(pathlib.Path('/nonexistent'),'sealed-validation',0,pathlib.Path('/never'))
 def test_export_excludes_scoring_files(self):
  with tempfile.TemporaryDirectory() as tmp:
   r=pathlib.Path(tmp);run=next(iter(ALLOWED));c=r/'outputs'/run/'case-00';c.mkdir(parents=True)
   (c/'episode.json').write_text(json.dumps({'status':'completed','infrastructure_error':False,'primitive_calls':1,'task':'example','seed':1,'success':True}))
   (c/'task-spec.json').write_text('SECRET_SCORER');(c/'initial-layout-evaluator-only.json').write_text('SECRET_LAYOUT')
   (c/'render-health.jsonl').write_text(json.dumps({'error':None,'rgb_max':255})+'\n')
   (c/'calls.jsonl').write_text(json.dumps({'method':'observe','result':{'ok':True}})+'\n');(c/'initial-proprioception.json').write_text('{}')
   obs=c/'observation_00';obs.mkdir()
   for name in ['rgb.png','depth_mm.npy','calibration.json']:(obs/name).write_bytes(b'fixture')
   export(r,run,0,r/'packet');s=(r/'packet/feedback.json').read_text()
   self.assertNotIn('SECRET',s);self.assertNotIn('success',json.loads(s));self.assertFalse((r/'packet/task-spec.json').exists())
if __name__=='__main__':unittest.main()
