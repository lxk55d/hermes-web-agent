"""
Gemini 网页版桥接 (gemini.google.com)

登录流程（Google OAuth）：
  1. 访问 gemini.google.com/app
  2. 如果未登录，重定向到 Google 登录
  3. 输入 email → 点击 Next
  4. 输入 password → 点击 Next
  5. 可能 2FA 验证

对话流程：
  1. 在 contenteditable div 输入文本
  2. 点击发送按钮
  3. 等待流式回复完成
  4. 读取回复内容
"""
import asyncio
import random
import time

from ..core.browser import BrowserEngine
from ..core.session import SessionManager, LLMSite
from .base import BaseBridge, LLMResponse


GEMINI_LOGIN = {
    "email_input": 'input[type="email"]',
    "password_input": 'input[type="password"]',
    "next_btn": '#identifierNext, #passwordNext',
}

GEMINI_CHAT = {
    "textarea": 'div[contenteditable="true"]',
    "send_button": 'button[aria-label="发送"], button[aria-label="Send"]',
    "stop_button": 'button[aria-label="停止"], button[aria-label="Stop"]',
    "response": '.response-content, .model-response-content, .conversation-turn',
    "new_chat_btn": 'a[href="/app"], button:has-text("New chat")',
}


class GeminiBridge(BaseBridge):
    """Gemini 网页版桥接"""

    def __init__(
        self,
        engine: BrowserEngine,
        session_mgr: SessionManager,
        headless: bool = False,
    ):
        super().__init__(engine, session_mgr, LLMSite.gemini(), headless=headless)

    async def _check_login_status(self) -> bool:
        """检查是否已登录 — Gemini 登录后看到输入框或对话"""
        try:
            current_url = await self._page.evaluate("window.location.href")
            # 如果还在 accounts.google.com 说明未登录
            if "accounts.google.com" in current_url or "signin" in current_url:
                return False
            # Gemini 登录后能看到 contenteditable div
            textarea = await self._page.query_selector(GEMINI_CHAT["textarea"])
            return textarea is not None
        except Exception:
            return False

    async def _perform_login(self, email: str, password: str) -> bool:
        """执行 Google OAuth 登录流程"""
        try:
            await asyncio.sleep(2)

            # 输入 email
            email_input = await self._page.wait_for_selector(
                GEMINI_LOGIN["email_input"], timeout=15000
            )
            if not email_input:
                # 可能已经输入了 email 跳转到密码页
                pwd_input = await self._page.query_selector(GEMINI_LOGIN["password_input"])
                if pwd_input:
                    await self.engine.type_text(GEMINI_LOGIN["password_input"], password)
                    await asyncio.sleep(0.5)
                    await self.engine.click(GEMINI_LOGIN["next_btn"])
                    await asyncio.sleep(3)
                    # 保存 Cookie
                    if self._page and self._page.context:
                        cookies = await self._page.context.cookies()
                        self.session_mgr.save_cookies(self.site.name, cookies)
                    self._logged_in = await self._check_login_status()
                    return self._logged_in
                raise Exception("找不到 email 输入框或 password 输入框")

            await self.engine.type_text(GEMINI_LOGIN["email_input"], email)
            await asyncio.sleep(0.5)

            # 点击 Next
            await self.engine.click(GEMINI_LOGIN["next_btn"])
            await asyncio.sleep(2)
            await self.engine.wait_for_navigation(timeout=20000)

            # 输入 password
            pwd_input = await self._page.wait_for_selector(
                GEMINI_LOGIN["password_input"], timeout=15000
            )
            if not pwd_input:
                raise Exception("找不到 password 输入框")

            await self.engine.type_text(GEMINI_LOGIN["password_input"], password)
            await asyncio.sleep(0.5)

            # 点击 Next
            await self.engine.click(GEMINI_LOGIN["next_btn"])
            await asyncio.sleep(3)
            await self.engine.wait_for_navigation(timeout=30000)

            # 保存 Cookie
            if self._page and self._page.context:
                cookies = await self._page.context.cookies()
                self.session_mgr.save_cookies(self.site.name, cookies)

            # 验证登录成功
            self._logged_in = await self._check_login_status()
            if not self._logged_in:
                # 可能有 2FA 验证
                print("[Gemini] 登录可能需要手动验证（2FA/CAPTCHA）")
                for i in range(30):
                    if await self._check_login_status():
                        self._logged_in = True
                        return True
                    await asyncio.sleep(1)
                return False

            return True

        except Exception as e:
            print(f"[Gemini] 登录失败: {e}")
            return False

    async def send_message(self, prompt: str, timeout: int = 120) -> LLMResponse:
        """
        发送消息并等待 Gemini 回复

        Gemini 使用 contenteditable div 而非 textarea
        """
        if not self._page:
            raise RuntimeError("浏览器未启动，请先调用 ensure_login()")

        start_time = time.time()
        response = LLMResponse()

        try:
            # 确保在 Gemini 对话页
            current_url = await self._page.evaluate("window.location.href")
            if "gemini.google.com/app" not in current_url:
                await self.engine.navigate(self.site.home_url)
                await asyncio.sleep(2)

            # 找到 contenteditable div
            textarea = await self._page.wait_for_selector(
                GEMINI_CHAT["textarea"], timeout=10000
            )
            if not textarea:
                raise Exception("找不到 Gemini 输入框")

            # 输入 prompt
            await textarea.click()
            await asyncio.sleep(0.3)
            await self.engine.type_text(GEMINI_CHAT["textarea"], prompt)
            await asyncio.sleep(random.uniform(0.3, 0.8))

            # 点击发送按钮
            send_btn = await self._page.query_selector(GEMINI_CHAT["send_button"])
            if send_btn:
                await send_btn.click()
            else:
                # 尝试 Enter 键
                await textarea.press("Enter")

            # 等待回复完成
            await self._wait_for_stream_complete(
                GEMINI_CHAT["stop_button"], timeout=timeout
            )

            # 额外等待渲染
            await asyncio.sleep(0.5)

            # 收集回复内容
            response_text = await self._page.evaluate("""
                () => {
                    const containers = document.querySelectorAll('.response-content, .model-response-content');
                    if (containers.length === 0) return '';
                    const last = containers[containers.length - 1];
                    return last.innerText.trim();
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
        """开启新对话 — 导航回 gemini.google.com/app"""
        if not self._page:
            return False
        try:
            await self.engine.navigate("https://gemini.google.com/app")
            await asyncio.sleep(2)
            return True
        except Exception:
            return False
