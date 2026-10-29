"""Local Responses transport for a pinned Codex CLI and metered Qwen chat backend.

This is a protocol/backbone adaptation, not a new baseline score. Full history is
client-owned (Codex resume); unsupported semantic input fails closed. No tools
are executed here. Every backend request, including summary turns and failures,
must go through the separately bounded shared chat ledger.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

MODEL = "qwen3-vl-8b-instruct"

class ContractError(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise ContractError(message)

def local_url(url):
    p = urllib.parse.urlparse(url)
    require(p.scheme == "http" and p.hostname in {"127.0.0.1", "::1"}, "upstream must be an explicit loopback HTTP address")
    require(not p.username and not p.password and not p.query and not p.fragment, "credentials/query forbidden in upstream URL")
    return url.rstrip("/")

def content(parts):
    if isinstance(parts, str):
        return parts
    require(isinstance(parts, list), "content must be text or parts")
    out = []
    for part in parts:
        t = part.get("type")
        if t in {"input_text", "output_text", "text"}:
            require(isinstance(part.get("text"), str), "missing text")
            require("image content omitted because it could not be processed" not in part["text"], "CLI failed to decode an attached image")
            out.append({"type": "text", "text": part["text"]})
        elif t == "input_image":
            url = part.get("image_url", "")
            require(isinstance(url, str) and url.startswith("data:image/") and ";base64," in url, "images must contain local embedded bytes")
            out.append({"type": "image_url", "image_url": {"url": url, "detail": part.get("detail", "auto")}})
        else:
            raise ContractError(f"unsupported content type: {t}")
    return out

def translate_request(body, max_output=1024):
    require(body.get("model") == MODEL, "model identity mismatch")
    require(not body.get("previous_response_id"), "client must send complete history; previous_response_id is unsupported")
    require(not body.get("conversation"), "server-side conversation objects are unsupported")
    require(not body.get("background"), "background execution unsupported")
    require(body.get("truncation", "disabled") == "disabled", "silent context truncation forbidden")
    require(body.get("tool_choice", "auto") in {"auto", "none"}, "only explicit auto/none tool choice supported")
    cap = body.get("max_output_tokens", max_output)
    require(type(cap) is int and 0 < cap <= max_output <= 1024, "output cap exceeds fixed contract")
    tools = []
    custom_names = set()
    namespaces = {}
    flattened = []
    for tool in body.get("tools", []):
        if tool.get("type") == "namespace":
            for nested in tool.get("tools", []):
                require(nested.get("type") in {"function", "custom"}, "nested namespace/tool type unsupported")
                name = tool["name"] + "__" + nested["name"]
                require(name not in namespaces, "duplicate flattened namespace tool")
                namespaces[name] = {"namespace": tool["name"], "name": nested["name"]}
                flattened.append({**nested, "name": name, "description": tool.get("description", "") + "\n" + nested.get("description", "")})
        else:
            flattened.append(tool)
    require(len({t["name"] for t in flattened}) == len(flattened), "flattened tool name collision")
    for tool in flattened:
        t = tool.get("type")
        if t == "function":
            tools.append({"type": "function", "function": {k: v for k, v in tool.items() if k in {"name", "description", "parameters", "strict"}}})
        elif t == "custom":
            custom_names.add(tool["name"])
            # Reversible representation: free-form tool input is the single
            # string argument. The tool grammar stays in the model's description.
            desc = tool.get("description", "")
            if tool.get("format"):
                desc += "\nRequired raw input format: " + json.dumps(tool["format"], ensure_ascii=False)
            tools.append({"type": "function", "function": {"name": tool["name"], "description": desc, "parameters": {"type": "object", "properties": {"input": {"type": "string"}}, "required": ["input"], "additionalProperties": False}}})
        else:
            raise ContractError(f"unsupported tool type: {t}")
    messages = []
    instructions = body.get("instructions")
    if instructions:
        require(isinstance(instructions, str), "instructions must be text")
        messages.append({"role": "system", "content": instructions})
    items = body.get("input", [])
    if isinstance(items, str):
        items = [{"role": "user", "content": items}]
    require(isinstance(items, list), "input must be a list or text")
    pending = {}
    for item in items:
        t = item.get("type", "message")
        if t == "message":
            role = item.get("role")
            require(role in {"user", "assistant", "system", "developer"}, "unsupported role")
            messages.append({"role": "system" if role == "developer" else role, "content": content(item.get("content", ""))})
        elif t in {"function_call", "custom_tool_call"}:
            cid = item["call_id"]
            require(cid not in pending, "duplicate call ID")
            pending[cid] = t
            args = item.get("arguments", "") if t == "function_call" else json.dumps({"input": item["input"]})
            require(isinstance(args, str), "function arguments must retain their serialized string")
            messages.append({"role": "assistant", "content": None, "tool_calls": [{"id": cid, "type": "function", "function": {"name": (item["namespace"] + "__" if item.get("namespace") else "") + item["name"], "arguments": args}}]})
        elif t in {"function_call_output", "custom_tool_call_output"}:
            cid = item["call_id"]
            require(cid in pending, "orphan tool output; complete call history required")
            expected = "function_call" if t == "function_call_output" else "custom_tool_call"
            require(pending.pop(cid) == expected, "tool output type does not match call")
            messages.append({"role": "tool", "tool_call_id": cid, "content": content(item.get("output", ""))})
        elif t == "reasoning":
            require(not item.get("encrypted_content"), "encrypted reasoning cannot be silently discarded")
            summaries = item.get("summary", [])
            if summaries:
                require(all(x.get("type") == "summary_text" for x in summaries), "unsupported reasoning summary")
                messages.append({"role": "assistant", "content": "\n".join(x["text"] for x in summaries)})
        else:
            raise ContractError(f"unsupported input item: {t}")
    require(not pending, "unresolved tool call in input")
    schema = body.get("text", {}).get("format", {})
    if schema and schema.get("type") not in {"text", "json_schema"}:
        raise ContractError("unsupported output format")
    if schema.get("type") == "json_schema":
        messages.append({"role": "system", "content": "Your final answer must be JSON satisfying this exact schema. Tool calls may precede the final answer.\n" + json.dumps(schema["schema"], ensure_ascii=False)})
    out = {"model": MODEL, "messages": messages, "tools": tools, "stream": False, "max_tokens": cap, "seed": 42}
    if body.get("tool_choice") == "none":
        out["tools"] = []
    return out, {"custom_names": sorted(custom_names), "namespace_map": namespaces, "schema": schema, "requested_cap": cap, "model": MODEL, "history_items": len(items), "allow_parallel": body.get("parallel_tool_calls", True), "tool_choice": body.get("tool_choice", "auto"), "tool_names": [t["function"]["name"] for t in tools], "images": sum(p.get("type") == "image_url" for m in messages if isinstance(m.get("content"), list) for p in m["content"])}

def translate_response(chat, audit):
    require(chat.get("model") == MODEL, "backend model mismatch")
    require(len(chat.get("choices", [])) == 1, "exactly one choice required")
    choice = chat["choices"][0]
    msg = choice["message"]
    require(choice.get("finish_reason") in {"stop", "tool_calls", "length"}, "unsupported finish reason")
    require(audit["tool_choice"] != "none" or not msg.get("tool_calls"), "backend violated no-tools request")
    require(audit["allow_parallel"] or len(msg.get("tool_calls", [])) <= 1, "backend violated sequential tool contract")
    output = []
    if msg.get("content"):
        require(isinstance(msg["content"], str), "backend assistant content must be text")
        if audit["schema"].get("type") == "json_schema" and not msg.get("tool_calls") and choice["finish_reason"] != "length":
            import jsonschema
            jsonschema.validate(json.loads(msg["content"]), audit["schema"]["schema"])
        output.append({"type": "message", "id": "msg_" + uuid.uuid4().hex, "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": msg["content"], "annotations": []}], "phase": "final_answer" if not msg.get("tool_calls") else "commentary"})
    for call in msg.get("tool_calls", []):
        f = call["function"]
        require(f["name"] in audit["tool_names"], "backend called an undeclared tool")
        item = {"id": "fc_" + uuid.uuid4().hex, "call_id": call["id"], "name": f["name"], "status": "completed"}
        if f["name"] in audit["custom_names"]:
            args = json.loads(f["arguments"])
            require(set(args) == {"input"} and isinstance(args["input"], str), "custom tool must contain only raw input string")
            item.update(type="custom_tool_call", input=args["input"])
        else:
            item.update(type="function_call", arguments=f["arguments"])
        if f["name"] in audit["namespace_map"]:
            item.update(audit["namespace_map"][f["name"]])
        output.append(item)
    u = chat.get("usage")
    require(isinstance(u, dict) and all(type(u.get(k)) is int for k in ("prompt_tokens", "completion_tokens", "total_tokens")), "backend usage missing; do not invent token counts")
    status = "incomplete" if choice["finish_reason"] == "length" else "completed"
    return {"id": "resp_" + uuid.uuid4().hex, "object": "response", "created_at": int(time.time()), "model": MODEL, "status": status, "output": output, "error": None, "incomplete_details": {"reason": "max_output_tokens"} if status == "incomplete" else None, "usage": {"input_tokens": u["prompt_tokens"], "output_tokens": u["completion_tokens"], "total_tokens": u["total_tokens"], "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 0}}}

def events(response):
    seq = 0
    def event(kind, **extra):
        nonlocal seq
        e = {"type": kind, "sequence_number": seq, **extra}
        seq += 1
        return e
    start = {**response, "status": "in_progress", "output": [], "usage": None}
    yield event("response.created", response=start)
    yield event("response.in_progress", response=start)
    for i, item in enumerate(response["output"]):
        empty = copy.deepcopy(item)
        if item["type"] == "message":
            empty["content"] = []
        elif item["type"] == "function_call":
            empty["arguments"] = ""
        else:
            empty["input"] = ""
        empty["status"] = "in_progress"
        yield event("response.output_item.added", output_index=i, item=empty)
        if item["type"] == "message":
            for j, part in enumerate(item["content"]):
                yield event("response.content_part.added", output_index=i, item_id=item["id"], content_index=j, part={**part, "text": ""})
                yield event("response.output_text.delta", output_index=i, item_id=item["id"], content_index=j, delta=part["text"])
                yield event("response.output_text.done", output_index=i, item_id=item["id"], content_index=j, text=part["text"])
                yield event("response.content_part.done", output_index=i, item_id=item["id"], content_index=j, part=part)
        else:
            field = "arguments" if item["type"] == "function_call" else "input"
            kind = "response.function_call_arguments" if field == "arguments" else "response.custom_tool_call_input"
            yield event(kind + ".delta", output_index=i, item_id=item["id"], delta=item[field])
            yield event(kind + ".done", output_index=i, item_id=item["id"], **{field: item[field]})
        yield event("response.output_item.done", output_index=i, item=item)
    yield event("response." + response["status"], response=response)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream", required=True, help="shared metered localhost chat endpoint root, never raw unmetered model")
    ap.add_argument("--port", type=int, default=18020)
    ap.add_argument("--output", required=True)
    ap.add_argument("--max-output", type=int, default=1024)
    a = ap.parse_args()
    upstream = local_url(a.upstream)
    require(0 < a.max_output <= 1024, "fixed output budget")
    health_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with health_opener.open(upstream + "/health", timeout=5) as f:
        health = json.load(f)
    ledger = health.get("ledger", {})
    require(type(ledger.get("max_backend_calls")) is int and ledger["max_backend_calls"] > 0 and type(ledger.get("backend_attempts")) is int, "upstream must expose a bounded shared ledger; raw model server is forbidden")
    root = Path(a.output)
    root.mkdir(parents=True, exist_ok=False)
    identity = {"adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "model": MODEL, "upstream": upstream, "max_output": a.max_output, "history": "client supplied; no truncation", "started_unix": time.time(), "initial_ledger": ledger}
    (root / "identity.json").write_text(json.dumps(identity, indent=2))
    class Handler(BaseHTTPRequestHandler):
        def send_json(self, code, obj):
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        def do_GET(self):
            if self.path in {"/health", "/v1/models"}:
                return self.send_json(200, {"object": "list", "data": [{"id": MODEL, "object": "model", "owned_by": "local"}], "identity": identity})
            self.send_json(404, {"error": "unsupported route"})
        def do_POST(self):
            idx = f"{time.time_ns()}-{uuid.uuid4().hex[:8]}"
            audit = {"request_id": idx, "path": self.path, "started_unix": time.time(), "backend_attempted": False}
            try:
                require(self.path == "/v1/responses", "only /v1/responses is supported; remote encrypted compaction is not implemented")
                n = int(self.headers.get("Content-Length", 0))
                require(0 < n < 12 * 1024 * 1024, "request size outside contract")
                body = json.loads(self.rfile.read(n))
                (root / (idx + "-incoming.json")).write_text(json.dumps(body))
                converted, contract = translate_request(body, a.max_output)
                audit["contract"] = contract
                (root / (idx + "-forwarded.json")).write_text(json.dumps(converted))
                req = urllib.request.Request(upstream + "/v1/chat/completions", data=json.dumps(converted).encode(), headers={"Content-Type": "application/json"})
                audit["backend_attempted"] = True
                # Disable proxy environment and redirects: localhost only.
                class NoRedirect(urllib.request.HTTPRedirectHandler):
                    def redirect_request(self, *args, **kwargs):
                        raise ContractError("upstream redirect forbidden")
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
                with opener.open(req, timeout=240) as f:
                    chat = json.load(f)
                (root / (idx + "-backend.json")).write_text(json.dumps(chat))
                response = translate_response(chat, contract)
                (root / (idx + "-response.json")).write_text(json.dumps(response))
                audit.update(status=response["status"], usage=response["usage"])
                if body.get("stream"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    for e in events(response):
                        self.wfile.write(("event: " + e["type"] + "\ndata: " + json.dumps(e) + "\n\n").encode())
                    self.wfile.flush()
                else:
                    self.send_json(200, response)
            except Exception as e:
                audit.update(status="failed", error=repr(e))
                if isinstance(e, urllib.error.HTTPError):
                    audit["upstream_body"] = e.read().decode(errors="replace")
                self.send_json(400, {"error": {"type": "local_transport_contract", "message": str(e)}})
            finally:
                audit["elapsed_seconds"] = time.time() - audit["started_unix"]
                (root / (idx + "-audit.json")).write_text(json.dumps(audit, indent=2))
    HTTPServer(("127.0.0.1", a.port), Handler).serve_forever()

if __name__ == "__main__":
    main()
