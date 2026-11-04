# Native Skill-RSI caller and offline author transport — 2026-11-04 evening

No model or simulation was launched this turn. Both lzgpu201 GPUs were occupied by independent training (roughly43.9GiB each,99%utilization). Free RSI locks are not proof that a GPU is available. Those processes were neither modified nor stopped. There are no active RSI jobs.

## Executable delivery

scripts/skill_rsi_caller_bridge.py extracts the exact orchestrated branch from fixed official episode.py (SHA0d77a29d...), preserving its decision parser, execution_log, atomic plan execution, failure-triggered replanning, abort and decisions_max semantics. Only the decision provider is replaced by a loopback Qwen adapter. It uses the published caller prompt and SKILL.md, without skills.py/perception.py source disclosure to the caller. JSON content is not repaired, fenced JSON is not silently unwrapped, and truncated/nontext responses are rejected. Failures consume attempts; request/response/receipt SHA and token usage are retained. HTTP errors propagate as native InfraFailure, not an atom failure. Official validation still controls what executes.

Explicit adaptation: original env.task_spec includes criterion_source. This bridge removes that field from model input and rejects evaluator/layout fields in its remaining context. The physical scorer is unchanged. Future methods share this observation restriction. LocalQwen30BMoE/32K/1024 replaces the paper's caller product; no automatic transport retries, paid fallback, model training or forced robot action. This is not numerical reproduction of the original model.

scripts/run_skill_rsi_caller.py is the actual bounded simulator entrypoint, using the existing single-setup/no-denoiser native worker structure and the original orchestration branch. It records per-case Qwen receipts even on exceptions and uses the existing service owner/shared hard8-call ledger. Native invalid initialization may be censored only with exact UnStableError before any policy/CLIP/Qwen, one setup with unchanged seed, exit0, no rendererror/lingering process. Then it proceeds only to the next already declared case, never replaces/retries. Other infrastructure errors stop the panel. This is an explicitly new census policy, not a rewrite of earlier closed outcomes.

scripts/skill_rsi_author_workspace.py is a capability-only file transport, with pinned owner-provided resource IDs and read limits, writes to four named files only, revision compare-and-swap, byte/operation caps and retained versions/rejections. It refuses arbitrary paths/shell and symlinks; it never executes generated Python. Its CLI accepts capability JSON via stdin. This is not an OS sandbox or a completed autonomous author. Generated skills must pass the original static validator and a separately reviewed execution boundary before any evaluation; future api.task_spec must not expose criterion_source to generated code. No native root useradd/authorhost setup or credentials were used.

37CPU tests passed (24previous+13new). They exercise native failed-step replanning, unknown atom and abort paths, scoring-source redaction, transport failure classification, failed-call budget accounting, exact invalid-scene classification, workspace traversal/symlink/CAS/capability/size/budget/input-hash rejection. Fixtures are not robot performance. Three new modules compile. Initial console-only test output was incomplete; the bounded rerun and final37-test log are preserved, not counted as an additional scientific experiment.

## Frozen independent next task, not launched

configs/skill-rsi-caller-dev2-20261104-2100.json, SHA151db4d79e342f4aede2a5cfe3e713f7e4486d57abc80fc1cb21d8b3b73fa564.
- move_can_pot_d885e5 seed3455213, then stack_bowls_two_79dfa1 seed3446055.
- Deterministic SHA-derived new seeds, pre-outcome public/local record exclusions; no outcome selection or canceled-tail reuse.
-2attempts, at most4caller decisions each/8globalQwen,0VLA. Each1setup,90primitives,90simseconds,240executionwall excluding decision waits,2settle. Each1080processseconds;2220panel seconds after service readiness; service startup<=360seconds separately. All failed requests/auxiliary costs counted. Same frozen published packages/API/CLIP/native scorer/denoiser adaptation.
-928source references verified and --check passed. Old code/assets/protocols remain unchanged.
-Only when BOTH GPUs/locks/ports/storage pass realtime checks, launch once through source scripts/activate.sh skillrsi and python scripts/run_skill_rsi_caller.py --protocol configs/skill-rsi-caller-dev2-20261104-2100.json. Do not run new model qualification or repeat frozen code-only panels. Preserve PID/starttime/protocol SHA. Check report/CLOSE and qwen sibling before any launch.

This two-case pilot evaluates real autonomous skill calls. It is not a matched method ranking: previous fallback successes used other seeds. Frozen published code-only fallback remains the strong reference, and a later comparison must pair it on the same new inputs. A failing local caller cannot be the sole weak baseline used to claim innovation.

## Research progression and limits

If valid autonomous feedback identifies a specific description/argument/composition failure, freeze one bounded author-revision comparison against fixed published package and inheritance-only, with the same library/API/permissions/observations and complete costs. Existing Skill-RSI already studies description repair and inheritance; neither is automatically new. Use observed robot execution to define a falsifiable mechanism before claiming contribution. The two existing successful code-only cases show capability, not a binding defect; do not invent one, use invalid black images or leak sealed validation.

If GPUs stay busy, implement candidate artifact validation and a safe author-to-evaluation handoff on CPU, not another literature/interface audit. If the caller pilot fails structurally, close that configuration and choose a concrete alternative rather than repeat prompts/context/models/seed search. First useful persistentH, later fixed/evolvingU and U-only transfer. AcceptedHupdates0, forgetting-after-update null, strictRSI0. No600episode/allocator comparison.

All historical protocols CLOSED, including both afternoon panels and their six canceled attempts. Sealed two-task100006..100015 excluded from authors/final testing. Only lzgpu201/uv; independentpi0/RL/WAM untouched. Storage reserve max100GiB/20%capacity+projected2GiB; no deletions this turn. Models/assets/raw/candidates/records checkpoints retained.

## Continued CPU handoff work

scripts/skill_rsi_candidate_artifact.py now seals the exact four author artifacts only after version-ledger, byte/hash, path and pinned official static validation. It records rejection or static-valid status, copies byte snapshots, and always sets executed/accepted_update/rollout_authorized false. This does not execute candidates, create an OS sandbox, or authorize a rollout. Five new tests cover published-byte acceptance, malicious-code rejection, version/output tampering, symlink/extra-file rejection, and immutable destinations. Final42CPUtests pass. Initial fixture mistakenly used the package directory as SKILL.md frontmatter name; corrected to the actual published name, with initial failure retained. Frozen caller source/protocol hashes remain unchanged.
