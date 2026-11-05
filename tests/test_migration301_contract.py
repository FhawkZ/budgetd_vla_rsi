import ast,hashlib,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class MigrationContract(unittest.TestCase):
 def test_service_only_host_edits(self):
  old=(ROOT/'scripts/qwen_service_owner.py').read_text()
  expected=old.replace("gpu0.lock","gpu2.lock").replace('gpu_snapshot(0)','gpu_snapshot(2)').replace("CUDA_VISIBLE_DEVICES='0'","CUDA_VISIBLE_DEVICES='2'").replace("python=str(r/'software/envs/qwen/bin/python')","python=cfg['qwen_python']")
  self.assertEqual(ast.dump(ast.parse(expected)),ast.dump(ast.parse((ROOT/'scripts/qwen_service_owner_301.py').read_text())))
 def test_draft_cannot_pass_native_verify(self):
  sys.path.insert(0,str(ROOT/'scripts'));import run_skill_rsi_caller as native
  c=json.loads((ROOT/'configs/skill-rsi-caller-dev2-lzgpu301-draft.json').read_text())
  with self.assertRaises(AssertionError):native.verify(c)
 def test_budget_and_roles_unchanged(self):
  a=json.loads((ROOT/'configs/skill-rsi-caller-dev2-20261104-2100.json').read_text());b=json.loads((ROOT/'configs/skill-rsi-caller-dev2-lzgpu301-draft.json').read_text())
  for key in ['cases','limits','monitor','task_cards','max_qwen_calls_total','qwen_max','vla_max','attempts_max','model_id','denoiser','total_wall_seconds','process_wall_seconds']:
   self.assertEqual(a[key],b[key],key)
  self.assertEqual((b['gpu'],b['qwen_gpu']),(3,2))
  for name,digest in b['host_adapter_sha256'].items():self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest,name)
if __name__=='__main__':unittest.main()
