# Persistent RoboRSI roles on local Qwen

This implementation keeps the pinned upstream `persistent_agent.run`: task/role session keys, Codex session IDs, resume history, PNG attachment, `_grow` trigger, the manager's `_roll` generation, persisted summary, and successor-session seeding. The Engineer remains the upstream in-process API agent. Replacing the backbone with Qwen and restricting the CLI's permissions/tools are explicit deployment adaptations; they are not the paper's original model results or evidence of RSI improvement.

## Fixed components

- RoboRSI source: `90c8569705bf4004a4f79e34e650c87ab7f075d4`.
- Codex CLI: official npm Linux x64 binary **0.165.0**, downloaded from `https://registry.npmjs.org/@openai/codex/-/codex-0.165.0-linux-x64.tgz`. The original registry SHA512 integrity is checked before extraction; receipt lives in runtime `software/codex-0.165.0/receipt.json`. No Node installation is needed for the native executable.
- Executable: `$RSI_SOFTWARE_ROOT/codex-0.165.0/package/vendor/x86_64-unknown-linux-musl/bin/codex`.
- Local model: `qwen3-vl-8b-instruct`, existing fixed Qwen3-VL-8B-Instruct weights. Input 32768, output at most 1024, deterministic generation with the frozen server.
- Wire path: CLI `/v1/responses` → `scripts/responses_adapter.py` → the shared bounded `/v1/chat/completions` ledger → local Qwen. Engineer, selector and all LLM perception helpers must use that **same** ledger. Original fixed DINO/SAM vision inference has separate compute accounting.
- The pre-existing chat ledger's latest-three-image rule is an explicit shared observation adaptation. The Responses adapter itself preserves all image bytes and history; it does not truncate text, synthesize actions, or silently remove unknown items.

## What was verified offline

`tests/test_responses_adapter.py` has ten zero-generation tests: text/image history, function and custom-tool ID round trips, SSE event order and usage, incomplete output, unknown/opaque/remote image rejection, output cap, missing usage, manager roll prompt, and JSON output schema.

`tests/offline_persistent_cli.py` executes the real pinned CLI and unmodified upstream `persistent_agent` against a deterministic local fixture. Final evidence is runtime `outputs/persistent-transport-offline-20261029-1955/report.json`. All eight synthetic requests passed: fresh image, same-ID resume, summary generation, session clear, successor memory, real `view_image` call/output ID and image serialization, and HTTP failure propagation without retries. It also verified the permission wrapper that removes upstream yolo and enforces read-only/never on both fresh and resumed turns. These eight synthetic requests used **zero neural-model calls and zero GPUs**; synthetic token counts are not experimental costs.

Earlier fixture failures are retained. Default CLI multi-agent namespace tools were rejected as unsupported, then disabled explicitly in the fixed configuration. A corrupt tiny PNG was omitted by CLI; this was diagnosed and replaced by a valid generated fixture. The adapter now fails if the CLI reports an image processing omission. The repaired runs were still offline transport tests, not repeated task attempts.

## Local-only CLI configuration

Use an isolated `CODEX_HOME`, no copied authentication file, and independent `ROBORSI_HOME` and workspace per split/run. The online qualification script creates these. Disable analytics, feedback, all OTEL exporters, remote browser/image generation/apps/plugins, and CLI multi-agent delegation. Requests use only an explicitly configured loopback Responses provider with HTTP and stream retries zero. The provider does not require OpenAI authentication. Automatic history summaries must also use this provider and ledger.

Do not blindly copy the upstream `dangerous_yolo=True` into execution. `scripts/qualify_persistent_qwen.py` places a pinned wrapper ahead of the CLI on PATH; it removes that flag and adds global `sandbox_mode="read-only"` and `approval_policy="never"`. This also works with `codex exec resume`, which does not accept the same sandbox CLI flags as a fresh exec. The canary additionally disables shell and image-reading tools; supplied PNGs use the normal image attachment route. It runs in a synthetic Git workspace without task/final-test data. Later full role trials need their own frozen tool/read scope; this canary is not sufficient evidence of final-test isolation.

## Launch after a new protocol is frozen

The owner starts the GPU service and shared ledger before the adapter. The adapter rejects a raw model upstream lacking a bounded ledger health response.

```bash
source scripts/env.sh
source scripts/activate.sh agent
python scripts/responses_adapter.py \
  --upstream http://127.0.0.1:18019 --port 18020 \
  --output "$RSI_RUNTIME_ROOT/outputs/NEW_RUN/responses"
python scripts/qualify_persistent_qwen.py \
  --budget-url http://127.0.0.1:18019 \
  --adapter-url http://127.0.0.1:18020 \
  --codex "$RSI_SOFTWARE_ROOT/codex-0.165.0/package/vendor/x86_64-unknown-linux-musl/bin/codex" \
  --protocol "$RSI_RUNTIME_ROOT/outputs/NEW_RUN/protocol.json" \
  --output "$RSI_RUNTIME_ROOT/outputs/NEW_RUN/runner"
```

