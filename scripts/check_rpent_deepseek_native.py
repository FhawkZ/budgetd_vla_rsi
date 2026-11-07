"""One frozen two-request official ApiAgentLoop integration; no robot or VLA.

Uses installed DeepSeekProvider, original RPent tool scheduling/history/image
conversion. The fixture is synthetic, explicitly not a policy evaluation.
Credential arrives through stdin, never a CLI argument or output file.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import time
from types import SimpleNamespace
import zlib


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,v):Path(p).write_text(json.dumps(v,indent=2,ensure_ascii=False,default=str))


def png_blue():
    def chunk(t,b):return struct.pack('>I',len(b))+t+b+struct.pack('>I',zlib.crc32(t+b)&0xffffffff)
    raw=b''.join(b'\x00'+b'\x00\x00\xff'*8 for _ in range(8))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',8,8,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--protocol',type=Path,required=True);ap.add_argument('--sha256',required=True)
    ap.add_argument('--check',action='store_true');a=ap.parse_args()
    assert sha(a.protocol)==a.sha256
    cfg=json.loads(a.protocol.read_text())
    assert cfg['status']=='FROZEN_NATIVE_API2' and cfg['max_requests']==2 and cfg['usd_reservation_cap']==.25
    for p,h in cfg['source_files'].items():assert sha(p)==h,p
    if a.check:print('native RPent API2 frozen source contract verified, no model calls');return
    out=Path(cfg['output']);out.mkdir(exist_ok=False)
    dump(out/'protocol.json',cfg)
    os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['PYDANTIC_AI_NO_BANNER']='1'
    sys.path.insert(0,cfg['source_root'])
    from rpent.planner.api_loop import ApiAgentLoop
    from rpent.tools import Toolkit,ToolResult,common
    from rpent.tools import tool
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.deepseek import DeepSeekProvider
    from openai import AsyncOpenAI
    import httpx

    class Events:
        enabled=True
        def __init__(self):self.rows=[]
        def emit(self,e):self.rows.append(str(e))

    class Fixture(Toolkit):
        def __init__(self,events):
            self.seen=False;self.calls=[]
            super().__init__(dashboard_events=events,memory=SimpleNamespace())
        def _register_common_tools(self):
            self.add_tool(common.CommonTools.finish.with_handler(self.finish))
            self.add_tool(tool(name='observe',readonly=True)(self.observe))
        def observe(self)->ToolResult:
            """Read the synthetic fixture image and its public nonce."""
            self.seen=True;self.calls.append('observe')
            return ToolResult(data={'nonce':'native-deepseek-fixture-20261108'},images=[png_blue()])
        def finish(self,status,summary):
            self.calls.append('finish')
            if not self.seen:return ToolResult(data={'error':'observe first'})
            return ToolResult(data={'_finish':True,'status':status,'summary':summary})

    class AuditTransport(httpx.AsyncBaseTransport):
        def __init__(self):self.inner=httpx.AsyncHTTPTransport(retries=0);self.rows=[];self.reserved=0
        async def handle_async_request(self,req):
            body=await req.aread()
            assert req.url.host=='api.deepseek.com' and req.url.path.endswith('/chat/completions')
            assert len(body)<=200000
            payload=json.loads(body);assert payload['model']=='deepseek-flash'
            assert payload.get('max_completion_tokens',payload.get('max_tokens'))==32768
            reservation=((len(body)+1024)*.30+32768*1.20)/1e6
            if len(self.rows)>=2 or self.reserved+reservation>.25:raise RuntimeError('frozen request/USD cap')
            i=len(self.rows)+1;self.reserved+=reservation
            row={'index':i,'reserved_usd':reservation,'request_sha256':hashlib.sha256(body).hexdigest(),'status':'pending'}
            self.rows.append(row);(out/f'{i:02d}-request.json').write_bytes(body);dump(out/'calls.json',self.rows)
            t=time.monotonic()
            try:
                response=await self.inner.handle_async_request(req)
                raw=await response.aread();assert len(raw)<16*1024**2
                (out/f'{i:02d}-response.raw').write_bytes(raw)
                row.update(status='http_response',http_status=response.status_code,response_sha256=hashlib.sha256(raw).hexdigest())
                objects=[]
                if 'text/event-stream' in response.headers.get('content-type',''):
                    for line in raw.decode().splitlines():
                        if line.startswith('data: ') and line[6:]!='[DONE]':
                            objects.append(json.loads(line[6:]))
                else:objects=[json.loads(raw)]
                usages=[x['usage'] for x in objects if x.get('usage')]
                row['usage']=usages[-1] if usages else None
                return httpx.Response(response.status_code,headers=response.headers,content=raw,request=req)
            except BaseException as e:
                row.update(status='error',error_type=type(e).__name__);raise
            finally:
                row['seconds']=time.monotonic()-t;dump(out/'calls.json',self.rows)
        async def aclose(self):await self.inner.aclose()

    t=time.monotonic();report={'status':'running','robot_episodes':0,'VLA_calls':0,'accepted_H':0,'strict_RSI':0}
    transport=AuditTransport();events=Events();fixture=Fixture(events)
    try:
        key=sys.stdin.read().strip();assert key.startswith('sk-') and '\n' not in key
        client=httpx.AsyncClient(transport=transport,timeout=httpx.Timeout(180))
        sdk=AsyncOpenAI(api_key=key,base_url='https://api.deepseek.com/v1',http_client=client,max_retries=0)
        model=OpenAIChatModel('deepseek-flash',provider=DeepSeekProvider(openai_client=sdk))
        planner=ApiAgentLoop(model=model,dashboard_events=events,max_tokens=32768,reasoning_effort='high',no_images=False,timeout_s=380)
        result=planner.solve(system_prompt='This is an API integration fixture, not a robot task. Call observe first. Then finish with status success and summarize the observed nonce and image color. No other tools are available.',
                             user_message='Inspect the fixture and finish.',toolkit=fixture,max_turns=2)
        dump(out/'planner-result.json',{'finish_result':result.finish_result,'messages':result.messages,'stats':result.stats,'error':result.error})
        report.update(status='passed' if not result.error and fixture.calls==['observe','finish'] and result.finish_result else 'failed',
                      error=result.error,fixture_tool_calls=fixture.calls,stats=result.stats,finish_result=result.finish_result,
                      interpretation='native agent/provider two-turn tool+image contract only; synthetic, no robot score')
    except BaseException as e:report.update(status='failed',error_type=type(e).__name__,error=str(e)[:500])
    finally:
        report.update(model_requests=len(transport.rows),reserved_usd=transport.reserved,elapsed_seconds=time.monotonic()-t)
        dump(out/'report.json',report);dump(out/'CLOSE.json',{'status':'CLOSED','report_sha256':sha(out/'report.json')})
    print(json.dumps(report,default=str))


if __name__=='__main__':main()
