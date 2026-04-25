"""
Copilot 网页版桥接 (copilot.microsoft.com)

登录流程：
  1. 访问 copilot.microsoft.com
  2. Microsoft 账户登录
  3. 输入 email → Next
  4. 输入 password → Sign in

对话流程：
  1. 在 textarea 输入文本
  2. 点击发送按钮
  3. 等待思考完成（Copilot 可能显示"思考中...")
  4. 读取回复内容
"""
import asyncio
import random
import time

from ..core.browser import BrowserEngine
from ..core.session import SessionManager, LLMSite
from .base import BaseBridge, LLMResponse


COPILOT_LOGIN = {
    "email_input": 'input[type="email"]',
    "password_input": 'input[type="password"]',
    "next_btn": 'input[type="submit"][value*="Next"], button:has-text("Next")',
    "signin_btn": 'input[type="submit"][value*="Sign in"], button:has-text("Sign in")',
}

COPILOT_CHAT = {
    "textarea": 'textarea, #userInput, div[contenteditable="true"][role="textbox"]',
    "send_button": 'button[aria-label*="Submit"], button[aria-label*="Send"], button[aria-label*="发送"]',
    "stop_button": 'button[aria-label*="Stop"], button[aria-label*="停止"]',
    "response": '.response-message-content, .message-content, .prose, .ac-textBlock',
    "new_chat_btn": 'button:has-text("New topic"), button:has-text("新对话"), a[href="/"]',
    "thinking_indicator": '[aria-label*="Thinking"], [aria-label*="思考"], .thinking, .typing-indicator',
}


class CopilotBridge(BaseBridge):
    """Copilot 网页版桥接"""

    def __init__(
        self,
        engine: BrowserEngine,
        session_mgr: SessionManager,
        headless: bool = False,
    ):
        super().__init__(engine, session_mgr, LLMSite.copilot(), headless=headless)

    async def _check_login_status(self) -> bool:
        """检查是否已登录"""
        try:
            current_url = await self._page.evaluate("window.location.href")
            if "login" in current_url or "live.com" in current_url:
                return False
            # 登录后能看到输入框
            textarea = await self._page.query_selector(COPILOT_CHAT["textarea"])
            return textarea is not None
        except Exception:
            return False

    async def _perform_login(self, email: str, password: str) -> bool:
        """执行 Microsoft 账户登录"""
        try:
            await asyncio.sleep(2)

            # 输入 email
            email_input = await self._page.wait_for_selector(
                COPILOT_LOGIN["email_input"], timeout=15000
            )
            if not email_input:
                # 可能已经在 Copilot 页面，检查是否有登录按钮
                login_btn = await self._page.query_selector(
                    'button:has-text("Sign in"), a:has-text("Sign in")'
                )
                if login_btn:
                    await login_btn.click()
                    await asyncio.sleep(2)
                    email_input = await self._page.wait_for_selector(
                        COPILOT_LOGIN["email_input"], timeout=15000
                    )
                    if not email_input:
                        raise Exception("找不到 email 输入框")
                else:
                    raise Exception("找不到 email 输入框")

            await self.engine.type_text(COPILOT_LOGIN["email_input"], email)
            await asyncio.sleep(0.5)

            # 点击 Next
            next_btn = await self._page.query_selector(COPILOT_LOGIN["next_btn"])
            if next_btn:
                await next_btn.click()
            else:
                # 尝试 #idSIButton9 (Microsoft 登录通用按钮)
                ms_btn = await self._page.query_selector('#idSIButton9')
                if ms_btn:
                    await ms_btn.click()
            await asyncio.sleep(2)
            await self.engine.wait_for_navigation(timeout=20000)

            # 输入 password
            pwd_input = await self._page.wait_for_selector(
                COPILOT_LOGIN["password_input"], timeout=15000
            )
            if not pwd_input:
                raise Exception("找不到 password 输入框")

            await self.engine.type_text(COPILOT_LOGIN["password_input"], password)
            await asyncio.sleep(0.5)

            # 点击 Sign in
            signin_btn = await self._page.query_selector(COPILOT_LOGIN["signin_btn"])
            if signin_btn:
                await signin_btn.click()
            else:
                ms_btn = await self._page.query_selector('#idSIButton9')
                if ms_btn:
                    await ms_btn.click()
            await asyncio.sleep(3)
            await self.engine.wait_for_navigation(timeout=30000)

            # 处理"是否保持登录"的对话框
            stay_signed_in = await self._page.query_selector(
                '#idBtn_Back, input[value="No"], button:has-text("No")'
            )
            if stay_signed_in:
                await stay_signed_in.click()
                await asyncio.sleep(2)
                await self.engine.wait_for_navigation(timeout=15000)

            # 保存 Cookie
            if self._page and self._page.context:
                cookies = await self._page.context.cookies()
                self.session_mgr.save_cookies(self.site.name, cookies)

            # 验证登录
            self._logged_in = await self._check_login_status()
            if not self._logged_in:
                print("[Copilot] 登录可能需要手动验证")
                for i in range(30):
                    if await self._check_login_status():
                        self._logged_in = True
                        return True
                    await asyncio.sleep(1)
                return False

            return True

        except Exception as e:
            print(f"[Copilot] 登录失败: {e}")
            return False

    async def send_message(self, prompt: str, timeout: int = 180) -> LLMResponse:
        """
        发送消息并等待 Copilot 回复

        Copilot 有时需要较长时间思考（搜索+生成），timeout 默认 180 秒
        """
        if not self._page:
            raise RuntimeError("浏览器未启动，请先调用 ensure_login()")

        start_time = time.time()
        response = LLMResponse()

        try:
            # 确保在 Copilot 对话页
            current_url = await self._page.evaluate("window.location.href")
            if "copilot.microsoft.com" not in current_url:
                await self.engine.navigate(self.site.home_url)
                await asyncio.sleep(2)

            # 找到输入框
            textarea = await self._page.wait_for_selector(
                COPILOT_CHAT["textarea"], timeout=15000
            )
            if not textarea:
                raise Exception("找不到 Copilot 输入框")

            await textarea.click()
            await asyncio.sleep(0.3)

            # 输入 prompt
            await self.engine.type_text(COPILOT_CHAT["textarea"], prompt)
            await asyncio.sleep(random.uniform(0.3, 0.8))

            # 发送
            send_btn = await self._page.query_selector(COPILOT_CHAT["send_button"])
            if send_btn:
                await send_btn.click()
            else:
                await textarea.press("Enter")

            # 等待思考完成 — 监控停止按钮或思考指示器消失
            await self._wait_for_stream_complete(
                COPILOT_CHAT["stop_button"], timeout=timeout, poll_interval=1.0
            )

            # 额外等待渲染
            await asyncio.sleep(1)

            # 收集回复
            response_text = await self._page.evaluate("""
                () => {
                    const selectors = [
                        '.response-message-content',
                        '.message-content',
                        '.prose',
                        '.ac-textBlock',
                    ];
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
            new_chat = await self._page.query_selector(COPILOT_CHAT["new_chat_btn"])
            if new_chat:
                await new_chat.click()
                await asyncio.sleep(2)
                return True
            await self.engine.navigate("https://copilot.microsoft.com")
            await asyncio.sleep(2)
            return True
        except Exception:
            return False
