"""
MCP Server — 让 Hermes / Claude Desktop / Cursor 通过 MCP 协议调用

MCP (Model Context Protocol) 定义了标准化的工具调用接口。
本模块将 hermes-web-agent 的所有功能注册为 MCP 工具。

暴露的工具列表：
  1. web_agent_chat           — 向指定 LLM 发送消息
  2. web_agent_multi_chat     — 多个 LLM 协作（流水线/共识模式）
  3. web_agent_screenshot     — 截取浏览器当前画面
  4. web_agent_status         — 查看当前连接状态
  5. web_agent_new_chat       — 开启新对话
  6. web_agent_recover        — 恢复异常连接

使用方式：
  - Hermes: native-mcp 加载
  - Claude Desktop: mcpServers 配置
  - 命令行: python -m hermes_web_agent.mcp.server
"""
import asyncio
import json
import os
import sys
from typing import Any, Dict, List, Optional

# ── 延迟导入 MCP ─────────────────────────────
try:
    from mcp.server import Server, NotificationOptions
    from mcp.server.models import InitializationOptions
    import mcp.server.stdio
    import mcp.types as types
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

from ..core.browser import BrowserEngine
from ..core.session import SessionManager
from ..core.orchestrator import Orchestrator, Task, CollaborationMode
from ..bridges.chatgpt import ChatGPTBridge
from ..bridges.claude import ClaudeBridge
from ..bridges.deepseek import DeepSeekBridge


class WebAgentMCP:
    """
    MCP 服务端 — 管理浏览器引擎和所有桥接器
    
    生命周期：
      1. 启动时自动创建 SessionManager（从环境变量加载凭证）
      2. 首次调用工具时惰性创建 BrowserEngine
      3. 所有桥接器共享同一个浏览器引擎
    """

    def __init__(self):
        self.session_mgr = SessionManager()
        self.engine: Optional[BrowserEngine] = None
        self.bridges: Dict[str, Any] = {}
        self.orchestrator = Orchestrator()

    async def get_engine(self) -> BrowserEngine:
        """获取或创建浏览器引擎"""
        if not self.engine:
            self.engine = BrowserEngine()
            # 从环境变量读取代理配置
            proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
            if proxy:
                self.engine.config.proxy = proxy
        return self.engine

    async def get_bridge(self, name: str) -> Any:
        """获取或创建 LLM 桥接器"""
        name = name.lower()
        if name not in self.bridges:
            engine = await self.get_engine()
            headless = os.environ.get("HERMES_WEB_HEADLESS", "true").lower() == "true"

            bridge_map = {
                "chatgpt": ChatGPTBridge,
                "claude": ClaudeBridge,
                "deepseek": DeepSeekBridge,
            }

            if name not in bridge_map:
                raise ValueError(f"不支持的 LLM: {name}。支持: {list(bridge_map.keys())}")

            bridge = bridge_map[name](engine, self.session_mgr, headless=headless)
            await bridge.ensure_login()
            self.bridges[name] = bridge
            self.orchestrator.register_bridge(name, bridge)

        return self.bridges[name]

    async def chat(
        self,
        llm: str,
        prompt: str,
        timeout: int = 120,
        new_conversation: bool = False,
    ) -> Dict[str, Any]:
        """向指定 LLM 发送消息"""
        bridge = await self.get_bridge(llm)

        if new_conversation:
            await bridge.start_new_conversation()

        response = await bridge.send_message(prompt, timeout=timeout)

        return {
            "content": response.content,
            "model": response.model_name,
            "elapsed": round(response.elapsed_seconds, 2),
            "success": response.success,
            "error": response.error,
        }

    async def multi_chat(
        self,
        prompt: str,
        llms: List[str],
        mode: str = "consensus",
        timeout: int = 180,
    ) -> Dict[str, Any]:
        """多个 LLM 协作"""
        bridges = []
        for name in llms:
            bridge = await self.get_bridge(name)
            bridges.append(bridge)

        mode_map = {
            "single": CollaborationMode.SINGLE,
            "pipeline": CollaborationMode.PIPELINE,
            "consensus": CollaborationMode.CONSENSUS,
            "roundtable": CollaborationMode.ROUNDTABLE,
        }
        if mode not in mode_map:
            raise ValueError(f"不支持的协作模式: {mode}")

        task = Task(
            prompt=prompt,
            bridges=bridges,
            mode=mode_map[mode],
            timeout=timeout,
        )

        result = await self.orchestrator.execute(task)

        return {
            "final_output": result.final_output,
            "responses": [
                {
                    "model": r.model_name,
                    "content": r.content,
                    "elapsed": round(r.elapsed_seconds, 2),
                    "success": r.success,
                }
                for r in result.responses
            ],
            "elapsed": round(result.elapsed_seconds, 2),
            "success": result.success,
            "error": result.error,
        }

    async def screenshot(self) -> str:
        """截取当前浏览器画面（返回 base64）"""
        engine = await self.get_engine()
        data = await engine.screenshot()
        import base64
        return base64.b64encode(data).decode()

    async def status(self) -> Dict[str, Any]:
        """查看当前连接状态"""
        bridges_status = {}
        for name, bridge in self.bridges.items():
            bridges_status[name] = {
                "logged_in": bridge._logged_in,
            }

        return {
            "bridges": bridges_status,
            "engine_running": self.engine is not None,
            "credentials": {
                "chatgpt": self.session_mgr.has_credential("chatgpt"),
                "claude": self.session_mgr.has_credential("claude"),
                "deepseek": self.session_mgr.has_credential("deepseek"),
            },
            "cookies": {
                "chatgpt": self.session_mgr.has_valid_cookies("chatgpt"),
                "claude": self.session_mgr.has_valid_cookies("claude"),
                "deepseek": self.session_mgr.has_valid_cookies("deepseek"),
            },
        }

    async def new_chat(self, llm: str) -> bool:
        """开启新对话"""
        bridge = await self.get_bridge(llm)
        return await bridge.start_new_conversation()

    async def cleanup(self):
        """清理资源"""
        for bridge in self.bridges.values():
            try:
                await bridge.close()
            except Exception:
                pass
        self.bridges.clear()
        self.engine = None


