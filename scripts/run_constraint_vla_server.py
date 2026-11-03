"""Opt-in fixed program wrapper around unchanged RPent native LingBot server.
No tool routing/hidden scene access. Each inference rebinds measured EEF XYZ.
"""
import hashlib,json,os,time
from pathlib import Path
from physical_constraint_harness import LingBotPhysicalMap,physical_guidance,validate_program

def install(native_module):
 Native=native_module.LingbotVLAServer
 program_path=Path(os.environ['RSI_CONSTRAINT_PROGRAM_FILE']);raw=program_path.read_bytes()
 assert hashlib.sha256(raw).hexdigest()==os.environ['RSI_CONSTRAINT_PROGRAM_SHA256']
 program=validate_program(json.loads(raw));assert not program['landmarks']
 cap=float(os.environ['RSI_CONSTRAINT_VELOCITY_M']);assert 0<=cap<=0.01
 log=Path(os.environ['RSI_CONSTRAINT_TRACE']);counter=0
 class ProgramPolicy(Native):
  def __init__(self,*args,**kwargs):
   super().__init__(*args,**kwargs)
   self.vla.requires_grad_(False)
   self._coordinate_map=LingBotPhysicalMap(self.vla.feature_transform)
  def infer(self,observation):
   nonlocal counter
   if observation.get('reset'):return super().infer(observation)
   import numpy as np
   state=np.asarray(observation['observation.state']);assert state.shape==(16,) and np.isfinite(state).all()
   bindings={'left_eef':state[:3].tolist(),'right_eef':state[8:11].tolist()}
   counter+=1;steps=[];r={'index':counter,'started_unix':time.time(),'program_sha256':hashlib.sha256(raw).hexdigest(),'max_velocity_m':cap,'bindings':bindings,'status':'started'}
   with log.open('a') as f:f.write(json.dumps(r)+'\n')
   try:
    with physical_guidance(self.vla.model,self._coordinate_map,program,bindings,max_velocity_m=cap,ledger=steps):result=super().infer(observation)
    r['status']='completed';return result
   except BaseException as e:r.update(status='failed',error=repr(e));raise
   finally:
    r.update(finished_unix=time.time(),guidance=steps)
    with log.open('a') as f:f.write(json.dumps(r)+'\n')
 native_module.LingbotVLAServer=ProgramPolicy

if __name__=='__main__':
 import deploy.lingbot_vla_policy as module
 install(module)
 from robots.robotwin.vla_server import main
 main()
