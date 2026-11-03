import importlib.util, pathlib, unittest, ast
ROOT=pathlib.Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('native',ROOT/'scripts/run_skill_rsi_native.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class NativeContract(unittest.TestCase):
 def test_success(self):self.assertTrue(mod.classify(True,None,None)['success'])
 def test_failure(self):self.assertFalse(mod.classify(False,None,None)['success'])
 def test_infra_missing(self):self.assertIsNone(mod.classify(None,'infra:setup','setup')['success'])
 def test_safety(self):self.assertFalse(mod.classify(True,'safety_stop:x',None)['success'])
 def test_budget(self):self.assertFalse(mod.classify(True,'budget_exhausted:x',None)['success'])
 def test_wall(self):self.assertFalse(mod.classify(True,'timeout:wall',None)['success'])
 def test_native_success_after_error(self):self.assertEqual(mod.classify(True,'atom_error',None)['failure_class'],'success_after_atom_error')
 def test_single_setup(self):
  tree=ast.parse((ROOT/'scripts/run_skill_rsi_native.py').read_text());fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='worker');calls=[x for x in ast.walk(fn) if isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute) and isinstance(x.func.value,ast.Name) and x.func.value.id=='env' and x.func.attr=='setup'];self.assertEqual(len(calls),1)
if __name__=='__main__':unittest.main()
