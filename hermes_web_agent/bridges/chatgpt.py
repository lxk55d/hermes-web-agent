"""
ChatGPT 网页版桥接

登录流程（2024-2025 版）：
  1. 访问 chat.openai.com/auth/login
  2. 点击 "Log in" 按钮
  3. 输入 email → 点击 Continue
  4. 输入 password → 点击 Continue
  5. 可能重定向到首页（对话列表）

对话流程：
  1. 导航到 chat.openai.com
  2. 点击 textarea 输入 prompt
  3. 点击发送按钮
  4. 等待流式回复完成（停止按钮消失）
  5. 读取回复内容
  6. 支持多轮对话
"""
import asyncio
import random
import re
import time
from typing import Optional

from ..core.browser import BrowserEngine, create_engine
from ..core.session import SessionManager, LLMSite
from .base import BaseBridge, LLMResponse


# ChatGPT 前端 DOM 选择器（自适应多版本）
LOGIN_SELECTORS_V1 = {
    "email_input": 'input[name="email"]',
    "password_input": 'input[name="password"]',
    "continue_btn": 'button[type="submit"]',
    "login_btn": 'button:has-text("Log in")',
}

CHAT_SELECTORS = {
    "textarea": "#prompt-textarea, textarea[placeholder*=\"Send a message\"]",
    "send_button": '[data-testid="send-button"], button[aria-label="Send prompt"]',
    "stop_button": '[data-testid="stop-button"], button[aria-label="Stop streaming"]',
    "response": '[data-testid="conversation-turn-"] .markdown, .prose',
    "new_chat_btn": 'a[href="/"], button:has-text("New chat")',
    "continue_generating": 'button:has-text("Continue generating")',
}


