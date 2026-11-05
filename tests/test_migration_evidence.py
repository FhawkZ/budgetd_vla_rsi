import tempfile,unittest
from pathlib import Path
from migration_evidence import snapshot,persistent_trial
class EvidenceTest(unittest.TestCase):
 def test_copy_and_finally(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d)/'ram';p=Path(d)/'disk';src=r/'outputs'/'case';src.mkdir(parents=True);(src/'receipt').write_text('one')
   with self.assertRaisesRegex(ValueError,'failure'):
    with persistent_trial(r,p,'case'):
     (src/'receipt').write_text('two');raise ValueError('failure')
   self.assertEqual((p/'case'/'receipt').read_text(),'two')
   with self.assertRaises(AssertionError):
    with persistent_trial(r,p,'case'):pass
 def test_official_link_is_recorded_not_followed(self):
  with tempfile.TemporaryDirectory() as d:
   a=Path(d)/'a';a.mkdir();v=Path(d)/'vendor';v.mkdir();(v/'secret').write_text('not copied');(a/'official').symlink_to(v)
   snapshot(a,Path(d)/'b',allowed_targets=(str(v),))
   self.assertTrue((Path(d)/'b/official.symlink.json').exists())
   self.assertFalse((Path(d)/'b/official').exists())
 def test_symlink_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   a=Path(d)/'a';a.mkdir();(a/'link').symlink_to('/etc/passwd')
   with self.assertRaises(ValueError):snapshot(a,Path(d)/'b')
if __name__=='__main__':unittest.main()
