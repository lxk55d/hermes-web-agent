"""
示例3: MCP Server 集成（Python 调用方式）
"""
import asyncio
import json

# 直接启动 MCP Server 的方式
# 推荐配合 Hermes 的 native-mcp 使用
# 配置:
#   mcpServers:
#     hermes-web-agent:
#       command: python
#       args: [-m, hermes_web_agent.mcp.server]

# Python 端以代码方式调用
from hermes_web_agent.mcp.server import WebAgentMCP


async def main():
    agent = WebAgentMCP()

    # 查看状态
    status = await agent.status()
    print("状态:", json.dumps(status, indent=2, ensure_ascii=False))

    # 向 ChatGPT 发消息
    result = await agent.chat(
        llm="chatgpt",
        prompt="用 Python 写一个计算斐波那契数列的函数",
        timeout=60,
    )
    print("\nChatGPT 回复:")
    print(result.get("content", "")[:500])
    print(f"耗时: {result.get('elapsed', 0)}s")

    # 多 LLM 协作
    result = await agent.multi_chat(
        prompt="Python 中 __init__ 和 __new__ 的区别是什么？",
        llms=["chatgpt", "claude"],
        mode="consensus",
    )
    print("\n多 LLM 协作结果:")
    print(result.get("final_output", "")[:500])

    await agent.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
