"""测试桥接器基类和全部桥接器 — 使用 mock 不启动真实浏览器"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from hermes_web_agent.bridges.base import BaseBridge, LLMResponse
from hermes_web_agent.bridges.chatgpt import ChatGPTBridge
from hermes_web_agent.bridges.claude import ClaudeBridge
from hermes_web_agent.bridges.deepseek import DeepSeekBridge
from hermes_web_agent.bridges.gemini import GeminiBridge
from hermes_web_agent.bridges.grok import GrokBridge
from hermes_web_agent.bridges.perplexity import PerplexityBridge
from hermes_web_agent.bridges.copilot import CopilotBridge
from hermes_web_agent.core.session import SessionManager, LLMSite


# ── Fixtures ────────────────────────────────────────────


@pytest.fixture
def mock_engine():
    """模拟 BrowserEngine"""
    engine = MagicMock()
    engine.start = AsyncMock(return_value=MagicMock())
    engine.navigate = AsyncMock(return_value=True)
    engine.set_session_name = MagicMock()
    engine.wait_for_navigation = AsyncMock(return_value=True)
    engine.type_text = AsyncMock(return_value=True)
    engine.click = AsyncMock(return_value=True)
    engine.close = AsyncMock()
    return engine


@pytest.fixture
def mock_session_mgr():
    """模拟 SessionManager"""
    mgr = MagicMock(spec=SessionManager)
    mgr.get_credential = MagicMock(return_value=None)
    mgr.save_cookies = MagicMock()
    mgr.has_credential = MagicMock(return_value=False)
    return mgr


@pytest.fixture
def mock_page():
    """模拟 Playwright Page"""
    page = MagicMock()
    page.evaluate = AsyncMock(return_value="https://chat.openai.com")
    page.query_selector = AsyncMock(return_value=MagicMock())
    page.wait_for_selector = AsyncMock(return_value=MagicMock())
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.type = AsyncMock()
    page.press = AsyncMock()
    page.title = AsyncMock(return_value="ChatGPT")
    page.context = MagicMock()
    page.context.cookies = AsyncMock(return_value=[])
    return page


# ── LLMResponse 数据类 ──────────────────────────────────


class TestLLMResponse:
    """测试 LLMResponse 数据类"""

    def test_default_initialization(self):
        resp = LLMResponse()
        assert resp.content == ""
        assert resp.model_name == "unknown"
        assert resp.tokens_used is None
        assert resp.elapsed_seconds == 0.0
        assert resp.success is False
        assert resp.error is None
        assert resp.screenshot_path is None

    def test_custom_initialization(self):
        resp = LLMResponse(
            content="Hello world",
            model_name="gpt-4",
            tokens_used=150,
            elapsed_seconds=5.2,
            success=True,
        )
        assert resp.content == "Hello world"
        assert resp.model_name == "gpt-4"
        assert resp.tokens_used == 150
        assert resp.success is True


# ── BaseBridge ──────────────────────────────────────────


class TestBaseBridge:
    """测试 BaseBridge 基类"""

    def test_abstract_class_cannot_instantiate(self):
        """抽象类不能直接实例化"""
        with pytest.raises(TypeError):
            BaseBridge(
                engine=MagicMock(),
                session_mgr=MagicMock(),
                site=LLMSite.chatgpt(),
            )

    @pytest.mark.asyncio
    async def test_ensure_login_missing_credential(self, mock_engine, mock_session_mgr):
        """ensure_login 在没有凭证时抛出 RuntimeError"""

        class TestBridge(BaseBridge):
            async def _check_login_status(self):
                return False

            async def _perform_login(self, email, password):
                return False

        bridge = TestBridge(
            engine=mock_engine,
            session_mgr=mock_session_mgr,
            site=LLMSite.chatgpt(),
        )
        # mock_page 返回 textarea → 已登录
        bridge._page = MagicMock()
        bridge._page.evaluate = AsyncMock(return_value="https://chat.openai.com")
        bridge._page.query_selector = AsyncMock(return_value=MagicMock())

        # mock_session_mgr.has_credential 已经返回 False，get_credential 返回 None
        # _check_login_status 返回 False → 需要检查凭证 → 没有凭证 → RuntimeError
        with pytest.raises(RuntimeError, match="未找到登录凭证"):
            await bridge.ensure_login()

    @pytest.mark.asyncio
    async def test_base_bridge_name(self, mock_engine, mock_session_mgr):
        """BaseBridge.name 返回站点名"""

        class TestBridge(BaseBridge):
            async def _check_login_status(self):
                return False

            async def _perform_login(self, email, password):
                return False

        bridge = TestBridge(
            engine=mock_engine,
            session_mgr=mock_session_mgr,
            site=LLMSite.chatgpt(),
        )
        assert bridge.name == "chatgpt"

    def test_llm_site(self):
        """LLMSite 站点的 URL 正确"""
        sites = {
            "chatgpt": ("https://chat.openai.com", LLMSite.chatgpt()),
            "claude": ("https://claude.ai", LLMSite.claude()),
            "deepseek": ("https://chat.deepseek.com", LLMSite.deepseek()),
            "gemini": ("https://gemini.google.com", LLMSite.gemini()),
            "grok": ("https://grok.com", LLMSite.grok()),
            "perplexity": ("https://www.perplexity.ai", LLMSite.perplexity()),
            "copilot": ("https://copilot.microsoft.com", LLMSite.copilot()),
        }
        for name, (expected_url, site) in sites.items():
            assert site.base_url == expected_url, f"{name} base_url mismatch"
            assert site.name == name, f"{name} name mismatch"


# ── Bridge _check_login_status 字符串匹配测试 ─────────────


class TestBridgeLoginStatus:
    """测试各桥接器的 _check_login_status 逻辑（不启动浏览器）"""

    @pytest.mark.asyncio
    async def test_chatgpt_login_check(self, mock_engine, mock_session_mgr, mock_page):
        """ChatGPT: 未登录时 URL 含 auth/login"""
        bridge = ChatGPTBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = mock_page

        # 模拟未登录：URL 含 auth
        mock_page.evaluate = AsyncMock(return_value="https://chat.openai.com/auth/login")
        result = await bridge._check_login_status()
        assert result is False

        # 模拟已登录：URL 不含 auth，有 textarea
        mock_page.evaluate = AsyncMock(return_value="https://chat.openai.com")
        mock_page.query_selector = AsyncMock(return_value=MagicMock())
        result = await bridge._check_login_status()
        assert result is True

        # 模拟已登录但无 textarea（异常情况）
        mock_page.query_selector = AsyncMock(return_value=None)
        result = await bridge._check_login_status()
        assert result is False

    @pytest.mark.asyncio
    async def test_claude_login_check(self, mock_engine, mock_session_mgr, mock_page):
        """Claude: 未登录时 URL 含 login"""
        bridge = ClaudeBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = mock_page

        mock_page.evaluate = AsyncMock(return_value="https://claude.ai/login")
        result = await bridge._check_login_status()
        assert result is False

        mock_page.evaluate = AsyncMock(return_value="https://claude.ai/new")
        mock_page.query_selector = AsyncMock(return_value=MagicMock())
        result = await bridge._check_login_status()
        assert result is True

    @pytest.mark.asyncio
    async def test_deepseek_login_check(self, mock_engine, mock_session_mgr, mock_page):
        """DeepSeek: 未登录时 URL 含 sign_in/login"""
        bridge = DeepSeekBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = mock_page

        mock_page.evaluate = AsyncMock(return_value="https://chat.deepseek.com/sign_in")
        result = await bridge._check_login_status()
        assert result is False

        mock_page.evaluate = AsyncMock(return_value="https://chat.deepseek.com")
        mock_page.query_selector = AsyncMock(return_value=MagicMock())
        result = await bridge._check_login_status()
        assert result is True

    @pytest.mark.asyncio
    async def test_gemini_login_check(self, mock_engine, mock_session_mgr, mock_page):
        """Gemini: 未登录时 URL 含 accounts.google.com"""
        bridge = GeminiBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = mock_page

        mock_page.evaluate = AsyncMock(return_value="https://accounts.google.com/signin")
        result = await bridge._check_login_status()
        assert result is False

        mock_page.evaluate = AsyncMock(return_value="https://gemini.google.com/app")
        mock_page.query_selector = AsyncMock(return_value=MagicMock())
        result = await bridge._check_login_status()
        assert result is True

    @pytest.mark.asyncio
    async def test_grok_login_check(self, mock_engine, mock_session_mgr, mock_page):
        """Grok: 未登录时 URL 含 login/auth/i/flow"""
        bridge = GrokBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = mock_page

        mock_page.evaluate = AsyncMock(return_value="https://grok.com/i/flow/login")
        result = await bridge._check_login_status()
        assert result is False

        mock_page.evaluate = AsyncMock(return_value="https://grok.com")
        mock_page.query_selector = AsyncMock(return_value=MagicMock())
        result = await bridge._check_login_status()
        assert result is True

    @pytest.mark.asyncio
    async def test_perplexity_login_check(self, mock_engine, mock_session_mgr, mock_page):
        """Perplexity: 未登录时 URL 含 auth/login"""
        bridge = PerplexityBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = mock_page

        mock_page.evaluate = AsyncMock(return_value="https://www.perplexity.ai/auth/login")
        result = await bridge._check_login_status()
        assert result is False

        mock_page.evaluate = AsyncMock(return_value="https://www.perplexity.ai")
        mock_page.query_selector = AsyncMock(return_value=MagicMock())
        result = await bridge._check_login_status()
        assert result is True

    @pytest.mark.asyncio
    async def test_copilot_login_check(self, mock_engine, mock_session_mgr, mock_page):
        """Copilot: 未登录时 URL 含 login/live.com"""
        bridge = CopilotBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = mock_page

        mock_page.evaluate = AsyncMock(return_value="https://login.live.com/login")
        result = await bridge._check_login_status()
        assert result is False

        mock_page.evaluate = AsyncMock(return_value="https://copilot.microsoft.com")
        mock_page.query_selector = AsyncMock(return_value=MagicMock())
        result = await bridge._check_login_status()
        assert result is True


# ── Bridge send_message URL 检查 ──────────────────────────


class TestBridgeSendMessage:
    """测试各桥接器 send_message 的 URL 检查逻辑"""

    @pytest.mark.asyncio
    async def test_chatgpt_send_message_no_page(self, mock_engine, mock_session_mgr):
        """send_message 在 page 为 None 时抛出 RuntimeError"""
        bridge = ChatGPTBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = None
        with pytest.raises(RuntimeError, match="浏览器未启动"):
            await bridge.send_message("hello")

    @pytest.mark.asyncio
    async def test_claude_send_message_no_page(self, mock_engine, mock_session_mgr):
        bridge = ClaudeBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = None
        with pytest.raises(RuntimeError, match="浏览器未启动"):
            await bridge.send_message("hello")

    @pytest.mark.asyncio
    async def test_deepseek_send_message_no_page(self, mock_engine, mock_session_mgr):
        bridge = DeepSeekBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = None
        with pytest.raises(RuntimeError, match="浏览器未启动"):
            await bridge.send_message("hello")

    @pytest.mark.asyncio
    async def test_gemini_send_message_no_page(self, mock_engine, mock_session_mgr):
        bridge = GeminiBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = None
        with pytest.raises(RuntimeError, match="浏览器未启动"):
            await bridge.send_message("hello")

    @pytest.mark.asyncio
    async def test_grok_send_message_no_page(self, mock_engine, mock_session_mgr):
        bridge = GrokBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = None
        with pytest.raises(RuntimeError, match="浏览器未启动"):
            await bridge.send_message("hello")

    @pytest.mark.asyncio
    async def test_perplexity_send_message_no_page(self, mock_engine, mock_session_mgr):
        bridge = PerplexityBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = None
        with pytest.raises(RuntimeError, match="浏览器未启动"):
            await bridge.send_message("hello")

    @pytest.mark.asyncio
    async def test_copilot_send_message_no_page(self, mock_engine, mock_session_mgr):
        bridge = CopilotBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = None
        with pytest.raises(RuntimeError, match="浏览器未启动"):
            await bridge.send_message("hello")
