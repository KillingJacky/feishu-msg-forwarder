# Feishu 消息转发器

这是一个基于 Python 的飞书消息转发器，使用用户授权的 `user_access_token` 从源群读取消息，按规则匹配后转发到目标群。

## 核心特性

- **以用户身份发送**：系统基于 OAuth 授权获取 `user_access_token`，转发的消息在目标群默认以你的名义展示，不使用机器人身份。
- **媒体与资源转发**：支持图片 (`image`)、文件 (`file`) 和富文本 (`post`) 的转发。遇到飞书的跨群或权限限制时，系统会自动尝试下载原文件并重新上传，以确保在新群中可见。
- **容错与文本降级**：优先尝试保持原消息样式（`preserve` 模式）。遇到不支持转换的复杂内容（如特定卡片）时，会自动提取正文与发送者信息，并降级为纯文本发送。
- **消息规则过滤**：支持指定多个源群获取消息，并可通过正则表达式、关键字、发送人过滤等规则进行匹配分发。
- **本地去重**：使用本地 SQLite 记录已转发的消息状态，避免重启服务后重复转发。支持 OAuth token 自动刷新。

## 🚀 快速部署

### 1. 飞书开放平台配置（重要）
在飞书开放平台创建企业自建应用后，除了获取 `App ID` 和 `App Secret` 以外，你还必须**配置回调白名单**才能顺利完成最终的个人身份授权：
- 进入**安全设置** -> **重定向 URL**
- 将你配置文件 `config.yaml` 中配置的 `redirect_uri`（如默认的 `http://127.0.0.1:9768/callback`）完整填写在该设定里并保存。

### 2. 准备目录结构与配置

在你打算部署的服务器或电脑上，创建一个空目录并维持如下结构：
```text
.
├── docker-compose.yml
└── data/
    └── config.yaml
```

**`docker-compose.yml` 示例模板：**
```yaml
services:
  forwarder:
    image: killingjacky/feishu-msg-forwarder:latest
    container_name: feishu-msg-forwarder
    restart: unless-stopped
    volumes:
      - ./data:/app/data
```

**`data/config.yaml` 示例：**
请参考项目中的 `config.example.yaml` 格式进行配置。重点补充 `system.app_id`、`system.app_secret` 以及你的转发规则(`rules`)和数据源(`sources`)。

### 3. 交互式授权获取身份 (关键)

由于我们要**完全模拟你本人的身份**去监听和发送消息，首次运行前必须进行 OAuth 授权以生成 Token（生成后会自动保存在 `data/token.json` 中）。根据你的运行环境分类，流程如下：

#### 【场景 A】本机部署（Docker 跑在你当前的个人电脑上）

如果你就在正在看屏幕的这台电脑上玩 Docker：
1. 运行以下命令并**映射 9768 端口**：
```bash
docker run --rm -it -v ${PWD}/data:/app/data -p 9768:9768 killingjacky/feishu-msg-forwarder feishu-msg-forwarder auth login --config-file /app/data/config.yaml
```
2. 随后终端会给出一个授权网址。复制它到浏览器中打开并**同意授权**。
3. 授权通过后，浏览器会自动跳转到本地回调地址。此时你终端里运行的 Docker 进程将**自动侦测**并接管这个跳转信号，为你生成 `data/token.json` 后自行安全退出。（大功告成，直接前往第 4 步！）

#### 【场景 B】远程服务器部署（Docker 跑在没有界面的云主机/NAS上）

由于云端服务器无法被外网浏览器直接访问到内部的 `127.0.0.1`，所以你必须分两步手动介入：

> **第一步：获取授权 URL**
在机器上执行（不再需要映射端口）：
```bash
docker run --rm -it -v ${PWD}/data:/app/data killingjacky/feishu-msg-forwarder feishu-msg-forwarder auth login --config-file /app/data/config.yaml
```
复制终端打印出来的授权网址到你的浏览器上同意授权。此时浏览器跳出授权后必然会展示“无法访问此网站/连接拒绝”的错误页面（这是完全正常的！）。在终端中按 `Ctrl+C` 强行退出阻塞的第一步进程。

> **第二步：手工提取跳转信息换取 Token**
在你的机器终端里直接执行以下交互式命令：
```bash
docker run --rm -it -v ${PWD}/data:/app/data killingjacky/feishu-msg-forwarder feishu-msg-forwarder auth callback --config-file /app/data/config.yaml
```
根据提示，依次完成粘贴操作：
1. 粘贴第一步那个报错崩溃页面里，**地址栏中带有 `code=` 开头的超长完整网址**并回车。
2. 粘贴刚刚第一步终端打印出来让你备用的 **专属 `state` 值**并回车。

屏幕提示“✅ 手动授权成功”后，`token.json` 便会如期而至被创建好了。

### 4. 一键启动服务

只要前序步骤生成了 `data/token.json` 文件即可一键在后台常驻服务：
```bash
docker-compose up -d
```

如需查看这台转发器的后台实时运作情况，随时执行：
```bash
docker-compose logs -f
```

## 配置说明

配置文件结构参考 `config.example.yaml`。

核心字段：

- `sources`: 源群列表
- `rules`: 规则列表
- `target_chat_ids`: 命中后转发到的目标群
- `forward_mode`: `preserve` 或 `text`
- `append_source_info`: 是否在转发内容中附加来源群、发送者、消息类型等说明

关于 `append_source_info`：

- 当值为 `false` 时，`preserve` 模式仍会尽可能通过原样式重建消息机制维持清晰版面。
- 当值为 `true` 时，系统在重建的消息内容开头注入强溯源文本标识，类似：
```text
[来源群: 运维告警群]
[发送者: 监控机器人]
[类型: interactive]
CPU 使用率超过阈值，请及时处理。
```

它的作用主要是：

1. 让目标群的人知道这条消息是从哪个源群转来的
2. 在多源群整合路由转发场景下极大地降低追溯困难
3. 对极度复杂受保护的消息触发降级保护为文本时，提供具有可读性的汇总信息

## ⚠️ 已知限制

- 极为复杂的消息类型（例如特定格式的分享卡片、系统日志或交互式卡片等）在保持原样上可能会受限，这部分都会触发安全机制降级为纯文本转发。
- 系统当前仅基于单用户+本地单实例 SQLite 方式设计，支持容器或后台常驻防抖，不可使用分布式或多实例横向并发扩容（对应到个人消息代理场景下完全够用）。