The runner requires a **new 12-call ledger with zero attempts**. Its intended five calls are fresh image turn, resume, a third role turn, upstream manager summary, and successor turn. It stops on the first failure, records exact observed outputs/cost ledger snapshots, and does not spend unused allocation automatically. The owning process closes the run and frees its GPU lock. Do not reuse this allocation for robotics or count it as an autonomous task result.

For actual full three-role execution, set all role/helper models explicitly to local Qwen, including `ROBORSI_PLANNER_MODEL`, `ROBORSI_ENGINEER_MODEL`, `ROBORSI_REVIEWER_MODEL`, `ROBORSI_SKILL_SELECTOR_MODEL`, and perception routing. API-role output caps require `ROBORSI_OPENAI_MAX_OUTPUT_TOKENS=1024`; some helper source paths have separate hardcoded caps and must be audited before they are enabled. No model routing may fall back to a public provider or a copied user credential.

## Supported contract and limitations

The adapter preserves Responses input messages, inline images, function calls/outputs, custom tools represented reversibly by a single raw-string argument, and visible reasoning summaries. It emits SSE item/content/function deltas and a completed or incomplete response with real backend usage. JSON-schema final answers are validated; they are not repaired by the transport. Tool names and IDs must match the declaration and history. The Qwen backend does not implement OpenAI encrypted reasoning or constrained grammar decoding; custom grammar text is preserved in the tool description and raw payload rather than enforced by the model sampler.

Unknown tools/items, opaque encrypted content, remote image URLs, orphan tool outputs, unavailable usage, previous-response server state, oversized outputs and remote `/responses/compact` fail closed. Codex client-owned history and upstream manager summary are the supported compaction mechanisms. The transport does not execute tools or invent a tool call. A successful transport canary says nothing about manipulation success, memory utility, forgetting, or the quality of the learned improvement rule.

## Frozen-mode source correction

The upstream `agents/README.md` frozen-eval paragraph is stale relative to this commit. `runtime_mode.py` explicitly retains persistent Planner/Reviewer in both evolve and frozen modes. `persistent_agent.run_role` only appends an evaluation prompt and does not change `ROBORSI_ROLE_SESSION`. The explicit stateless override is in the candidate gate subprocess `agents/evolution/episode_gate.py:82`. In that branch Planner's fallback ignores its `images` argument; Reviewer instead uses `run_review_agent` and a separate evidence-reading path. A stateless gate adaptation cannot silently be reported as the default persistent three-role system.

## Official protocol references

