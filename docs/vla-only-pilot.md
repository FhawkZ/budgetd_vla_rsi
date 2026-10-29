# VLA-only 开发筛选入口（DRAFT，2026-10-29）

`scripts/run_vla_only_pilot.py` 使用固定 RPent 的 `_init_runtime`、`RoboTwinPrimitives.lingbot_act` 及 LingBot 原生 websocket 推理。每次从当前三路 RGB、原生机器人状态和不变的任务指令生成 50 个 EEF16 动作。没有 Qwen、高层 planner、手写动作、expert、技能更新或 RSI。不会执行 archive。

配置 `configs/vla-only-screening-draft.json` 仍为 draft，不可启动。草案仅含 stack_blocks_two / handover_block，各一个新开发 seed；每场景1200动作、最多24次VLA推理，两场景总48次。RPC reset只有一次，自动重置关闭，实际seed和step_lim在每个chunk检查，动作计数必须单调增长。成功以原生eval_success原值为准；提前成功则停止。每场景1800秒，总3900秒，遇基础设施错误停止且不重采样。不是成功率比较，也不与已关闭600步或10000cap协议混表。

## 先检查

```bash
cd /root/autodl-tmp/budgeted-vla-rsi
source scripts/activate.sh robotwin
python scripts/run_vla_only_pilot.py --check
```

这是CPU检查：验证固定源码、模型清单、原生horizon/auto_reset契约，列出缺失权重，不启动daemon、模型或GPU。CPU native imports、无效预算拒绝、draft拒绝已检查。另以合成RPC和假模型跑过契约fixture：恰好一次reset、2个RGB输入chunk、原生success提前停止及动作/RGB证据保存；真实模型调用0、真实环境步0。这不是机器人实验。

## 冻结后运行

主任务先核实完整权重、环境资格、GPU空闲和本协议用途，再另存冻结配置：status设frozen，填写当前runner SHA256；固定所有其余字段，对整份JSON计算SHA。启动显式传入该SHA：

```bash
python scripts/run_vla_only_pilot.py --config /absolute/path/frozen-protocol.json --run --protocol-sha256 SHA256_OF_FROZEN_JSON
```

运行前重新验证全部模型文件哈希和资产，获取共享 `locks/gpuN.lock` 并检查显存/进程，不共享已有服务。每场景启动自己所有的env/VLA子进程，外层有时限；仅按自己保存的PID与/proc出生时间清理。任何已存在输出目录均拒绝覆盖，未运行场景没有补回预算的自动路径。完整运行尚未资格通过，不声称可复现成绩。

输出位于runtime/outputs/<run_id>，包含冻结协议、整体report、每场景episode、daemon日志、RGB PNG、推理前输入JSON、完整预测action NPY及哈希、原生chunk状态和终态图像。失败推理计入VLA调用；模型初始化与终止等待包含在墙钟/GPU分配时间。GPU分配时间不冒充纯推理时间。

## 显式后端适配

RPent所用packaged RoboTwin的_base_task.py同样硬编码SapienRenderer()、rt shader；在当前机器需要明确选择实际分配的Vulkan设备。runner仅给自己的env子进程创建运行时sitecustomize：PCI核对、显式SAPIEN Device、CPU物理+指定RenderSystem、保留官方RT shader、denoiser none。官方源文件、物理步骤、控制器和成功函数不变；将适配源码保存在该场景bootstrap目录。此渲染选择属于平台适配，不能叫未修改原生图像分布；CPU仅检查代码，GPU有效性由独立native资格及实际运行确认；并不宣称禁用denoiser后的图像与官方像素等价。此前raster草案从未执行，现已废弃。推理保留每chunk输入图像，不记录每个物理帧视频。

## 已知边界

只验证低层策略可达性及新机真实rollout。结果低不等于harness机制失败；一次失败也不证明任务不可达。无模型权重训练，模型调用48上限不借用已关闭RPent或VLA-only协议。六任务大筛暂不启动。



## 工作目录与设备索引核查（同日修订）

RLinf packaged RoboTwin多数资源函数由ASSETS_PATH/ROBOTWIN_ASSETS_ROOT取绝对路径，仍有少量相对路径回退。env子进程因此显式cwd到已校验asset snapshot根（该根下存在assets/objects/objaverse/list.json），同时传入两个绝对资产变量；不使用RoboRSI源码backend作为RPent的执行根。RPent及RLinf源码仍通过绝对PYTHONPATH和脚本路径固定，VLA进程保留原RPent工作目录。

父/子进程的CUDA_VISIBLE_DEVICES都写同一个物理GPU编号（例如1），子进程环境是覆盖字符串而非在父映射上再索引；子进程torch使用cuda:0/默认cuda，SAPIEN Device(\"cuda:0\")并核对物理PCI。不把物理1再传给torch.set_device(1)。已CPU核对RPent _resolve_cuda_devices与ProcessDaemon环境覆盖，不做实际GPU探测/启动。
