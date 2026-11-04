# Perception isolation and prepared author inputs — 2026-11-05 morning

Both GPUs remain occupied by other training112194/112195 (~43.9GiB each). The frozen callerdev2 protocol151db4d7 is unchanged and still unlaunched. No Qwen/VLA/CLIP, new simulation or training ran. No H update was accepted; forgetting-after-update remains null and strictRSI0.

## New implementation and completed CPU comparison

The new perception_worker/perception_ipc pair accepts source text, RGB, depth and camera calibration only. Images travel as bounded arrays with dtype/shape/content hashes; no pickle or runtime paths are passed to candidate code. It preloads trusted NumPy/PIL/sklearn and the pinned official world_points camera transform, enables the prior seccomp allowlist before source execution, and enforces2GiB address-space/5sCPU/15sprocess wall and bounded output. No CLIP model or GPU visibility. A small trusted numerical warmup occurs before the filter; it is included in process elapsed time and not a learned-model call.

Five new synthetic CPU tests pass: numerical RGBD/DBSCAN roundtrip, invalid hash/dtype/shape denial, forbidden source rejection, output byte cap and owned-child deadline. Previous skill/caller tests were not rerun. Four author-input tests also pass: both approved manifests load with fixed hashes, unknown tasks and tampering are rejected, snapshots cannot be overwritten.

Independent skill-rsi-perception-cpu2-20261105-0630, SHA f1a40beeb98474af9ef6c2b3c965e8c5a90f6c973adc70a2cd4467cf35978582, was frozen before execution and is CLOSED. Exactly two previously approved development observations were used: can671334 and bowls561222. Each pinned published detect ran once directly and once isolated,4detect calls total. Both outputs were exactly equal, each with2components; table heights0.7405657818409971 and0.7405871473011474. Isolated children exited0 in1.0943s/1.0624s including loading; full protocol3.1285s elapsed. This is deployment equivalence, not robot rerun, perception quality improvement, stable task rate or learned harness benefit. Raw input/output SHA and frozen references were checked. No sealed validation or scorer feedback was read. This CPU protocol must not be repeated or refilled.

## Author data contract

The new public API document and skill_rsi_author_inputs.py prepare exactly five pinned text resources per task: public API, SKILL.md, inheritedskills, inheritedperception, approveddevelopmentfeedback. They exclude episode scoring/layout/scorer/sealed evidence. Two input manifests were staged, with0author calls and0image attachments. Relative image metadata in a text packet is not proof of model vision. Passing or creating input manifests does not authorize a proposal or rollout. Generic author inheritance/data isolation is existing mechanism/engineering, not a paper contribution.

## Next executable work

When both GPUs/locks/ports/storage are actually idle, run the unchanged frozen callerdev2 once, after checking report/CLOSE/qwen sibling. No new GPU qualification or random seed panel. Current two-case caller trial tests native autonomous calls; previous code-only successes on other seeds are not a matched method ranking.

If GPUs remain occupied, finish the real API deadline and native exception/status mapping in a versioned supervisor using CPU fake-backend tests. Skill/perception children now have isolated CPU paths, but the synchronous parent backend is not yet a full bounded simulator integration. Do not claim complete author isolation or execute generated skills in a robot runner until that integration is explicitly reviewed under a new bounded protocol. After valid caller feedback identifies a concrete error, freeze limited author proposals and matched fixedlibrary/inherit-only/feedbackrevision comparison. Do not manufacture errors from the two successful development examples or claim generic description repair as innovation.

All historical budgets and canceled seeds remain CLOSED; two-task100006..100015 sealed validation is unavailable to authors. Only lzgpu201/uv; other GPU jobs and independent pi0/RL/WAM unchanged. No cleanup this round; retain evidence and max100GiB/20%capacity+expected outputs.