# ── 创建 MCP Server 实例 ─────────────────────

web_agent = WebAgentMCP()

if MCP_AVAILABLE:
    server = Server("hermes-web-agent")

    @server.list_tools()
    async def handle_list_tools() -> List[types.Tool]:
        """注册 MCP 工具列表"""
        return [
            types.Tool(
                name="web_agent_chat",
                description="通过浏览器向指定LLM网页版发送消息并获取回复。支持: chatgpt, claude, deepseek",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "llm": {
                            "type": "string",
                            "description": "LLM平台: chatgpt, claude, deepseek",
                            "enum": ["chatgpt", "claude", "deepseek"],
                        },
                        "prompt": {
                            "type": "string",
                            "description": "发送的消息内容",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "最大等待时间(秒)，默认120",
                            "default": 120,
                        },
                        "new_conversation": {
                            "type": "boolean",
                            "description": "是否开启新对话，默认False（保持上下文）",
                            "default": False,
                        },
                    },
                    "required": ["llm", "prompt"],
                },
            ),
            types.Tool(
                name="web_agent_multi_chat",
                description="多个LLM网页版协作完成复杂任务。支持流水线(先后接力)、共识(同时回答取最佳)、圆桌(多轮讨论)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "任务描述",
                        },
                        "llms": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["chatgpt", "claude", "deepseek"]},
                            "description": "参与的LLM列表（按顺序）",
                            "minItems": 1,
                        },
                        "mode": {
                            "type": "string",
                            "description": "协作模式: single(单个), pipeline(流水线), consensus(共识), roundtable(圆桌)",
                            "enum": ["single", "pipeline", "consensus", "roundtable"],
                            "default": "consensus",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "最大等待时间(秒)，默认180",
                            "default": 180,
                        },
                    },
                    "required": ["prompt", "llms"],
                },
            ),
            types.Tool(
                name="web_agent_screenshot",
                description="截取浏览器当前画面（base64图片），配合web_agent_chat查看对话状态",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            types.Tool(
                name="web_agent_status",
                description="查看浏览器引擎和各LLM桥接器的连接状态",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            types.Tool(
                name="web_agent_new_chat",
                description="在指定LLM中开启新对话",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "llm": {
                            "type": "string",
                            "description": "LLM平台: chatgpt, claude, deepseek",
                            "enum": ["chatgpt", "claude", "deepseek"],
                        },
                    },
                    "required": ["llm"],
                },
            ),
        ]

    @server.call_tool()
    async def handle_call_tool(
        name: str, arguments: Optional[Dict[str, Any]] = None
    ) -> List[types.TextContent]:
        """处理 MCP 工具调用"""
        args = arguments or {}

        try:
            if name == "web_agent_chat":
                result = await web_agent.chat(
                    llm=args["llm"],
                    prompt=args["prompt"],
                    timeout=args.get("timeout", 120),
                    new_conversation=args.get("new_conversation", False),
                )
            elif name == "web_agent_multi_chat":
                result = await web_agent.multi_chat(
                    prompt=args["prompt"],
                    llms=args["llms"],
                    mode=args.get("mode", "consensus"),
                    timeout=args.get("timeout", 180),
                )
            elif name == "web_agent_screenshot":
                img_b64 = await web_agent.screenshot()
                return [types.TextContent(
                    type="text",
                    text=img_b64,
                )]
            elif name == "web_agent_status":
                result = await web_agent.status()
            elif name == "web_agent_new_chat":
                success = await web_agent.new_chat(args["llm"])
                result = {"success": success}
            else:
                raise ValueError(f"未知工具: {name}")

            return [types.TextContent(
                type="text",
                text=json.dumps(result, ensure_ascii=False, indent=2),
            )]

        except Exception as e:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": str(e)}, ensure_ascii=False),
            )]

    async def run_server():
        """启动 MCP Server（stdio 模式）"""
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="hermes-web-agent",
                    server_version="0.1.0",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )


# ── CLI 入口 ──────────────────────────────────

def main():
    """命令行入口"""
    if not MCP_AVAILABLE:
        print("错误: 请安装 mcp 包: pip install mcp")
        sys.exit(1)

    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        pass
    finally:
        asyncio.run(web_agent.cleanup())


if __name__ == "__main__":
    main()
