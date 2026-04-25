"""
会话管理器 — 管理 LLM 网页版的登录状态和 Cookie 持久化

核心能力：
  - 多个 LLM 站点的登录凭证管理
  - Cookie 保存/加载/刷新
  - 登录状态检测（判断是否需要重新登录）
  - 安全的凭证存储（环境变量 / .env 文件 / keyring）
"""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict


@dataclass
class LLMCredentials:
    """LLM 平台登录凭证"""
    email: str
    password: str
    # 部分平台支持 OAuth/SSO
    auth_method: str = "email"  # "email" | "google" | "github" | "microsoft"


@dataclass
class LLMSite:
    """LLM 站点配置"""
    name: str
    base_url: str
    login_url: str
    home_url: str
    # DOM 选择器
    login_selectors: dict = field(default_factory=lambda: {
        "email_input": "",
        "password_input": "",
        "submit_button": "",
        "login_success_indicator": "",
    })
    # 对话页面选择器
    chat_selectors: dict = field(default_factory=lambda: {
        "textarea": "",
        "send_button": "",
        "response_container": "",
        "stop_button": "",
    })

    @classmethod
    def chatgpt(cls) -> "LLMSite":
        return cls(
            name="chatgpt",
            base_url="https://chat.openai.com",
            login_url="https://chat.openai.com/auth/login",
            home_url="https://chat.openai.com",
            login_selectors={
                "email_input": 'input[name="email"]',
                "password_input": 'input[name="password"]',
                "submit_button": 'button[type="submit"]',
                "login_success_indicator": '[data-testid="conversation-turn-2"]',
            },
            chat_selectors={
                "textarea": "#prompt-textarea",
                "send_button": '[data-testid="send-button"]',
                "response_container": '[data-testid="conversation-turn-"]',
                "stop_button": '[data-testid="stop-button"]',
            },
        )

    @classmethod
    def claude(cls) -> "LLMSite":
        return cls(
            name="claude",
            base_url="https://claude.ai",
            login_url="https://claude.ai/login",
            home_url="https://claude.ai/new",
            login_selectors={
                "email_input": 'input[name="email"]',
                "password_input": 'input[name="password"]',
                "submit_button": 'button[type="submit"]',
                "login_success_indicator": '[data-testid="conversation-list"]',
            },
            chat_selectors={
                "textarea": '[data-testid="chat-input"]',
                "send_button": '[data-testid="send-button"]',
                "response_container": '[data-testid="message"]',
                "stop_button": '[data-testid="stop-button"]',
            },
        )

    @classmethod
    def deepseek(cls) -> "LLMSite":
        return cls(
            name="deepseek",
            base_url="https://chat.deepseek.com",
            login_url="https://chat.deepseek.com/sign_in",
            home_url="https://chat.deepseek.com",
            login_selectors={
                "email_input": 'input[name="email"]',
                "password_input": 'input[name="password"]',
                "submit_button": 'button[type="submit"]',
                "login_success_indicator": '[data-testid="chat-list"]',
            },
            chat_selectors={
                "textarea": "#chat-input",
                "send_button": '[data-testid="send-button"]',
                "response_container": '.ds-markdown',
                "stop_button": '[data-testid="stop-btn"]',
            },
        )

    @classmethod
    def gemini(cls) -> "LLMSite":
        return cls(
            name="gemini",
            base_url="https://gemini.google.com",
            login_url="https://gemini.google.com/app",
            home_url="https://gemini.google.com/app",
            login_selectors={
                "email_input": 'input[type="email"]',
                "password_input": 'input[type="password"]',
                "submit_button": '#identifierNext, #passwordNext',
                "login_success_indicator": 'input-placeholder="给 Gemini 输入提示词"',
            },
            chat_selectors={
                "textarea": 'div[contenteditable="true"]',
                "send_button": 'button[aria-label="发送"]',
                "response_container": '.response-content',
                "stop_button": 'button[aria-label="停止"]',
            },
        )

    @classmethod
    def grok(cls) -> "LLMSite":
        return cls(
            name="grok",
            base_url="https://grok.com",
            login_url="https://grok.com",
            home_url="https://grok.com",
            login_selectors={
                "email_input": 'input[name="email"]',
                "password_input": 'input[name="password"]',
                "submit_button": 'button[type="submit"]',
                "login_success_indicator": 'textarea[placeholder*="问任何问题"], div[contenteditable="true"]',
            },
            chat_selectors={
                "textarea": 'textarea[placeholder*="问任何问题"], div[contenteditable="true"]',
                "send_button": 'button[aria-label*="发送"]',
                "response_container": '.prose, .markdown, .message-content',
                "stop_button": 'button[aria-label*="停止"]',
            },
        )

    @classmethod
    def perplexity(cls) -> "LLMSite":
        return cls(
            name="perplexity",
            base_url="https://www.perplexity.ai",
            login_url="https://www.perplexity.ai/auth/login",
            home_url="https://www.perplexity.ai",
            login_selectors={
                "email_input": 'input[name="email"]',
                "password_input": 'input[name="password"]',
                "submit_button": 'button[type="submit"]',
                "login_success_indicator": 'textarea[placeholder*="Ask"]',
            },
            chat_selectors={
                "textarea": 'textarea[placeholder*="Ask"], div[contenteditable="true"]',
                "send_button": 'button[type="submit"]',
                "response_container": '.prose, .markdown',
                "stop_button": 'button[aria-label*="stop"]',
            },
        )
    
    @classmethod
    def kimi(cls) -> "LLMSite":
        return cls(
            name="kimi",
            base_url="https://kimi.moonshot.cn",
            login_url="https://kimi.moonshot.cn/login",
            home_url="https://kimi.moonshot.cn",
            login_selectors={
                "email_input": 'input[type="email"], input[name="email"], input[placeholder*="邮箱"]',
                "password_input": 'input[type="password"], input[name="password"]',
                "submit_button": 'button[type="submit"], button:has-text("登录")',
                "login_success_indicator": 'textarea[placeholder*="发送"], #chat-input',
            },
            chat_selectors={
                "textarea": 'textarea[placeholder*="发送"], #chat-input',
                "send_button": 'button[aria-label*="发送"]',
                "response_container": '.markdown-body, .message-content',
                "stop_button": 'button[aria-label*="停止"]',
            },
        )


    @classmethod
    def copilot(cls) -> "LLMSite":
        return cls(
            name="copilot",
            base_url="https://copilot.microsoft.com",
            login_url="https://copilot.microsoft.com",
            home_url="https://copilot.microsoft.com",
            login_selectors={
                "email_input": 'input[type="email"]',
                "password_input": 'input[type="password"]',
                "submit_button": 'button[type="submit"]',
                "login_success_indicator": 'textarea, #userInput',
            },
            chat_selectors={
                "textarea": 'textarea, #userInput',
                "send_button": 'button[aria-label*="Submit"]',
                "response_container": '.response-message-content, .message-content, .prose',
                "stop_button": 'button[aria-label*="Stop"]',
            },
        )


