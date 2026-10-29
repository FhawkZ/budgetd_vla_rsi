"""Bounded environment smoke; no robot task or Agent call."""
import argparse,fcntl,json,os,subprocess,time,math
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output',required=True);args=p.parse_args()
R=Path(os.environ['RSI_RUNTIME_ROOT']);O=Path(args.output);O.mkdir(parents=True,exist_ok=True);(R/'locks').mkdir(parents=True,exist_ok=True);locks=[]
try:
 for gpu in [0,1]:
  f=(R/f'locks/gpu{gpu}.lock').open('a');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
 rows=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used','--format=csv,noheader,nounits'],text=True)
 procs=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
 assert not procs and all(int(row.split(',')[1])<100 for row in rows.splitlines()),'GPU occupied'
 import sapien,numpy as np
 scene=sapien.Scene();scene.set_timestep(1/240);scene.add_ground(0)
 b=scene.create_actor_builder();b.add_box_collision(half_size=[.02]*3);b.add_box_visual(half_size=[.02]*3,material=sapien.render.RenderMaterial(base_color=[.2,.8,.2,1]));a=b.build(name='setup_probe');a.set_pose(sapien.Pose([0,0,.2]))
 for _ in range(240):scene.step()
 z=float(a.get_pose().p[2]);assert abs(z-.02)<.003
 scene.set_ambient_light([.5,.5,.5]);scene.add_directional_light([0,1,-1],[1,1,1])
 cam=scene.add_camera('setup',128,128,1.0,.01,10);cam.set_entity_pose(sapien.Pose([-.3,0,.2],[math.cos(.27),0,math.sin(.27),0]))
 scene.update_render();cam.take_picture();color=cam.get_picture('Color');assert color.shape==(128,128,4) and np.isfinite(color).all() and float(color[:,:,:3].std())>.001
 from PIL import Image
 Image.fromarray((np.clip(color[:,:,:3],0,1)*255).astype('uint8')).save(O/'render.png')
 report={'passed':True,'physics_steps':240,'final_box_z':z,'render_shape':list(color.shape),'render_std':float(color[:,:,:3].std()),'agent_calls':0,'robot_actions':0,'role':'installation smoke only'}
except Exception as e:
 report={'passed':False,'error':repr(e),'agent_calls':0,'robot_actions':0};raise
finally:
 if 'report' in locals():(O/'physics-render-check.json').write_text(json.dumps(report,indent=2));print(report,flush=True)
 for f in locks:f.close()
