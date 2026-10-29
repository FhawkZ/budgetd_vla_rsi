# RoboRSI 本地模型路由审计（2026-10-29，部分完成）

固定源码90c8569705bf4004a4f79e34e650c87ab7f075d4。本轮0模型调用，不构成执行协议或完整基线验收。

- Planner/Reviewer默认使用持久CLI会话（ROBORSI_ROLE_SESSION=1），带会话ID、历史和压缩；openai前缀会选择codex CLI。只替换主模型名和HTTP地址并不足以证明所有角色走本地Qwen。需检查CLI的实际传输配置、所有请求及压缩计费。
- 上游显式支持ROLE_SESSION=0，但这是无状态分支。run_role该分支未序列化images参数；不可静默关闭持久会话并冒充默认完整RoboRSI。若使用，必须另标消融/适配并解释观测差异。
- SkillSelector独立默认claude-sonnet-4-6，感知也有独立默认模型；两者均须明确固定本地模型并计费。主VLM按模型前缀选择provider，仅改ROBORSI_VLM_PROVIDER并不覆盖所有调用。
- Python3.11环境补msgpack-numpy0.4.8后原生HTTP服务模块导入成功；完整RPC与机器人任务尚未验证。

下一步保留默认持久会话的语义，验证本地后端传输和预算代理；然后冻结有界在线资格。不得调用收费模型，也不得用单执行器替代完整三角色系统。

## 2026-10-29 transport follow-up

`command -v codex`, `node`, and `npm` found no executable in the lzgpu201 task environment. The existing Qwen server and metering proxy only expose `/v1/chat/completions`. Current official [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference) says `responses` is the only supported custom-provider wire API; [advanced configuration](https://learn.chatgpt.com/docs/config-file/config-advanced) documents local custom providers. Thus changing the model name/base URL alone does not qualify the default persistent CLI path. No CLI generation was attempted.

Next transport work: pin a CLI version and qualify an explicit local Responses-to-Qwen adapter with offline fixtures for message history, image bytes, function call/output identity, SSE completion/failure and usage. Unknown tool types or context overflow must fail closed, not silently drop input. Preserve upstream role/task session IDs, resume and manager memory-roll behavior; every generation, helper and roll passes the shared budget ledger. Use isolated credentials/configuration and a local-only provider with no cloud fallback. The upstream role runner's prompt-only read restrictions and `dangerous_yolo` flag are not an adequate final-test isolation boundary: keep final test artifacts inaccessible to the role workspace and enforce write scope before autonomous execution. These are deployment/transport adaptations, not evidence of RSI or baseline task success.
