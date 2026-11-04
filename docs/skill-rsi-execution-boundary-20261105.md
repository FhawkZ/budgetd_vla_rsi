# CPU skill execution boundary — 2026-11-05

The pending native callerdev2 protocol151db4d7 remains frozen and unlaunched. Both GPUs remain occupied by other training PID112194/112195 (~43.9GiB each), despite a momentary0utilization reading. No resource was taken from those jobs. No Qwen/VLA/robot simulation was launched and no persistent harness update accepted.

## New executable implementation

scripts/skill_rsi_skill_worker.py loads the pinned official static validator, validates source, then enables no_new_privs plus a libseccomp syscall allowlist before candidate load/execution. It is a fresh uv Python child with sanitized environment, closed nonstandard descriptors and memory/CPU/core/file-size limits. It receives text and JSON only, not a simulator object. Filesystem-open, socket creation and process creation are absent from the allowlist. No root access, account creation, dependency installation or unrestricted fallback is used.

scripts/skill_rsi_skill_ipc.py mediates the seven official API methods through bounded JSON messages. task_spec projects instruction and roles, excluding criterion_source; unexpected methods/argument keys and evaluator fields are rejected. The underlying physical API and scorer are not modified. Failed requests and terminal messages are recorded with hashes. The owner kills only its exact child on timeout. This is explicit deployment isolation, not a research contribution.

Six new CPU tests passed in0.957s unittest time (wall time in receipt): an authored-format synthetic skill makes a fake API roundtrip without scorer disclosure; invalid source is rejected; wrong methods and nested evaluator data are denied; a long-running child is killed; excess allocation returns MemoryError; an independent trusted containment probe bypasses static validation and verifies actual open/socket/fork calls return EPERM. Initial test-file escaping error is retained. Existing42tests were not repeated because their files did not change. The test name was clarified from published_contract to skill_contract after passing; its body is unchanged. All three new modules compile. Fixtures are not policy or paper results.

## Deliberate limits and next steps

This is not the full author/simulator sandbox. Candidate perception.py still needs its own data-only boundary; it is never loaded by this worker. The broker currently calls its backend synchronously, so a future real-simulator integration needs an independent API deadline and native exception/status mapping. CPU fixture timeouts are not proof of a simulator hard deadline. No new robot runner is wired to this module and the frozen callerdev2 is unchanged. The official native validator alone is not asserted to be a security proof.

Priority remains: when BOTH GPUs/locks/ports/storage are actually idle, execute the existing frozen two-case/eight-Qwen caller protocol once, without an extra qualification. Check its output/CLOSE and qwen sibling first. If GPUs remain occupied, continue the concrete perception/author input boundary, not another repeat of these checks. After valid caller feedback identifies a specific execution failure, independently freeze a bounded author revision and matched fixed-library/inheritance-only/feedback-revision comparison. Generic inheritance or isolation is existing engineering, not new RSI. All historical closed protocols/canceled seeds and sealed validation remain closed.

Only lzgpu201/uv; storage ~335GiB free with100GiB/20% reserve and this CPUwork projected10MiB. No cleanup this round. Preserve independent pi0/RL/WAM and all other jobs.
