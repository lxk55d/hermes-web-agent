---
name: hermes-web-agent
description: 通过浏览器操控 LLM 网页版（ChatGPT/Claude/DeepSeek）完成任务。无需 API Key，使用订阅账号。支持 MCP 集成和多 LLM 协作。
allowed-tools: Bash(hermes-web-agent:*), Bash(*)
hidden: false
---

# hermes-web-agent

通过浏览器操控 LLM 网页版的工具包。使用 Playwright 自动化浏览器登录并操作 ChatGPT/Claude/DeepSeek 的网页版，让 AI Agent 能直接调用这些 LLM。

## 安装

```bash
# 安装项目
pip install -e /path/to/hermes-web-agent

# 安装 Playwright 浏览器
playwright install chromium

# （可选）安装 MCP 支持
pip install mcp
```

## 设置凭证

推荐使用环境变量:

```bash
# ChatGPT 账号
export CHATGPT_EMAIL="your@email.com"
export CHATGPT_PASSWORD="your-password"

# Claude 账号
export CLAUDE_EMAIL="your@email.com"
export CLAUDE_PASSWORD="your-password"

# DeepSeek 账号
export DEEPSEEK_EMAIL="your@email.com"
export DEEPSEEK_PASSWORD="your-password"
```

## 使用方式

### 方式1: MCP Server（推荐 - 集成到 Hermes）

```yaml
# ~/.hermes/config.yaml 的 mcpServers 部分
mcpServers:
  hermes-web-agent:
    command: hermes-web-agent
    args: [mcp]
```

然后 Hermes 就能直接调用 `web_agent_chat`、`web_agent_multi_chat` 等工具。

### 方式2: 命令行对话

```bash
# 启动 MCP Server
hermes-web-agent mcp

# 命令行对话
hermes-web-agent chat chatgpt "你好，请介绍一下自己"

# 交互模式
hermes-web-agent chat claude

# 查看状态
hermes-web-agent status
```

### 方式3: Python API

```python
from hermes_web_agent.core.browser import create_engine
from hermes_web_agent.core.session import SessionManager
from hermes_web_agent.bridges.chatgpt import ChatGPTBridge

# 创建引擎和桥接器
engine = await create_engine(headless=False, session_name="chatgpt")
session_mgr = SessionManager()
session_mgr.set_credential("chatgpt", "you@email.com", "password")

bridge = ChatGPTBridge(engine, session_mgr, headless=False)
await bridge.ensure_login()

# 对话
response = await bridge.send_message("用 Python 写一个快速排序")
print(response.content)
```

## 功能

| 功能 | 描述 |
|------|------|
| 单 LLM 对话 | 向 ChatGPT/Claude/DeepSeek 发送消息 |
| 多 LLM 协作 | 流水线/共识/圆桌模式 |
| Cookie 持久化 | 一次登录持续使用 |
| 反检测 | 随机化指纹，避免封号 |
| 会话管理 | 新建对话、保持上下文、查看历史 |
