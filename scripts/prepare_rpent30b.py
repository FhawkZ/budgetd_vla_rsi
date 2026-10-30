"""Freeze a single common-backend development attempt only after candidate qualification."""
import hashlib,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];R=Path(os.environ['RSI_RUNTIME_ROOT'])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
qual=R/'outputs/qwen30b-contract2-20261031-0700/report.json';q=json.loads(qual.read_text());assert q['status']=='passed' and q['token_ledger_match'] and q['hard_budget_rejection_verified'];assert (qual.parent/'CLOSE.json').exists()
image=R/'outputs/qwen30b-qual3-20261031-0640/server/0001-generation.json';assert json.loads(image.read_text())['image_count']==3
s=(ROOT/'scripts/run_rpent_structured.py').read_text().replace('serve_qwen_structured.py','serve_qwen_structured30b.py').replace('budget_proxy.py','budget_proxy30b.py').replace('Qwen3-VL-8B-Instruct','Qwen3-VL-30B-A3B-Instruct').replace('qwen3-vl-8b-instruct','qwen3-vl-30b-a3b-instruct')
s=s.replace("assert (receipt.parent/'CLOSE.json').exists()", "assert (receipt.parent/'CLOSE.json').exists()\n image_receipt=RUNTIME/cfg['image_receipt'];assert digest(image_receipt)==cfg['image_receipt_sha256'];assert json.loads(image_receipt.read_text())['image_count']==3\n assets=RUNTIME/cfg['model_assets_receipt'];assert digest(assets)==cfg['model_assets_receipt_sha256']\n for f in json.loads(assets.read_text())['files']:\n  asset=RUNTIME/'models/Qwen3-VL-30B-A3B-Instruct'/f['path'];assert asset.stat().st_size==f['bytes'] and asset.stat().st_mtime_ns==f['mtime_ns']")
s=s.replace("health('http://127.0.0.1:8018/health',qwen,150)", "assert health('http://127.0.0.1:8018/health',qwen,150)['model']=='qwen3-vl-30b-a3b-instruct'")
runner=ROOT/'scripts/run_rpent30b.py';assert not runner.exists();runner.write_text(s)
cfg=json.loads((ROOT/'configs/rpent-structured-native-dev64-20261031-0140.json').read_text());cfg['run_id']='rpent30b-native-dev64-20261031-0710';cfg['structured_receipt']=str(qual.relative_to(R));cfg['structured_receipt_sha256']=sha(qual)
cfg['image_receipt']=str(image.relative_to(R));cfg['image_receipt_sha256']=sha(image)
asset=R/'outputs/qwen30b-qualification-prepare-20261031-0630/assets.json';cfg['model_assets_receipt']=str(asset.relative_to(R));cfg['model_assets_receipt_sha256']=sha(asset)
cfg['code_sha256']={f:sha(ROOT/f) for f in ['scripts/run_rpent30b.py','scripts/structured_qwen.py','scripts/serve_qwen_structured30b.py','scripts/rpent_local_compaction.py','scripts/run_vla_only_pilot.py','scripts/budget_proxy30b.py']}
cfg['asset_manifests']['configs/qwen30b-candidate-model-files.json']=sha(ROOT/'configs/qwen30b-candidate-model-files.json')
cfg['adaptations'][0]='Qwen3-VL-30B-A3B-Instruct frozen BF16 MoE, explicit model id,32Kinput/1024output; same greedyseed42. Separate model backend, not8B method gain or original paper model.'
cfg['adaptations'].append('Native compaction unchanged afterCPUaudit: recorded dense world-map outputs dominate context. No lossy summaries or path/coordinate fixes. At most one64call attempt on this configuration; no prompt search.')
cfg['qualification_only_not_RSI']=False;cfg['baseline_development_not_RSI']=True;cfg['baseline_comparison']='Backend feasibility diagnosis on same already-used development cases. No stable-rate inference or learned-method comparison.'
p=ROOT/'configs/rpent30b-native-dev64-20261031-0710.json';assert not p.exists();p.write_text(json.dumps(cfg,indent=2)+'\n');print(sha(p))
