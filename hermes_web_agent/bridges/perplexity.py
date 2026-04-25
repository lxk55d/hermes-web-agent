"""
Perplexity 网页版桥接 (perplexity.ai)

登录流程：
  1. 访问 perplexity.ai/auth/login
  2. Google OAuth 为主（也支持 email + password）
  3. 成功后重定向到对话页

对话流程：
  1. 在 textarea 输入文本
  2. 点击发送按钮
  3. 等待流式回复
  4. 收集回复内容
"""
import asyncio
import random
import time

from ..core.browser import BrowserEngine
from ..core.session import SessionManager, LLMSite
from .base import BaseBridge, LLMResponse


PERPLEXITY_LOGIN = {
    "email_input": 'input[name="email"]',
    "password_input": 'input[name="password"]',
    "submit_btn": 'button[type="submit"]',
    "google_oauth_btn": 'button:has-text("Continue with Google"), a:has-text("Google")',
}

PERPLEXITY_CHAT = {
    "textarea": 'textarea[placeholder*="Ask"], textarea[placeholder*="提问"], div[contenteditable="true"]',
    "send_button": 'button[type="submit"], button[aria-label*="Send"]',
    "stop_button": 'button[aria-label*="Stop"], button[aria-label*="停止"]',
    "response": '.prose, .markdown',
    "new_chat_btn": 'a[href="/"], button:has-text("New Thread")',
}


class PerplexityBridge(BaseBridge):
    """Perplexity 网页版桥接"""

    def __init__(
        self,
        engine: BrowserEngine,
        session_mgr: SessionManager,
        headless: bool = False,
    ):
        super().__init__(engine, session_mgr, LLMSite.perplexity(), headless=headless)

    async def _check_login_status(self) -> bool:
        """检查是否已登录"""
        try:
            current_url = await self._page.evaluate("window.location.href")
            if "auth" in current_url or "login" in current_url:
                return False
            # 登录后看到输入框
            textarea = await self._page.query_selector(PERPLEXITY_CHAT["textarea"])
            return textarea is not None
        except Exception:
            return False

    async def _perform_login(self, email: str, password: str) -> bool:
        """执行 Perplexity 登录（优先 Google OAuth）"""
        try:
            await asyncio.sleep(2)

            cred = self.session_mgr.get_credential(self.site.name)
            auth_method = cred.auth_method if cred else "email"

            if auth_method == "google":
                # Google OAuth 方式
                google_btn = await self._page.wait_for_selector(
                    PERPLEXITY_LOGIN["google_oauth_btn"], timeout=15000
                )
                if google_btn:
                    await google_btn.click()
                    await asyncio.sleep(3)

                    # 此时跳转到 Google 登录
                    # 输入 email
                    email_input = await self._page.wait_for_selector(
                        'input[type="email"]', timeout=15000
                    )
                    if email_input:
                        await self.engine.type_text('input[type="email"]', email)
                        await asyncio.sleep(0.5)
                        next_btn = await self._page.query_selector('#identifierNext')
                        if next_btn:
                            await next_btn.click()
                            await asyncio.sleep(2)

                        # 输入 password
                        pwd_input = await self._page.wait_for_selector(
                            'input[type="password"]', timeout=15000
                        )
                        if pwd_input:
                            await self.engine.type_text('input[type="password"]', password)
                            await asyncio.sleep(0.5)
                            pwd_next = await self._page.query_selector('#passwordNext')
                            if pwd_next:
                                await pwd_next.click()
                                await asyncio.sleep(3)

                    await self.engine.wait_for_navigation(timeout=30000)

            else:
                # email + password 方式
                email_input = await self._page.wait_for_selector(
                    PERPLEXITY_LOGIN["email_input"], timeout=15000
                )
                if not email_input:
                    raise Exception("找不到 email 输入框")

                await self.engine.type_text(PERPLEXITY_LOGIN["email_input"], email)
                await asyncio.sleep(0.5)

                # 点击 Continue
                submit_btn = await self._page.query_selector(PERPLEXITY_LOGIN["submit_btn"])
                if submit_btn:
                    await submit_btn.click()
                    await asyncio.sleep(2)

                # 输入 password
                pwd_input = await self._page.wait_for_selector(
                    PERPLEXITY_LOGIN["password_input"], timeout=15000
                )
                if pwd_input:
                    await self.engine.type_text(PERPLEXITY_LOGIN["password_input"], password)
                    await asyncio.sleep(0.5)
                    await self.engine.click(PERPLEXITY_LOGIN["submit_btn"])
                    await asyncio.sleep(3)

                await self.engine.wait_for_navigation(timeout=25000)

            # 保存 Cookie
            if self._page and self._page.context:
                cookies = await self._page.context.cookies()
                self.session_mgr.save_cookies(self.site.name, cookies)

            # 验证登录
            self._logged_in = await self._check_login_status()
            if not self._logged_in:
                print("[Perplexity] 登录可能需要手动验证")
                for i in range(30):
                    if await self._check_login_status():
                        self._logged_in = True
                        return True
                    await asyncio.sleep(1)
                return False

            return True

        except Exception as e:
            print(f"[Perplexity] 登录失败: {e}")
            return False

    async def send_message(self, prompt: str, timeout: int = 120) -> LLMResponse:
        """
        发送消息并等待 Perplexity 回复

        Perplexity 回复包含内联引用和搜索结果
        """
        if not self._page:
            raise RuntimeError("浏览器未启动，请先调用 ensure_login()")

        start_time = time.time()
        response = LLMResponse()

        try:
            # 确保在对话页
            current_url = await self._page.evaluate("window.location.href")
            if "perplexity.ai" not in current_url:
                await self.engine.navigate(self.site.home_url)
                await asyncio.sleep(2)

            # 找到输入框
            textarea = await self._page.wait_for_selector(
                PERPLEXITY_CHAT["textarea"], timeout=10000
            )
            if not textarea:
                raise Exception("找不到 Perplexity 输入框")

            await textarea.click()
            await asyncio.sleep(0.3)

            # 输入 prompt
            await self.engine.type_text(PERPLEXITY_CHAT["textarea"], prompt)
            await asyncio.sleep(random.uniform(0.3, 0.8))

            # 发送
            send_btn = await self._page.query_selector(PERPLEXITY_CHAT["send_button"])
            if send_btn:
                await send_btn.click()
            else:
                await textarea.press("Enter")

            # 等待回复
            await self._wait_for_stream_complete(
                PERPLEXITY_CHAT["stop_button"], timeout=timeout
            )

            await asyncio.sleep(0.5)

            # 收集回复内容
            response_text = await self._page.evaluate("""
                () => {
                    const containers = document.querySelectorAll('.prose, .markdown');
                    const results = Array.from(containers)
                        .map(el => el.innerText.trim())
                        .filter(t => t.length > 0);
                    return results.length > 0 ? results[results.length - 1] : '';
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
            new_chat = await self._page.query_selector(PERPLEXITY_CHAT["new_chat_btn"])
            if new_chat:
                await new_chat.click()
                await asyncio.sleep(2)
                return True
            await self.engine.navigate("https://www.perplexity.ai")
            await asyncio.sleep(2)
            return True
        except Exception:
            return False
