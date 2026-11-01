# Finite shared-patch pilot closed without promotion

The frozen validation `single-seed-paired-val20-20261101-2300` attempted all 20 scheduled cases. Eighteen policy episodes completed; both roles for handover seed 100012 were invalid before any policy action. The native receipts report `UnStableError` for `101_milk-tea`, with the requested seed unchanged. No replacement was attempted. This is `completed_with_censored`, not a complete efficacy evaluation.

| Task | Complete pairs / planned | Fixed50 successes | Frozen candidate successes | VLA calls: baseline / candidate |
|---|---:|---:|---:|---:|
| Stack | 5 / 5 | 2 / 5 | 2 / 5 | 85 / 85 |
| Handover | 4 / 5 | 1 / 4 | 1 / 4 | 78 / 80 |

There were no outcome gains or losses in the nine complete pairs. The all-20-policy-complete requirement failed, and the observed handover results did not show the required strict gain. The HCL receipt adapter correctly rejected censored outcomes. **Do not promote; stop this finite candidate pilot and the current close-on-command patch route.** Do not add seeds, calls, prompts, prefixes or rounds to rescue it. This is a stopping decision under a finite protocol, not a statistical proof of equivalence or universal inefficacy.

The audit verified nine paired initial states, three-camera hashes, native languages and first predictions; 328 submitted VLA prefixes; 984 inference images; 2,283 raw files; 38 exact-seed setup entries and 18 public resets. All 40 daemons exited: 38 exit 0, two native invalid-scene servers exit 1. No infrastructure timeout was observed in this panel; this does not prove the old RPC timeout's root cause was fixed. The 152 unused VLA calls are canceled.

Cost: 328 VLA calls, 0 Qwen, 16,285 native action counts (170 typed-skill counts included), 4,898.375836 GPU1 allocation seconds, 157.013896 VLA RPC seconds. Baseline/candidate totals are 163/165 VLA and 8,071/8,214 native counts. Worker intervals include initialization and invalid attempts, and are not kernel times. Native counts are not physics ticks. Proposal failures, fixture qualifications, development selection and the previous censored validation retain their separate receipts; the above is this protocol's cost, not the full research campaign. Neither old development gains nor these validation results constitute a deployed update or forgetting measurement.

## What the source audit changed

Pinned RPent `rlinf_env.py:_robot_state` reads native `get_left/right_gripper_val`. In the installed RoboTwin implementation those getters return cached requested command values. `set_gripper` assigns them before drive-target interpolation. Even `get_normal_real_gripper_val` reads drive targets, not physical finger positions. The RPent `arm_qpos_real12` field excludes gripper joints. The `set_gripper` primitive's `success=True` reports execution of commands; it does not verify grasp/contact.

Eight exact-getter AST probes with fake objects confirmed that varying a synthetic physical aperture does not change the cached-command return. These are CPU contract probes, not physics tests. Of 17 actual candidate triggers, eight already had cached command zero. Arm targets were unchanged; measured EEF translations during the extra commands ranged 0.355–2.316 mm. This does not establish a causal settling effect. Earlier references to “closed gripper” must be interpreted as “reported command zero,” not observed contact or object possession. No upstream source, observation, scorer, weights or frozen candidate was changed.

## Next work and limits

1. Keep fixed50 as incumbent. Close the current candidate; accepted common updates remain 0, forgetting after update is null, strict RSI rounds 0. Freeze the candidate and rejection evidence; validation observations must not be sent to Qwen.
2. Perform one finite CPU source/metadata audit of the frozen LingBot checkpoint's stated task/training coverage and the complete feedback path. Produce a table separating commanded values, measured robot state, RGB evidence and privileged simulator state. Use existing development data only for any failure taxonomy; these validation scenes are not candidate-generation feedback. Do not infer actual grasp from command success.
3. Before another online pilot, identify one concrete, generalizable intervention and the observation needed to trigger it, with matched permissions and a meaningful strong baseline. State what would falsify it. If coverage/feedback evidence does not support an actionable hypothesis, record that no new experiment is justified instead of inventing a successor patch or using idle GPUs to sweep parameters.
4. Continue baseline source-equivalence planning: HCL's official gate/screening adapter is not full HCL; RPent/RoboRSI local-Qwen failures remain separate native-reproduction attempts. Any common feedback or skill-interface change must be explicitly versioned and shared by all compared methods. No paper numerical result has been reproduced by these trials. No new HCL/RSI or 600-episode budget is authorized by this closure.
5. The RA-L core remains unestablished. Reliable execution feedback may motivate a future robot-specific hypothesis, but standard sensing/verification, engineering fixes or a budget allocator alone are not claimed as novelty. Check primary prior work before proposing a new contribution. Do not merge into the independent pi0/RL/WAM project.

Full evidence remains outside Git at runtime `outputs/single-seed-closure-audit-20261102-0310` and `outputs/gripper-observation-audit-20261102-0330`. The closed run/protocol and all raw data remain unchanged. This closure adds read-only auditors and four gate tests; 65 CPU tests and six subtests passed, plus eight source probes. The first postprocessing attempt incorrectly assumed submitted prefixes always contain 50 rows; corrected to the frozen executor's `min(50, remaining native budget)` rule. This caused no robot/model execution and changed no experiment results.

## Analysis workflow attribution

The scientific-critical-thinking skill supported the distinction between descriptive paired outcomes, censored coverage and causal claims. Workflow reference (not a robot baseline): Kassis, T., Agarwal, V., He, Y., Patel, D., and Brueckner, A. M. (2026). *Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents*. [arXiv:2609.00065](https://arxiv.org/abs/2609.00065), metadata checked 2026-11-02; current revision v2, no journal reference listed.
