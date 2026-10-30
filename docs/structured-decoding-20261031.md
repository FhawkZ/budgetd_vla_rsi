# 结构化生成适配与有界任务复测：2026-10-31

这是部署验证，不是新harness学习方法。原版RPent工具参数schema保持不变，固定Qwen3-VL-8B和LingBot权重。依据[XGrammar官方HF集成](https://xgrammar.mlc.ai/docs/latest/start/quick_start.html)与[工具调用文档](https://xgrammar.mlc.ai/docs/latest/structural_tag/tool_calling_and_reasoning.html)，在生成采样阶段掩蔽非法token；工具选择保持auto，可以纯文本回答或调用多个工具，不猜测或重写生成参数。解码器声明JSON属性顺序，所有相关比较方法必须一致使用此适配。原始失败独立保留。

## 验证与结果

- CPU：14工具原schema，10个完整字符串接受/拒绝用例和历史非法token边界通过；另5项拒绝路径单元测试通过。原robotwin环境23项测试仍通过。
- 独立资格structured-qual3-20261031-0130：两条历史失败请求产生合法嵌套像素数组；一条文本canary不调用工具。3生成40757输入/97输出、6.585生成秒，GPU0分配17.718秒。第四次代理请求被硬预算拒绝，未生成。资格关闭；没有执行任何机器人工具，不能据此认为坐标选择正确。
- 独立任务rpent-structured-native-dev64-20261031-0140：堆叠/交接各32调用，用满后关闭。相同初始机器人状态与三路RGB；两个任务均失败，0动作、0VLA。64请求原始/转发SHA精确匹配，0原生schema违规。总960793输入/3748输出，142.461生成秒；GPU0分配264.128秒、GPU1任务进程区间254.373秒。没有持久更新、遗忘或严格RSI结果。

结构正确不等于自主决策有效。两任务仍有8/2个显式工具错误反馈（主要图像路径语义错误），各发生2次上下文裁剪；裁剪前估计峰值47726/50196，不是实际模型输入长度，实际服务输入仍受32K硬限制。压缩器在代理执行latest3-image裁减之前估计全部历史图像，可能提前裁剪文本，是仍须审计的混淆。不能仅据此断言8B能力不足，也不能声称增加参数一定解决问题。

## 停止条件与共同后端候选

已兑现一次适配试跑后停止的条件，不再给8B此配置追加调用或挑选新seed。下一步先CPU审计“压缩器图像计数与latest3传输”的一致性。任何修正显式版本化并对所有比较方法共用，不作为创新。

并行准备官方[Qwen3-VL-30B-A3B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-30B-A3B-Instruct)候选。ModelScope官方Qwen仓库24文件、62153205636字节逐文件固定revision/SHA，单独目录下载；四线程、每块最多3次、总2小时上限、独立锁。不改8B权重，不加载新模型、不自动启动新任务。需要全文件SHA完成、MoE类兼容、真实32K显存与工具/图像/成本资格，以及新的共同后端冻结协议，才能选择它。两个模型的结果必须分列；新方法与所有基线最终使用同一已资格模型。

本课题仍须证明等总预算下“新任务探索/旧能力复验证分配器”的学习收益、旧能力保留和分配器单独迁移。当前部署负结果不支持这些主张；600episode草案仍不能启动。

## uv复现

先完成原qwen profile，再使用uv安装requirements/structured-decoding-py312.in；全环境快照为requirements/qwen-structured-cu128-py312.lock。Qwen额外依赖没有装入robotwin profile。CPU输出验证用 `PYTHONPATH=scripts python -m unittest discover -s tests/qwen`，robotwin测试保持在tests根目录。脚本和协议已关闭的输出目录不可覆盖重跑。
