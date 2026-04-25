"""
Kimi (moonshot.cn) 网页版桥接

Kimi 是国内最活跃的 LLM 网页版之一（Moonshot AI），特点：
  - 登录方式：手机号验证码 / 微信扫码 / 密码登录
  - 对话界面：极简设计，输入框 + 发送按钮 + 回复区域
  - 支持多模态（文件上传、图片理解）
  - 回复速度快，支持长上下文（200K tokens）

登录流程（2025 版）：
  1. 访问 kimi.moonshot.cn
  2. 点击登录按钮（右上角）
  3. 输入手机号 → 获取验证码 / 或密码登录
  4. 登录成功后跳转回对话页

对话流程：
  1. 导航到 kimi.moonshot.cn
  2. 在 textarea 输入 prompt
  3. 点击发送按钮
  4. 等待流式回复完成（停止按钮消失）
  5. 读取回复内容
"""
import asyncio
import random
import time

from ..core.browser import BrowserEngine
from ..core.session import SessionManager, LLMSite
from .base import BaseBridge, LLMResponse


KIMI_LOGIN = {
    "login_btn": 'button:has-text("登录"), button:has-text("Log in"), [data-testid="login-btn"]',
    "phone_input": 'input[type="tel"], input[placeholder*="手机号"], input[name="phone"]',
    "email_input": 'input[type="email"], input[name="email"], input[placeholder*="邮箱"]',
    "password_input": 'input[type="password"], input[name="password"]',
    "submit_btn": 'button[type="submit"], button:has-text("登录"), button:has-text("下一步")',
    "switch_to_pwd": 'span:has-text("密码登录"), a:has-text("密码登录")',
}

KIMI_CHAT = {
    "textarea": 'textarea[placeholder*="发送"], textarea[placeholder*="输入"], #chat-input',
    "send_button": 'button[aria-label*="发送"], button[aria-label*="Send"], button[type="submit"]',
    "stop_button": 'button[aria-label*="停止"], button[aria-label*="Stop"]',
    "response": '.markdown-body, .message-content, .prose, [data-testid="assistant-message"]',
    "new_chat_btn": 'a[href="/"], button:has-text("新对话"), button:has-text("New Chat")',
}