- [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference): Responses custom provider, retries, analytics/OTEL and permissions.
- [Responses create API](https://developers.openai.com/api/reference/python/resources/responses/methods/create): input/output items and tool IDs.
- [Streaming Responses](https://developers.openai.com/api/docs/guides/streaming-responses): typed SSE lifecycle events.

Fetched 2026-10-29. The implementation was checked against the actual pinned CLI request/response trace, rather than assuming a base URL substitution was sufficient.
## First bounded online qualification

Runtime `outputs/persistent-qwen-qualification-20261029` passed the fresh-image/resume/manager-summary/successor transport canary with 5 real local Qwen calls. Input tokens: 27,559; generated tokens: 377. Server generation records and the shared ledger match exactly. Red-square color and the synthetic marker survived resume and the manager summary. Seven unused calls were canceled via the owner CLOSE marker. This demonstrates transport and persistence only: zero robot episodes and zero strict RSI rounds.

## Native pilot preparation (2026-10-29)

The runnable entrypoint is `scripts/run_roborsi_native_pilot.py`, with `prepare`,
`cap-bridge`, `rpc`, and `run` subcommands. It invokes the official
`run_atomic_attempt(..., mode=RunMode.EVAL, agent_mode="roborsi")`; Planner,
Engineer and Reviewer are retained, including `ROBORSI_ROLE_SESSION=1`.
This is a **native RoboRSI local-model adaptation**, not a VLA result or strict
RSI. The draft protocol is `configs/roborsi-native-pilot-draft.json`; it has no
call allowance until independently frozen. It cannot reuse the closed 12-call
transport protocol.

`prepare` copies the pinned official source/skill tree into a new run, hashes
all source files, and creates separate HOME, CODEX_HOME, ROBORSI_HOME, workspace
and optional initial images. Both client and RPC strip inherited model routes
and provider credentials. Every model and auxiliary selector/perception route
is explicitly `openai/qwen3-vl-8b-instruct`. The native RPC executes Engineer
requests on the server process; changing client environment alone is insufficient.
The RPC qualification endpoint therefore reports the exact state hash, model
routes, cap-bridge URL and ledger identity; `run` refuses mismatches.

The explicit cap bridge records original requested limits (native Chat code uses
2048, and one helper 16384) and forwards `min(requested, 1024)` to the common ledger.
It does not increase output length or allowance. Persistent CLI Responses and
native Chat/auxiliary calls converge on the same ledger. Latest-three-image
transport remains explicit; no textual context truncation is introduced.

Container namespaces reject bwrap, so shell access is disabled; upstream yolo
arguments are stripped and read-only/never remains enforced. Persistent roles
receive `readonly_role_mcp.py` read/list/literal-search/image tools over only the
run's source/workspace/role-home/images. A real fixed CLI fixture exercised its
image tool successfully. Namespace flattening is reversible and preserves call
IDs. The current CLI also exposes its internal resource/query/goal tools; these
are present in the counted 11-tool prompt. No shell, write, network or real-system
computer tools are exposed through this MCP.

The native `exec_python` skill is **not an OS sandbox**: it uses Python exec with
selected builtins and exposes NumPy; a CPU fixture proved a NumPy file read works.
No private files were accessed. Only development qualification files currently
exist; D_final/D_curve have not been created or mounted. This limitation must be
resolved with a process/permission boundary before formal independent testing;
it is not represented as a security guarantee for the development pilot.

### Zero-generation checks

`tests/preflight_native_planner.py` calls the actual official SkillSelector and
Planner, real CLI 0.165.0, cap bridge and Responses adapter against a deterministic
loopback fixture. It attaches the real seed-42 reset head/left/right camera images.
The selector reply is a declared synthetic 8-name shortlist (26 including native
always-retained tools). This tests serialization, not model planning ability.

- `outputs/native-planner-wire-preflight-20261029-v3/report.json`: two wire requests,
  pass, zero model generations and zero new physical episodes.
- Exact fixed Qwen CPU processor count from the same v2 request shape: selector
  11,935 input tokens; Planner 9,240 tokens including three real images and 11
  CLI/MCP tools. Both fit 32K with the 1024 output cap. Dynamic later histories and
  other selected catalogs still require normal per-request accounting.
- `tests/test_persistent_boundaries.py`: namespace call/output round-trip,
  symlink/outside-root/credential path denial, and explicit cap handling pass.
- Initial `agent` uv profile lacks torch and caused native SkillSelector's broad
  exception to silently fall back to all skills. This was detected, not accepted.
  The existing `robotwin` uv profile completed the actual two-call fixture without
  fallback; it is the ready native client/RPC environment. Agent dependency repair
  is separately bounded and recorded.

### Launch contract

After final code fixes and before any generation, prepare a **new** run with the
uv `robotwin` interpreter. Freeze the resulting `state.json` hash, source hashes,
64 calls only if approved by the owning launcher, 32K/1024, one task/seed, and a
wall/physics bound. The owner launcher holds GPU0 for Qwen and owns process cleanup; RPC install_runtime holds GPU1 itself. Do not double-lock GPU1 in the outer launcher.
Start raw Qwen 8018 and a **new** budget ledger 18019; then:

```bash
python scripts/responses_adapter.py --upstream http://127.0.0.1:18019 --port 18020 --output "$RUN/adapter"
python scripts/run_roborsi_native_pilot.py cap-bridge --state "$RUN/state.json" --output "$RUN/cap-bridge"
# RPC uses robotwin profile and explicit GPU1 rendering compatibility hook.
CUDA_VISIBLE_DEVICES=1 python scripts/run_roborsi_native_pilot.py rpc --state "$RUN/state.json" --protocol "$RUN/protocol.json"
# Client needs no GPU; hard preflight checks server/ledger/model identities.
CUDA_VISIBLE_DEVICES= python scripts/run_roborsi_native_pilot.py run --state "$RUN/state.json" --protocol "$RUN/protocol.json"
```

A complete bounded native attempt is also the online qualification of the newer
namespace/MCP model transport. A route/schema/model failure is classified as such;
it is not a paper success rate. Unused calls are canceled and no failed protocol
is silently reopened.

## Saved development checkpoint; not yet qualified for full tasks

The current namespace/MCP adapter and full native runner are preserved for migration. The 13 CPU tests pass; the earlier five-call online qualification used a prior adapter snapshot, preserved in runtime evidence. Full autonomous execution of this draft has not been qualified. Before launch, set ROBORSI_GROUNDING_DINO_MODEL and ROBORSI_POINT_SAM_MODEL to the verified local directories in the new state; check the fixed vision manifests and receipts, qualify perception, review code/state hashes, and freeze a new bounded protocol. The draft has a null call cap and state hash and must remain non-executable until completed. No closed qualification allocation may be reused.
