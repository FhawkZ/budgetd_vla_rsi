"""One-shot six-forward controllability probe, cached DEVELOPMENT input only.
Synthetic +1cm Z goals are fixtures, not candidate skills or task scores.
"""
import argparse, copy, fcntl, hashlib, json, os, signal, subprocess, sys, time, traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda:f.read(8<<20),b""): h.update(b)
    return h.hexdigest()
def save(p,x):
    tmp=Path(str(p)+".tmp");tmp.write_text(json.dumps(x,indent=2)+"\n");tmp.replace(p)
def main():
    p=argparse.ArgumentParser();p.add_argument("--protocol",type=Path,required=True);p.add_argument("--sha",required=True);a=p.parse_args()
    assert sha(a.protocol)==a.sha
    cfg=json.loads(a.protocol.read_text());r=Path(os.environ["RSI_RUNTIME_ROOT"])
    assert cfg["status"]=="frozen" and cfg["max_vla_calls"]==6 and cfg["qwen_calls"]==0
    assert cfg["classification"]=="cached_development_controllability_fixture"
    for rel,h in cfg["code_sha256"].items():assert sha(ROOT/rel)==h,rel
    for rel,h in cfg["runtime_source_sha256"].items():assert sha(r/rel)==h,rel
    assert cfg["expected_hostname"]==os.uname().nodename
    out=r/"outputs"/cfg["run_id"];out.mkdir(exist_ok=False)
    save(out/"protocol.json",cfg)
    lock=(r/"locks"/f"gpu{cfg['gpu']}.lock").open("r+")
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    started=time.time()
    report={"status":"running","classification":cfg["classification"],"protocol_sha256":a.sha,
      "vla_calls_attempted":0,"vla_calls_completed":0,"qwen_calls":0,"simulation_episodes":0,
      "policy_actions":0,"accepted_updates":0,"strict_rsi":0,"pid":os.getpid(),
      "fixtures":[],"started_unix":started,"limitations":cfg["limitations"]}
    save(out/"report.json",report)
    try:
        gpu=cfg["gpu"]
        used=subprocess.check_output(["nvidia-smi","-i",str(gpu),"--query-gpu=memory.used,utilization.gpu","--format=csv,noheader,nounits"],text=True)
        processes=subprocess.check_output(["nvidia-smi","-i",str(gpu),"--query-compute-apps=pid","--format=csv,noheader"],text=True).strip()
        assert not processes and int(used.split(",")[0])<256,used
        disk=os.statvfs(r);free=disk.f_bavail*disk.f_frsize;capacity=disk.f_blocks*disk.f_frsize
        assert free>max(100*2**30,.2*capacity)+cfg["expected_output_bytes"] and disk.f_favail>100000
        report["preflight"]={"gpu":gpu,"gpu_memory_utilization":used.strip(),"free_bytes":free,"capacity_bytes":capacity,"free_inodes":disk.f_favail}
        model=r/cfg["model_path"];manifest=json.loads((ROOT/"configs/lingbot-model-manifest.json").read_text())
        assert manifest["sha"]==cfg["model_revision"]
        for row in manifest["siblings"]:
            q=model/row["rfilename"];assert q.stat().st_size==row["size"]
            if "lfs" in row:assert sha(q)==row["lfs"]["sha256"]
            else:
                b=q.read_bytes();assert hashlib.sha1(b"blob "+str(len(b)).encode()+bytes([0])+b).hexdigest()==row["blobId"]
        report["model_files_verified"]=len(manifest["siblings"]);save(out/"report.json",report)
        os.environ["CUDA_VISIBLE_DEVICES"]=str(gpu)
        os.environ["QWEN25_PATH"]=str(model/cfg["qwen_base"])
        os.environ["HF_HUB_OFFLINE"]="1";os.environ["TRANSFORMERS_OFFLINE"]="1"
        import numpy as np
        import torch
        from PIL import Image
        from deploy.lingbot_vla_policy import LingbotVLAServer,set_seed_everywhere
        from program_guidance import velocity_guidance
        policy=LingbotVLAServer(str(model),use_length=50,robot_norm_path=str(model/"norm_stats/robotwin_eef.json"),robot_config=model/"configs/robot_configs/robotwin_eef.yaml",num_denoising_step=10,use_compile=False)
        policy.vla.requires_grad_(False);assert not any(x.requires_grad for x in policy.vla.parameters())
        def payload(case):
            d=r/case["directory"];p=d/"inference-001.json"
            assert sha(p)==case["input_sha256"]
            x=json.loads(p.read_text());s=x["robot_state"]
            obs={"observation.state":np.array(s["left_eef_pose"]+[s["left_gripper"]]+s["right_eef_pose"]+[s["right_gripper"]],dtype=np.float32),"task":x["task_language"]}
            for view,key in [("head","observation.images.cam_high"),("left_wrist","observation.images.cam_left_wrist"),("right_wrist","observation.images.cam_right_wrist")]:
                q=d/x["images"][view]["path"];assert sha(q)==x["images"][view]["sha256"]
                obs[key]=np.array(Image.open(q).convert("RGB"))
            return obs
        def infer(case,mode):
            assert report["vla_calls_attempted"]<cfg["max_vla_calls"]
            report["vla_calls_attempted"]+=1
            rec={"index":report["vla_calls_attempted"],"case":case["directory"],"mode":mode,"input_sha256":case["input_sha256"],"seed":42,"status":"started"}
            path=out/f"call-{rec['index']:02d}.json";save(path,rec);save(out/"report.json",report)
            set_seed_everywhere(42);t=time.time()
            pred=np.asarray(policy.infer(payload(case))["action"])
            torch.cuda.synchronize()
            report["vla_calls_completed"]+=1
            np.save(out/f"call-{rec['index']:02d}.npy",pred)
            rec.update(status="completed",seconds=time.time()-t,shape=list(pred.shape),output_sha256=sha(out/f"call-{rec['index']:02d}.npy"))
            save(path,rec);save(out/"report.json",report)
            assert pred.shape==(50,16) and np.isfinite(pred).all()
            return pred
        for case in cfg["cases"]:
            baseline=infer(case,"native")
            target=baseline.copy();target[:,[2,10]]+=cfg["synthetic_z_offset_m"]
            obs=payload(case);policy.resize_image(obs)
            obs={k:torch.from_numpy(v) if isinstance(v,np.ndarray) else v for k,v in obs.items()}
            obs["action"]=torch.from_numpy(target);obs["action_is_pad"]=torch.zeros(50)
            transformed=policy.vla.feature_transform.apply(obs)["actions"].unsqueeze(0)
            assert transformed.shape[-1]>=16
            zero_log=[]
            with velocity_guidance(policy.vla.model,transformed,cfg["internal_xyz_indices"],0.0,zero_log):zero=infer(case,"zero_hook")
            assert np.array_equal(baseline,zero),"zero guidance changed native result"
            guidance_log=[]
            with velocity_guidance(policy.vla.model,transformed,cfg["internal_xyz_indices"],cfg["guide_scale"],guidance_log):guided=infer(case,"synthetic_z_guidance")
            indices=[0,1,2,8,9,10]
            fixture={"case":case["directory"],"zero_exact":True,"native_target_mse_m2":float(np.mean((baseline[:,indices]-target[:,indices])**2)),"guided_target_mse_m2":float(np.mean((guided[:,indices]-target[:,indices])**2)),"mean_signed_z_change_m":np.mean(guided[:,[2,10]]-baseline[:,[2,10]],axis=0).tolist(),"max_non_xyz_change":float(np.max(np.abs((guided-baseline)[:,[3,4,5,6,7,11,12,13,14,15]]))),"guidance_steps":len(guidance_log),"gradient_nonzero":any(x.get("gradient_norm",0)>0 for x in guidance_log)}
            report["fixtures"].append(fixture);save(out/f"fixture-{len(report['fixtures'])}.json",{"summary":fixture,"guidance":guidance_log,"zero":zero_log});save(out/"report.json",report)
        report["status"]="completed"
        report["peak_cuda_allocated_bytes"]=torch.cuda.max_memory_allocated()
        report["gate"]="pass_effect_only" if all(x["zero_exact"] and x["gradient_nonzero"] and x["guided_target_mse_m2"]<x["native_target_mse_m2"] for x in report["fixtures"]) else "reject_current_guidance_configuration"
    except BaseException as e:
        report["status"]="failed";report["error"]=repr(e);report["traceback"]=traceback.format_exc()
    finally:
        report["finished_unix"]=time.time();report["gpu_lock_interval_seconds"]=time.time()-started
        report["unused_vla_calls_cancelled"]=cfg["max_vla_calls"]-report["vla_calls_attempted"]
        save(out/"report.json",report);save(out/"CLOSE.json",{"status":"CLOSED","vla_calls_attempted":report["vla_calls_attempted"],"unused_cancelled":report["unused_vla_calls_cancelled"],"qwen_calls":0,"policy_actions":0})
        fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
        print(json.dumps(report),flush=True)
    return 0 if report["status"]=="completed" else 1
if __name__=="__main__":
    def expired(*args):raise TimeoutError("frozen 900s wall budget exhausted")
    signal.signal(signal.SIGALRM,expired);signal.alarm(900)
    sys.exit(main())
