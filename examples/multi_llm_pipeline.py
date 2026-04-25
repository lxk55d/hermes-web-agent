"""
示例2: 多 LLM 协作 — 流水线模式

流程: ChatGPT 写代码 → Claude 审查 → DeepSeek 优化
"""
import asyncio
import os

from hermes_web_agent.core.browser import BrowserEngine, BrowserConfig
from hermes_web_agent.core.session import SessionManager
from hermes_web_agent.bridges.chatgpt import ChatGPTBridge
from hermes_web_agent.bridges.claude import ClaudeBridge
from hermes_web_agent.bridges.deepseek import DeepSeekBridge
from hermes_web_agent.core.orchestrator import Orchestrator, Task, CollaborationMode


async def on_partial(info):
    """部分结果回调"""
    print(f"\n--- 阶段 {info['stage'] + 1}: {info['bridge']} 完成 ---")
    print(f"   回复长度: {len(info['response'].content)} 字符")
    print(f"   耗时: {info['response'].elapsed_seconds:.1f}s")


async def main():
    # 设置凭证
    session_mgr = SessionManager()

    # 检查是否有凭证
    if not session_mgr.has_credential("chatgpt"):
        session_mgr.set_credential(
            "chatgpt",
            os.environ.get("CHATGPT_EMAIL", ""),
            os.environ.get("CHATGPT_PASSWORD", ""),
        )
    if not session_mgr.has_credential("claude"):
        session_mgr.set_credential(
            "claude",
            os.environ.get("CLAUDE_EMAIL", ""),
            os.environ.get("CLAUDE_PASSWORD", ""),
        )
    if not session_mgr.has_credential("deepseek"):
        session_mgr.set_credential(
            "deepseek",
            os.environ.get("DEEPSEEK_EMAIL", ""),
            os.environ.get("DEEPSEEK_PASSWORD", ""),
        )

    # 共享浏览器引擎
    engine = BrowserEngine(BrowserConfig.create_random(headless=True))

    # 创建桥接器
    bridges = [
        ChatGPTBridge(engine, session_mgr),
        ClaudeBridge(engine, session_mgr),
        DeepSeekBridge(engine, session_mgr),
    ]

    # 确保全部登录
    for b in bridges:
        ok = await b.ensure_login()
        print(f"{'✅' if ok else '❌'} {b.name} {'已登录' if ok else '登录失败'}")

    if not all(b._logged_in for b in bridges):
        print("⚠️ 部分 LLM 未登录，将跳过")

    # 创建编排器
    orchestrator = Orchestrator()
    for b in bridges:
        orchestrator.register_bridge(b.name, b)

    # 流水线任务
    task = Task(
        prompt=(
            "用 Python 写一个股票数据获取和分析工具，"
            "支持从 tushare 获取日线数据，计算 MA5/MA10/MA20 均线，"
            "并输出买入/卖出信号。包含详细的注释。"
        ),
        bridges=bridges,
        mode=CollaborationMode.PIPELINE,
        on_partial=on_partial,
        timeout=180,
    )

    print("\n🚀 开始流水线任务: ChatGPT → Claude → DeepSeek\n")
    result = await orchestrator.execute(task)

    print("\n" + "=" * 50)
    print("  最终输出")
    print("=" * 50)
    print(result.final_output)
    print(f"\n⏱ 总耗时: {result.elapsed_seconds:.1f}s")
    print(f"✅ 成功: {result.success}")

    # 清理
    await engine.close()


if __name__ == "__main__":
    asyncio.run(main())
