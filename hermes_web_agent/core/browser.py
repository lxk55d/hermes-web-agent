"""
浏览器引擎 — 基于 Playwright 的浏览器管理核心

支持多种 Chrome/Chromium 来源：
  1. Playwright 内置浏览器（自动下载）
  2. 系统安装的 Chrome（通过 executable_path 指定）
  3. Windows 上的 Chrome（在 WSL 中通过 /mnt/ 路径访问）
  4. 环境变量 CHROME_PATH 指定

参考 camofox-mcp 的 anti-detection 架构设计：
  - 通过配置禁用 CDP 暴露（避免被检测）
  - 随机化浏览器指纹（User-Agent、Viewport、时区、语言）
  - 自动等待策略（模仿人类操作节奏）
  - Cookie 持久化（复用登录会话）
  - 失败重试与恢复机制
"""
import asyncio
import json
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Playwright 延迟导入
try:
    from playwright.async_api import (
        async_playwright, Page, Browser, BrowserContext,
        TimeoutError as PlaywrightTimeout
    )
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Page = None
    Browser = None


# ── 用户代理清单（最新浏览器版本） ──────────────────────────
USER_AGENTS = [
    # Chrome 124+ on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    # Chrome 124+ on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.2478.80",
]

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 2560, "height": 1440},
]

TIMEZONES = [
    "Asia/Shanghai",
    "Asia/Shanghai",
    "America/New_York",
    "Europe/London",
]

LOCALES = [
    "zh-CN",
    "zh-CN",
    "en-US",
    "en-GB",
]


@dataclass
class BrowserConfig:
    """浏览器实例配置"""
    headless: bool = False
    user_data_dir: Optional[str] = None
    proxy: Optional[str] = None
    viewport: Optional[dict] = None
    user_agent: Optional[str] = None
    locale: Optional[str] = None
    timezone_id: Optional[str] = None
    slow_mo: int = 50  # 人类操作间隔(ms)
    navigation_timeout: int = 30000  # 30s
    action_timeout: int = 10000     # 10s
    executable_path: Optional[str] = None  # Chrome/Chromium 可执行文件路径
    
    @classmethod
    def create_random(cls, headless: bool = False) -> "BrowserConfig":
        """创建随机化配置（反检测）"""
        return cls(
            headless=headless,
            viewport=random.choice(VIEWPORTS),
            user_agent=random.choice(USER_AGENTS),
            locale=random.choice(LOCALES),
            timezone_id=random.choice(TIMEZONES),
        )


