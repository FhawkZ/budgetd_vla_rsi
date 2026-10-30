import json,os,socket,subprocess,sys,tempfile,threading,time,unittest,urllib.request,urllib.error
from pathlib import Path
from http.server import BaseHTTPRequestHandler,HTTPServer
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from budget_proxy import account_usage
class AccountingTests(unittest.TestCase):
 def test_invalid_usage_is_not_zero(self):
  state={'prompt_tokens':0,'completion_tokens':0}
  for value in ({},None,{'prompt_tokens':True,'completion_tokens':0},{'prompt_tokens':1,'completion_tokens':-1}):
   with self.assertRaises(ValueError):account_usage(state,value)
  self.assertEqual(state,{'prompt_tokens':0,'completion_tokens':0})
 def test_failed_request_charged_and_cap_kept(self):
  class Backend(BaseHTTPRequestHandler):
   calls=0
   def do_POST(self):
    Backend.calls+=1;self.rfile.read(int(self.headers['Content-Length']))
    raw=json.dumps({'error':'undeclared_tool_fixture','usage':{'prompt_tokens':24308,'completion_tokens':28,'total_tokens':24336}}).encode()
    self.send_response(400);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
   def log_message(self,*args):pass
  server=HTTPServer(('127.0.0.1',0),Backend);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  probe=socket.socket();probe.bind(('127.0.0.1',0));port=probe.getsockname()[1];probe.close()
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  try:
   with tempfile.TemporaryDirectory() as tmp:
    out=Path(tmp)/'ledger';proc=subprocess.Popen([sys.executable,str(ROOT/'scripts/budget_proxy.py'),'--upstream',f'http://127.0.0.1:{server.server_port}','--port',str(port),'--output',str(out),'--max-calls','1'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
     for _ in range(100):
      try:
       with opener.open(f'http://127.0.0.1:{port}/health',timeout=.2):pass
       break
      except Exception:time.sleep(.05)
     body={'model':'qwen3-vl-8b-instruct','messages':[{'role':'user','content':'CPU fixture'}],'max_tokens':10}
     for _ in range(2):
      req=urllib.request.Request(f'http://127.0.0.1:{port}/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
      with self.assertRaises(urllib.error.HTTPError) as e:opener.open(req,timeout=3)
      e.exception.read()
     with opener.open(f'http://127.0.0.1:{port}/health',timeout=3) as f:ledger=json.load(f)['ledger']
     self.assertEqual((ledger['backend_attempts'],ledger['received_requests'],ledger['prompt_tokens'],ledger['completion_tokens']),(1,2,24308,28));self.assertEqual(Backend.calls,1)
    finally:proc.terminate();proc.wait(timeout=5)
  finally:server.shutdown();server.server_close();thread.join(timeout=2)
if __name__=='__main__':unittest.main()
