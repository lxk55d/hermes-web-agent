# Hermes Web Agent 🕸️🤖

> 通过浏览器操控 LLM 网页版完成任务的工具包。**无需 API Key，使用你的订阅账号。**

[![CI](https://github.com/lxk55d/hermes-web-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/lxk55d/hermes-web-agent/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![GitHub release](https://img.shields.io/github/v/release/lxk55d/hermes-web-agent)](https://github.com/lxk55d/hermes-web-agent/releases)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-6C47FF)](https://modelcontextprotocol.io)

让 AI Agent（Hermes / Claude Code / Cursor / 任何 MCP 客户端）通过浏览器自动化登录并操控 **ChatGPT、Claude、DeepSeek、Gemini、Grok、Perplexity、Copilot** 的网页版，实现：

- 🎯 **免 API 费用** — 用 Plus/Pro 订阅额度，不用按 token 计费
- 🔄 **多 LLM 协作** — 流水线 / 共识 / 圆桌模式，发挥各自优势
- 🔌 **MCP 协议集成** — 作为 MCP Server，"一键"接入 Hermes / Claude Desktop / Cursor
- 🛡️ **反检测保护** — 随机化浏览器指纹，避免被封号
- 🍪 **Cookie 持久化** — 一次登录，持续使用

---

## 快速开始

### 1️⃣ 安装

```bash
# 克隆项目
git clone https://github.com/hermes-web-agent/hermes-web-agent.git
cd hermes-web-agent

# 安装依赖
pip install -e .
pip install playwright
playwright install chromium

# （可选）MCP 集成支持
pip install mcp
```

### 2️⃣ 设置凭证

```bash
# 推荐：环境变量方式
export CHATGPT_EMAIL="your@email.com"
export CHATGPT_PASSWORD="***"
export CLAUDE_EMAIL="your@email.com"
export CLAUDE_PASSWORD="***"
export DEEPSEEK_EMAIL="your@email.com"
export DEEPSEEK_PASSWORD="***"
```

### 3️⃣ 启动 MCP Server

```bash
hermes-web-agent mcp
```

然后在 Hermes 的 `config.yaml` 中加载：

```yaml
mcpServers:
  hermes-web-agent:
    command: hermes-web-agent
    args: [mcp]
```

### 🔗 连接 Windows Chrome（WSL2 CDP 模式）

在 WSL2 中，可连接 Windows 宿主机的 Chrome 浏览器，避免 Linux Chromium 的兼容性问题。

```bash
# 1. Windows 上启动带远程调试的 Chrome
#    使用 windows-chrome-devtools-mcp 项目脚本：
#    https://github.com/lxk55d/windows-chrome-devtools-mcp

# 2. WSL 中设置环境变量并启动
export HERMES_WEB_CDP_URL=http://127.0.0.1:9922
hermes-web-agent mcp
```

也可在代码中指定：

```python
engine = await create_engine(cdp_url="http://127.0.0.1:9922")
```

CDP 模式的优点：
- ✅ 使用真实 Windows Chrome（含 Cookie、扩展、登录态）
- ✅ 无需 `playwright install chromium`
- ✅ 更好的反隐身能力（真实浏览器指纹）
- ✅ 支持 `windows-chrome-devtools-mcp` 的 NAT 网络转接

### 4️⃣ 调用工具

Hermes 将自动发现以下工具：

| 工具 | 描述 |
|------|------|
| `web_agent_chat` | 向指定 LLM 发送消息（chatgpt/claude/deepseek/gemini/grok/perplexity/copilot） |
| `web_agent_multi_chat` | 多个 LLM 协作（pipeline/consensus/roundtable） |
| `web_agent_screenshot` | 截取浏览器画面 |
| `web_agent_status` | 查看连接状态 |
| `web_agent_new_chat` | 开启新对话 |

---

## ✨ 核心功能

### 单 LLM 对话

```python
from hermes_web_agent.bridges.chatgpt import ChatGPTBridge
from hermes_web_agent.core.browser import create_engine

engine = await create_engine(headless=False)
bridge = ChatGPTBridge(engine, session_mgr)
await bridge.ensure_login()

response = await bridge.send_message("用 Python 写一个快速排序")
print(response.content)  # ChatGPT 的回复
```

### 🚀 多 LLM 协作

**流水线模式** — 先后接力：ChatGPT 写代码 → Claude 审查 → DeepSeek 优化

```python
task = Task(
    prompt="用 Python 实现一个 HTTP 服务器",
    bridges=[chatgpt, claude, deepseek],
    mode=CollaborationMode.PIPELINE,
)
result = await orchestrator.execute(task)
```

**共识模式** — 同时回答取最佳

```python
task = Task(
    prompt="解释量子纠缠",
    bridges=[chatgpt, claude, deepseek],
    mode=CollaborationMode.CONSENSUS,
)
```

**圆桌模式** — 多轮讨论直到达成一致

```python
task = Task(
    prompt="设计一个微服务架构方案",
    bridges=[chatgpt, claude, deepseek],
    mode=CollaborationMode.ROUNDTABLE,
)
```

---

## 🏗️ 架构

```
hermes-web-agent/
├── hermes_web_agent/
│   ├── core/
│   │   ├── browser.py       # Playwright 浏览器引擎（反检测、Cookie持久化）
│   │   ├── session.py       # 会话管理（凭证、Cookie）
│   │   └── orchestrator.py  # 任务编排器（多LLM协作）
│   ├── bridges/
│   │   ├── base.py          # 桥接器基类
│   │   ├── chatgpt.py       # ChatGPT 网页版桥接
│   │   ├── claude.py        # Claude 网页版桥接
│   │   ├── deepseek.py      # DeepSeek 网页版桥接
│   │   ├── gemini.py        # Gemini 网页版桥接
│   │   ├── grok.py          # Grok 网页版桥接
│   │   ├── perplexity.py    # Perplexity 网页版桥接
│   │   └── copilot.py       # Copilot 网页版桥接
│   ├── mcp/
│   │   └── server.py        # MCP Server（工具注册）
│   └── utils/
│       ├── anti_detection.py # 反检测策略引擎（Cloudflare/reCAPTCHA）
│       ├── fingerprint.py   # 浏览器指纹随机化（UA/Canvas/WebGL/WebRTC）
│       ├── human_like.py    # 人类行为模拟（打字/鼠标/滚动）
│       ├── proxy_rotation.py# 代理轮换系统（多代理池/健康检查）
│       └── cookie_pool.py   # Cookie池（多站点管理/自动过期持久化）
├── skill/
│   └── SKILL.md             # Hermes Skill 定义
└── tests/
    ├── conftest.py           # Mock Playwright 测试夹具
    ├── test_bridges.py       # 桥接器基类测试
    ├── test_fingerprint.py   # 指纹随机化测试
    ├── test_human_like.py    # 行为模拟测试
    ├── test_anti_detection.py# 反检测策略测试
    ├── test_orchestrator.py  # 编排器测试
    └── integration/          # 集成测试（需要真实浏览器）
```

---

## 🔧 原理

```
你的 AI Agent (Hermes/Claude Code/Cursor)
        │
        ▼  MCP 协议
Hermes Web Agent (MCP Server)
        │
        ├── Playwright → Chrome 浏览器 (headless / Linux Chromium)
        │                    ├─ chatgpt.com   ──→ ChatGPT Plus/Pro
        │                    ├─ claude.ai     ──→ Claude Pro/Max
        │                    ├─ chat.deepseek.com ──→ DeepSeek
        │                    ├─ gemini.google.com ──→ Gemini Advanced
        │                    ├─ x.ai/i/grok   ──→ Grok
        │                    ├─ perplexity.ai ──→ Perplexity Pro
        │                    └─ copilot.microsoft.com ──→ GitHub Copilot
        │
        └── Playwright → CDP 连接 → Windows Chrome (宿主机, WSL2)
                             （通过 HERMES_WEB_CDP_URL 指定）
```

---

## ⚠️ 注意事项

1. **带验证码的网站**：首次登录可能需要手动验证（CAPTCHA/2FA），登录成功后 Cookie 会持久化
2. **保持账号活跃**：长期不用的账号可能被要求重新验证
3. **不要高频率调用**：过快请求可能触发风控（建议间隔 2-5 秒）
4. **headless 模式**：生产环境建议 `headless=True`；首次使用建议 `headless=False` 观察登录过程

---

## 🤝 贡献

欢迎提交 PR 和 Issue！目标路线图：

- [x] Gemini / Grok / Perplexity / Copilot 网页版桥接
- [x] 浏览器指纹随机化（UA/Canvas/WebGL/WebRTC）
- [x] 代理轮换系统（多代理池 / 健康检查）
- [x] Cookie 池持久化系统
- [ ] Docker 容器化部署
- [ ] Web UI 管理界面
- [ ] 自动 CAPTCHA 识别（如 2Captcha/BestCaptchaSolver）
- [ ] 浏览器池（多实例负载均衡）

---

## 📄 许可证

MIT License — 详见 [LICENSE](LICENSE)。
