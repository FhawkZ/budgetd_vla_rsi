"""CPU comparison with the actual pinned primitive using fake env/model only."""
import hashlib,json,os,sys
from pathlib import Path
import numpy as np
R=Path(os.environ['RSI_RUNTIME_ROOT']);ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'vendor/RPent-a744bd5f128ebef3cb8c6736cf7cd98adff681f1'))
sys.path.insert(0,str(ROOT/'tests'))
from test_bounded_vla import make
from robots.robotwin.primitives import RoboTwinPrimitives
native_e,native_m,native_h=make();p=RoboTwinPrimitives(env=native_e,model=native_m,seed=42,check_cancelled=lambda:None);p._build_lingbot_observation=native_h.build_observation
adapter_e,adapter_m,adapter_h=make()
for _ in range(2):
 p.lingbot_act(chunks=1,use_length=50)
 adapter_h.dispatch(dict(action='execute_vla_chunk',use_length=50))
assert native_m.seen==adapter_m.seen==[0,50]
for a,b in zip(native_e.executed,adapter_e.executed):np.testing.assert_array_equal(a,b)
try:p.lingbot_act(chunks=1,use_length=25);raise AssertionError('native unexpectedly accepts25')
except ValueError:pass
assert len(native_m.seen)==2
report=dict(status='passed',classification='CPU fake-env comparison against pinned actual native primitive, not task success',checks=['Two prefix50calls have identical inference observations and exact executed arrays to original primitive','Original primitive rejects25 before inference;25adapter is explicitly different'],qwen_calls=0,vla_model_inferences=0,simulator_episodes=0,interface_sha256=hashlib.sha256((ROOT/'scripts/bounded_vla.py').read_bytes()).hexdigest(),native_source_sha256=hashlib.sha256((R/'vendor/RPent-a744bd5f128ebef3cb8c6736cf7cd98adff681f1/robots/robotwin/primitives.py').read_bytes()).hexdigest())
o=R/'outputs/bounded-vla-prepare-20261031-1120';o.mkdir(exist_ok=True);(o/'cpu-native-equivalence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
