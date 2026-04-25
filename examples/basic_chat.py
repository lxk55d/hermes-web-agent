"""
示例1: 通过 Python API 调用 ChatGPT 网页版
"""
import asyncio
import os

from hermes_web_agent.core.browser import create_engine
from hermes_web_agent.core.session import SessionManager
from hermes_web_agent.bridges.chatgpt import ChatGPTBridge


async def main():
    # 1. 从环境变量读取凭证
    session_mgr = SessionManager()
    email = os.environ.get("CHATGPT_EMAIL") or "your@email.com"
    password = os.environ.get("CHATGPT_PASSWORD") or "your-password"
    session_mgr.set_credential("chatgpt", email, password)

    # 2. 创建浏览器引擎（headless=False 可以看到浏览器窗口）
    engine = await create_engine(headless=False, session_name="chatgpt")

    # 3. 创建桥接器并登录
    bridge = ChatGPTBridge(engine, session_mgr, headless=False)
    logged_in = await bridge.ensure_login()

    if not logged_in:
        print("❌ 登录失败")
        return

    print("✅ 已登录 ChatGPT")

    # 4. 发送消息
    response = await bridge.send_message(
        "用 Python 实现一个简单的 HTTP 服务器，"
        "支持静态文件服务和 404 页面"
    )

    if response.success:
        print("=" * 40)
        print(response.content)
        print("=" * 40)
        print(f"⏱ {response.elapsed_seconds:.1f}s")
    else:
        print(f"❌ {response.error}")

    # 5. 多轮对话（上下文保持）
    response2 = await bridge.send_message("给上面的代码添加日志功能")

    if response2.success:
        print("\n" + "=" * 40)
        print(response2.content)
        print("=" * 40)

    # 6. 清理
    await bridge.close()


if __name__ == "__main__":
    asyncio.run(main())
