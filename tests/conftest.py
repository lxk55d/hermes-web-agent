"""测试 tools test fixtures — MockPlaywright"""
from unittest.mock import AsyncMock, MagicMock

import pytest


class MockPage:
    """Mock Playwright Page 对象"""

    def __init__(self):
        self.url = "about:blank"
        self._content = ""
        self._selectors = {}
        self._cookies = []
        self.context = MagicMock()
        self.context.cookies = AsyncMock(return_value=[])
        self.context.add_cookies = AsyncMock()
        self._default_timeout = 30000

    async def goto(self, url, **kwargs):
        self.url = url
        return MagicMock(ok=True)

    async def title(self):
        return "Test Page"

    async def evaluate(self, js_code):
        if "location.href" in js_code:
            return self.url
        if "innerText" in js_code or "textContent" in js_code:
            return self._content
        if "model_name" in js_code or "model-tag" in js_code:
            return ""
        return ""

    async def query_selector(self, selector):
        return MagicMock() if selector in self._selectors else None

    async def wait_for_selector(self, selector, **kwargs):
        if selector in self._selectors:
            return MagicMock()
        return None

    async def click(self, selector, **kwargs):
        return None

    async def fill(self, selector, text, **kwargs):
        return None

    async def type(self, selector, text, delay=0):
        return None

    async def press(self, key):
        return None

    def set_default_navigation_timeout(self, timeout):
        self._default_timeout = timeout

    def set_default_timeout(self, timeout):
        self._default_timeout = timeout

    async def screenshot(self, **kwargs):
        return b"mock_screenshot_bytes"

    def set_content(self, content: str):
        self._content = content

    def add_selector(self, selector: str):
        self._selectors[selector] = True


@pytest.fixture
def mock_page():
    return MockPage()


@pytest.fixture
def mock_engine(mock_page):
    """创建一个 mock BrowserEngine 实例"""
    from unittest.mock import AsyncMock, MagicMock

    engine = MagicMock()
    engine.start = AsyncMock(return_value=mock_page)
    engine.close = AsyncMock()
    engine.navigate = AsyncMock(return_value=True)
    engine.click = AsyncMock(return_value=True)
    engine.type_text = AsyncMock(return_value=True)
    engine.wait_for_navigation = AsyncMock(return_value=True)
    engine.wait_for_selector = AsyncMock(return_value=True)
    engine.get_text = AsyncMock(return_value="")
    engine.get_title = AsyncMock(return_value="Test")
    engine.screenshot = AsyncMock(return_value=b"data")
    engine.evaluate = AsyncMock(return_value="")
    engine.scroll_to_bottom = AsyncMock()
    engine.set_session_name = MagicMock()
    engine._page = mock_page
    engine.config = MagicMock()
    engine.config.viewport = {"width": 1920, "height": 1080}
    engine._cookies_path = None
    engine._session_dir = None
    return engine


@pytest.fixture
def mock_session_mgr():
    """创建一个 mock SessionManager 实例"""
    from unittest.mock import MagicMock
    mgr = MagicMock()
    mgr.get_credential = MagicMock()
    mgr.has_credential = MagicMock(return_value=True)
    mgr.save_cookies = MagicMock()
    mgr.load_cookies = MagicMock(return_value=[])
    mgr.has_valid_cookies = MagicMock(return_value=False)
    mgr.cookies_path = MagicMock()
    mgr.clear_cookies = MagicMock()
    cred = MagicMock()
    cred.email = "test@example.com"
    cred.password = "password123"
    mgr.get_credential.return_value = cred
    return mgr
