"""
LLM 网页版桥接基类

所有 LLM 平台（ChatGPT / Claude / DeepSeek / Gemini）都需要：
  1. 登录
  2. 发送消息
  3. 等待回复
  4. 读取回复内容
  5. 保持会话持续对话
"""
import asyncio
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from ..core.browser import BrowserEngine
from ..core.session import SessionManager, LLMSite


@dataclass
class LLMResponse:
    """LLM 回复"""
    content: str = ""
    model_name: str = "unknown"
    tokens_used: Optional[int] = None
    elapsed_seconds: float = 0.0
    success: bool = False
    error: Optional[str] = None
    screenshot_path: Optional[str] = None


class BaseBridge(ABC):
    """LLM 网页版桥接基类"""

    def __init__(
        self,
        engine: BrowserEngine,
        session_mgr: SessionManager,
        site: LLMSite,
        headless: bool = False,
    ):
        self.engine = engine
        self.session_mgr = session_mgr
        self.site = site
        self.headless = headless
        self._page = None
        self._logged_in = False

    @property
    def name(self) -> str:
        return self.site.name

    async def ensure_login(self) -> bool:
        """确保已登录 — 先尝试 Cookie 恢复，失败则自动登录"""
        if self._logged_in:
            return True

        self._page = await self.engine.start(headless=self.headless)
        self.engine.set_session_name(self.site.name)

        # 步骤1: 导航到首页，检查 Cookie 是否有效
        await self.engine.navigate(self.site.home_url)
        await asyncio.sleep(1)

        if await self._check_login_status():
            self._logged_in = True
            return True

        # 步骤2: Cookie 失效，去登录页
        await self.engine.navigate(self.site.login_url)
        await asyncio.sleep(1)

        cred = self.session_mgr.get_credential(self.site.name)
        if not cred:
            raise RuntimeError(
                f"[{self.site.name}] 未找到登录凭证。请设置环境变量 "
                f"或通过 session_manager.set_credential() 提供。"
            )

        return await self._perform_login(cred.email, cred.password)

    @abstractmethod
    async def _check_login_status(self) -> bool:
        """检查当前页面是否已登录"""
        ...

    @abstractmethod
    async def _perform_login(self, email: str, password: str) -> bool:
        """执行登录流程"""
        ...

    def _get_text_safe(self, selector: str, default: str = "") -> str:
        """安全获取元素文本（不抛异常）"""
        try:
            return self._page.eval_on_selector(
                selector, "el => el.textContent.trim()"
            ) if self._page else default
        except Exception:
            return default

    async def _wait_for_stream_complete(
        self,
        stop_selector: str,
        timeout: int = 120,
        poll_interval: float = 0.5,
    ) -> bool:
        """
        等待流式回复完成 — 监控停止按钮消失
        
        许多 LLM 网页版在生成回复时显示停止按钮，
        生成完毕后自动消失。
        """
        if not self._page:
            return False

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                stop_btn = await self._page.query_selector(stop_selector)
                if not stop_btn:
                    return True  # 停止按钮消失 → 生成完成
                await asyncio.sleep(poll_interval)
            except Exception:
                return False
        return False  # 超时

    async def close(self):
        """关闭浏览器"""
        await self.engine.close()
        self._logged_in = False
        self._page = None
