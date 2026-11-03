import importlib.util,pathlib,unittest,numpy as np
ROOT=pathlib.Path(__file__).resolve().parents[2];s=importlib.util.spec_from_file_location('m',ROOT/'scripts/run_skill_rsi_native_v2.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class RenderGuard(unittest.TestCase):
 def test_black(self):self.assertEqual(m.render_input_error(np.zeros((2,3,3),dtype='uint8'),np.ones((2,3))),'all_zero_rgb')
 def test_good(self):self.assertIsNone(m.render_input_error(np.ones((2,3,3),dtype='uint8'),np.ones((2,3))))
 def test_no_depth(self):self.assertEqual(m.render_input_error(np.ones((2,3,3)),np.zeros((2,3))),'invalid_depth')
 def test_cpp_error(self):self.assertTrue(m.render_log_error('[error] OptiX Error: OPTIX_ERROR_INTERNAL_ERROR'))
 def test_denoising(self):self.assertTrue(m.render_log_error('Failed to denoise'))
 def test_good_log(self):self.assertFalse(m.render_log_error('model loaded successfully'))
if __name__=='__main__':unittest.main()
