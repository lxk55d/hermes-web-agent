"""
Grok 网页版桥接 (grok.com)

登录流程：
  1. 访问 grok.com
  2. 输入 email → Continue
  3. 输入 password → Sign in
  4. 可能 X/Twitter OAuth 跳转

对话流程：
  1. 在 textarea 或 contenteditable div 输入文本
  2. 点击发送按钮
  3. 等待回复
  4. 读取最后回复内容
"""
import asyncio
import random
import time
from typing import Optional

from ..core.browser import BrowserEngine
from ..core.session import SessionManager, LLMSite
from .base import BaseBridge, LLMResponse


GROK_LOGIN = {
    "email_input": 'input[name="email"]',
    "password_input": 'input[name="password"]',
    "submit_btn": 'button[type="submit"]',
}

GROK_CHAT = {
    "textarea": 'textarea[placeholder*="问任何问题"], textarea[placeholder*="Ask"], div[contenteditable="true"]',
    "send_button": 'button[aria-label*="发送"], button[aria-label*="Send"]',
    "stop_button": 'button[aria-label*="停止"], button[aria-label*="Stop"]',
    "response": '.prose, .markdown, .message-content',
    "new_chat_btn": 'a[href="/"], button:has-text("New chat")',
}


class GrokBridge(BaseBridge):
    """Grok 网页版桥接"""

    def __init__(
        self,
        engine: BrowserEngine,
        session_mgr: SessionManager,
        headless: bool = False,
    ):
        super().__init__(engine, session_mgr, LLMSite.grok(), headless=headless)

    async def _check_login_status(self) -> bool:
        """检查是否已登录"""
        try:
            current_url = await self._page.evaluate("window.location.href")
            if "login" in current_url or "auth" in current_url or "i/flow" in current_url:
                return False
            # 登录后能看到输入框
            textarea = await self._page.query_selector(GROK_CHAT["textarea"])
            return textarea is not None
        except Exception:
            return False

    async def _perform_login(self, email: str, password: str) -> bool:
        """执行 Grok 登录流程"""
        try:
            await asyncio.sleep(2)

            # 输入 email
            email_input = await self._page.wait_for_selector(
                GROK_LOGIN["email_input"], timeout=15000
            )
            if not email_input:
                raise Exception("找不到 email 输入框")

            await self.engine.type_text(GROK_LOGIN["email_input"], email)
            await asyncio.sleep(0.5)

            # 点击 Continue / Next
            submit_btn = await self._page.query_selector(GROK_LOGIN["submit_btn"])
            if submit_btn:
                await submit_btn.click()
            await asyncio.sleep(2)
            await self.engine.wait_for_navigation(timeout=20000)

            # 检查是否跳转到 X/Twitter OAuth
            current_url = await self._page.evaluate("window.location.href")
            if "x.com" in current_url or "twitter.com" in current_url or "i/flow" in current_url:
                print("[Grok] 检测到 X/Twitter OAuth 跳转...")
                # 尝试在 Twitter OAuth 页面输入
                tw_email = await self._page.query_selector('input[name="text"], input[type="email"], input[name="session[username_or_email]"]')
                if tw_email:
                    await tw_email.fill("")
                    await self.engine.type_text('input[name="text"], input[type="email"], input[name="session[username_or_email]"]', email)
                    await asyncio.sleep(0.5)
                    next_btn = await self._page.query_selector('button[role="button"]:has-text("Next"), button[type="submit"]')
                    if next_btn:
                        await next_btn.click()
                        await asyncio.sleep(2)

                    tw_pwd = await self._page.query_selector('input[type="password"], input[name="session[password]"]')
                    if tw_pwd:
                        await self.engine.type_text('input[type="password"], input[name="session[password]"]', password)
                        await asyncio.sleep(0.5)
                        login_btn = await self._page.query_selector('button[role="button"]:has-text("Log in"), button[type="submit"]')
                        if login_btn:
                            await login_btn.click()
                            await asyncio.sleep(3)
                            await self.engine.wait_for_navigation(timeout=25000)
            else:
                # 常规登录：输入 password
                pwd_input = await self._page.wait_for_selector(
                    GROK_LOGIN["password_input"], timeout=15000
                )
                if pwd_input:
                    await self.engine.type_text(GROK_LOGIN["password_input"], password)
                    await asyncio.sleep(0.5)

                    # 点击 Sign in
                    await self.engine.click(GROK_LOGIN["submit_btn"])
                    await asyncio.sleep(3)
                    await self.engine.wait_for_navigation(timeout=25000)

            # 保存 Cookie
            if self._page and self._page.context:
                cookies = await self._page.context.cookies()
                self.session_mgr.save_cookies(self.site.name, cookies)

            # 验证登录
            self._logged_in = await self._check_login_status()
            if not self._logged_in:
                print("[Grok] 登录可能需要手动验证")
                for i in range(30):
                    if await self._check_login_status():
                        self._logged_in = True
                        return True
                    await asyncio.sleep(1)
                return False

            return True

        except Exception as e:
            print(f"[Grok] 登录失败: {e}")
            return False

    async def send_message(self, prompt: str, timeout: int = 120) -> LLMResponse:
        """
        发送消息并等待 Grok 回复

        支持 textarea 和 contenteditable div 两种输入方式
        """
        if not self._page:
            raise RuntimeError("浏览器未启动，请先调用 ensure_login()")

        start_time = time.time()
        response = LLMResponse()

        try:
            # 确保在 Grok 对话页
            current_url = await self._page.evaluate("window.location.href")
            if "grok.com" not in current_url:
                await self.engine.navigate(self.site.home_url)
                await asyncio.sleep(2)

            # 找到输入框
            textarea = await self._page.wait_for_selector(
                GROK_CHAT["textarea"], timeout=10000
            )
            if not textarea:
                raise Exception("找不到 Grok 输入框")

            # 点击激活输入框
            await textarea.click()
            await asyncio.sleep(0.3)

            # 输入 prompt
            await self.engine.type_text(GROK_CHAT["textarea"], prompt)
            await asyncio.sleep(random.uniform(0.3, 0.8))

            # 发送
            send_btn = await self._page.query_selector(GROK_CHAT["send_button"])
            if send_btn:
                await send_btn.click()
            else:
                await textarea.press("Enter")

            # 等待回复
            await self._wait_for_stream_complete(
                GROK_CHAT["stop_button"], timeout=timeout
            )

            await asyncio.sleep(0.5)

            # 读取最后回复内容
            response_text = await self._page.evaluate("""
                () => {
                    const selectors = ['.prose', '.markdown', '.message-content'];
                    for (const sel of selectors) {
                        const elements = document.querySelectorAll(sel);
                        if (elements.length > 0) {
                            return elements[elements.length - 1].innerText.trim();
                        }
                    }
                    return '';
                }
            """)

            response.content = response_text or "(空回复)"
            response.success = bool(response_text)
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
            await self.engine.navigate("https://grok.com")
            await asyncio.sleep(2)
            return True
        except Exception:
            return False
