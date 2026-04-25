"""
Hermes Web Agent CLI

Usage:
  hermes-web-agent mcp              # 启动 MCP Server（供 Hermes/Claude Desktop 加载）
  hermes-web-agent chat [options]   # 命令行直接对话
  hermes-web-agent status           # 查看连接状态
"""
import argparse
import asyncio
import sys

from .mcp.server import main as mcp_main, WebAgentMCP


def main():
    parser = argparse.ArgumentParser(
        description="Hermes Web Agent — 通过浏览器操控 LLM 网页版"
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # MCP Server
    subparsers.add_parser("mcp", help="启动 MCP Server（默认模式）")

    # Chat
    chat_parser = subparsers.add_parser("chat", help="命令行对话")
    chat_parser.add_argument("llm", choices=["chatgpt", "claude", "deepseek"], help="LLM 平台")
    chat_parser.add_argument("prompt", nargs="?", help="消息内容（留空则进入交互模式）")
    chat_parser.add_argument("--timeout", type=int, default=120, help="超时秒数")

    # Status
    subparsers.add_parser("status", help="查看连接状态")

    args = parser.parse_args()

    if not args.command:
        # 默认启动 MCP Server
        mcp_main()
        return

    if args.command == "mcp":
        mcp_main()
        return

    if args.command == "status":
        asyncio.run(_show_status())
        return

    if args.command == "chat":
        asyncio.run(_interactive_chat(args))
        return


async def _show_status():
    agent = WebAgentMCP()
    status = await agent.status()
    print("=" * 40)
    print("  Hermes Web Agent Status")
    print("=" * 40)
    print(f"  引擎: {'运行中' if status['engine_running'] else '未启动'}")
    print()
    print("  凭证:")
    for name, has in status["credentials"].items():
        print(f"    {name}: {'✅' if has else '❌'}")

    print()
    print("  Cookie:")
    for name, valid in status["cookies"].items():
        print(f"    {name}: {'✅ 有效' if valid else '❌ 无效'}")

    print()
    print("  桥接器:")
    for name, info in status["bridges"].items():
        print(f"    {name}: {'✅ 已登录' if info['logged_in'] else '❌ 未登录'}")

    await agent.cleanup()


async def _interactive_chat(args):
    agent = WebAgentMCP()

    try:
        bridge = await agent.get_bridge(args.llm)
        print(f"✅ {args.llm} 已就绪")

        if args.prompt:
            resp = await bridge.send_message(args.prompt, timeout=args.timeout)
            if resp.success:
                print(resp.content)
            else:
                print(f"❌ 错误: {resp.error}")
        else:
            # 交互模式
            print(f"💬 进入 {args.llm} 交互模式 (输入 /quit 退出, /new 新对话)")
            while True:
                try:
                    prompt = input("\n>>> ").strip()
                    if prompt == "/quit":
                        break
                    if prompt == "/new":
                        await bridge.start_new_conversation()
                        print("🔄 已开启新对话")
                        continue
                    if not prompt:
                        continue

                    resp = await bridge.send_message(prompt)
                    if resp.success:
                        print(f"\n{resp.content}")
                        print(f"\n--- ⏱ {resp.elapsed_seconds:.1f}s ---")
                    else:
                        print(f"❌ {resp.error}")
                except KeyboardInterrupt:
                    print("\n再见!")
                    break

    finally:
        await agent.cleanup()


if __name__ == "__main__":
    main()
