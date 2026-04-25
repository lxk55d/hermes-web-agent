"""KimiBridge 集成测试（独立于 MockPage，避免与其他桥接器冲突）"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hermes_web_agent.bridges.kimi import KimiBridge


class TestKimiBridgeSpecific:
    """KimiBridge 构造、发送、新对话测试（使用纯 MagicMock）"""

    @pytest.fixture
    def kimi_el(self):
        """返回一个支持 await element.click() 的 mock element"""
        el = MagicMock()
        el.click = AsyncMock()
        el.type = AsyncMock()
        el.press = AsyncMock()
        el.is_visible = AsyncMock(return_value=True)
        el.text_content = AsyncMock(return_value="")
        return el

    @pytest.fixture
    def kimi_page(self):
        """返回一个 async-capable 的 mock page"""
        page = MagicMock()
        page.evaluate = AsyncMock(return_value="")
        page.query_selector = AsyncMock(return_value=None)
        page.wait_for_selector = AsyncMock(return_value=None)
        page.wait_for_timeout = AsyncMock()
        page.eval_on_selector = AsyncMock(return_value="")
        page.context = MagicMock()
        page.context.cookies = AsyncMock(return_value=[])
        page.context.add_cookies = AsyncMock()
        return page

    def test_kimi_bridge_construction(self, mock_engine, mock_session_mgr):
        """KimiBridge 构造后 name 正确"""
        bridge = KimiBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        assert bridge.name == "kimi"
        assert bridge.site.base_url == "https://kimi.moonshot.cn"

    @pytest.mark.asyncio
    async def test_kimi_send_message(self, mock_engine, mock_session_mgr, kimi_page, kimi_el):
        """Kimi send_message 使用 mock 正常执行"""
        bridge = KimiBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = kimi_page

        kimi_page.evaluate = AsyncMock(side_effect=[
            "https://kimi.moonshot.cn",
            "Kimi 的回复内容",
        ])
        kimi_page.wait_for_selector = AsyncMock(return_value=kimi_el)
        kimi_page.query_selector = AsyncMock(side_effect=[
            kimi_el,    # textarea
            kimi_el,    # send_button
            None,       # stop_button → 消失（完成标志）
        ])
        with patch.object(bridge, '_wait_for_stream_complete', AsyncMock(return_value=True)):
            result = await bridge.send_message("test")
            assert result.success is True
            assert result.content == "Kimi 的回复内容"

    @pytest.mark.asyncio
    async def test_kimi_send_message_empty_response(self, mock_engine, mock_session_mgr, kimi_page, kimi_el):
        """Kimi 空回复时 success=False"""
        bridge = KimiBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = kimi_page

        kimi_page.evaluate = AsyncMock(side_effect=[
            "https://kimi.moonshot.cn",
            "",
        ])
        kimi_page.wait_for_selector = AsyncMock(return_value=kimi_el)
        kimi_page.query_selector = AsyncMock(side_effect=[
            kimi_el,    # textarea
            kimi_el,    # send_button
            None,       # stop_button → 消失（完成标志）
        ])
        with patch.object(bridge, '_wait_for_stream_complete', AsyncMock(return_value=True)):
            result = await bridge.send_message("test")
            assert result.success is False
            assert result.content == "(空回复)"

    @pytest.mark.asyncio
    async def test_kimi_start_new_conversation(self, mock_engine, mock_session_mgr, kimi_page):
        """Kimi 开启新对话（无 new chat 按钮）"""
        bridge = KimiBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = kimi_page
        mock_engine.navigate = AsyncMock(return_value=True)

        # query_selector 返回 None → 没有 new_chat_btn → 走 navigate 路径
        kimi_page.query_selector = AsyncMock(return_value=None)

        result = await bridge.start_new_conversation()
        assert result is True
        mock_engine.navigate.assert_called_with("https://kimi.moonshot.cn")

    @pytest.mark.asyncio
    async def test_kimi_start_new_conversation_with_selector(self, mock_engine, mock_session_mgr, kimi_page, kimi_el):
        """Kimi 使用 selector 开启新对话（有 New Chat 按钮时）"""
        bridge = KimiBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = kimi_page

        kimi_page.query_selector = AsyncMock(return_value=kimi_el)
        result = await bridge.start_new_conversation()
        assert result is True
        kimi_el.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_kimi_start_new_conversation_no_page(self, mock_engine, mock_session_mgr):
        """Kimi start_new_conversation 在 page 为 None 时返回 False"""
        bridge = KimiBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = None
        result = await bridge.start_new_conversation()
        assert result is False

    @pytest.mark.asyncio
    async def test_kimi_get_conversation_history(self, mock_engine, mock_session_mgr, kimi_page):
        """Kimi 获取对话历史"""
        bridge = KimiBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = kimi_page

        # 设置 eval_on_selector 返回内容
        kimi_page.eval_on_selector = AsyncMock(return_value="对话历史内容")
        history = await bridge._get_text_safe('.markdown-body', default="历史")
        assert history == "对话历史内容"

    @pytest.mark.asyncio
    async def test_kimi_get_conversation_history_empty(self, mock_engine, mock_session_mgr, kimi_page):
        """Kimi 对话历史为空时返回默认值"""
        bridge = KimiBridge(engine=mock_engine, session_mgr=mock_session_mgr)
        bridge._page = kimi_page

        kimi_page.eval_on_selector = AsyncMock(return_value="")
        history = await bridge._get_text_safe('.markdown-body', default="历史")
        assert history == ""
