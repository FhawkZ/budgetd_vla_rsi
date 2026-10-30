"""Stage a separately pinned 30B candidate only; not a backend switch or inference. Two-hour download bound; original 8B artifacts remain frozen."""
import argparse, concurrent.futures, fcntl, hashlib, json, os, shutil, time
import urllib.parse, urllib.request
from pathlib import Path

CHUNK = 64 << 20

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()

def write_json(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n')
    tmp.replace(path)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit-files', type=int, default=0)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    runtime = Path(os.environ['RSI_RUNTIME_ROOT'])
    manifest = root / 'configs/qwen30b-candidate-model-files.json'
    spec = json.loads(manifest.read_text())
    rows = spec['files'][:args.limit_files] if args.limit_files else spec['files']
    model = runtime / 'models/Qwen3-VL-30B-A3B-Instruct'
    output = runtime / 'outputs/qwen30b-candidate-deploy-20261031'
    model.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    (runtime / 'locks').mkdir(exist_ok=True)
    lock = (runtime / 'locks/qwen30b-candidate-download.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    started = time.time()
    deadline = started + 7200
    status = {'status': 'running', 'pid': os.getpid(), 'started_unix': started,
              'manifest_sha256': digest(manifest), 'files_total': len(rows),
              'verified_files': [], 'model_calls': 0, 'gpu_jobs': 0,
              'limits': {'workers': 4, 'retries_per_chunk': 3, 'wall_seconds': 7200}}
    def save():
        status['updated_unix'] = time.time()
        write_json(output / 'status.json', status)
    def download_chunk(url, start, end, size, target):
        expected = end - start + 1
        if target.exists() and target.stat().st_size == expected:
            return
        for attempt in range(3):
            if time.time() >= deadline:
                raise TimeoutError('Deployment wall budget exhausted')
            try:
                request = urllib.request.Request(url, headers={'Range': f'bytes={start}-{end}'})
                with urllib.request.urlopen(request, timeout=120) as response:
                    if response.status == 206:
                        assert response.headers.get('Content-Range') == f'bytes {start}-{end}/{size}', 'Wrong Content-Range'
                    else:
                        assert response.status == 200 and start == 0 and end + 1 == size, 'Range ignored'
                    part = target.with_suffix('.part')
                    count = 0
                    with part.open('wb') as out:
                        while chunk := response.read(1 << 20):
                            count += len(chunk)
                            if count > expected or time.time() >= deadline:
                                raise RuntimeError('Transfer bound exceeded')
                            out.write(chunk)
                    assert count == expected, 'Incomplete chunk'
                    part.replace(target)
                return
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(1)
    save()
    try:
        need = sum(row['bytes'] for row in rows)
        assert shutil.disk_usage(model).free > 2 * need + (5 << 30), 'Insufficient staging space'
        for row in rows:
            name = Path(row['path'])
            assert not name.is_absolute() and '..' not in name.parts
            target = model / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if not (target.exists() and target.stat().st_size == row['bytes'] and digest(target) == row['sha256']):
                url = 'https://modelscope.cn/models/' + spec['repository'] + '/resolve/' + urllib.parse.quote(row['revision']) + '/' + urllib.parse.quote(row['path'])
                parts = model / (row['path'] + '.chunks')
                parts.mkdir(exist_ok=True)
                pieces = [(start, min(start + CHUNK, row['bytes']) - 1, parts / str(start)) for start in range(0, row['bytes'], CHUNK)]
                status['current_file'] = row['path']; save()
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                    futures = [pool.submit(download_chunk, url, s, e, row['bytes'], p) for s, e, p in pieces]
                    for future in concurrent.futures.as_completed(futures):
                        future.result()
                        status['current_file_chunks_ready'] = sum(p.exists() for _, _, p in pieces)
                        save()
                assembled = target.with_suffix(target.suffix + '.assembling')
                with assembled.open('wb') as out:
                    for _, _, part in pieces:
                        with part.open('rb') as inp:
                            shutil.copyfileobj(inp, out, 8 << 20)
                assert assembled.stat().st_size == row['bytes'] and digest(assembled) == row['sha256'], 'File SHA mismatch'
                assembled.replace(target)
                shutil.rmtree(parts)  # only our verified download chunks
            status['verified_files'].append(row); save()
            print('verified', row['path'], flush=True)
        if not args.limit_files:
            weights = set(json.loads((model / 'model.safetensors.index.json').read_text())['weight_map'].values())
            assert weights <= {r['path'] for r in rows}
        status.update(status='subset_verified' if args.limit_files else 'complete', model_path=str(model), total_verified_bytes=sum(r['bytes'] for r in rows))
        save()
    except Exception as exc:
        status.update(status='failed', error=repr(exc)); save(); raise

if __name__ == '__main__':
    main()