class ChatGPTBridge(BaseBridge):
    """ChatGPT 网页版桥接"""

    def __init__(
        self,
        engine: BrowserEngine,
        session_mgr: SessionManager,
        headless: bool = False,
    ):
        super().__init__(engine, session_mgr, LLMSite.chatgpt(), headless=headless)

    async def _check_login_status(self) -> bool:
        """检查是否已登录 — 看页面是否跳转到了对话页"""
        try:
            current_url = await self._page.evaluate("window.location.href")
            # 如果在登录页，说明未登录
            if "auth" in current_url or "login" in current_url:
                return False
            # 检查是否有 textarea（登录后必有）
            textarea = await self._page.query_selector(CHAT_SELECTORS["textarea"])
            return textarea is not None
        except Exception:
            return False

    async def _perform_login(self, email: str, password: str) -> bool:
        """执行 ChatGPT 登录流程"""
        try:
            # 等待页面加载完成
            await asyncio.sleep(2)

            # 检查是否有 Log in 按钮（新版登录页）
            login_btn = await self._page.query_selector(LOGIN_SELECTORS_V1["login_btn"])
            if login_btn:
                await login_btn.click()
                await asyncio.sleep(2)
                await self.engine.wait_for_navigation()

            # 输入 email
            email_input = await self._page.wait_for_selector(
                LOGIN_SELECTORS_V1["email_input"], timeout=15000
            )
            if not email_input:
                raise Exception("找不到 email 输入框")

            await self.engine.type_text(LOGIN_SELECTORS_V1["email_input"], email)
            await asyncio.sleep(0.5)

            # 点击 Continue
            continue_btn = await self._page.query_selector(LOGIN_SELECTORS_V1["continue_btn"])
            if continue_btn:
                await continue_btn.click()
                await asyncio.sleep(2)

            # 输入 password
            pwd_input = await self._page.wait_for_selector(
                LOGIN_SELECTORS_V1["password_input"], timeout=15000
            )
            if not pwd_input:
                raise Exception("找不到 password 输入框")

            await self.engine.type_text(LOGIN_SELECTORS_V1["password_input"], password)
            await asyncio.sleep(0.5)

            # 提交登录
            submit_btn = await self._page.query_selector(LOGIN_SELECTORS_V1["continue_btn"])
            if submit_btn:
                await submit_btn.click()

            # 等待登录完成（可能重定向回首页）
            await asyncio.sleep(3)
            await self.engine.wait_for_navigation(timeout=20000)

            # 保存 Cookie
            if self._page and self._page.context:
                cookies = await self._page.context.cookies()
                self.session_mgr.save_cookies(self.site.name, cookies)

            # 验证登录成功
            self._logged_in = await self._check_login_status()
            if not self._logged_in:
                # 可能有 CAPTCHA 或 2FA
                print("[ChatGPT] 登录可能需要手动验证（CAPTCHA/2FA）")
                # 给用户 30 秒手动验证
                for i in range(30):
                    if await self._check_login_status():
                        self._logged_in = True
                        return True
                    await asyncio.sleep(1)
                return False

            return True

        except Exception as e:
            print(f"[ChatGPT] 登录失败: {e}")
            return False

    async def send_message(self, prompt: str, timeout: int = 120) -> LLMResponse:
        """
        发送消息并等待回复

        支持：
          - 新建对话（如果是第一轮）
          - 多轮对话（保持上下文）
          - 流式回复等待
          - 自动 Continue generating
        """
        if not self._page:
            raise RuntimeError("浏览器未启动，请先调用 ensure_login()")

        start_time = time.time()
        response = LLMResponse()

        try:
            # 检查是否需要新建对话
            if not await self._page.query_selector(CHAT_SELECTORS["textarea"]):
                # 点击 New chat
                new_chat = await self._page.query_selector(CHAT_SELECTORS["new_chat_btn"])
                if new_chat:
                    await new_chat.click()
                    await asyncio.sleep(2)

            # 找到 textarea 并输入
            textarea = await self._page.wait_for_selector(
                CHAT_SELECTORS["textarea"], timeout=10000
            )
            if not textarea:
                raise Exception("找不到输入框")

            # 输入 prompt（模拟人类打字）
            await self.engine.type_text(CHAT_SELECTORS["textarea"], prompt)
            await asyncio.sleep(random.uniform(0.3, 0.8))

            # 点击发送
            send_btn = await self._page.query_selector(CHAT_SELECTORS["send_button"])
            if send_btn:
                await send_btn.click()
            else:
                # 如果找不到发送按钮，试试 Enter 键
                await textarea.press("Enter")

            # 等待流式回复完成
            await self._wait_for_stream_complete(
                CHAT_SELECTORS["stop_button"], timeout=timeout
            )

            # 检查是否有 Continue generating
            continue_btn = await self._page.query_selector(
                CHAT_SELECTORS["continue_generating"]
            )
            if continue_btn:
                await continue_btn.click()
                await self._wait_for_stream_complete(
                    CHAT_SELECTORS["stop_button"], timeout=timeout
                )

            # 收集回复内容
            response_text = await self._page.evaluate("""
                () => {
                    const turns = document.querySelectorAll('[data-testid="conversation-turn-"]');
                    if (turns.length === 0) return '';
                    const lastTurn = turns[turns.length - 1];
                    const markdown = lastTurn.querySelector('.markdown, .prose');
                    return markdown ? markdown.innerText.trim() : '';
                }
            """)

            response.content = response_text or "(空回复)"
            response.success = bool(response_text)
            response.elapsed_seconds = time.time() - start_time

            # 尝试识别模型
            model_tag = await self._page.evaluate("""
                () => {
                    const tags = document.querySelectorAll('[data-testid="model-tag"]');
                    return tags.length > 0 ? tags[0].innerText.trim() : '';
                }
            """)
            if model_tag:
                response.model_name = model_tag

        except Exception as e:
            response.success = False
            response.error = str(e)
            response.elapsed_seconds = time.time() - start_time

        return response

    async def get_conversation_history(self) -> list:
        """获取当前对话历史"""
        if not self._page:
            return []

        try:
            history = await self._page.evaluate("""
                () => {
                    const turns = document.querySelectorAll('[data-testid="conversation-turn-"]');
                    return Array.from(turns).map(turn => {
                        const role = turn.getAttribute('data-testid')?.includes('user') ? 'user' : 'assistant';
                        const text = turn.querySelector('.markdown, .prose');
                        return {
                            role: role,
                            content: text ? text.innerText.trim() : '',
                            timestamp: turn.getAttribute('data-conversation-turn') || ''
                        };
                    });
                }
            """)
            return history
        except Exception:
            return []

    async def start_new_conversation(self) -> bool:
        """开启新对话"""
        if not self._page:
            return False

        try:
            new_chat = await self._page.query_selector(CHAT_SELECTORS["new_chat_btn"])
            if new_chat:
                await new_chat.click()
                await asyncio.sleep(2)
                return True
            return False
        except Exception:
            return False
