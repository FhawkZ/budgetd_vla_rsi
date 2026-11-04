"""Versioned resource-gate adaptation; v2 worker and policy remain byte-identical.
No retry of a robot episode. Only utilization-only resource sampling may wait6s.
No old protocol may run through this entrypoint: require explicit runner_version=3.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
from gpu_idle_gate import wait_idle

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("frozen_skillrsi_v2",ROOT/"scripts/run_skill_rsi_native_v2.py")
native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)

def gpu_read(gpu):
    rows=subprocess.check_output(["nvidia-smi","--query-gpu=index,uuid,pci.bus_id,memory.used,utilization.gpu","--format=csv,noheader,nounits"],text=True,timeout=2)
    g=next(x.strip().split(", ") for x in rows.splitlines() if int(x.split(",")[0])==gpu)
    apps=subprocess.check_output(["nvidia-smi","--query-compute-apps=gpu_uuid,pid","--format=csv,noheader"],text=True,timeout=2)
    return {"index":gpu,"uuid":g[1],"pci":g[2],"memory_mib":int(g[3]),"utilization":int(g[4]),"processes":[x for x in apps.splitlines() if g[1] in x],"time":time.time()}

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--protocol",required=True,type=Path);ap.add_argument("--check",action="store_true");a=ap.parse_args()
    cfg=json.loads(a.protocol.read_text());assert cfg.get("runner_version")==3
    native.verify(cfg)
    assert cfg["resource_wait_seconds"]==6
    if a.check:print("frozen_sources_verified_v3")
    else:
        receipt=Path(os.environ["RSI_RUNTIME_ROOT"])/"outputs"/(cfg["id"]+"-resource-checks.jsonl")
        assert not receipt.exists(),"one-shot resource receipt already exists"
        def check(gpu):
            return wait_idle(lambda:gpu_read(gpu),lambda row:native.append(receipt,row),timeout=6)
        native.gpu_check=check
        native.parent(cfg,a.protocol.resolve())
