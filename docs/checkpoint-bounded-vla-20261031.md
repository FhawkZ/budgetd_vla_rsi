# Bounded VLA executor development checkpoint — 2026-10-31

The common executor now performs real LingBot actions. This is an explicit deployment adaptation, not an original-paper reproduction or an RSI result. The native tool only supports 50 waypoints; this interface also permits submitting the first 25 unchanged waypoints and replanning from the resulting observation. Native language, checkpoint, initial state/RGB, horizon and scorer are preserved. No high-level model selected these schedules.

The frozen four-case protocol `bounded-vla-pair4-20261031-1130` completed and is CLOSED. These are two previously observed development scenes, not an independent test set or stable success-rate estimate.

| Task / seed | Prefix | Native success | VLA calls | Native action counter |
|---|---:|---|---:|---:|
| stack_blocks_two / 2026103011 | 50 | yes | 6 | 280 |
| stack_blocks_two / 2026103011 | 25 | no | 48 | 1200 |
| handover_block / 2026103012 | 50 | no | 24 | 1200 |
| handover_block / 2026103012 | 25 | no | 48 | 1200 |

Total: 126 VLA inferences, 3880 native action-counter increments, 1348.620 GPU allocation seconds, 58.236 inference RPC seconds, zero Qwen generations. The remaining 66 inference allowance was canceled. Allocation time includes simulator/setup and is not pure inference compute. Native action counts are not physics ticks or successful motion plans. Submitted prefixes exactly match saved predictions; the simulator may terminate inside a submitted prefix, so array length is not necessarily executed motion.

All four initial states and three camera hashes match the frozen reference, and every inference uses the native task language. Paired first predictions are exactly identical; second inference states differ as expected from the different prefix lengths. The current successful stack's first prediction equals the historical native control, but its final action count is 280 versus 272; whole-trajectory deterministic equality is not established. No additional terminal stability test was run.

Six new CPU tests and the actual-native-primitive comparison passed. All 29 root CPU tests passed with the correct RPent PYTHONPATH. The initial missing-PYTHONPATH import failure is retained in runtime evidence. Three tool schemas pass structural validation; online model-controlled transport remains UNQUALIFIED.

The result falsifies the assumption that simply observing/replanning more frequently is an improvement in these cases. Preserve fixed-50 `bounded-harness-v000.json` as a functional control, not a learned promotion. No accepted shared update, post-update retention measurement, or strict RSI round exists. Equal caps do not imply equal consumed cost, and this table is not a method ranking.

## Next bounded work

1. Implement the shared model-controlled execute/observe/stop transport using the existing frozen 30B model, 32K context and 1024 output ceiling, with a complete external ledger. Do not automatically force execution after repeated observe. Every request, failed generation, observation, attempted execution and refusal must be recorded. No arbitrary files, code execution, final-test data or scoring tools are exposed.
2. Freeze an independent small cached-observation qualification before generation. Include image round-trip, legal autonomous tool selection, stop and exhausted-budget handling. Structural fixtures and prescribed branches only qualify transport, not autonomous competence. Do not reopen any old quota.
3. Only after that qualification, predeclare a bounded task-level comparison against fixed-50 with the same starting conditions, observation access and total-cost accounting. Learned/paper-inspired controllers on this reduced interface are explicit adaptations; original native RPent/RoboRSI failures remain separate. Do not claim superiority by beating an unusable local baseline.
4. If this controller still cannot act, stop that configuration. Audit a predeclared broader task panel and checkpoint/task compatibility without picking successful seeds. If scheduling alone has no useful improvement, study bounded experience retrieval/retention decisions only after a real, useful shared update exists. Do not continue a 25/10/5 prefix sweep or enlarge model/call limits.
5. Before the paper experiment, specify shared candidate generator/features/permissions/gates for uniform, strong fixed VOI+risk, and evolved allocation. Count modification, rejected proposals, failures and evaluation costs. Prove allocator-only transfer to reset executor/experience on new sequences. The 600-episode draft remains NOT AUTHORIZED TO RUN as a frozen protocol; final testing requires isolation and no feedback to the improver.
