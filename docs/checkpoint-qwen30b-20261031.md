# Candidate backend and context audit — 2026-10-31

The 8B autonomous configuration remains stopped. A bigger model is a deployment candidate, not the proposed RSI method. All eventual comparison arms must share the qualified model, VLA, tools, language and cost accounting.

## Verified assets and bounded qualification

All 24 files of Qwen3-VL-30B-A3B-Instruct were independently rehashed: 62,153,205,636 bytes match the pinned manifest. No downloads were repeated. The original 8B files and all closed protocols remain untouched.

`qwen30b-qual3-20261031-0640` is CLOSED after one generation; two unused calls were canceled. The correct `Qwen3VLMoeForConditionalGeneration` class loaded BF16 weights on GPU0. Loaded allocated memory was 62,141,815,296 bytes. The real request included three images and 19,258 input tokens; it generated 41 tokens in 4.121 seconds. Peak allocated/reserved memory was 68,191,311,872 / 69,851,938,816 bytes. GPU allocation lasted 26.260 seconds. The proxy and raw server usage match. The model returned schema-valid `query_world_map(view=head,bbox=[0,0,240,320])`.

The frozen historical-input test required `sample_world_xyz`, so the qualification stopped at its coverage assertion. This is NOT evidence of malformed output, OOM, or an unusable model. It is also NOT a complete pass. The target nested-array boundary, 31,744-token capacity canary and hard-budget refusal were not reached. No tools, robot actions, episodes or persistent updates occurred. Both GPUs and locks were released.

Three additional CPU tests pass for explicit 30B identity rejection of 8B, output limits, remote-image rejection, latest-three transport, and preservation of input/text; all five existing structured-output tests pass. Original executables are unchanged; 30B entrypoints have explicit names and model identity.

## Context-pressure evidence

The source audit corrects an overly broad prior hypothesis: the trigger normally uses the latest provider usage anchor plus new suffix, rather than recounting every historical image. The suffix cutoff search does use unanchored image estimates. On the saved max-image requests, six-image exact input counts versus latest-three transport differ by only 8 tokens (stack) and 15 (handover). These small differences do not explain the large peaks.

At the first trim, `query_world_map` alone contributes 27,450 tokens on stack and 27,877 on handover. History falls from 45/47 Pydantic messages to 3. The actual post-trim model inputs remain 32,239/32,670 tokens. The following request trims again. These are recorded development observations, not reconstructed pre-trim full histories or proof of a causal task failure. The original native context budget checks input length, not input plus maximum output; this distinction must remain explicit.

Do not introduce a speculative image-accounting patch as the presumed fix. Full native pre-trim message capture and transport-aligned counting should be added to a new adapter version, consistently across methods, before attributing behavioral changes to compaction. A lossy map summary or bounded tool payload would change observations and must be a declared common-backend adaptation, not a silent native reproduction patch or RSI gain.

## Independent contract completion and autonomous result

The separate `qwen30b-contract2-20261031-0700` protocol is CLOSED/PASSED. It did not reuse the canceled quota or replay the historical input. A frozen 31,744-input-token canary returned 3 output tokens; an explicit synthetic serialization request produced the required nested array using the unchanged original tools. The third proxy request was refused before generation. Two generations cost 33,857 input / 44 output tokens, 5.279 generation seconds and 28.905 GPU allocation seconds. Peak allocated memory was 72,079,902,720 bytes. This tests long-input inference under a 1,024 output cap, not an actual 1,024-token continuation or worst-case memory. Combined with the earlier three-image request, this is deployment eligibility, not autonomous perception/task success. The internal fixture discriminator retains `historical_schema_boundary`, but the frozen fixture explicitly says synthetic serialization; it must not be reported as an autonomous historical replay pass.

One separate autonomous protocol, `rpent30b-native-dev64-20261031-0710`, then ran and CLOSED. Each task used 32 generations: one `view_env_state` and 31 `read_text_file` requests. On each task, 29 calls repeated exactly the same MEMORY.md path with no pagination arguments; the other two read the task prior and recipe. Both tasks failed with zero native actions and zero VLA calls. No schema or explicit tool errors occurred, and neither task compacted its context. This is a distinct failure mechanism from the 8B dense-map context episode. Do not attribute this 30B failure to compaction or insufficient schema support.

The autonomous run used 1,117,027 input / 4,364 output tokens, 231.554 generation seconds, 365.374 GPU0 allocation seconds and 344.095 GPU1 task-process interval seconds. All 64 raw/forwarded request SHAs and token totals match; both initial robot states and three RGB views match the frozen VLA-only control. Two development cases cannot establish a stable success rate. Total new work this heartbeat: 67 generations, 1,170,142 input / 4,449 output tokens; no accepted update, retention unmeasured, strict RSI zero. Both GPUs and locks were released.

## Next action after the stop condition

The one-attempt stop condition has been met for both8B and30B arbitrary-tool configurations. Do not add calls, pick seeds, or download a larger model. Read `docs/common-execution-contract-next.md`: define a shared bounded VLA execution interface, establish a functional fixed-harness baseline, verify an editable scheduling parameter changes real execution, then compare uniform, strong fixed VOI/risk and evolved allocation under equal total learning cost. Reduced-interface literature baselines must be explicitly labeled adaptations/reimplementations. Keep the original failed reproduction attempts separately; do not claim an RSI improvement from beating them.

No own-method superiority, retention or strict RSI claim follows from this deployment work. The600episode draft remains closed to execution.
