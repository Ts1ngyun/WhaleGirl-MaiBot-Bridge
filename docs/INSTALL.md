# 人工安装、配置和还原

## 0. 准备与边界

这是对已有程序的桥接部署，不是鲸鲸或麦麦安装器。先从各自官方项目安装：鲸鲸 `4.0.8.1`、源码版麦麦 `1.4.3`。先让鲸鲸单独成功监听/发送微信，让麦麦成功启动、创建一个机器人并能打开 WebUI。不要把任何已有用户的 `instance` 或 `data` 复制进本仓库。

下文 `C:\Apps\…` 和 `YOUR_BOT_DIRECTORY` 都是示例，必须替换为你自己的路径。麦麦实例目录是包含 `host/`、`bots/` 的目录；机器人目录名可在 `bots/` 下查看，不能随便选择第一个。Python 指麦麦已有环境的解释器，不是鲸鲸内置 Python。

## 1. 下载独立仓库，准备转发环境

```powershell
git clone https://github.com/Ts1ngyun/WhaleGirl-MaiBot-Bridge.git
cd WhaleGirl-MaiBot-Bridge
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

不需要 Fork 上游，不要将本仓库复制覆盖整个鲸鲸或麦麦目录。运行环境留在本机，被 `.gitignore` 排除。

## 2. 预览安装

```powershell
.\.venv\Scripts\python.exe install.py --whale-root "C:\Apps\WhaleGirl" --maibot-root "C:\Apps\MaiBot" --instance-root "C:\Apps\MaiBot-instance" --bot-id "YOUR_BOT_DIRECTORY" --maibot-python "C:\Apps\MaiBot\.venv\Scripts\python.exe"
```

默认只列出目标文件，不修改任何东西。不匹配的版本、缺失依赖、未初始化的机器人、已链接到其他桥接目录都会拒绝。若同版本安装包有自行修改，先手工对比下表文件；版本号相同不保证内容相同。

## 3. 备份并安装

先停止麦麦、断开微信桥接并完全退出鲸鲸（Node 路由也需要重载）。将上条命令末尾加 `--apply`。

安装器会先把全部将修改的文件备份到本仓库 `backups/<时间>/`，再执行以下操作；中途写入失败会尝试恢复。备份可能包含本机路径或配置，**不能上传或粘贴给他人**。

| 本仓库文件 | 安装目标/操作 |
| --- | --- |
| `whale_patch/bridge/*.py` | 复制到鲸鲸 `bridge/`，其中已有同名文件将被替换 |
| `whale_patch/routes/maibot-link.js` | 复制到鲸鲸 `src/http/routes/` |
| 路由注册 | 在鲸鲸 `src/http/routes/index.js` 的 `const modules = [` 后最先加入 `require('./maibot-link'),`，只加一次 |
| `plugin/plugin.py`、`plugin/_manifest.json` | 复制到选定麦麦机器人 `plugins/whale_text/` |
| 插件配置 | 仅在不存在时创建 `config.toml`，设置 `[plugin] enabled = true` |
| 本机路径 | 创建本仓库 `installation.local.json`，保存鲸鲸、麦麦、实例、Python 路径 |
| 关联文件 | 创建鲸鲸 `data/maibot-link.json`，保存 `tokenFile` 和 `bridgeRoot` 本机路径 |
| 桥接数据 | 首次生成 `data/token`、`data/settings.json`、`data/image-policy.json` |

不用一份份手动覆盖，但表格也给出了人工部署位置。选择手工部署时同样必须备份、使用随机 Token，并建立上述配置；不能只复制插件就启动。

如果原来有同名麦麦插件配置，安装器保留它。请检查其 `enabled` 状态；不要为了让插件加载而禁用麦麦的权限管理。插件需要 manifest 列出的 `gateway.route_message`、`gateway.update_state`、`chat.open_session`、`maisaka.context.append` 能力。

## 4. 配置模型和微信

在麦麦 WebUI 配置自己的模型供应商与任务分配：聊天/规划、视觉模型、Embedding 等按需要分别设置。Key 不从鲸鲸自动复制；不要运行旧工程的自动迁移脚本。图片理解需要麦麦的 VLM，Embedding 警告应在麦麦模型任务分配中解决。

鲸鲸保留原本微信账号和允许收发会话配置。本插件仍检查鲸鲸发送权限，不会通过麦麦跳过。进入桥接的聊天调用走麦麦；鲸鲸已有聊天 Key 不删除，也不作为失败兜底。

可选 API 语音：在鲸鲸填写语音 API 地址、Key、模型、音色并开启相应会话类型。安装 VB-CABLE，选择向 `CABLE Input` 播放，微信录音使用 Windows 的 `CABLE Output`。按鲸鲸已有方式配置/核实录音快捷键。本桥接会在录音前将 Windows 三种默认录音角色都切到 `CABLE Output (VB-Audio Virtual Cable)`；切换失败则取消，不会自动恢复真实麦克风。没有 `/v` 不会调用麦麦语音工具。

## 5. 启动、使用、关闭

双击 `Start-Whale-Mai.cmd`。它启动转发服务及选定麦麦实例，打开鲸鲸启动器；你在鲸鲸登录并连接微信。启动器不会自动替你操作微信登录。

若报 18787 被其他服务占用，应先停止旧桥接；不能同时运行旧工程与发布副本。当前发布版也固定使用 18788 提供本机远程网页，不能多个实例并行共用这些端口。麦麦 WebUI 端口使用其已有实例配置。

`Image-Settings.cmd` 可选择自动识图、请求识图、关闭识图。改模式即时生效。收到的表情包不识别；麦麦主动发送表情包需要鲸鲸表情包开关开启，并通过前台发送校验。

双击 `Stop-Mai.cmd`，停止麦麦、取消队列及语音授权、关闭远程隧道。转发服务空闲保留，鲸鲸和微信仍由你手动关闭；脚本不会结束其他 Python、鲸鲸或微信进程。移动本仓库目录前请停止并重新安装更新关联路径。

## 6. 手机远程控制（可选）

本机访问 `http://127.0.0.1:18788`，必须填写 `data/remote-key.txt` 中的独立 Key。首次启动会生成它，不能用模型 API Key 代替。

需要临时 HTTPS 时，从 [Cloudflare 官方发行页](https://github.com/cloudflare/cloudflared/releases) 下载 Windows amd64 程序，核实来源后保存为 `tools/cloudflared.exe`。仓库不附带二进制；没有这个文件时本机网页仍可用。重新执行启动后在 `data/remote-url.txt` 查看临时网址。隧道只公开 18788，不公开 18787。

手机登录后选会话、开启人工接管、填写文字、核对目标并确认。网页不支持任意文件上传或执行命令。关闭接管后后续新消息恢复自动回复。Key 泄露时在本机换成长随机值；服务每次读取，无需把 Key 放进 URL。

## 7. 还原

先用关闭 CMD，断开微信并完全退出鲸鲸。查看安装时输出的备份路径，先预览：

```powershell
.\.venv\Scripts\python.exe restore.py "backups\YOUR_BACKUP_DIRECTORY"
```

确认后加 `--apply`。还原器只还原安装触及的文件；若它们安装后又被修改，会拒绝覆盖，需按备份人工合并。运行时新产生的聊天记录、Key、日志不主动删除。系统麦克风选项也不恢复。

还原后重新启动原版程序。不要把完整备份上传到 Issue。

## 8. 排错

- 麦麦在线但微信没反应：检查鲸鲸桥接、允许会话、麦麦插件状态，确认完整重启鲸鲸加载 Node 路由。
- 图片/Embedding 不可用：检查麦麦相关模型任务；不会回退到鲸鲸模型。
- 表情发送失败：检查鲸鲸表情开关、可交互桌面和目标输入框；不确定发送若留有草稿，手动清空后再处理，不能自动重复。
- 语音失败：检查鲸鲸语音 API、设备名称、播放设备和录音快捷键；勿用真实麦克风录到环境声音测试。
- 临时网址不通：本机网页先验通，再检查 `data/remote_tunnel.log`；网络环境与隧道服务可能影响可达性。
- 分享错误时只提供脱敏的错误类型与版本，禁止提交完整 `data/`、`instance/` 或日志。
