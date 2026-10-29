# RoboRSI 本地模型路由审计（2026-10-29，部分完成）

固定源码90c8569705bf4004a4f79e34e650c87ab7f075d4。本轮0模型调用，不构成执行协议或完整基线验收。

- Planner/Reviewer默认使用持久CLI会话（ROBORSI_ROLE_SESSION=1），带会话ID、历史和压缩；openai前缀会选择codex CLI。只替换主模型名和HTTP地址并不足以证明所有角色走本地Qwen。需检查CLI的实际传输配置、所有请求及压缩计费。
- 上游显式支持ROLE_SESSION=0，但这是无状态分支。run_role该分支未序列化images参数；不可静默关闭持久会话并冒充默认完整RoboRSI。若使用，必须另标消融/适配并解释观测差异。
- SkillSelector独立默认claude-sonnet-4-6，感知也有独立默认模型；两者均须明确固定本地模型并计费。主VLM按模型前缀选择provider，仅改ROBORSI_VLM_PROVIDER并不覆盖所有调用。
- Python3.11环境补msgpack-numpy0.4.8后原生HTTP服务模块导入成功；完整RPC与机器人任务尚未验证。

下一步保留默认持久会话的语义，验证本地后端传输和预算代理；然后冻结有界在线资格。不得调用收费模型，也不得用单执行器替代完整三角色系统。