class KimiBridge(BaseBridge):
    """Kimi 网页版桥接"""

    def __init__(
        self,
        engine: BrowserEngine,
        session_mgr: SessionManager,
        headless: bool = False,
    ):
        super().__init__(engine, session_mgr, LLMSite.kimi(), headless=headless)

    async def _check_login_status(self) -> bool:
        """检查是否已登录 — 看页面是否在对话页（能看到输入框）"""
        try:
            current_url = await self._page.evaluate("window.location.href")
            # 如果在登录/注册页，说明未登录
            if "login" in current_url or "sign_in" in current_url or "auth" in current_url:
                return False
            # 检查是否有输入框（登录后必有）
            textarea = await self._page.query_selector(KIMI_CHAT["textarea"])
            return textarea is not None
        except Exception:
            return False

    async def _perform_login(self, email: str, password: str) -> bool:
        """执行 Kimi 登录流程

        支持两种登录方式：
          1. 密码登录（email + password）
          2. 验证码登录（需要手动干预）
        """
        try:
            await asyncio.sleep(2)

            # 步骤1: 点击登录按钮（如果页面上有）
            login_btn = await self._page.query_selector(KIMI_LOGIN["login_btn"])
            if login_btn:
                await login_btn.click()
                await asyncio.sleep(2)
                await self.engine.wait_for_navigation()

            # 步骤2: 尝试切换到密码登录（默认可能是验证码登录）
            switch_btn = await self._page.query_selector(KIMI_LOGIN["switch_to_pwd"])
            if switch_btn:
                await switch_btn.click()
                await asyncio.sleep(1)

            # 步骤3: 检查是否需要输入 email（有些版本用 email）
            email_input = await self._page.query_selector(KIMI_LOGIN["email_input"])
            if email_input:
                await self.engine.type_text(KIMI_LOGIN["email_input"], email)
            else:
                # 尝试手机号输入框（如果有 email 参数的自动适配）
                phone_input = await self._page.query_selector(KIMI_LOGIN["phone_input"])
                if phone_input:
                    # 如果是手机号登录，用 email 作为用户名
                    # 实际使用时可以自定义
                    await self.engine.type_text(KIMI_LOGIN["phone_input"], email)

            await asyncio.sleep(0.5)

            # 步骤4: 输入密码
            pwd_input = await self._page.query_selector(KIMI_LOGIN["password_input"])
            if pwd_input:
                await self.engine.type_text(KIMI_LOGIN["password_input"], password)
                await asyncio.sleep(0.5)

            # 步骤5: 提交登录
            submit_btn = await self._page.query_selector(KIMI_LOGIN["submit_btn"])
            if submit_btn:
                await submit_btn.click()

            # 等待登录完成
            await asyncio.sleep(3)
            await self.engine.wait_for_navigation(timeout=20000)

            # 保存 Cookie
            if self._page and self._page.context:
                cookies = await self._page.context.cookies()
                self.session_mgr.save_cookies(self.site.name, cookies)

            # 验证登录
            self._logged_in = await self._check_login_status()
            if not self._logged_in:
                print("[Kimi] 登录可能需要手动验证（验证码/扫码）")
                for i in range(30):
                    if await self._check_login_status():
                        self._logged_in = True
                        return True
                    await asyncio.sleep(1)
                return False

            return True

        except Exception as e:
            print(f"[Kimi] 登录失败: {e}")
            return False

    async def send_message(self, prompt: str, timeout: int = 120) -> LLMResponse:
        """
        发送消息并等待 Kimi 回复

        Kimi 的对话流程：
          1. 在 textarea 输入 prompt
          2. 点击发送按钮
          3. 等待流式回复完成（停止按钮消失）
          4. 读取最后回复内容
        """
        if not self._page:
            raise RuntimeError("浏览器未启动，请先调用 ensure_login()")

        start_time = time.time()
        response = LLMResponse()

        try:
            # 确保在 Kimi 对话页
            current_url = await self._page.evaluate("window.location.href")
            if "kimi.moonshot.cn" not in current_url:
                await self.engine.navigate(self.site.home_url)
                await asyncio.sleep(2)

            # 找到 textarea 输入框
            textarea = await self._page.wait_for_selector(
                KIMI_CHAT["textarea"], timeout=10000
            )
            if not textarea:
                raise Exception("找不到 Kimi 输入框")

            # 点击激活输入框
            await textarea.click()
            await asyncio.sleep(0.3)

            # 输入 prompt（模拟人类打字）
            await self.engine.type_text(KIMI_CHAT["textarea"], prompt)
            await asyncio.sleep(random.uniform(0.3, 0.8))

            # 点击发送
            send_btn = await self._page.query_selector(KIMI_CHAT["send_button"])
            if send_btn:
                await send_btn.click()
            else:
                await textarea.press("Enter")

            # 等待流式回复完成
            await self._wait_for_stream_complete(
                KIMI_CHAT["stop_button"], timeout=timeout
            )

            # 额外等待渲染完成
            await asyncio.sleep(0.5)

            # 收集回复内容
            response_text = await self._page.evaluate("""
                () => {
                    const selectors = ['.markdown-body', '.message-content', '.prose',
                        '[data-testid="assistant-message"]'];
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
            new_chat = await self._page.query_selector(KIMI_CHAT["new_chat_btn"])
            if new_chat:
                await new_chat.click()
                await asyncio.sleep(2)
                return True
            await self.engine.navigate("https://kimi.moonshot.cn")
            await asyncio.sleep(2)
            return True
        except Exception:
            return False
