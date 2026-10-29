# uv 环境管理

统一使用 uv 0.13.1 管理 Python、虚拟环境及依赖。代码与运行目录分离，不创建 Conda 环境。

```bash
cd /root/autodl-tmp/budgeted-vla-rsi
source scripts/env.sh
bash scripts/bootstrap.sh qwen
bash scripts/bootstrap.sh agent
bash scripts/bootstrap.sh rpent
bash scripts/bootstrap.sh sim
bash scripts/bootstrap_graphics.sh
source scripts/activate.sh agent
python scripts/check_environment.py --profile agent --output "$RSI_RUNTIME_ROOT/agent-check.json"
```

四个独立环境：qwen（Python3.12.15推理）、agent（3.12.15 RoboRSI控制面）、rpent（3.12.15 Harness VLA控制面）、sim（3.11.17 SAPIEN/MPlib基础）。每套依赖精确冻结在 requirements/，由 uv pip 安装并检查。根 uv.lock 仅管理轻量项目；不能用根环境代替这些运行环境。bootstrap 不清空现有环境。

activate.sh 为 Agent 环境设置固定提交的源码 PYTHONPATH；不宣称安装了 RoboRSI 的所有实机硬件 extras。完整 RoboTwin、cuRobo/RLinf编译及任务资产是另一层部署，robotwin配置尚未验收。旧 file:// 依赖只留在历史清单，不能安装。

默认使用清华 PyPI 镜像；RPent使用华为镜像，缺失包回退官方 PyPI；Qwen CUDA wheel来自官方 PyTorch源。RSI_PYPI_INDEX 可覆盖索引。版本不随镜像改变，最终保存 uv pip freeze/check。旧47项Qwen固定依赖均保留，新增解析传递项共57包；不是旧环境逐字节复制。

容器缺 libEGL.so.1 会导致 NVIDIA Vulkan无法建立实例。bootstrap_graphics.sh 将 Ubuntu22.04固定版本deb校验后解包到software/system，只补用户态EGL/Vulkan库，不更改驱动或系统目录。NVIDIA ICD仍来自/etc/vulkan/icd.d/nvidia_icd.json。安装后source入口加入项目库路径。

GPU smoke须持有锁且实时检查空闲；渲染检查因驱动可能枚举两卡，保守取得两卡锁。权重未部署时不启动模型服务。环境通过不等于基线任务通过。
