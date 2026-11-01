import unittest
import numpy as np
from run_typed_skill_panel import initial_reference_equal
class InitialReferenceTest(unittest.TestCase):
 def test_rpc_array_equivalent_to_serialized_lists(self):
  a={'initial_robot_state':{'pose':np.array([1.,2.]),'g':np.float64(.5)},'initial_image_sha256':{'head':'a'}}
  b={'initial_robot_state':{'g':.5,'pose':[1.,2.]},'initial_image_sha256':{'head':'a'}}
  self.assertTrue(initial_reference_equal(a,b))
  b['initial_robot_state']['pose'][0]=1.00001
  self.assertFalse(initial_reference_equal(a,b))
  b['initial_robot_state']['pose'][0]=1.;b['initial_image_sha256']['head']='b'
  self.assertFalse(initial_reference_equal(a,b))
