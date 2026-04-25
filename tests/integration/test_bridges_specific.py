"""测试各桥接器特定逻辑 — 消息选择器、模式标签检测、回复收集等"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from hermes_web_agent.bridges.chatgpt import ChatGPTBridge
from hermes_web_agent.bridges.claude import ClaudeBridge
from hermes_web_agent.bridges.deepseek import DeepSeekBridge
from hermes_web_agent.bridges.gemini import GeminiBridge
from hermes_web_agent.bridges.grok import GrokBridge
from hermes_web_agent.bridges.perplexity import PerplexityBridge
from hermes_web_agent.bridges.copilot import CopilotBridge


# ── Fixtures ────────────────────────────────────────────


@pytest.fixture
def mock_engine():
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
    mgr = MagicMock()
    mgr.get_credential = MagicMock(return_value=None)
    mgr.save_cookies = MagicMock()
    return mgr


@pytest.fixture
def mock_page():
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


@pytest.fixture
def mock_element():
    """模拟 DOM 元素，所有可能被 await 的方法都是 AsyncMock"""
    el = MagicMock()
    el.click = AsyncMock()
    el.fill = AsyncMock()
    el.type = AsyncMock()
    el.press = AsyncMock()
    el.bounding_box = AsyncMock(
        return_value={"x": 0, "y": 0, "width": 100, "height": 50}
    )
    el.inner_text = AsyncMock(return_value="")
    el.get_attribute = AsyncMock(return_value=None)
    return el


# ── ChatGPTBridge 特定测试 ──────────────────────────────


class TestChatGPTBridgeSpecific:
    """ChatGPTBridge 消息选择器测试"""

    @pytest.mark.asyncio
    async def test_send_message_with_mock_page(self, mock_engine, mock_session_mgr, mock_page, mock_element):
        """send_message 在 mock 环境中正常执行"""
        bridge = ChatGPTBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = mock_page

        # mock textarea 存在
        mock_page.query_selector = AsyncMock(return_value=mock_element)

        # mock 回复收集
        mock_page.evaluate = AsyncMock(side_effect=[
            "https://chat.openai.com",  # 第一次: URL
            "Hello! How can I help you?",  # 第二次: 回复内容
            "gpt-4-turbo",  # 第三次: 模型标签
        ])

        result = await bridge.send_message("test prompt")
        assert result.success is True
        assert result.content == "Hello! How can I help you?"

    @pytest.mark.asyncio
    async def test_start_new_conversation(self, mock_engine, mock_session_mgr, mock_page, mock_element):
        """start_new_conversation 调用 query_selector"""
        bridge = ChatGPTBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = mock_page

        mock_page.query_selector = AsyncMock(return_value=mock_element)
        result = await bridge.start_new_conversation()
        assert result is True

    @pytest.mark.asyncio
    async def test_get_conversation_history(self, mock_engine, mock_session_mgr, mock_page):
        """get_conversation_history 返回列表"""
        bridge = ChatGPTBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = mock_page

        mock_page.evaluate = AsyncMock(return_value=[
            {"role": "user", "content": "hello", "timestamp": "1"},
            {"role": "assistant", "content": "hi there", "timestamp": "2"},
        ])
        history = await bridge.get_conversation_history()
        assert len(history) == 2
        assert history[0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_get_conversation_history_no_page(self, mock_engine, mock_session_mgr):
        """page 为 None 时返回空列表"""
        bridge = ChatGPTBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = None
        history = await bridge.get_conversation_history()
        assert history == []


# ── ClaudeBridge 特定测试 ────────────────────────────────


class TestClaudeBridgeSpecific:
    """ClaudeBridge 模式标签检测"""

    @pytest.mark.asyncio
    async def test_send_message_with_model_info(self, mock_engine, mock_session_mgr, mock_page, mock_element):
        """send_message 检测模型标签"""
        bridge = ClaudeBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = mock_page

        # 模拟 navigate to /new if not in chat
        mock_page.evaluate = AsyncMock(side_effect=[
            "https://claude.ai/chat/123",  # URL → 已在新对话
        ])

        mock_page.wait_for_selector = AsyncMock(return_value=mock_element)
        mock_page.query_selector = AsyncMock(side_effect=[
            mock_element,  # textarea 存在
            mock_element,  # send_btn 存在
            None,  # stop_button → 已完成
        ])

        # 模拟消息收集
        with patch.object(bridge, '_wait_for_stream_complete', AsyncMock(return_value=True)):
            mock_page.evaluate = AsyncMock(side_effect=[
                "https://claude.ai/chat/123",
                [  # messages
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "Hello! I'm Claude."},
                ],
                "Claude 3.5 Sonnet",  # model_info
            ])

            result = await bridge.send_message("hello")
            assert result.success is True
            assert result.content == "Hello! I'm Claude."
            assert result.model_name == "Claude 3.5 Sonnet"

    @pytest.mark.asyncio
    async def test_start_new_conversation_claude(self, mock_engine, mock_session_mgr, mock_page):
        """Claude 开启新对话"""
        bridge = ClaudeBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = mock_page
        mock_engine.navigate = AsyncMock(return_value=True)

        result = await bridge.start_new_conversation()
        assert result is True
        mock_engine.navigate.assert_called_with("https://claude.ai/new")


# ── DeepSeekBridge 特定测试 ──────────────────────────────


class TestDeepSeekBridgeSpecific:
    """DeepSeekBridge 回复收集逻辑"""

    @pytest.mark.asyncio
    async def test_send_message_empty_response(self, mock_engine, mock_session_mgr, mock_page, mock_element):
        """空回复时 success=False"""
        bridge = DeepSeekBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = mock_page

        mock_page.evaluate = AsyncMock(side_effect=[
            "https://chat.deepseek.com",
            [],
        ])
        mock_page.wait_for_selector = AsyncMock(return_value=mock_element)
        mock_page.query_selector = AsyncMock(return_value=mock_element)
        with patch.object(bridge, '_wait_for_stream_complete', AsyncMock(return_value=True)):
            result = await bridge.send_message("hello")
            assert result.success is False
            assert "(空回复)" in result.content

    @pytest.mark.asyncio
    async def test_send_message_with_responses(self, mock_engine, mock_session_mgr, mock_page, mock_element):
        """收集多个回复块，取最后一个"""
        bridge = DeepSeekBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = mock_page

        mock_page.evaluate = AsyncMock(side_effect=[
            "https://chat.deepseek.com",
            ["block1", "block2", "最终回复"],
        ])
        mock_page.wait_for_selector = AsyncMock(return_value=mock_element)
        mock_page.query_selector = AsyncMock(return_value=mock_element)
        with patch.object(bridge, '_wait_for_stream_complete', AsyncMock(return_value=True)):
            result = await bridge.send_message("hello")
            assert result.success is True
            assert result.content == "最终回复"


# ── GeminiBridge 特定测试 ────────────────────────────────


class TestGeminiBridgeSpecific:
    """GeminiBridge contenteditable 交互"""

    @pytest.mark.asyncio
    async def test_send_message_contenteditable(self, mock_engine, mock_session_mgr, mock_page, mock_element):
        """Gemini 使用 contenteditable div"""
        bridge = GeminiBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = mock_page

        mock_page.evaluate = AsyncMock(side_effect=[
            "https://gemini.google.com/app",
            "Gemini response text",
        ])
        mock_page.wait_for_selector = AsyncMock(return_value=mock_element)
        mock_page.query_selector = AsyncMock(side_effect=[
            mock_element,  # textarea
            mock_element,  # send_btn
            None,  # stop_button → done
        ])
        with patch.object(bridge, '_wait_for_stream_complete', AsyncMock(return_value=True)):
            result = await bridge.send_message("test")
            assert result.success is True
            assert result.content == "Gemini response text"

    @pytest.mark.asyncio
    async def test_start_new_conversation_gemini(self, mock_engine, mock_session_mgr, mock_page):
        """Gemini 开启新对话"""
        bridge = GeminiBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = mock_page
        mock_engine.navigate = AsyncMock(return_value=True)

        result = await bridge.start_new_conversation()
        assert result is True
        mock_engine.navigate.assert_called_with("https://gemini.google.com/app")


# ── GrokBridge / PerplexityBridge / CopilotBridge ─────────


class TestOtherBridgesSpecific:
    """Grok/Perplexity/Copilot 构造与基础行为"""

    def test_grok_bridge_construction(self, mock_engine, mock_session_mgr):
        """GrokBridge 构造后 name 正确"""
        bridge = GrokBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        assert bridge.name == "grok"
        assert bridge.site.base_url == "https://grok.com"

    def test_perplexity_bridge_construction(self, mock_engine, mock_session_mgr):
        """PerplexityBridge 构造后 name 正确"""
        bridge = PerplexityBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        assert bridge.name == "perplexity"
        assert bridge.site.base_url == "https://www.perplexity.ai"

    def test_copilot_bridge_construction(self, mock_engine, mock_session_mgr):
        """CopilotBridge 构造后 name 正确"""
        bridge = CopilotBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        assert bridge.name == "copilot"
        assert bridge.site.base_url == "https://copilot.microsoft.com"

    @pytest.mark.asyncio
    async def test_perplexity_send_message(self, mock_engine, mock_session_mgr, mock_page, mock_element):
        """Perplexity send_message 使用 mock 正常执行"""
        bridge = PerplexityBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = mock_page

        mock_page.evaluate = AsyncMock(side_effect=[
            "https://www.perplexity.ai",
            "Perplexity reply",
        ])
        mock_page.query_selector = AsyncMock(return_value=mock_element)
        mock_page.wait_for_selector = AsyncMock(return_value=mock_element)
        with patch.object(bridge, '_wait_for_stream_complete', AsyncMock(return_value=True)):
            result = await bridge.send_message("test")
            assert result.success is True
            assert result.content == "Perplexity reply"

    @pytest.mark.asyncio
    async def test_copilot_send_message(self, mock_engine, mock_session_mgr, mock_page, mock_element):
        """Copilot send_message 使用 mock 正常执行"""
        bridge = CopilotBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = mock_page

        mock_page.evaluate = AsyncMock(side_effect=[
            "https://copilot.microsoft.com",
            "Copilot reply",
        ])
        mock_page.query_selector = AsyncMock(return_value=mock_element)
        mock_page.wait_for_selector = AsyncMock(return_value=mock_element)
        with patch.object(bridge, '_wait_for_stream_complete', AsyncMock(return_value=True)):
            result = await bridge.send_message("test")
            assert result.success is True
            assert result.content == "Copilot reply"
