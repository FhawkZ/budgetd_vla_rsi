"""Common bounded VLA adapter: fixed50 versus prefix25 schedule diagnosis.

Autonomous reduced tool controller; explicit adaptation, not native RPent.
Default is CPU-only configuration checking. --run requires a separately frozen
protocol and its exact SHA. No planner, Qwen, expert action, skill update or RSI.
"""
from __future__ import annotations

import argparse
import ast
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
RPENT_COMMIT = "a744bd5f128ebef3cb8c6736cf7cd98adff681f1"
VLA_REVISION = "e727b46cd220b66981ea4d2fd9ba84adc189e2cc"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, default=lambda x: x.tolist()) + "\n")
    tmp.replace(path)


def append(path, value):
    with Path(path).open("a") as stream:
        stream.write(json.dumps(value, default=lambda x: x.tolist()) + "\n")


def validate(cfg):
    assert cfg['classification']=='common_reduced_model_controller_development'
    assert cfg['status'] in {'draft','frozen'} and cfg['execution_host']=='lzgpu201'
    assert cfg['max_qwen_calls_total']==64 and cfg['skill_updates']==0 and cfg['weights_frozen']
    assert cfg['vla_revision']==VLA_REVISION and cfg['rpent_commit']==RPENT_COMMIT
    assert cfg['gpu']==1 and cfg['task_config']=='demo_randomized'
    assert cfg['horizon']==1200 and cfg['max_episodes']==2
    assert cfg['max_vla_inferences_per_episode']==48 and cfg['max_vla_inferences_total']==96
    assert [(x['task'],x['seed']) for x in cfg['cases']]==[('stack_blocks_two',2026103011),('handover_block',2026103012)]
    assert cfg['max_environment_reset_rpc_per_episode']==1
    assert cfg['episode_wall_seconds']==1200 and cfg['total_wall_seconds']==2400
    assert cfg['renderer_adapter']=='explicit_device_native_rt_no_denoiser'
    assert cfg['stop_on_infrastructure_error'] is True
    assert cfg['env_working_directory']=='asset_snapshot_root'
    return cfg


