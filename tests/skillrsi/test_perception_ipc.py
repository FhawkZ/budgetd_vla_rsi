import json,pathlib,sys,tempfile,unittest
import numpy as np
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'scripts'))
from skill_rsi_perception_ipc import run_perception,pack
from skill_rsi_perception_worker import decode_array
ROOT=pathlib.Path('/root/autodl-tmp/Dex_runtime/agent-rsi/vendor/Skill-RSI-3483ea128ba432730f135aac326da1b768b671e4/runtime')
CAL={'intrinsic_cv':[[100,0,1],[0,100,1],[0,0,1]],'extrinsic_cv':[[1,0,0,0],[0,1,0,0],[0,0,1,0]]}
SOURCE="""def detect(rgb, depth_mm, calibration):
    world=world_points(depth_mm,calibration)
    points=world[:,:,:2].reshape(-1,2)
    labels=DBSCAN(eps=0.1,min_samples=2).fit_predict(points)
    return [{'point_count':int((labels==0).sum()),'position_world':[0.0,0.0,float(np.mean(world[:,:,2]))],'xyxy':[0,0,1,1]}],0.1
"""
class Perception(unittest.TestCase):
 def run_child(self,code,d,**kw):
  return run_perception(code,np.ones((2,2,3),dtype=np.uint8),np.full((2,2),100,dtype=np.uint16),CAL,ROOT,pathlib.Path(d)/'out',**kw)
 def test_data_only_numerical_roundtrip(self):
  with tempfile.TemporaryDirectory() as d:
   r=self.run_child(SOURCE,d);self.assertEqual(r['status'],'result',r)
   self.assertEqual(r['response']['result'],[[{'point_count':4,'position_world':[0.,0.,.1],'xyxy':[0,0,1,1]}],.1]);self.assertTrue(r['response']['seccomp_allowlist'])
 def test_array_hash_and_object_dtype_refused(self):
  for kind in ['hash','dtype','shape']:
   x=pack(np.ones((2,2),dtype=np.uint16))
   if kind=='hash':x['sha256']='0'*64
   elif kind=='dtype':x['dtype']='|O'
   else:x['shape']=[2048,2]
   with self.subTest(kind=kind),self.assertRaises(ValueError):decode_array(x,np,'depth')
 def test_forbidden_source_rejected_before_load(self):
  with tempfile.TemporaryDirectory() as d:
   self.assertEqual(self.run_child('import os\n'+SOURCE,d)['status'],'static_rejected')
 def test_output_size_cap(self):
  with tempfile.TemporaryDirectory() as d:
   r=self.run_child('def detect(rgb,depth_mm,calibration):\n    return [0]*100000,0.0\n',d)
   self.assertEqual(r['status'],'worker_error',r);self.assertEqual(r['response']['message'],'output cap')
 def test_deadline_stops_owned_child(self):
  with tempfile.TemporaryDirectory() as d:
   code='def detect(rgb,depth_mm,calibration):\n    for i in range(1000000000):\n        x=i*i\n    return [],0.0\n'
   r=self.run_child(code,d,timeout=2.5);self.assertEqual(r['status'],'rejected_or_error',r);self.assertIn('Timeout',r['error']);self.assertLess(r['seconds'],4)
if __name__=='__main__':unittest.main()
