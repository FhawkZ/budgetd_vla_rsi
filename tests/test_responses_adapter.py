"""Zero-generation protocol fixtures. These are not task/baseline episodes."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location("adapter",Path(__file__).parents[1]/"scripts/responses_adapter.py")
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)

class Contract(unittest.TestCase):
    def body(self):
        return {"model":a.MODEL,"input":[{"role":"user","content":"hello"}],"stream":True}
    def chat(self):
        return {"model":a.MODEL,"choices":[{"message":{"role":"assistant","content":"done"},"finish_reason":"stop"}],"usage":{"prompt_tokens":11,"completion_tokens":2,"total_tokens":13}}
    def test_history_and_image_bytes(self):
        b=self.body();url="data:image/png;base64,aGVsbG8="
        b["input"]=[{"role":"developer","content":"rules"},{"role":"user","content":[{"type":"input_image","image_url":url},{"type":"input_text","text":"frame"}]},{"role":"assistant","content":[{"type":"output_text","text":"seen"}]},{"role":"user","content":"remember"}]
        out,_=a.translate_request(b)
        self.assertEqual(len(out["messages"]),4);self.assertEqual(out["messages"][1]["content"][0]["image_url"]["url"],url)
    def test_function_identity(self):
        b=self.body();b["input"] += [{"type":"function_call","call_id":"call_x","name":"read","arguments":"{\"x\":1}"},{"type":"function_call_output","call_id":"call_x","output":"ok"}]
        out,_=a.translate_request(b);self.assertEqual(out["messages"][-1]["tool_call_id"],"call_x")
        self.assertEqual(out["messages"][-2]["tool_calls"][0]["function"]["arguments"],'{"x":1}')
    def test_custom_roundtrip(self):
        b=self.body();b["tools"]=[{"type":"custom","name":"apply_patch","format":{"type":"grammar","syntax":"lark","definition":"raw"}}]
        _,audit=a.translate_request(b);chat=self.chat();chat["choices"][0].update(finish_reason="tool_calls",message={"content":None,"tool_calls":[{"id":"call_x","function":{"name":"apply_patch","arguments":json.dumps({"input":"*** Begin Patch\n*** End Patch"})}}]})
        r=a.translate_response(chat,audit);self.assertEqual(r["output"][0]["type"],"custom_tool_call");self.assertEqual(r["output"][0]["call_id"],"call_x")
        b["input"] += [r["output"][0],{"type":"custom_tool_call_output","call_id":"call_x","output":"applied"}]
        o,_=a.translate_request(b);self.assertEqual(json.loads(o["messages"][-2]["tool_calls"][0]["function"]["arguments"])["input"],"*** Begin Patch\n*** End Patch")
    def test_sse_usage_complete(self):
        _,audit=a.translate_request(self.body());r=a.translate_response(self.chat(),audit);e=list(a.events(r))
        self.assertEqual(e[-1]["type"],"response.completed");self.assertEqual(e[-1]["response"]["usage"]["total_tokens"],13)
        self.assertEqual([x["sequence_number"] for x in e],list(range(len(e))))
    def test_length_not_completed(self):
        _,audit=a.translate_request(self.body());c=self.chat();c["choices"][0]["finish_reason"]="length"
        self.assertEqual(list(a.events(a.translate_response(c,audit)))[-1]["type"],"response.incomplete")
    def test_unknown_and_opaque_fail(self):
        for item in [{"type":"compaction","encrypted_content":"opaque"},{"type":"reasoning","encrypted_content":"opaque"},{"type":"function_call_output","call_id":"orphan","output":"x"},{"role":"user","content":[{"type":"input_image","image_url":"https://example.com/x"}]}]:
            b=self.body();b["input"].append(item)
            with self.assertRaises(a.ContractError):a.translate_request(b)
    def test_call_cap_and_local_endpoint(self):
        b=self.body();b["max_output_tokens"]=1025
        with self.assertRaises(a.ContractError):a.translate_request(b)
        for url in ["https://api.openai.com/v1","http://localhost:1","http://127.0.0.1:3/?x=1"]:
            with self.assertRaises(a.ContractError):a.local_url(url)
    def test_missing_usage_fails(self):
        _,audit=a.translate_request(self.body());c=self.chat();del c["usage"]
        with self.assertRaises(a.ContractError):a.translate_response(c,audit)
    def test_roll_prompt_not_intercepted(self):
        b=self.body();b["input"][0]["content"]="Compact your own memory. Keep durable lessons."
        out,_=a.translate_request(b);self.assertEqual(out["messages"][0]["content"],b["input"][0]["content"])
    def test_json_contract(self):
        b=self.body();b["text"]={"format":{"type":"json_schema","schema":{"type":"object","required":["ok"],"properties":{"ok":{"type":"boolean"}},"additionalProperties":False}}}
        _,audit=a.translate_request(b);c=self.chat();c["choices"][0]["message"]["content"]='{"ok":true}'
        a.translate_response(c,audit)
        c["choices"][0]["message"]["content"]='{"wrong":true}'
        with self.assertRaises(Exception):a.translate_response(c,audit)

if __name__=="__main__":unittest.main()
