# Common bounded VLA execution contract v1

This is an explicit common-backend adaptation, not a reproduction of the original arbitrary-tool RPent planner and not an RSI contribution. The failed8B/30B reproduction attempts remain closed and separately reported. All eventual comparison arms must share the same qualified execution surface and cost accounting.

## What is implemented

`scripts/bounded_vla.py` accepts only `execute_vla_chunk(use_length=25|50)`, `observe`, and `stop`. It uses the pinned native RGB/state/task-language builder, the frozen LingBot model and native `chunk_step(action_type="ee",return_all_frames=False)`. It never edits generated poses, replays demonstrations, changes the scorer or browses files. The selected actions are an exact prefix of a real inference output. The25prefix changes the observation/replanning schedule; it is deliberately outside the upstream tool's fixed50 contract. The upstream source/schema is untouched.

Requests, explicit observations and inference attempts have hard caps. Failed inference attempts count; the wrapper does not retry. Termination/horizon stops before another inference; invalid arguments cannot expand privileges. The current fixed-harness pilot calls this interface deterministically. It has no high-level LLM planner, learned allocator or persistent update. The interface has not yet been integrated or qualified as a model-controlled tool loop.

Six CPU tests cover prefix binding, next-observation changes,50behavior, stop/observe with no actions, failed/invalid call accounting, horizon truncation and language immutability. A separate comparison executes the actual pinned original primitive with fake env/model: two50chunks exactly match the adapter's inference inputs and executed arrays. The original primitive rejects25before inference. These are implementation checks, not robot-task scores.

## Frozen physical diagnostic

`bounded-vla-pair4-20261031-1130` contains exactly four development episodes: stack50, stack25, handover50, handover25 on the existing paired seeds2026103011/2026103012. Initial robot state and three RGB hashes must match the frozen native-language reference before the first inference. Model/observation/source hashes are checked; weights, native language, scorer, render configuration and1200-action horizon are unchanged.

Each case has a48inference cap and1200seconds; the total cap is192inferences/4800seconds. Prefix50 ordinarily reaches the horizon within24calls, while prefix25may need48. Equal caps/horizons do not imply equal consumed compute. This is an execution-binding and scheduling diagnosis, not an equal-cost method ranking. Report both outcome and actual cost. All unused allowance is canceled; infrastructure/initial-state failure stops the remaining cases without retries or replacement seeds.

The owner uses only an idle GPU1 after a live occupancy/lock check. Qwen is not loaded. Every inference records language, images, state, output array and latency; each executed prefix is separately saved/hashed. Initial actions, first predicted arrays and next-inference states are compared offline. Model/physics nondeterminism must be reported if matching inputs yield different outputs; don't attribute every trajectory difference to scheduling. Native counts are not exact physics ticks or successful planning counts.

## Interpretation and next gate

- A successful50control establishes functional frozen execution on that development scene, not a learned high-level Agent or a stable rate.
- Differing next observations/actions establish that the scheduling parameter is effective. Success differences on two scenes are hypotheses, not evidence of general superiority.
- If25adds cost without task benefit, keep the negative result; do not start an unbounded schedule search.
- If both modes fail, diagnose the executor or use a predeclared task-panel screen including all failures. Do not screen for successful seeds.
- Before any RSI experiment, implement the same reduced tools for a model-controlled baseline. Its decision budget must count observe/stop/failed calls; no forced execution after indecision, no hand-coded motion, no reusing this pilot's unused allowance.
- Require a real persisted shared-harness update and old-task remeasurement before claiming retention. All allocator arms must share candidate generation, features, gates and executor. Original and evolved improvers then need a reset-executor/experience transfer comparison on new sequences.

The600episode outline stays a draft. Final-test results are not available to evolution. `summary.json` and the checkpoint report record completed results; an existing running status alone is not proof of completion.