class BrowserEngine:
    """
    浏览器引擎 — 管理 Playwright 浏览器实例
    
    功能：
      - 启动/关闭浏览器
      - Cookie 持久化
      - 截图
      - 反检测注入
      - 页面操控（导航、点击、输入、等待）
    """
    
    def __init__(self, config: Optional[BrowserConfig] = None):
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError(
                "playwright 未安装。请运行: pip install playwright && playwright install chromium"
            )
        self.config = config or BrowserConfig.create_random()
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._cookies_path: Optional[Path] = None
        self._anti_detect_scripts = self._build_anti_detect_scripts()
        
        # 会话存储目录
        self._session_dir = Path.home() / ".hermes-web-agent" / "sessions"
        self._session_dir.mkdir(parents=True, exist_ok=True)
        
        self._blocked_domains = [
            "google-analytics.com",
            "doubleclick.net",
            "googlesyndication.com",
            "facebook.com/tr",
            "amazon-adsystem.com",
        ]
    
    def _build_anti_detect_scripts(self) -> list:
        """构建反检测 JavaScript 注入脚本列表"""
        return [
            # 覆盖 navigator.webdriver（Playwright 默认已做，但双重保险）
            """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
                configurable: true,
            });
            """,
            # 覆盖 navigator.plugins（自动化浏览器插件少）
            """
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
                configurable: true,
            });
            """,
            # 覆盖 navigator.languages（真实用户通常多语言）
            """
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en'],
                configurable: true,
            });
            """,
            # 覆盖 chrome.runtime（检测 headless）
            """
            window.chrome = window.chrome || {};
            window.chrome.runtime = window.chrome.runtime || {};
            """,
            # 覆盖 Permissions API
            """
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
            );
            """,
        ]
    
    async def _block_trackers(self, page: Page):
        """拦截跟踪类请求"""
        await page.route(
            lambda url: any(d in url for d in self._blocked_domains),
            lambda route: route.abort()
        )
    
    async def start(self, headless: bool = False) -> Page:
        """启动浏览器并返回页面对象"""
        self._playwright = await async_playwright().start()
        
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            f"--window-size={self.config.viewport['width']},{self.config.viewport['height']}",
        ]
        
        if self.config.proxy:
            launch_args.append(f"--proxy-server={self.config.proxy}")
        
        launch_kwargs = {
            "headless": headless or self.config.headless,
            "args": launch_args,
            "slow_mo": self.config.slow_mo,
        }
        
        # 支持自定义 Chrome 路径（如 Windows 上的 Chrome）
        executable_path = (
            self.config.executable_path
            or os.environ.get("CHROME_PATH")
        )
        if executable_path:
            launch_kwargs["executable_path"] = executable_path
        
        self._browser = await self._playwright.chromium.launch(**launch_kwargs)
        
        # 创建上下文（独立隔离）
        context_args = {
            "viewport": self.config.viewport,
            "locale": self.config.locale or "zh-CN",
            "timezone_id": self.config.timezone_id or "Asia/Shanghai",
            "no_viewport": False,
        }
        if self.config.user_agent:
            context_args["user_agent"] = self.config.user_agent
        
        self._context = await self._browser.new_context(**context_args)
        
        # 注入反检测脚本
        await self._context.add_init_script("\n".join(self._anti_detect_scripts))
        
        # 创建页面
        self._page = await self._context.new_page()
        self._page.set_default_navigation_timeout(self.config.navigation_timeout)
        self._page.set_default_timeout(self.config.action_timeout)
        
        await self._block_trackers(self._page)
        
        # 加载 Cookie
        if self._cookies_path and self._cookies_path.exists():
            try:
                cookies = json.loads(self._cookies_path.read_text())
                await self._context.add_cookies(cookies)
            except Exception:
                pass  # Cookie 失效则忽略
        
        return self._page
    
    async def close(self):
        """关闭浏览器并保存会话"""
        if self._page:
            try:
                self._page = None
            except Exception:
                pass
        
        if self._context and self._cookies_path:
            try:
                cookies = await self._context.cookies()
                self._cookies_path.parent.mkdir(parents=True, exist_ok=True)
                self._cookies_path.write_text(json.dumps(cookies, indent=2))
            except Exception:
                pass
        
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
        
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
        
        self._context = None
        self._browser = None
        self._playwright = None
    
    async def navigate(self, url: str, wait_until: str = "networkidle") -> bool:
        """导航到 URL，等待页面加载完成"""
        if not self._page:
            raise RuntimeError("浏览器未启动，请先调用 start()")
        
        try:
            resp = await self._page.goto(url, wait_until=wait_until)
            return resp is not None and resp.ok
        except PlaywrightTimeout:
            return False
    
    async def screenshot(self, path: Optional[str] = None) -> bytes:
        """截取当前页面截图"""
        if not self._page:
            raise RuntimeError("浏览器未启动")
        
        if path:
            await self._page.screenshot(path=path, full_page=False)
            with open(path, "rb") as f:
                return f.read()
        else:
            return await self._page.screenshot(full_page=False)
    
    async def get_text(self) -> str:
        """获取页面可见文本"""
        if not self._page:
            raise RuntimeError("浏览器未启动")
        return await self._page.evaluate("document.body.innerText")
    
    async def get_title(self) -> str:
        """获取页面标题"""
        if not self._page:
            raise RuntimeError("浏览器未启动")
        return await self._page.title()
    
    async def wait_for_selector(self, selector: str, timeout: int = 10000) -> bool:
        """等待元素出现"""
        if not self._page:
            raise RuntimeError("浏览器未启动")
        try:
            await self._page.wait_for_selector(selector, timeout=timeout)
            return True
        except PlaywrightTimeout:
            return False
    
    async def click(self, selector: str) -> bool:
        """点击元素（带人类模拟）"""
        if not self._page:
            raise RuntimeError("浏览器未启动")
        try:
            # 模仿人类点击前的微小延迟
            await asyncio.sleep(random.uniform(0.1, 0.3))
            await self._page.click(selector)
            return True
        except Exception:
            return False
    
    async def type_text(self, selector: str, text: str, human_like: bool = True) -> bool:
        """输入文本（可模拟人类打字节奏）"""
        if not self._page:
            raise RuntimeError("浏览器未启动")
        try:
            await self._page.click(selector)
            await self._page.fill(selector, "")
            
            if human_like:
                # 逐字输入，模拟人类打字
                for char in text:
                    await self._page.type(selector, char, delay=random.randint(30, 120))
            else:
                await self._page.fill(selector, text)
            return True
        except Exception:
            return False
    
    async def evaluate(self, js_code: str):
        """执行 JavaScript"""
        if not self._page:
            raise RuntimeError("浏览器未启动")
        return await self._page.evaluate(js_code)
    
    async def wait_for_navigation(self, timeout: int = 15000) -> bool:
        """等待页面导航完成"""
        if not self._page:
            raise RuntimeError("浏览器未启动")
        try:
            await self._page.wait_for_load_state("networkidle", timeout=timeout)
            return True
        except PlaywrightTimeout:
            return False
    
    async def scroll_to_bottom(self):
        """滚动到底部（触发懒加载）"""
        if not self._page:
            raise RuntimeError("浏览器未启动")
        await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(random.uniform(0.5, 1.0))
    
    def set_session_name(self, name: str):
        """设置会话名称（用于 Cookie 存储）"""
        self._cookies_path = self._session_dir / f"{name}.cookies.json"


# 快捷函数
async def create_engine(
    headless: bool = False,
    session_name: Optional[str] = None,
    user_data_dir: Optional[str] = None,
    proxy: Optional[str] = None,
) -> BrowserEngine:
    """快速创建并启动浏览器引擎"""
    config = BrowserConfig.create_random(headless=headless)
    if proxy:
        config.proxy = proxy
    
    engine = BrowserEngine(config)
    if session_name:
        engine.set_session_name(session_name)
    
    await engine.start(headless=headless)
    return engine
