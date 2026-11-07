# Typed persistent atom-program CPU delivery

本轮完成受限typed atom-program CPU解释器：一个owner绑定package/contract，call/typed引用绑定/yes-no-unknown分支/终态，固定节点/transition/attempt上限、失败调用先计账并停止、不向程序开放未声明返回。持久artifact带SHA且exclusive写入/加载复验，accepted与rollout_authorized始终false。每次运行重新建临时绑定；native adapter保留ns[atom](projected_api,args)签名，但只在fake namespace验收，不是完整原版orchestrated循环复现或OS沙箱。
独立审查修正declared number返回int与float字面量的相等语义，bool仍拒绝；冻结owner contract快照、拒绝非正/非整数限额、fsync文件。16CPUtests本地/远端通过（13初版+3审查新增，同一演进套件不叠加）。持久合成H0加载两次，ready真/假分别调用probe与probe-act；手工夹具H1改变分支后改变调用路径。是CPU表达能力，不是Agent自主更新或机器人收益。无真实底层API硬wall、源码身份认证或SAPIEN资格；未来需可信owner/supervisor，不能据此运行生成技能。
当前burger typed-repair线上NO-GO：原包已有重试，place的ok与lowered/raised分量只说明源码可能的后条件差异，没有观察到错误或可恢复位置grounding；不能手写救动作或制造故障。没有新在线预算，不跑随机burger面板。
已选择独立替代：Qwen2.5-Coder14B在非三碗的place_phone_stand做完整artifact作者基线设计；两完整发布包及有效配对观察提供任务/强对照依据。下一交付精确只读输入/初文件manifest与独立部署生成配置，草案两条件各1响应/总2、input<=24000/output<=8192/context32768，无重试修补；是新后端新任务草案，不补旧30B1024预算。尚未下载/加载/调用模型；初始继承源码不同是处理变量，不能称输入信息相同或仅胜过空库。静态完整不等于机器人能力/有益H；真实物理比较与非空保留问题仍须独立门槛。
CLI2.1.319已有00:03新健康检查两轮通过，本轮不重复，正式委派137.514秒exit0且工具日志通过；报告输入3349、缓存写92814/读141699、输出17433，估算0.8544658USD非核实实付，标签不认证后端身份。科研Qwen/VLA/CLIP/机器人/训练均0，acceptedH0、forgettingnull、strictRSI0。

See task contract and tests in scripts/skill_rsi_atom_program.py and tests/test_atom_program.py. Artifact SHA is integrity, not cryptographic authorization. Trusted owner must pin the actual namespace and supply approved contract; callback and blocking native-call deadlines are outside this interpreter.