class SessionManager:
    """
    会话管理器
    
    凭证来源优先级：
      1. 环境变量 (LLM_EMAIL / LLM_PASSWORD / CHATGPT_EMAIL / ...)
      2. .env 文件 (项目根目录或用户目录)
      3. 显式传入
    """

    def __init__(self, session_dir: Optional[str] = None):
        self._session_dir = Path(session_dir or Path.home() / ".hermes-web-agent" / "sessions")
        self._session_dir.mkdir(parents=True, exist_ok=True)
        self._credentials: Dict[str, LLMCredentials] = {}
        self._load_from_env()

    def _load_from_env(self):
        """从环境变量加载凭证"""
        # ChatGPT
        email = os.environ.get("CHATGPT_EMAIL") or os.environ.get("LLM_EMAIL")
        password = os.environ.get("CHATGPT_PASSWORD") or os.environ.get("LLM_PASSWORD")
        if email and password:
            self._credentials["chatgpt"] = LLMCredentials(email=email, password=password)
        
        # Claude
        email = os.environ.get("CLAUDE_EMAIL")
        password = os.environ.get("CLAUDE_PASSWORD")
        if email and password:
            self._credentials["claude"] = LLMCredentials(email=email, password=password)
        
        # DeepSeek
        email = os.environ.get("DEEPSEEK_EMAIL")
        password = os.environ.get("DEEPSEEK_PASSWORD")
        if email and password:
            self._credentials["deepseek"] = LLMCredentials(email=email, password=password)
        
        # Gemini
        email = os.environ.get("GEMINI_EMAIL")
        password = os.environ.get("GEMINI_PASSWORD")
        if email and password:
            self._credentials["gemini"] = LLMCredentials(email=email, password=password, auth_method="google")
        
        # Grok
        email = os.environ.get("GROK_EMAIL")
        password = os.environ.get("GROK_PASSWORD")
        if email and password:
            self._credentials["grok"] = LLMCredentials(email=email, password=password)
        
        # Kimi
        email = os.environ.get("KIMI_EMAIL")
        password = os.environ.get("KIMI_PASSWORD")
        if email and password:
            self._credentials["kimi"] = LLMCredentials(email=email, password=password)
        
        # Perplexity
        email = os.environ.get("PERPLEXITY_EMAIL")
        password = os.environ.get("PERPLEXITY_PASSWORD")
        if email and password:
            self._credentials["perplexity"] = LLMCredentials(email=email, password=password, auth_method="google")
        
        # Copilot
        email = os.environ.get("COPILOT_EMAIL")
        password = os.environ.get("COPILOT_PASSWORD")
        if email and password:
            self._credentials["copilot"] = LLMCredentials(email=email, password=password)

    def set_credential(self, site: str, email: str, password: str, auth_method: str = "email"):
        """设置平台凭证"""
        self._credentials[site.lower()] = LLMCredentials(
            email=email, password=password, auth_method=auth_method
        )

    def get_credential(self, site: str) -> Optional[LLMCredentials]:
        """获取平台凭证"""
        return self._credentials.get(site.lower())

    def has_credential(self, site: str) -> bool:
        """检查是否有凭证"""
        return site.lower() in self._credentials

    def cookies_path(self, site: str) -> Path:
        """获取 Cookie 文件路径"""
        return self._session_dir / f"{site.lower()}.cookies.json"

    def has_valid_cookies(self, site: str) -> bool:
        """检查是否有有效 Cookie"""
        path = self.cookies_path(site)
        if not path.exists():
            return False
        try:
            cookies = json.loads(path.read_text())
            # 检查是否有会话 cookie 未过期
            return any(
                c.get("name") in ("__session", "session", "token", "__cf_bm")
                and (not c.get("expires") or c["expires"] > 0)
                for c in cookies
            )
        except (json.JSONDecodeError, OSError):
            return False

    def save_cookies(self, site: str, cookies: list):
        """保存 Cookie"""
        path = self.cookies_path(site)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cookies, indent=2, ensure_ascii=False))

    def load_cookies(self, site: str) -> list:
        """加载 Cookie"""
        path = self.cookies_path(site)
        if path.exists():
            return json.loads(path.read_text())
        return []

    def clear_cookies(self, site: str):
        """清除 Cookie（强制重新登录）"""
        path = self.cookies_path(site)
        if path.exists():
            path.unlink()
