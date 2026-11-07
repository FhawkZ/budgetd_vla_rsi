"""Budgeted audit wrapper around the UNMODIFIED released DeepSeek caller adapter.

No credential values enter request/response receipts. Preserve upstream prompt,
full task_spec, JSON parser and adapter decoding parameters. No automatic retries.
"""
import contextlib
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import time

from skill_rsi_caller_bridge import checked, pure_functions


def dump(path, value):
    p = Path(path)
    with p.open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.flush(); os.fsync(f.fileno())


def reserve(path, request_bytes, max_tokens, max_calls, usd_cap):
    """Conservative peak-rate reservation, never reclaimed after unknown failure.

UTF8 bytes + 1024 framing tokens bound this one-message text request. This is
an enforcement reserve, not a reported actual charge. API usage is separate.
"""
    if request_bytes > 200000 or max_tokens != 32768:
        raise ValueError('request/token bound')
    amount = ((request_bytes + 1024) * .30 + max_tokens * 1.20) / 1e6
    p = Path(path)
    with p.open('a+') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        rows = [json.loads(x) for x in f if x.strip()]
        if len(rows) >= max_calls or sum(x['reserved_usd'] for x in rows) + amount > usd_cap:
            raise RuntimeError('shared API budget exhausted before request')
        row = dict(index=len(rows)+1, reserved_usd=amount, request_bytes=request_bytes,
                   max_tokens=max_tokens, time=time.time(), accounting='reservation_not_actual_charge')
        f.seek(0, 2); f.write(json.dumps(row)+'\n'); f.flush(); os.fsync(f.fileno())
        return row


@contextlib.contextmanager
def capture_http(module, directory):
    """Capture body only; never serialize headers, Request repr or API key."""
    original = module.urllib.request.urlopen
    def audited(req, *args, **kwargs):
        if req.full_url != 'https://api.deepseek.com/chat/completions':
            raise ValueError('official endpoint required')
        dump(directory/'request.json', json.loads(req.data))
        with original(req, *args, **kwargs) as response:
            raw = response.read()
        (directory/'response.raw.json').write_bytes(raw)
        return io.BytesIO(raw)
    module.urllib.request.urlopen = audited
    try:
        yield
    finally:
        module.urllib.request.urlopen = original


class DeepSeekBroker:
    def __init__(self, root, limits, output, endpoint=None, adapter=None):
        self.limits = dict(limits)
        if self.limits['decisions_max'] != 4:
            raise ValueError('released decision budget required')
        self.output = Path(output); self.output.mkdir(parents=True, exist_ok=False)
        self.calls = 0
        self.template = checked(root, 'prompts/caller_prompt.md')
        self.formatters = pure_functions(root, 'broker.py', ['render','fill'], {'json':json,'re':re})
        if adapter is None:
            from adapters import openai_compat
            self.adapter = openai_compat.Adapter('deepseek_flash')
            self.module = openai_compat
        else:
            self.adapter, self.module = adapter, None
        c = self.adapter.cfg
        if c['model'] != 'deepseek-flash' or c['base_url'] != 'https://api.deepseek.com':
            raise ValueError('fixed official provider')
        if c['params'] != {'temperature':0,'max_tokens':32768} or c['structured_output'] != 'json_object':
            raise ValueError('released caller decoding required')

    def decide(self, ctx, context_sha, k):
        if k != self.calls or self.calls >= 4:
            raise RuntimeError('decision sequence/budget')
        if set(ctx) != {'task_spec','skill_md','atoms','history','decisions_used','decisions_max','calls_remaining'}:
            raise ValueError('native caller context contract')
        # Preserve exactly the released task_spec. Do not add evaluator results,
        # hidden test feedback or other campaigns; do not redact criterion_source.
        prompt = self.formatters['fill'](self.template, dict(self.limits, context=self.formatters['render'](ctx)))
        n = len(json.dumps({'model':'deepseek-flash','messages':[{'role':'user','content':prompt}],
                            'temperature':0,'max_tokens':32768,'response_format':{'type':'json_object'}}).encode())
        reservation = reserve(os.environ['RSI_DEEPSEEK_LEDGER'], n, 32768,
                              int(os.environ['RSI_DEEPSEEK_MAX_CALLS']), float(os.environ['RSI_DEEPSEEK_USD_CAP']))
        self.calls += 1
        d = self.output / f'{self.calls:03d}'; d.mkdir()
        dump(d/'context.json',ctx); (d/'prompt.txt').write_text(prompt)
        t0 = time.monotonic()
        receipt = dict(index=self.calls, status='pending', input_tokens=None, output_tokens=None,
                       native_context_sha256=context_sha, attempts=1, reservation=reservation,
                       prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest())
        try:
            scope = capture_http(self.module,d) if self.module else contextlib.nullcontext()
            with scope:
                r = self.adapter.caller(d,prompt,None,180,d,'native')
            receipt.update(r)
            if receipt.get('finish_reason') == 'length':
                receipt.update(status='refused', refusal='truncated_response_no_repair')
            if receipt.get('status') != 'ok':
                raise RuntimeError('official_adapter_'+str(receipt.get('status')))
            return receipt
        finally:
            receipt.update(latency_seconds=time.monotonic()-t0,waited_seconds=0)
            dump(self.output/f'{self.calls:03d}-receipt.json',receipt)
