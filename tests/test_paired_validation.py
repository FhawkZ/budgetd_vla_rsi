import unittest,tempfile
from pathlib import Path
import numpy as np
from run_paired_patch_validation import paired_initial_reference
class PairedValidationTest(unittest.TestCase):
 def test_input_reference_exact_and_no_outcome(self):
  r={'initial_robot_state':{'eef':np.array([1.,2.])},'initial_image_sha256':{'head':'a'},'native_task_language':'task','native_eval_success':True}
  c={'pair_index':0,'task':'stack_blocks_two','seed':100006}
  with tempfile.TemporaryDirectory() as d:
   self.assertEqual(paired_initial_reference(r,c,d),'recorded_first_member')
   self.assertNotIn('native_eval_success',(Path(d)/'paired-inputs/pair-00.json').read_text())
   self.assertEqual(paired_initial_reference(r,c,d),'matched_second_member')
   r['native_task_language']='other'
   with self.assertRaisesRegex(AssertionError,'mismatch'):paired_initial_reference(r,c,d)
