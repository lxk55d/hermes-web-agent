"""
Claude 网页版桥接

登录流程（2025 版）：
  1. 访问 claude.ai/login
  2. 输入 email → Continue
  3. 输入 password → Continue
  4. 可选 OAuth（Google/GitHub）

对话流程：
  1. 导航到 claude.ai/new（新建对话）
  2. 在 chat input 输入 prompt
  3. 点击发送按钮
  4. 等待回复完成（停止按钮消失）
  5. 读取完整回复
"""
import asyncio
import random
import time

from ..core.browser import BrowserEngine
from ..core.session import SessionManager, LLMSite
from .base import BaseBridge, LLMResponse


CLAUDE_LOGIN = {
    "email_input": 'input[name="email"]',
    "password_input": 'input[name="password"]',
    "continue_btn": 'button[type="submit"]',
    "login_success_check": '[data-testid="conversation-list"], [data-testid="new-chat-page"]',
}

CLAUDE_CHAT = {
    "textarea": '[data-testid="chat-input"], div[contenteditable="true"][data-placeholder*="message"]',
    "send_button": '[data-testid="send-button"], button[aria-label*="send"]',
    "stop_button": '[data-testid="stop-button"], button[aria-label*="stop"]',
    "message": '[data-testid="message"]',
    "new_chat_link": 'a[href="/new"], button:has-text("New chat")',
}


class ClaudeBridge(BaseBridge):
    """Claude 网页版桥接"""

    def __init__(
        self,
        engine: BrowserEngine,
        session_mgr: SessionManager,
        headless: bool = False,
    ):
        super().__init__(engine, session_mgr, LLMSite.claude(), headless=headless)

    async def _check_login_status(self) -> bool:
        """检查是否已登录"""
        try:
            current_url = await self._page.evaluate("window.location.href")
            if "login" in current_url:
                return False
            # Claude 登录后必见对话列表或新对话页
            check = await self._page.query_selector(CLAUDE_LOGIN["login_success_check"])
            return check is not None
        except Exception:
            return False

    async def _perform_login(self, email: str, password: str) -> bool:
        """执行 Claude 登录"""
        try:
            await asyncio.sleep(2)

            # 输入 email
            email_input = await self._page.wait_for_selector(
                CLAUDE_LOGIN["email_input"], timeout=15000
            )
            if not email_input:
                raise Exception("找不到 email 输入框")

            await self.engine.type_text(CLAUDE_LOGIN["email_input"], email)
            await asyncio.sleep(0.5)

            # 点击 Continue
            await self.engine.click(CLAUDE_LOGIN["continue_btn"])
            await asyncio.sleep(2)

            # 输入 password
            pwd_input = await self._page.wait_for_selector(
                CLAUDE_LOGIN["password_input"], timeout=15000
            )
            if pwd_input:
                await self.engine.type_text(CLAUDE_LOGIN["password_input"], password)
                await asyncio.sleep(0.5)

                # 提交
                await self.engine.click(CLAUDE_LOGIN["continue_btn"])
            else:
                # 可能是 OAuth 跳转（Google/GitHub）
                print("[Claude] 可能已跳转到 OAuth 登录...")
                await asyncio.sleep(5)

            # 等待登录完成
            await asyncio.sleep(3)
            await self.engine.wait_for_navigation(timeout=25000)

            # 保存 Cookie
            if self._page and self._page.context:
                cookies = await self._page.context.cookies()
                self.session_mgr.save_cookies(self.site.name, cookies)

            # 验证
            self._logged_in = await self._check_login_status()
            if not self._logged_in:
                print("[Claude] 登录可能需要手动验证")
                for i in range(30):
                    if await self._check_login_status():
                        self._logged_in = True
                        return True
                    await asyncio.sleep(1)
                return False

            return True

        except Exception as e:
            print(f"[Claude] 登录失败: {e}")
            return False

    async def send_message(self, prompt: str, timeout: int = 180) -> LLMResponse:
        """
        发送消息并等待 Claude 回复

        Claude 的回复通常较长且慢，timeout 默认 180 秒
        """
        if not self._page:
            raise RuntimeError("浏览器未启动，请先调用 ensure_login()")

        start_time = time.time()
        response = LLMResponse()

        try:
            # 确保在 Claude 对话页面
            current_url = await self._page.evaluate("window.location.href")
            if "/new" not in current_url and "/chat/" not in current_url:
                await self.engine.navigate(self.site.home_url)
                await asyncio.sleep(2)

            # 查找并点击 textarea
            textarea = await self._page.wait_for_selector(
                CLAUDE_CHAT["textarea"], timeout=15000
            )
            if not textarea:
                raise Exception("找不到 Claude 输入框")

            await textarea.click()
            await asyncio.sleep(0.3)

            # 输入文本（模拟人类）
            for char in prompt:
                await textarea.type(char, delay=random.randint(20, 80))
                # 每 50 个字符停顿一下（更像人类）
                if random.random() < 0.02:
                    await asyncio.sleep(random.uniform(0.1, 0.3))

            await asyncio.sleep(random.uniform(0.3, 0.8))

            # 发送
            send_btn = await self._page.query_selector(CLAUDE_CHAT["send_button"])
            if send_btn:
                await send_btn.click()
            else:
                # 尝试 Enter（claude.ai 的 contenteditable 需要 Ctrl+Enter）
                await textarea.press("Control+Enter")

            # 等待回复完成
            await self._wait_for_stream_complete(
                CLAUDE_CHAT["stop_button"], timeout=timeout, poll_interval=1.0
            )

            # Claude 有时生成完会继续思考，多等一下
            await asyncio.sleep(1)

            # 收集所有消息
            messages = await self._page.evaluate("""
                () => {
                    const msgs = document.querySelectorAll('[data-testid="message"]');
                    return Array.from(msgs).map(msg => {
                        const role = msg.getAttribute('data-testid') === 'message-user' ? 'user' : 'assistant';
                        const content = msg.innerText.trim();
                        return { role, content };
                    });
                }
            """)

            if messages:
                # 取最后一个 assistant 消息
                last_assistant = next(
                    (m for m in reversed(messages) if m["role"] == "assistant"),
                    None
                )
                if last_assistant:
                    response.content = last_assistant["content"]

            response.success = bool(response.content)
            response.elapsed_seconds = time.time() - start_time

            # 识别 Claude 模型版本
            model_info = await self._page.evaluate("""
                () => {
                    const el = document.querySelector('[data-testid="model-selector"], .model-badge');
                    return el ? el.innerText.trim() : '';
                }
            """)
            if model_info:
                response.model_name = model_info

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
            await self.engine.navigate("https://claude.ai/new")
            await asyncio.sleep(2)
            return True
        except Exception:
            return False
