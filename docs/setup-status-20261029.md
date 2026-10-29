# 新服务器部署记录（2026-10-29）

独立仓库budgeted-vla-rsi，主机仅lzgpu201。uv0.13.1；Qwen/Agent/RPent使用Python3.12.15，SAPIEN基础环境使用3.11.17。

- Qwen57包、Agent106包、RPent74包、sim32包：uv pip check及主要模块导入通过。
- GPU0 CUDA12.8/torch2.11.0+cu128算子检查通过，识别SM12.0。
- SAPIEN240步方块落地，最终z=0.01999995m；128×128图像已人工检查，方块可见。无Agent调用或机器人任务。
- 修复容器缺EGL导致Vulkan初始化失败：仅在运行目录补用户态库，未改系统驱动；保留失败记录。
- 65历史脚本SHA保留；11项官方源码关键文件SHA吻合；官方RoboRSI/RPent固定提交独立存放。

本轮完成代码抽离与基础环境配置。模型权重尚未迁入新主机，完整RoboTwin、cuRobo/RLinf及任务资产仍需部署和验收；不能声称完整基线可运行或有新成功率。旧关闭协议保持关闭。

详细机器证据位于运行目录outputs/setup-20261029，镜像下载错误保留。GitHub远程等待用户创建并提供URL。下一步先固定权重/任务后端，再资格验证RoboRSI完整Planner–Engineer–Reviewer。
