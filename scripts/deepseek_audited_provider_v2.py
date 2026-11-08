"""Official DeepSeek provider with finite shared request/USD reservation.
Audit decoded SSE without presenting stale Content-Encoding to httpx again.
No automatic retries, no tool/prompt/model-profile changes; no credential logs.
"""
import fcntl,hashlib,json,os,time
from pathlib import Path

def decoded_headers(headers):
    return {k:v for k,v in headers.items() if k.lower() not in ('content-encoding','content-length','transfer-encoding')}

def peak_cost(usage):
    if not isinstance(usage,dict):return None
    total=usage.get('prompt_tokens');out=usage.get('completion_tokens')
    hit=usage.get('prompt_cache_hit_tokens',0)
    if any(type(x) is not int or x<0 for x in (total,out,hit)) or hit>total:return None
    return ((total-hit)*.30+hit*.006+out*1.20)/1e6

def budget_state(rows):
    reservations={x['index']:x['reserved_usd'] for x in rows if x['kind']=='reserve'}
    for x in rows:
        if x['kind']=='settle':
            if x['index'] not in reservations:raise ValueError('unreserved settlement')
            reservations[x['index']]=x['peak_usage_usd']
    return len(reservations),sum(reservations.values())

def reserve(ledger,body,max_output,call_cap,usd_cap):
    amount=((len(body)+4096)*.30+max_output*1.20)/1e6
    with Path(ledger).open('a+') as f:
        fcntl.flock(f,fcntl.LOCK_EX);f.seek(0);rows=[json.loads(x) for x in f if x.strip()]
        count,used=budget_state(rows)
        if count>=call_cap or used+amount>usd_cap:raise RuntimeError('frozen API request/USD reservation exhausted')
        row=dict(kind='reserve',index=count+1,reserved_usd=amount,bytes=len(body),time=time.time())
        f.seek(0,2);f.write(json.dumps(row)+'\n');f.flush();os.fsync(f.fileno());return row

def settle(ledger,index,usage):
    cost=peak_cost(usage)
    if cost is None:return # Unknown usage keeps its entire reservation.
    with Path(ledger).open('a+') as f:
        fcntl.flock(f,fcntl.LOCK_EX);f.seek(0);rows=[json.loads(x) for x in f if x.strip()]
        matches=[x for x in rows if x['kind']=='reserve' and x['index']==index]
        if len(matches)!=1 or any(x['kind']=='settle' and x['index']==index for x in rows):raise ValueError('settlement identity')
        if cost>matches[0]['reserved_usd']:raise RuntimeError('actual usage exceeded preflight upper bound')
        f.seek(0,2);f.write(json.dumps(dict(kind='settle',index=index,peak_usage_usd=cost,time=time.time()))+'\n');f.flush();os.fsync(f.fileno())

def build_model(key,output,ledger,call_cap,usd_cap,max_output):
    import httpx
    from openai import AsyncOpenAI
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.deepseek import DeepSeekProvider
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    class Transport(httpx.AsyncBaseTransport):
        def __init__(self):self.inner=httpx.AsyncHTTPTransport(retries=0)
        async def handle_async_request(self,req):
            body=await req.aread();payload=json.loads(body)
            if req.url.host!='api.deepseek.com' or not req.url.path.endswith('/chat/completions'):raise ValueError('official endpoint only')
            if payload.get('model')!='deepseek-flash' or payload.get('max_completion_tokens',payload.get('max_tokens'))!=max_output:raise ValueError('model/output contract')
            if len(body)>8*1024**2:raise ValueError('request size cap')
            row=reserve(ledger,body,max_output,call_cap,usd_cap);prefix=out/f"{row['index']:04d}"
            prefix.with_suffix('.request.json').write_bytes(body);row['request_sha256']=hashlib.sha256(body).hexdigest();start=time.monotonic()
            try:
                response=await self.inner.handle_async_request(req);raw=await response.aread()
                if len(raw)>32*1024**2:raise ValueError('response cap')
                prefix.with_suffix('.response.raw').write_bytes(raw)
                row.update(http_status=response.status_code,response_sha256=hashlib.sha256(raw).hexdigest())
                if 'text/event-stream' in response.headers.get('content-type',''):
                    objs=[json.loads(x[6:]) for x in raw.decode().splitlines() if x.startswith('data: ') and x[6:]!='[DONE]']
                else:objs=[json.loads(raw)]
                usage=[x['usage'] for x in objs if x.get('usage')];row['usage']=usage[-1] if usage else None
                settle(ledger,row['index'],row['usage'])
                row['status']='response'
                return httpx.Response(response.status_code,headers=decoded_headers(response.headers),content=raw,request=req)
            except BaseException as e:row.update(status='error',error_type=type(e).__name__);raise
            finally:
                row['seconds']=time.monotonic()-start;prefix.with_suffix('.receipt.json').write_text(json.dumps(row,indent=2))
        async def aclose(self):await self.inner.aclose()
    client=httpx.AsyncClient(transport=Transport(),timeout=180)
    sdk=AsyncOpenAI(api_key=key,base_url='https://api.deepseek.com/v1',http_client=client,max_retries=0)
    return OpenAIChatModel('deepseek-flash',provider=DeepSeekProvider(openai_client=sdk))
