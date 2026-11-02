# Frozen-checkpoint coverage and feedback audit — 2026-11-02

This completes the single finite CPU audit requested after closing the gripper candidate. No model weights were loaded, no neural inference or simulation episode ran, and no validation trajectory was used for candidate generation. The result does not justify a new online experiment.

## Checkpoint provenance and coverage

Five metadata files match their exact Git blobs in the pinned model manifest, revision `e727b46cd220b66981ea4d2fd9ba84adc189e2cc`. The release is `RLinf/LingBot-VLA-RoboTwin-EEF-ckpt1500`, also identified by the pinned RPent leaderboard as its frozen RoboTwin SFT backend. The current paper describes RoboTwin post-training and the shared frozen baseline, but does not supply a per-task episode/seed manifest in the inspected section. [Harness VLA v5, Appendix D.3](https://arxiv.org/html/2607.08448v5#A4.SS3)

The released CLI YAML has `train_path: null`, `train_size: 10000000`, and `max_steps: 1500`. The latter two are configuration values, not independently verified dataset size or completed training steps. The model card and inspected metadata do not establish exact task membership, scene-seed splits, clean/randomized training mixture or the training-time command-versus-measured-gripper convention. These remain unknown, not evidence that the focal tasks were excluded. [Pinned model release](https://huggingface.co/RLinf/LingBot-VLA-RoboTwin-EEF-ckpt1500/tree/e727b46cd220b66981ea4d2fd9ba84adc189e2cc)

The published C2R evaluation manifest has 50 tasks and 250 episodes and includes both focal tasks. Its successful clean-scene priors and randomized evaluation cases describe the harness evaluation setup; they do not constitute the checkpoint's training manifest. [Pinned RPent instructions](https://github.com/RLinf/RPent/blob/a744bd5f128ebef3cb8c6736cf7cd98adff681f1/docs/source-en/rst_source/simulators/robotwin.rst)

## Actual feedback paths

| Field | Meaning in this installed backend | VLA payload | Reduced controller |
|---|---|---|---|
| Three RGB views | Rendered camera evidence | Yes | Initial view or explicit `observe` |
| EEF pose | Simulator robot-link pose, transformed to EEF coordinates | Yes | When observed |
| TCP pose | Same physical link, different coordinate offset | No | When observed |
| Gripper value | Cached requested command | Yes | When observed |
| `qpos_target14` | Arm drive targets plus cached gripper commands | No | When observed |
| `arm_qpos_real12` | Actual simulator arm joint positions, excluding grippers | No | When observed |
| Depth | Available in a native helper, excluded by RGB-only builder | No | No |
| Actual finger aperture/contact/object pose | Not present in the bounded observation | No | No |
| Native task success | Privileged scorer value | No | External termination in reduced runner |
| Submitted waypoints/native count delta | Execution receipts, not evidence of physical task progress | No | Automatic tool feedback |

Seven exact-upstream-method probes with an inert transport passed. EEF, cached-gripper, RGB and native-language changes altered the outgoing payload. Changing actual arm/target fields, adding a synthetic finger measurement, or changing depth/object-oracle/success extras did not alter it. No neural model ran. The native VLA receives fresh RGB/state for each inference; the reduced Qwen controller receives fresh pictures only when it explicitly observes. These are different feedback paths and must not be conflated.

The source shows where an observation extension would be needed; it does not establish that an extension improves performance. Replacing a cached command with measured aperture inside the frozen VLA input would change its interface semantics and cannot be a silent deployment fix. Any future measured-feedback channel should first have a separately qualified, shared contract for all methods, without leaking object/contact truth or changing the scorer.

## Existing development evidence only

The fixed50 development run `official-owner-fixed50-dev10-20261101-0300` supplied all 10 cases and all 186 saved inference-input records. Each input was hashed. No validation or final-test case was read for this analysis. We compared the 12 actual arm joints with the corresponding 12 drive targets at those observation instants. Across cases, median joint RMS residuals ranged from 0.001315 to 0.005470 rad; success and failure ranges overlap. This is a descriptive tracking diagnostic, not a task-failure classifier, causal explanation, or threshold selection experiment. The maximum single-coordinate residual was 0.057175 rad. The samples omit the intervals inside chunks and contain no actual finger/contact measurement, so they cannot identify grasp validity or justify a corrective rule.

## Decision and bounded next step

Keep the current gripper candidate closed and fixed50 as incumbent. Accepted shared updates remain zero, forgetting after an accepted update remains null, and strict RSI rounds remain zero. Do not restart the old configurations, add seeds, sweep thresholds, modify the VLA input or launch a new Qwen qualification from this audit. Do not repeat this completed audit unless its input sources actually change.

Before proposing another robot experiment, conduct one finite comparison of primary-source mechanisms in Harness VLA, RoboRSI and EmbodiedRSI/HCL: what evidence admits an experience into persistent memory, how outcome uncertainty is retained, and whether this is already explicit rather than inferred from a tool's return status. The question is whether evidence-conditioned memory admission and later invalidation under changed execution conditions has a specific unresolved mechanism. This is a question for novelty screening, not a claimed new method; sensing, verification, gates and skill dependencies already exist in prior work.

The screening should produce either one falsifiable mechanism with matched permissions, a strong comparison and an explicit independent finite protocol, or a documented no-go. It must not recycle validation feedback into another gripper patch, reframe local error recovery as this project's core, or expand the generic budget allocator. No online budget is opened here. If the proposed mechanism is already covered or cannot be tested with existing observations, stop it instead of creating experiments merely to keep GPUs occupied. The separate pi0/RL/WAM project stays unchanged.

Evidence: runtime `outputs/checkpoint-feedback-audit-20261102-0810/{report.json,development-input-manifest.json}`. Eight source files and five pinned metadata files are hashed. This is source/contract qualification, not a reproduction of paper numerical results. Git contains the read-only audit and this interpretation; models, raw records and validation evidence remain outside Git.
