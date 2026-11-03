import unittest
import torch
from program_guidance import velocity_guidance

class Model:
    def predict_velocity(self, state, masks, cache, x, time):
        return torch.zeros_like(x)

class GuidanceTests(unittest.TestCase):
    def test_zero_is_identity(self):
        m=Model();x=torch.randn(1,5,16);events=[]
        with velocity_guidance(m,x,[0,1,2],0,events):
            self.assertTrue(torch.equal(m.predict_velocity(None,None,None,x,torch.ones(1)),torch.zeros_like(x)))
        self.assertFalse(events[0]["applied"])

    def test_ascent_for_negative_native_dt(self):
        m=Model();x=torch.zeros(1,5,16);target=x.clone();target[:,:,2]=1
        with velocity_guidance(m,target,[0,1,2,7,8,9],.2,[]):
            y=x-.1*m.predict_velocity(None,None,None,x,torch.ones(1))
        self.assertGreater(float(y[:,:,2].mean()),0)
        self.assertEqual(torch.count_nonzero(y[:,:,[3,4,5,6,10,11,12,13,14,15]]),0)
        self.assertLess(float(((y-target)**2).mean()),float(((x-target)**2).mean()))

    def test_restore_on_exception(self):
        m=Model();original=m.predict_velocity
        with self.assertRaisesRegex(RuntimeError,"injected"):
            with velocity_guidance(m,torch.zeros(1,5,16),[2],1,[]):
                raise RuntimeError("injected")
        self.assertEqual(m.predict_velocity,original)
