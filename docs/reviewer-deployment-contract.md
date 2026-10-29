# Reviewer deployment contract and stopping rule

2026-10-30. These are deployment adaptations to fixed RoboRSI source with local Qwen, not learned harness updates or the paper's method contribution. Historical closed runs remain immutable.

The first full stack development attempt failed: 64 generations, native grasp followed by repeated rejected moves, and no Reviewer verdict. The files were present. Actual tick images are nested in `round_01/<task>-<seed>/` with five-digit physics ticks. The Reviewer guessed different paths and called text readers on images.

Two separately bounded CPU/GPU diagnostics used a copy of that closed development episode. Only public plan, summary, trace and images were exposed; episode_result, previous review and ground-truth score were excluded. No physics ran and no learning was enabled.

| Diagnostic | Model generations | Input/output tokens | Result |
|---|---:|---:|---|
| Explicit actual path inventory; original CLI tool surface | 4/4 | 59,378 / 324 | Correct image path, but repeated `read_mcp_resource(server=workspace)` for an unavailable server. Failed; closed. |
| Explicit inventory and four registered evidence tools only | 2/4 | 27,042 / 365 | Three image reads and parseable non-completion diagnosis. Unused two calls canceled. |

The second qualification establishes image-tool transport and JSON output, not robust judgement. It returned `continue` despite zero remaining action/round budget and omitted scene_check. Its IK/collision diagnosis is a model hypothesis, not verified cause. Path guidance and tool filtering changed together, so this is not a single-factor causal comparison. Hard resource limits remain outside the model and cannot be edited by it.

`responses_adapter.py --tool-profile role-evidence` exposes exactly the four registered scoped tools. It logs every removed CLI tool and rejects histories that already used excluded tools, requiring a fresh session. Default original profile is unchanged. It never maps a wrong tool call to a guessed tool or invents an image/result. All original and adapted model inputs, outputs and costs remain in the external runtime.

The independent handover development attempt uses the same Qwen weights, 32K input / 1024 output, 64 total generations including helpers and failures, 40 native tool budget, 20,000 physics-step ceiling including resets and 1,800-second wall limit. Both persistent roles use the restricted evidence interface; Reviewer receives actual current-run paths and a request for at most three evidence reads. This adaptation is disclosed. It does not reopen the old stack or VLA-only budgets. It cannot produce a success-rate or forgetting claim from one scene.

## Research progression

1. Close handover and reconcile every backend generation, native result, tool execution and resource cost. An unavailable Reviewer is a failure, not an implicit pass.
2. With working execution and evidence transport, freeze a small **paired** common-backend development comparison. Use the same fixed LingBot checkpoint, RoboTwin initial states, observations and action horizon for VLA-only, fixed harness and a reproduction-adapted harness. Native code/skill RoboRSI stays in a separate table. Existing mismatched-seed pilot scores cannot be mixed into that comparison.
3. Before allocating the larger continual-learning draft, establish nonzero old capability and genuine shared harness changes. Compare fixed uniform, strong fixed VOI+risk and evolved budget allocation under equal total cost. The fixed selector must see the same evidence/features. No final-test result goes to the Agent.
4. Count self-modification, rejected candidates, failed calls, qualification, screening and revalidation. Deployment costs are reported separately from learning curves but never hidden in total project costs.
5. If the fixed local model cannot use the permitted tools, stop that deployment configuration. If low-level control dominates failures, diagnose control before claiming allocation benefits. If evolved allocation does not beat strong fixed rules or does not transfer to a reset executor/experience sequence, report the negative result and reduce the RSI claim; do not add unlimited prompt trials or increase closed budgets.

## Handover closure and next gate

`roborsi-handover-dev64-20261030-0520` closed after two rounds: 64 generations / 1,390,925 input / 6,117 output tokens, 233.131 generation seconds, 330.440 GPU0 allocation seconds. The first Reviewer produced an actual review; the final Reviewer was unavailable after the shared budget exhausted. Native success=false, task_instruction empty. The plan incorrectly interpreted handover as stacking on a blue block. There were 42 trace entries, including ten no-tool entries; 32 named-tool records are not equivalent to 32 physical actions. One grasp_obb returned held; seven move_to_pose calls were rejected. Four grasp_object calls depended on the explicitly disabled GraspGen. No model or harness update occurred.

The frozen native source prioritizes `active_env.instruction` then reset observation extras, but the HTTP task path did not supply an instruction. The VLA-only pilot did have task language, so its results cannot be fairly compared to this native run. `configs/public-task-language-v1.json` pins the official public full_description for both tasks. `task_language_contract.py` verifies source hashes and binds that exact text to the client environment before the core plans; it preserves reset observations and does not read geometry or scores. CPU checks passed; online language propagation remains pending. New native launches now require an explicit manifest, preventing accidental reuse of the empty-language configuration. No more calls were made after this gate was added.

Next: independently qualify instruction propagation with a small predeclared budget, inspect disabled-tool exposure, then freeze matched common-backend runs. Do not silently install GraspGen or manually rescue movements. Native-control failure and missing language must be separated from any claim about RSI effectiveness.
