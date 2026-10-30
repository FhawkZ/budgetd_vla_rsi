# 2026-10-30 语言与能力契约检查

所有实验在 lzgpu201，权重冻结，原生上游文件未改。以下是开发/资格证据，不是论文原模型数值或RSI改进结果。

| 独立协议 | 结果 | 实际Qwen生成 | 输入/输出token | 剩余取消 |
|---|---|---:|---:|---:|
| native-language-dev24-20261030-1010 | Planner、Engineer、Reviewer参数及实际模型请求均包含同一官方交接描述；能力声明通过 | 13 | 194636 / 2366 | 11 |
| native-handover-language64-20261030-1020 | 第10次生成幻觉调用未声明grasp_object；HTTP400传至原生RPC500，执行未完成，Reviewer未到达 | 10 | 157397 / 1550 | 54 |

共23次生成，352033输入、3916输出token；生成101.671710秒，GPU0分配265.770512秒。两个协议均关闭，不补余额。资格试验本身没有任务成功；失败的完整开发尝试不是完整评测成功率的分母。

禁用GraspGen后仅从RoboTwin技能发现中排除grasp_object、grasp_diverse、grasp_top_down；保留grasp_obb与get_grasp_pose。过滤不能保证模型遵守工具声明。本次确实出现未声明调用，不能宣称问题已经解决。

旧代理账本漏掉第10次失败生成的24308输入/28输出token。服务器原始生成文件和审计记录保留，汇总采用包含失败的全部生成成本；原账本不改写。新代码让服务器返回已知失败usage并由代理计费，CPU HTTP400/硬调用上限测试通过；新代码尚无额外在线生成资格。不知道usage时明确标未知，不按零计费。

旧owner-report的passed仅表示调度返回，不能当作任务通过；新launcher区分完整终态completed与incomplete失败。原始报告保留不覆盖。

新共同语言VLA-only两任务协议见configs/vla-publiclang-dev2-20261030-frozen.json。最终结果保存在运行目录相应report.json；下一步设计见docs/common-backend-next.md。当前接受更新0、遗忘未测、严格RSI收益未证实。
