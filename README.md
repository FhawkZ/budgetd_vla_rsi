# budgetd_vla_rsi

预算约束下，基于 RSI 的 VLA–Harness 持续学习。目标是研究在冻结 VLA/LLM 权重时，执行 harness 与经验选择策略如何持续改进，并在统一总预算下测量新任务泛化、旧能力保留和饱和。

## 当前阶段

先复现官方基线，再提出新方法。RoboRSI 原生多角色执行与 RPent/Harness VLA 分开配置；共同 VLA 后端适配必须另行标注。尚无通过统一评测的新方法结果。

2026-10-29：cuRobo已编译，堆叠/交接均通过原生reset、实际关节动作和四相机检查；保留RT shader并显式关闭不支持的OIDN。Qwen持久CLI会话完成5次在线资格调用（27559输入/377输出tokens），不是机器人任务成绩。固定LingBot的34文件/24.33GB全部哈希验证，独立两任务VLA-only开发诊断已完成：交接267动作/6推理原生成功，堆叠1200动作/24推理未成功；每项仅一个未筛选开发场景，不能估计稳定成功率；原生RoboRSI完整角色执行仍在接入。详情见 `docs/vla-only-pilot.md` 与 `docs/experiment-case.md`。

仅在 `lzgpu201` 两张 PRO 6000 上执行。代码 `/root/autodl-tmp/budgeted-vla-rsi`；权重、虚拟环境、缓存、日志 `/root/autodl-tmp/Dex_runtime/agent-rsi`。GPU 编号是分工建议，不构成占卡；启动前查实时进程和锁。

## uv 配置

```bash
cd /root/autodl-tmp/budgeted-vla-rsi
source scripts/env.sh
bash scripts/bootstrap.sh qwen
bash scripts/bootstrap.sh agent
bash scripts/bootstrap.sh rpent
bash scripts/bootstrap.sh sim
bash scripts/bootstrap_graphics.sh
```

所有 Python 均由 uv 管理：Qwen/Agent 使用3.12.15，原生仿真使用3.11.17。`requirements/` 保存独立依赖清单，根 `uv.lock` 管理轻量项目。`rpent` 为独立 Agent 环境，`robotwin` 配置保留旧基线的冻结依赖供后续完整原生环境部署；`sim` 是小型物理/渲染基础环境，不能当作完整 RoboTwin 已验证。

固定版本官方源码：

```bash
"$RSI_SOFTWARE_ROOT/python/cpython-3.12.15-linux-x86_64-gnu/bin/python" scripts/fetch_sources.py
```

固定权重下载（仅CPU和网络，4个下载线程、最长2小时，逐文件验证SHA；不启动模型调用）：

```bash
source scripts/activate.sh qwen
python scripts/fetch_qwen.py
```

进度保存在运行目录 `outputs/qwen-deploy-20261029/status.json`。只有 `status=complete` 才代表16个冻结文件全部验收；下载中不算模型就绪。

`configs/sources.json` 固定提交，源码置于外部 vendor 目录，不把整套第三方仓库和大文件复制进 Git。模型另按文件 SHA 清单部署；环境导入通过不等于模型/任务通过。

## 目录

- `scripts/`：独立环境入口、固定Qwen服务、调用预算代理、源码获取和环境验证。
- `configs/`：主机、模型与官方源码固定版本。
- `requirements/`：各环境依赖与历史原始清单。
- `docs/`：课题、基线、迁移与当前资格状态。
- `archive/`：65份历史脚本，字节和SHA保留，后缀改为 `.txt` 防止误作入口。

## 实验纪律

所有角色、失败调用、自我修改、候选筛选、复测均计入总预算。冻结分割和评分器；最终测试反馈不进入进化Agent。只有在相同初始执行器与经验、新任务序列、等总预算下验证改进器收益，才讨论严格RSI。

旧RPent32K协议已经关闭：21次堆叠调用因工具参数错误退出，0物理动作，交接未启动；加2次早期canary共23次，179次剩余额度取消。没有技能更新或遗忘成绩，不重开这些预算。

## GitHub 同步

正式远程仓库：https://github.com/FhawkZ/budgetd_vla_rsi ，分支 `main`。

本机目录仍为 `/root/autodl-tmp/budgeted-vla-rsi`，Python项目名仍为 `budgeted-vla-rsi`，避免破坏已验证的环境入口。后续只在 lzgpu201 推进，统一使用 uv；每5小时检查进度并按冻结协议继续。

权重、数据、原始日志、虚拟环境与凭据不进 Git。服务器没有 GitHub 写入凭据时，通过本地已有认证和 Git bundle 中转同步，不复制私钥到服务器。

2026-10-29：lzgpu301旧RSI Qwen已按用户要求停止，后续只在lzgpu201运行。完整RoboRSI所需原生DINO/SAM按固定提交和文件哈希部署中；所有角色LLM走本地Qwen，固定视觉工具另记计算成本。无新方法收益、持久更新或遗忘结论。
