# 给后续 Agent 的架构与维护地图

## 消息链路

```text
微信数据库监听 → 鲸鲸 receiver_mixin → 鲸鲸 Node /webhook/wechat
  → maibot-link.js（鉴权与允许会话）→ hub /native/reply → inbox
  → 麦麦 whale_text 网关 → 麦麦原生模型/规划
  → hub /adapter/outbox → outbox → maibot_async → 鲸鲸原有前台发送
```

本账号文字经 `sync_self` 写持久待同步队列，再交 `/bridge/self-message`。Hub 判别短时间内机器人回声；人工代发使用 SDK `chat.open_session`、`maisaka.context.append(replyable=False)`，不是新问题，也不强制长期记忆。

语音通过插件 `whale_api_voice` 工具 → `/adapter/whale-voice`，必须消费当前会话、当前用户的未过期 `/v` 授权。群上下文缺少用户时只允许唯一待处理授权；不能任选一个。生成语音由鲸鲸原有 API 和配置负责。录音前调用 `microphone_guard`，系统检查失败返回失败。

## 文件归属

| 文件 | 作用/上游衔接 |
| --- | --- |
| `hub.py` | 本地监督、队列、网关认证、授权、API 语音任务、出站回执；18787 只绑定回环 |
| `deployment.py` | 读取安装器生成的本机路径，绝不内嵌开发者路径 |
| `plugin/` | 麦麦 SDK 网关/工具；无需修改麦麦核心 |
| `whale_patch/routes/maibot-link.js` | 替代桥接模式微信聊天路由，调用鲸鲸现有 `sendDenial` 后交麦麦，无鲸鲸聊天 API 兜底 |
| `whale_patch/bridge/app.py` | 上游文件副本，在监听启动后启动 `maibot_async.run` 线程 |
| `whale_patch/bridge/receiver_mixin.py` | 上游文件副本：普通图片转发实际 JPEG 数据、图片模式过滤、本账号文字提前同步；保留其他原有行为 |
| `whale_patch/bridge/maibot_async.py` | 异步领取文字/表情/API 语音；确认 send permit 后调用原发送器；上报一次回执 |
| `whale_patch/bridge/sticker_mixin.py` | 上游文件副本：接受桥接任务 gate 与受限表情目录；其余账号/前台/输入草稿保护沿用上游 |
| `whale_patch/bridge/voice_mixin.py` | 上游文件副本：录音前的 prepare 调用麦克风检查；API 合成发送沿用鲸鲸 |
| `whale_patch/bridge/microphone_guard.py`、`audio/` | 用安装关联定位 PowerShell/C# 检查；不依赖 RVC |
| `emoji_payload.py` | 仅解码并验证实际图片字节，内容哈希文件名；不读模型路径/下载 URL |
| `remote_console.py`、`remote/` | 独立 18788 网页、Key、人工接管、代发与可选隧道 |
| `launcher.py`、CMD | 检查端口所属安装，监督当前实例，不误杀其他程序 |
| `install.py`、`restore.py` | 预览、版本门控、完整覆盖前备份、受保护还原 |
| `bridge_runner.py` | 提取时保留的旧文本适配路径；正常安装设置 `native_whale=true`，不使用此路径，不将其作为图文语音替代 |

副本是本地已运行版本的源码快照，不宣称与同版本官方文件完全一致。首次适配新版本先获取该版本原文件，再根据此表对照语义和当前差异迁移，保留新上游修复。没有原始上游 SHA 时不能伪造“基于某提交”。

## 更新时重点核对的契约

- Node：路由加载顺序、`readBody`、`isLoopbackRequest`、微信 gateway token 校验、`sendDenial` 参数、Node fetch/超时支持。
- 鲸鲸 Python：`BridgeRuntime` 线程启动点、监听消息 type/username/sender_username/local_id/shard、`send_policy_allows`、`send_text`、`send_voice_reply`、`send_sticker`、各锁的获取顺序。
- 表情：结果是字典，只有 `status == confirmed` 算成功，不能 `bool(dict)`；保留 quarantine，不重复粘贴/Enter。
- 麦麦：SDK manifest/capabilities、`MessageGateway` 出站 `raw_message` 格式、`binary_data_base64`、会话定位返回字段、上下文 append 的 `replyable=False`、host `control_request` shutdown/open_webui。
- API 语音：保留过期时间、用户归属、单次消费、停止时 generation 失效。`voice_jobs` 表仍用于 API 任务取消，不代表包含本地合成。
- 自身消息：文字完全相同且 120 秒内匹配发送记录存在歧义；不要声称身份判别绝对可靠。
- 远程：18788 与受信 hub 18787 分离；认证 Key 在本机生成且不能随日志泄漏；人工接管必须在入站、出站、领取和执行前均生效。
- Windows：麦克风 API 包含 IPolicyConfig COM 接口，系统版本变化要实测；测试只切设备不发送语音。

## 测试与发布

测试分三层：临时目录/HTTP 客户端隔离测试；本机加载和设备检查；用户明确授权后才进行真实微信发送。前两层通过不能声称第三层通过。

运行 README 的测试命令，新增版本适配后补相关契约测试。用临时鲸鲸/麦麦目录验证安装器：第一次预览不得改文件，apply 应生成备份且不得写模型配置，restore 遇到后续修改应拒绝。

依赖更新应分别说明转发 Python 环境、鲸鲸内置运行时、麦麦运行时；不能把开发机上的 site-packages 或 venv 推进仓库。不要把 cloudflared 二进制或语音模型带入发布。

发布流程：确认远程 owner/repo → 检查是否有历史并正常合并 → privacy_check → staged 文件逐一核对 → commit → 普通 push → 比较本地 HEAD、远程 main 和网页。冲突时停止，禁止强推。

## 回滚与报告

更新必须给出备份位置、安装计划、重启/重连要求和还原指令。真实用户的备份、队列、日志不能附加进报告。日志错误只摘取脱敏部分。若发现新功能需要更改发送策略或模型路由，先说明行为变化，不以兼容适配名义偷偷加入。