def preflight(cfg, strict=False):
    assert digest(ROOT/"scripts/bounded_vla.py")==cfg["interface_sha256"]
    receipt=Path(os.environ["RSI_RUNTIME_ROOT"])/cfg["cpu_receipt"]
    assert digest(receipt)==cfg["cpu_receipt_sha256"] and json.loads(receipt.read_text())["status"]=="passed"
    runtime = Path(os.environ["RSI_RUNTIME_ROOT"]).resolve()
    source = runtime / "vendor" / ("RPent-" + RPENT_COMMIT)
    if cfg.get("public_language_manifest"):
        from task_language_contract import load
        language_file=ROOT/cfg["public_language_manifest"]
        assert digest(language_file)==cfg["public_language_manifest_sha256"]
        assert digest(ROOT/"scripts/task_language_contract.py")==cfg["language_binding_sha256"]
        languages=load(language_file,runtime/"backends/robotwin-ae507381-c15cc97b")
        assert cfg["policy_task_instructions"]=={x["task"]:languages[x["task"]] for x in cfg["cases"]}
    for rel, sha in cfg["source_sha256"].items():
        assert digest(source / rel) == sha, f"Changed pinned source: {rel}"
    manifest = json.loads((ROOT / "configs/lingbot-model-manifest.json").read_text())
    assert manifest["sha"] == VLA_REVISION
    assert digest(ROOT / "configs/lingbot-model-manifest.json") == cfg["model_manifest_sha256"]
    model = runtime / cfg["model_relative_path"]
    missing = [x["rfilename"] for x in manifest["siblings"]
               if not (model / x["rfilename"]).is_file()
               or (model / x["rfilename"]).stat().st_size != x["size"]]
    # AST checks only: no simulator/model imports or GPU allocation.
    tree = ast.parse((source / "robots/robotwin/env_server.py").read_text())
    src = ast.unparse(tree)
    assert "'auto_reset': False" in src
    assert "'max_episode_steps': step_limit" in src
    source_text = (source / "robots/robotwin/primitives.py").read_text()
    assert 'self.model.infer(observation)' in source_text
    assert 'observation["task_language"]' in source_text
    site = Path(sys.prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
    native_base = site / "robotwin/envs/_base_task.py"
    assert 'set_camera_shader_dir("rt")' in native_base.read_text()
    assert "set_camera_shader_dir" not in RENDER_BOOTSTRAP
    result = {"classification": "CPU_configuration_contract_only", "model_calls": 0,
              "GPU_used": False, "config_status": cfg["status"],
              "model_missing_or_wrong_size": missing, "native_auto_reset": False,
              "fixed_source_hashes_verified": len(cfg["source_sha256"]),
              "max_episode_steps_passed_to_native_runtime": True,
              "runtime_ready_not_proven": True}
    if strict:
        assert socket.gethostname() == cfg["execution_hostname"], "Wrong execution host"
        assert Path(sys.prefix).resolve() == runtime / "software/envs/robotwin", "Use uv robotwin profile"
        assert not missing, f"Incomplete model: {missing}"
        for row in manifest["siblings"]:
            path = model / row["rfilename"]
            if "lfs" in row:
                assert digest(path) == row["lfs"]["sha256"], row["rfilename"]
            else:
                h = hashlib.sha1(b"blob " + str(row["size"]).encode() + b"\0")
                h.update(path.read_bytes())
                assert h.hexdigest() == row["blobId"], row["rfilename"]
        from robotwin.assets import validate_root
        result["assets"] = validate_root(runtime / cfg["assets_relative_path"])
        result["all_model_hashes_verified"] = True
    return result


def proc_identity(pid):
    try:
        # Field 22 (starttime); comm may itself contain spaces.
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return fields[19], fields[0]
    except FileNotFoundError:
        return None


def cleanup_owned(path):
    cleaned = []
    if not path.exists():
        return cleaned
    for line in path.read_text().splitlines():
        row = json.loads(line)
        pid = row["pid"]
        identity = proc_identity(pid)
        if identity and identity[0] == row["starttime"] and identity[1] != "Z":
            os.kill(pid, signal.SIGTERM)
            for _ in range(30):
                identity = proc_identity(pid)
                if not identity or identity[0] != row["starttime"] or identity[1] == "Z":
                    break
                time.sleep(.1)
            identity = proc_identity(pid)
            if identity and identity[0] == row["starttime"] and identity[1] != "Z":
                os.kill(pid, signal.SIGKILL)
                for _ in range(20):
                    identity = proc_identity(pid)
                    if not identity or identity[0] != row["starttime"] or identity[1] == "Z":
                        break
                    time.sleep(.1)
        identity = proc_identity(pid)
        cleaned.append({"pid": pid, "live": bool(identity and identity[0] == row["starttime"] and identity[1] != "Z")})
    return cleaned


def gpu_snapshot(index):
    row = subprocess.check_output(
        ["nvidia-smi", "-i", str(index), "--query-gpu=uuid,memory.used,utilization.gpu,pci.bus_id",
         "--format=csv,noheader,nounits"], text=True, timeout=10).strip().split(",")
    procs = subprocess.check_output(
        ["nvidia-smi", "-i", str(index), "--query-compute-apps=pid",
         "--format=csv,noheader"], text=True, timeout=10).strip()
    return {"uuid": row[0].strip(), "memory_mib": int(row[1]), "utilization_percent": int(row[2]),
            "pci_bus_id": row[3].strip(), "compute_pids": procs}


# Loaded only inside an owned env_server process. CUDA_VISIBLE_DEVICES does not
# suffice for SAPIEN's Vulkan device choice. No physics or success rule changes.
RENDER_BOOTSTRAP = r'''
import os, sys
if os.environ.get("RSI_VLA_RENDER_CHILD") == "1":
    try:
        import importlib, json, sapien
        device = sapien.Device("cuda:0")
        expected = os.environ["RSI_EXPECTED_GPU_PCI"].lower()[-7:]
        assert device.pci_string.lower()[-7:] == expected
        old_denoiser = sapien.render.set_ray_tracing_denoiser
        sapien.render.set_ray_tracing_denoiser = lambda ignored: old_denoiser("none")
        engine = importlib.import_module("sapien.wrapper.engine")
        old_scene = engine.Scene
        engine.Scene = lambda: old_scene([sapien.physx.PhysxCpuSystem(), sapien.render.RenderSystem(device)])
        import sapien.core as core
        class PinnedRenderer(sapien.pysapien.render.SapienRenderer):
            def __init__(self, **kwargs):
                super().__init__(device)
            def create_material(self):
                return sapien.render.RenderMaterial()
        sapien.SapienRenderer = PinnedRenderer
        core.SapienRenderer = PinnedRenderer
        print("rsi_render_adapter " + json.dumps({"device": device.pci_string, "shader": "native_rt", "denoiser": "none"}), flush=True)
    except BaseException:
        import traceback
        traceback.print_exc()
        os._exit(73)
'''


def worker(cfg, index, out):
    """Exactly one native reset and only RGB-conditioned learned actions."""
    import numpy as np
    from PIL import Image
    from rpent.utils.daemon import ProcessDaemon
    from rpent.dashboard.events import NullDashboardEventSink
    from robots.robotwin.robot_spec import _init_runtime
    from robots.robotwin.primitives import RoboTwinPrimitives
    from robots.robotwin.env_client import RoboTwinEnvClient

    started = time.time()
    report = {"status": "running", "classification": cfg["classification"], **cfg["cases"][index],
              "qwen_calls": 0, "skill_updates": 0, "strict_rsi_rounds": 0,
              "vla_inferences": 0, "environment_reset_rpc": 0, "native_actions": 0,
              "native_eval_success": None, "started_unix": started}
    save(out / "episode.json", report)
    daemons = []
    original_start = ProcessDaemon.start
    def start_owned(daemon):
        if "robotwin_env_server" == daemon.name:
            asset_root = Path(os.environ["RSI_RUNTIME_ROOT"]) / cfg["assets_relative_path"]
            assert (asset_root / "assets/objects/objaverse/list.json").is_file()
            daemon.cwd = str(asset_root)
            daemon.subprocess_env.update(ROBOTWIN_ASSETS_ROOT=str(asset_root), ASSETS_PATH=str(asset_root))
            bootstrap = out / "bootstrap"
            bootstrap.mkdir(exist_ok=True)
            (bootstrap / "sitecustomize.py").write_text(RENDER_BOOTSTRAP)
            daemon.subprocess_env["PYTHONPATH"] = str(bootstrap) + os.pathsep + daemon.subprocess_env.get("PYTHONPATH", "")
            daemon.subprocess_env["RSI_VLA_RENDER_CHILD"] = "1"
        original_start(daemon)
        daemons.append(daemon)
        identity = proc_identity(daemon._proc.pid)
        assert identity is not None
        append(out / "owned-daemons.jsonl", {"pid": daemon._proc.pid, "starttime": identity[0],
                                            "name": daemon.name, "cmd": daemon.cmd, "cwd": daemon.cwd,
                                            "CUDA_VISIBLE_DEVICES": daemon.subprocess_env.get("CUDA_VISIBLE_DEVICES")})
    ProcessDaemon.start = start_owned
    original_reset = RoboTwinEnvClient.reset
    def counted_reset(env):
        report["environment_reset_rpc"] += 1
        save(out / "episode.json", report)
        assert report["environment_reset_rpc"] <= 1, "Unexpected environment reset"
        return original_reset(env)
    RoboTwinEnvClient.reset = counted_reset
    runtime = Path(os.environ["RSI_RUNTIME_ROOT"])
    kwargs = None
    try:
        args = argparse.Namespace(task_name=report["task"], seed=report["seed"], task_config=cfg["task_config"],
                                  max_episode_steps=cfg["horizon"], env_endpoint=None, vla_endpoint=None,
                                  robotwin_assets_path=str(runtime / cfg["assets_relative_path"]),
                                  vla_model_path=str(runtime / cfg["model_relative_path"]),
                                  lingbot_robot_config=None, cuda_device=str(cfg["gpu"]),
                                  env_cuda_device=None, vla_cuda_device=None)
        _, kwargs = _init_runtime(args, out, NullDashboardEventSink(), None)
        env, model = kwargs["env"], kwargs["model"]
        assert report["environment_reset_rpc"] == 1, "Expected exactly one native reset RPC"
        status = env.last_info["episode_status"]
        assert status["actual_seed"] == report["seed"]
        assert status["step_lim"] == cfg["horizon"], status
        assert status["take_action_cnt"] == 0, status
        assert not status["eval_success"], "Initial state is already successful; invalid screening case"
        instruction = env.get_task_language()
        report["native_task_language"] = instruction
        if cfg.get("public_language_manifest"):
            instruction=cfg["policy_task_instructions"][report["task"]]
            env.get_task_language=lambda: instruction
            report["language_adaptation"]="Client public task language binding; same frozen text required for every comparison arm. Original environment language retained above; no observation/score/action modification."
        assert instruction==cfg["cases"][index]["instruction"], "native language mismatch"
        report["policy_task_language"] = instruction
        report["initial_robot_state"] = env.last_info["robot_state"]
        original_infer = model.infer
        def traced_infer(observation):
            report["vla_inferences"] += 1
            save(out / "episode.json", report)  # failed inference still costs one
            assert report["vla_inferences"] <= cfg["max_vla_inferences_per_episode"]
            assert observation["task_language"] == instruction
            prefix = out / f"inference-{report['vla_inferences']:03d}"
            images = {}
            for camera, view in observation["views"].items():
                rgb = np.asarray(view["rgb"])
                assert rgb.ndim == 3 and rgb.shape[-1] == 3 and rgb.dtype == np.uint8
                file = prefix.with_name(prefix.name + "-" + camera + ".png")
                Image.fromarray(rgb).save(file)
                images[camera] = {"path": file.name, "sha256": digest(file), "shape": list(rgb.shape)}
            if report["vla_inferences"]==1:
                assert {k:v["sha256"] for k,v in images.items()}==cfg["cases"][index]["initial_image_sha256"], "initial RGB mismatch: stop without retry"
                assert json.dumps(observation["robot_state"],sort_keys=True,default=lambda x:x.tolist())==json.dumps(cfg["cases"][index]["initial_robot_state"],sort_keys=True), "initial state mismatch"
            before = time.time()
            record = {"index": report["vla_inferences"], "task_language": instruction,
                      "images": images, "robot_state": observation["robot_state"], "started_unix": before}
            save(prefix.with_suffix(".json"), record)
            try:
                actions = original_infer(observation)
                assert actions.ndim == 2 and actions.shape[1] == 16 and np.isfinite(actions).all()
                np.save(prefix.with_suffix(".npy"), actions)
                record.update(status="completed", elapsed_seconds=time.time()-before,
                              action_shape=list(actions.shape), actions_sha256=digest(prefix.with_suffix(".npy")))
                return actions
            except BaseException as exc:
                record.update(status="failed", elapsed_seconds=time.time()-before, error=repr(exc))
                raise
            finally:
                save(prefix.with_suffix(".json"), record)
        model.infer = traced_infer
        primitives = RoboTwinPrimitives(**kwargs, check_cancelled=lambda: None)
        from bounded_vla import BoundedVLA
        harness=BoundedVLA(env,model,primitives._build_lingbot_observation,horizon=cfg["horizon"],max_inferences=48)
        from bounded_controller import Controller
        tools=json.loads((ROOT/'configs/bounded-vla-interface-v1.json').read_text())['tools']
        initial=harness.dispatch({'action':'observe'})
        # Check initial inputs even when the controller never chooses an action.
        initial_hashes={}
        for name,view in initial['views'].items():
            file=out/('initial-'+name+'.png');Image.fromarray(np.asarray(view['rgb'])).save(file);initial_hashes[name]=digest(file)
        assert initial_hashes==cfg['cases'][index]['initial_image_sha256']
        assert json.dumps(initial['robot_state'],sort_keys=True,default=lambda x:x.tolist())==json.dumps(cfg['cases'][index]['initial_robot_state'],sort_keys=True)
        report['initial_images_equal']=True;report['initial_state_equal']=True
        controller=Controller(tools,initial,'http://127.0.0.1:18029/v1/chat/completions',out/'controller',cfg['max_qwen_calls_per_episode'])
        for _ in range(cfg['max_qwen_calls_per_episode']):
            status=env.last_info['episode_status']
            if status['eval_success'] or status['take_action_cnt']>=cfg['horizon'] or harness.stopped:break
            try:
                decision=controller.decide({'remaining_inferences':48-harness.inferences,'remaining_observations':48-harness.observations,'remaining_native_actions':cfg['horizon']-int(status['take_action_cnt'])})
                report['qwen_calls']=controller.calls;save(out/'episode.json',report)
                append(out/'decisions.jsonl',{'call':controller.calls,'decision':decision})
                result=harness.dispatch(decision)
                if decision['action']=='observe':
                    controller.feedback({'observation_returned':True},result)
                elif decision['action']=='stop':
                    controller.feedback({'stopped':True});break
                else:
                    selected=result.pop('selected_actions');chosen=out/f"executed-prefix-{report['vla_inferences']:03d}.npy";np.save(chosen,selected)
                    result['selected_actions_sha256']=digest(chosen);result['selected_actions_shape']=list(selected.shape)
                    append(out/'chunks.jsonl',{'time':time.time(),'result':result,'robot_state':env.last_info['robot_state']})
                    # No scorer or task outcome supplied to the controller.
                    controller.feedback({'submitted_waypoints':len(selected),'native_action_counter_delta':result['executed_actions']})
                status=env.last_info['episode_status']
                report.update(native_actions=int(status['take_action_cnt']),native_eval_success=bool(status['eval_success']))
                save(out/'episode.json',report)
            except Exception as exc:
                report.update(controller_error=repr(exc),qwen_calls=controller.calls)
                # Closed policy failure: no repaired arguments, retries or forced motion.
                break
        report["interface_status"]=harness.status()
        final_status = dict(env.last_info["episode_status"])
        for camera in ("head", "left_wrist", "right_wrist"):
            Image.fromarray(np.asarray(env.render_camera(camera))).save(out / f"terminal-{camera}.png")
        report.update(status="completed", native_episode_status=final_status,
                      native_eval_success=bool(final_status["eval_success"]),
                      native_actions=int(final_status["take_action_cnt"]),
                      final_robot_state=env.last_info["robot_state"],
                      termination="native_success" if final_status["eval_success"] else ("bounded_horizon" if final_status["take_action_cnt"]>=cfg["horizon"] else ("controller_error" if report.get("controller_error") else ("controller_stop" if harness.stopped else "controller_call_cap"))),
                      limitation="One development scene; reduced autonomous controller adaptation, no learning, forgetting or RSI evidence.")
    except BaseException as exc:
        report.update(status="infrastructure_error", error=repr(exc), traceback=traceback.format_exc())
        if kwargs is not None:
            report["last_native_episode_status"] = kwargs["env"].last_info.get("episode_status")
        raise
    finally:
        for daemon in reversed(daemons):
            try:
                daemon.stop(timeout=3)
            except Exception as exc:
                report.setdefault("cleanup_errors", []).append(repr(exc))
        report.update(finished_unix=time.time(), wall_seconds=time.time()-started)
        save(out / "episode.json", report)


def run(cfg, config_path, expected_sha):
    assert cfg["status"] == "frozen", "Draft protocol cannot run"
    assert digest(config_path) == expected_sha, "Exact frozen protocol SHA required"
    assert cfg["runner_sha256"] == digest(__file__), "Runner not frozen"
    runtime = Path(os.environ["RSI_RUNTIME_ROOT"]).resolve()
    out = runtime / "outputs" / cfg["run_id"]
    assert out.parent == runtime / "outputs" and not out.exists()
    preflight_result = preflight(cfg, strict=True)
    (runtime / "locks").mkdir(exist_ok=True)
    lock = (runtime / f"locks/gpu{cfg['gpu']}.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    gpu = gpu_snapshot(cfg["gpu"])
    assert gpu["memory_mib"] < 100 and not gpu["compute_pids"], gpu
    out.mkdir()
    save(out / "protocol.json", cfg)
    (out/"code").mkdir()
    import shutil
    for rel in ["scripts/run_model_bounded_vla.py","scripts/bounded_vla.py","scripts/bounded_controller.py"]:shutil.copy2(ROOT/rel,out/"code"/Path(rel).name)
    report = {"status": "running", "classification": cfg["classification"], "started_unix": time.time(),
              "protocol_sha256": expected_sha, "runner_sha256": digest(__file__), "gpu_before": gpu,
              "preflight": preflight_result, "episodes": [], "qwen_calls": 0, "skill_updates": 0}
    save(out / "report.json", report)
    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"signal {signum}")
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    active = None
    current = None
    try:
        for index, case in enumerate(cfg["cases"]):
            remaining = cfg["total_wall_seconds"] - (time.time() - report["started_unix"])
            assert remaining > 0, "Total wall budget exhausted"
            current = out / f"{index:02d}-{case['task']}-s{case['seed']}"
            current.mkdir()
            env = os.environ.copy()
            for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_BASE_URL", "ANTHROPIC_BASE_URL"):
                env.pop(key, None)
            source = runtime / "vendor" / ("RPent-" + RPENT_COMMIT)
            env.update(PYTHONPATH=str(source), RPENT_REPO_ROOT=str(source),
                       RPENT_RLINF_ROOT=str(runtime / cfg["rlinf_relative_path"]),
                       CUDA_VISIBLE_DEVICES=str(cfg["gpu"]), CUDA_DEVICE_ORDER="PCI_BUS_ID",
                       HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                       RSI_EXPECTED_GPU_PCI=gpu["pci_bus_id"], NO_PROXY="127.0.0.1,localhost",
                       RSI_VLA_WORKER_PROTOCOL_SHA256=expected_sha)
            with (current / "worker.log").open("w") as log:
                active = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--config", str(config_path),
                                           "--worker", str(index), "--output", str(current)],
                                          env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    code = active.wait(timeout=min(cfg["episode_wall_seconds"], remaining))
                except subprocess.TimeoutExpired:
                    os.killpg(active.pid, signal.SIGTERM)
                    try:
                        active.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(active.pid, signal.SIGKILL)
                        active.wait(timeout=5)
                    code = 124
            cleanup = cleanup_owned(current / "owned-daemons.jsonl")
            ep = json.loads((current / "episode.json").read_text()) if (current / "episode.json").exists() else {}
            if code != 0:
                ep.update(status="interrupted" if code == 124 else "infrastructure_error", worker_exit_code=code)
                save(current / "episode.json", ep)
            report["episodes"].append({"case": case, "result": ep, "cleanup": cleanup})
            save(out / "report.json", report)
            active = None
            assert not any(x["live"] for x in cleanup), "Owned process remained live"
            if code != 0:
                raise RuntimeError(f"Episode failed with exit {code}; no resampling or automatic retry")
        report["status"] = "completed"
    except BaseException as exc:
        report.update(status="closed_failed", error=repr(exc), traceback=traceback.format_exc())
        raise
    finally:
        if active is not None and active.poll() is None:
            os.killpg(active.pid, signal.SIGTERM)
            try:
                active.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(active.pid, signal.SIGKILL)
                active.wait(timeout=5)
        if current is not None and (current / "episode.json").exists():
            current_case = cfg["cases"][int(current.name.split("-", 1)[0])]
            if not any(row["case"] == current_case for row in report["episodes"]):
                interrupted_episode = json.loads((current / "episode.json").read_text())
                if interrupted_episode.get("status") == "running":
                    interrupted_episode["status"] = "interrupted"
                    save(current / "episode.json", interrupted_episode)
                report["episodes"].append({"case": current_case, "result": interrupted_episode})
        if current is not None:
            report["final_cleanup"] = cleanup_owned(current / "owned-daemons.jsonl")
        report.update(finished_unix=time.time(), GPU_allocation_seconds=time.time()-report["started_unix"],
                      gpu_after=gpu_snapshot(cfg["gpu"]),
                      total_native_actions=sum(x["result"].get("native_actions", 0) for x in report["episodes"]),
                      total_vla_inferences=sum(x["result"].get("vla_inferences", 0) for x in report["episodes"]),
                      strict_rsi_rounds=0, qwen_calls=sum(x["result"].get("qwen_calls",0) for x in report["episodes"]))
        save(out / "report.json", report)
        save(out/"CLOSE.json",dict(status=report["status"],unused_allowance="canceled",inferences=report["total_vla_inferences"],maximum=cfg["max_vla_inferences_total"]))
        lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/vla-only-screening-draft.json")
    parser.add_argument("--check", action="store_true", help="CPU-only default")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--protocol-sha256")
    parser.add_argument("--worker", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--output", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    cfg = validate(json.loads(args.config.read_text()))
    if args.worker is not None:
        assert cfg["status"] == "frozen" and args.output is not None
        assert os.environ.get("RSI_VLA_WORKER_PROTOCOL_SHA256") == digest(args.config)
        assert cfg["runner_sha256"] == digest(__file__)
        worker(cfg, args.worker, args.output)
    elif args.run:
        assert args.protocol_sha256 and not args.check
        from qwen_service_owner import service
        def timeout(*unused):raise TimeoutError('overall model-controller wall limit')
        signal.signal(signal.SIGALRM,timeout);signal.alarm(2700)
        try:
            with service(cfg):run(cfg, args.config.resolve(), args.protocol_sha256)
        finally:signal.alarm(0)
    else:
        print(json.dumps(preflight(cfg), indent=2))


if __name__ == "__main__":
    main()

