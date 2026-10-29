# Budgeted VLA RSI

- Development and execution only on lzgpu201, at most two genuinely idle GPUs. Recheck live processes and locks before each GPU launch. No connection to suspended 2026-liqz; no other-server GPU use.
- Code in this standalone repo; runtime/models/logs outside Git at /root/autodl-tmp/Dex_runtime/agent-rsi. Source scripts/env.sh and use a named isolated interpreter.
- Phase one freezes VLA and Qwen weights. Reproduce full official baselines before own method. Native baseline and common-backend adaptation must be labeled separately.
- Freeze protocol, task split, source/model hashes and total budget before online experiment. Count planner, engineer, reviewer, perception, revision, validation and failed calls. No test leakage or scorer changes.
- Archive files are closed historical provenance, renamed .txt, not runnable entrypoints. Do not rerun RPent16K or32K allocations.32K used21stack calls plus2earlier canaries;179unused calls canceled;handover notstarted;zero motor actions or persistentupdates.
- No claim of success/forgetting/strict RSI from smoke, replay or merely a changed tool interface. Protect all separate recovery/PI0 work.
- No external messages, paid model fallback, unattended real robot, or purchases.

- User requires uv for all Python version/environment/dependency management. Use uv python, uv venv, uv pip; no Conda environment creation. Exact versions and resolved manifests are part of provenance.
