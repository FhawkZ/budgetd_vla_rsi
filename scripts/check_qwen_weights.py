"""Load fixed weights once under a GPU lock; no generation or model requests."""
import fcntl, hashlib, json, os, subprocess, time
from pathlib import Path
runtime = Path(os.environ['RSI_RUNTIME_ROOT'])
output = runtime / 'outputs/qwen-deploy-20261029/weights-load-check.json'
lock = (runtime / 'locks/gpu0.lock').open('a')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
row = subprocess.check_output(['nvidia-smi', '-i', '0', '--query-gpu=memory.used,uuid', '--format=csv,noheader,nounits'], text=True).strip().split(',')
assert int(row[0]) < 100, 'GPU0 occupied'
procs = subprocess.check_output(['nvidia-smi', '-i', '0', '--query-compute-apps=pid', '--format=csv,noheader'], text=True).strip()
assert not procs, 'GPU0 has compute process'
os.environ['CUDA_VISIBLE_DEVICES'] = '0'
start = time.time()
report = {'status':'running','gpu':0,'gpu_uuid':row[1].strip(),'model_calls':0,'generated_tokens':0,'started_unix':start}
def save():
    output.write_text(json.dumps(report, indent=2))
save()
try:
    import torch
    from transformers import Qwen3VLForConditionalGeneration
    path = runtime / 'models/Qwen3-VL-8B-Instruct'
    manifest = json.loads((Path(__file__).resolve().parents[1] / 'configs/qwen-model-files.json').read_text())
    for r in manifest['files']:
        h = hashlib.sha256()
        with (path/r['path']).open('rb') as f:
            for chunk in iter(lambda:f.read(8<<20), b''):h.update(chunk)
        assert h.hexdigest() == r['sha256'], r['path']
    model = Qwen3VLForConditionalGeneration.from_pretrained(path, local_files_only=True, dtype=torch.bfloat16, device_map={'':'cuda:0'}, attn_implementation='sdpa').eval()
    report.update(status='passed', parameter_count=sum(p.numel() for p in model.parameters()), torch_version=torch.__version__, gpu_memory_allocated_bytes=torch.cuda.memory_allocated(), dtype=str(next(model.parameters()).dtype), all16_hashes_verified=True, model_type=model.config.model_type)
    del model
    torch.cuda.empty_cache()
except Exception as e:
    report.update(status='failed',error=repr(e));raise
finally:
    report['elapsed_seconds']=time.time()-start
    report['limitation']='Weights load only; no generation, tools, Agent evaluation or task score.'
    save()
