"""
DeepSeek 网页版桥接

特点：
  - 登录流程类似 ChatGPT（email + password）
  - 对话界面极简，DOM 结构稳定
  - 回复速度快（DeepSeek 性能优势）
  - 支持代码高亮、数学公式渲染
"""
import asyncio
import random
import time
from typing import Optional

from ..core.browser import BrowserEngine
from ..core.session import SessionManager, LLMSite
from .base import BaseBridge, LLMResponse


DEEPSEEK_LOGIN = {
    "email_input": 'input[name="email"]',
    "password_input": 'input[name="password"]',
    "submit_btn": 'button[type="submit"]',
}

DEEPSEEK_CHAT = {
    "textarea": "#chat-input",
    "send_button": '[data-testid="send-button"]',
    "stop_button": '[data-testid="stop-btn"]',
    "response": '.ds-markdown',
    "new_chat_btn": 'button:has-text("New Chat"), a[href="/"]',
}


class DeepSeekBridge(BaseBridge):
    """DeepSeek 网页版桥接"""

    def __init__(
        self,
        engine: BrowserEngine,
        session_mgr: SessionManager,
        headless: bool = False,
    ):
        super().__init__(engine, session_mgr, LLMSite.deepseek(), headless=headless)

    async def _check_login_status(self) -> bool:
        """检查是否已登录"""
        try:
            current_url = await self._page.evaluate("window.location.href")
            if "sign_in" in current_url or "login" in current_url:
                return False
            has_textarea = await self._page.query_selector(DEEPSEEK_CHAT["textarea"])
            return has_textarea is not None
        except Exception:
            return False

    async def _perform_login(self, email: str, password: str) -> bool:
        """执行 DeepSeek 登录"""
        try:
            await asyncio.sleep(2)

            # 输入 email
            email_input = await self._page.wait_for_selector(
                DEEPSEEK_LOGIN["email_input"], timeout=15000
            )
            if not email_input:
                raise Exception("找不到 email 输入框")

            await self.engine.type_text(DEEPSEEK_LOGIN["email_input"], email)
            await asyncio.sleep(0.5)

            # 输入 password
            pwd_input = await self._page.wait_for_selector(
                DEEPSEEK_LOGIN["password_input"], timeout=15000
            )
            if not pwd_input:
                raise Exception("找不到 password 输入框")

            await self.engine.type_text(DEEPSEEK_LOGIN["password_input"], password)
            await asyncio.sleep(0.5)

            # 提交
            await self.engine.click(DEEPSEEK_LOGIN["submit_btn"])

            # 等待登录完成
            await asyncio.sleep(3)
            await self.engine.wait_for_navigation(timeout=20000)

            # 保存 Cookie
            if self._page and self._page.context:
                cookies = await self._page.context.cookies()
                self.session_mgr.save_cookies(self.site.name, cookies)

            self._logged_in = await self._check_login_status()
            return self._logged_in

        except Exception as e:
            print(f"[DeepSeek] 登录失败: {e}")
            return False

    async def send_message(self, prompt: str, timeout: int = 120) -> LLMResponse:
        """发送消息并等待回复"""
        if not self._page:
            raise RuntimeError("浏览器未启动，请先调用 ensure_login()")

        start_time = time.time()
        response = LLMResponse()

        try:
            # 确保在对话页
            current_url = await self._page.evaluate("window.location.href")
            if "/chat" not in current_url:
                await self.engine.navigate(self.site.home_url)
                await asyncio.sleep(2)

            # 输入 prompt
            textarea = await self._page.wait_for_selector(
                DEEPSEEK_CHAT["textarea"], timeout=10000
            )
            if not textarea:
                raise Exception("找不到 DeepSeek 输入框")

            await self.engine.type_text(DEEPSEEK_CHAT["textarea"], prompt)
            await asyncio.sleep(random.uniform(0.3, 0.8))

            # 发送
            send_btn = await self._page.query_selector(DEEPSEEK_CHAT["send_button"])
            if send_btn:
                await send_btn.click()
            else:
                await textarea.press("Enter")

            # 等待回复
            await self._wait_for_stream_complete(
                DEEPSEEK_CHAT["stop_button"], timeout=timeout
            )

            # DeepSeek 回复完成后额外等待渲染
            await asyncio.sleep(0.5)

            # 收集回复
            responses = await self._page.evaluate("""
                () => {
                    const blocks = document.querySelectorAll('.ds-markdown');
                    return Array.from(blocks).map(b => b.innerText.trim()).filter(t => t.length > 0);
                }
            """)

            if responses:
                # 取最后一个完整的回复块
                response.content = responses[-1]
                response.success = True
            else:
                response.content = "(空回复)"
                response.success = False

            response.elapsed_seconds = time.time() - start_time

        except Exception as e:
            response.success = False
            response.error = str(e)
            response.elapsed_seconds = time.time() - start_time

        return response

    async def start_new_conversation(self) -> bool:
        """开启新对话"""
        if not self._page:
            return False
        try:
            new_chat = await self._page.query_selector(DEEPSEEK_CHAT["new_chat_btn"])
            if new_chat:
                await new_chat.click()
                await asyncio.sleep(2)
                return True
            await self.engine.navigate(self.site.home_url)
            await asyncio.sleep(2)
            return True
        except Exception:
            return False
