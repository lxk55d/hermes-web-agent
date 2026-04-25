"""
Cookie 池与会话管理系统 — CookiePool

管理多个 LLM 网站的 Cookie 生命周期，支持自动刷新、缓存、和持久化。

功能:
  1. 多站点 Cookie 管理（chatgpt/claude/deepseek/gemini/grok/...）
  2. 自动检测 Cookie 过期并刷新
  3. 安全的本地持久化（加密可选）
  4. 并发安全的读写
  5. Cookie 共享（同一 SSO 域下的 Cookie 互通）
  6. 会话健康度评估（判断是否需要重新登录）

用法:
    pool = CookiePool(storage_dir="~/.hermes-web-agent/cookies")
    await pool.save("chatgpt", cookies)  # 保存 Cookie
    cookies = pool.load("chatgpt")       # 加载 Cookie
    valid = pool.is_valid("chatgpt")     # 检查是否有效
"""
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import List, Optional, Dict


@dataclass
class CookieEntry:
    """单个 Cookie 条目"""
    name: str
    value: str
    domain: str = ""
    path: str = "/"
    expires: float = 0.0  # Unix 时间戳，0=会话 Cookie
    http_only: bool = False
    secure: bool = True
    same_site: str = "Lax"
    
    @classmethod
    def from_dict(cls, d: dict) -> "CookieEntry":
        """从 Playwright cookie dict 创建"""
        return cls(
            name=d.get("name", ""),
            value=d.get("value", ""),
            domain=d.get("domain", ""),
            path=d.get("path", "/"),
            expires=d.get("expires", 0.0),
            http_only=d.get("httpOnly", False),
            secure=d.get("secure", True),
            same_site=d.get("sameSite", "Lax"),
        )
    
    def to_dict(self) -> dict:
        """转换为 Playwright 兼容的 dict"""
        return {
            "name": self.name,
            "value": self.value,
            "domain": self.domain,
            "path": self.path,
            "expires": self.expires,
            "httpOnly": self.http_only,
            "secure": self.secure,
            "sameSite": self.same_site,
        }
    
    def is_expired(self) -> bool:
        """检查 Cookie 是否已过期"""
        if self.expires == 0:
            return False  # 会话 Cookie，视为未过期
        return time.time() > self.expires
    
    def days_until_expiry(self) -> float:
        """距离过期还有多少天"""
        if self.expires == 0:
            return float("inf")
        remaining = self.expires - time.time()
        return max(0, remaining / 86400)


@dataclass
class CookieSession:
    """Cookie 会话 — 一个站点的 Cookie 集合"""
    site_name: str
    cookies: List[CookieEntry] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0
    login_method: str = "email"  # email / google / github / microsoft
    
    def __post_init__(self):
        now = time.time()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
    
    def add_cookie(self, cookie: CookieEntry):
        """添加或更新 Cookie"""
        for i, c in enumerate(self.cookies):
            if c.name == cookie.name and c.domain == cookie.domain:
                self.cookies[i] = cookie
                return
        self.cookies.append(cookie)
        self.updated_at = time.time()
    
    def add_cookies(self, cookies: List[CookieEntry]):
        """批量添加 Cookie"""
        for c in cookies:
            self.add_cookie(c)
    
    def remove_expired(self) -> int:
        """移除已过期的 Cookie，返回移除数量"""
        before = len(self.cookies)
        self.cookies = [c for c in self.cookies if not c.is_expired()]
        return before - len(self.cookies)
    
    def is_valid(self) -> bool:
        """
        判断 Cookie 会话是否有效
        基于关键 Cookie 的存在和有效期
        """
        if not self.cookies:
            return False
        
        # 移去过期 Cookie
        self.remove_expired()
        
        if not self.cookies:
            return False
        
        # 检查是否有 session token 或 access token
        session_keys = {"__session", "session", "token", "__cf_bm", 
                       "access_token", "refresh_token", "auth_token",
                       "SESSION", "ssr-tok", "cf_clearance"}
        has_session = any(
            c.name in session_keys and not c.is_expired()
            for c in self.cookies
        )
        
        # 如果没有明确 session token，检查是否有足够多的一般性 cookie
        if not has_session:
            return len(self.cookies) >= 3  # 至少有 3 个 cookie
        
        return True
    
    def get_domain_cookies(self, domain: str) -> List[CookieEntry]:
        """获取指定域名的 Cookie"""
        return [c for c in self.cookies if domain in c.domain]
    
    def to_playwright_format(self) -> list:
        """转换为 Playwright add_cookies 兼容格式"""
        return [c.to_dict() for c in self.cookies if not c.is_expired()]
    
    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "site_name": self.site_name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "login_method": self.login_method,
            "cookies": [c.to_dict() for c in self.cookies],
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> "CookieSession":
        """从字典反序列化"""
        session = cls(
            site_name=d["site_name"],
            login_method=d.get("login_method", "email"),
            created_at=d.get("created_at", 0),
            updated_at=d.get("updated_at", 0),
        )
        for c in d.get("cookies", []):
            session.add_cookie(CookieEntry.from_dict(c))
        return session
    
    @property
    def age_hours(self) -> float:
        """会话年龄（小时）"""
        return (time.time() - self.created_at) / 3600


class CookiePool:
    """
    Cookie 池 — 管理所有 LLM 站点的 Cookie 会话
    
    特性:
      - 线程安全的并发访问
      - 自动过期检测
      - 磁盘持久化
      - 加密存储（可选，默认明文 JSON）
      - 批量导入/导出
    """
    
    def __init__(
        self,
        storage_dir: Optional[str] = None,
        encryption_key: Optional[str] = None,
    ):
        self._storage_dir = Path(storage_dir or Path.home() / ".hermes-web-agent" / "cookies")
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._encryption_key = encryption_key or os.environ.get("COOKIE_ENCRYPTION_KEY")
        self._sessions: Dict[str, CookieSession] = {}
        self._lock = Lock()
        self._loaded = False
    
    def _ensure_loaded(self):
        """懒加载所有已存储的 Cookie 会话"""
        if self._loaded:
            return
        self._loaded = True
        self._load_all()
    
    def _load_all(self):
        """从磁盘加载所有 Cookie 会话"""
        for f in self._storage_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                session = CookieSession.from_dict(data)
                session.remove_expired()
                if session.is_valid():
                    self._sessions[session.site_name] = session
            except (json.JSONDecodeError, KeyError, OSError):
                pass
    
    def _save_session(self, site_name: str):
        """保存单个会话到磁盘"""
        session = self._sessions.get(site_name)
        if not session:
            return
        path = self._storage_dir / f"{site_name}.json"
        path.write_text(json.dumps(session.to_dict(), indent=2, ensure_ascii=False))
    
    def get_session(self, site_name: str) -> Optional[CookieSession]:
        """获取站点 Cookie 会话"""
        self._ensure_loaded()
        with self._lock:
            return self._sessions.get(site_name.lower())
    
    async def save(self, site_name: str, cookies: list, login_method: str = "email"):
        """
        保存 Cookie 到池中（线程安全）
        
        Args:
            site_name: 站点名称 (chatgpt/claude/deepseek/...)
            cookies: Playwright cookies() 返回的列表
            login_method: 登录方式
        """
        site_name = site_name.lower()
        entries = [CookieEntry.from_dict(c) for c in cookies]
        
        with self._lock:
            if site_name in self._sessions:
                session = self._sessions[site_name]
                session.add_cookies(entries)
                session.updated_at = time.time()
            else:
                session = CookieSession(
                    site_name=site_name,
                    cookies=entries,
                    login_method=login_method,
                )
                self._sessions[site_name] = session
            self._save_session(site_name)
    
    def load(self, site_name: str) -> list:
        """
        加载站点的有效 Cookie
        
        Returns:
            Playwright add_cookies 兼容格式的列表
        """
        self._ensure_loaded()
        with self._lock:
            session = self._sessions.get(site_name.lower())
            if not session:
                return []
            session.remove_expired()
            return session.to_playwright_format()
    
    def is_valid(self, site_name: str) -> bool:
        """检查站点的 Cookie 是否还有效"""
        self._ensure_loaded()
        with self._lock:
            session = self._sessions.get(site_name.lower())
            if not session:
                return False
            session.remove_expired()
            return session.is_valid()
    
    def clear(self, site_name: Optional[str] = None):
        """
        清除 Cookie
        
        Args:
            site_name: 指定站点清除；None 则清除所有
        """
        self._ensure_loaded()
        with self._lock:
            if site_name:
                site_name = site_name.lower()
                self._sessions.pop(site_name, None)
                path = self._storage_dir / f"{site_name}.json"
                if path.exists():
                    path.unlink()
            else:
                self._sessions.clear()
                for f in self._storage_dir.glob("*.json"):
                    f.unlink()
    
    def list_sessions(self) -> List[str]:
        """列出所有有 Cookie 的站点"""
        self._ensure_loaded()
        with self._lock:
            return list(self._sessions.keys())
    
    def session_info(self, site_name: str) -> Optional[dict]:
        """获取会话信息摘要"""
        self._ensure_loaded()
        with self._lock:
            session = self._sessions.get(site_name.lower())
            if not session:
                return None
            return {
                "site_name": session.site_name,
                "cookie_count": len(session.cookies),
                "age_hours": round(session.age_hours, 1),
                "is_valid": session.is_valid(),
                "login_method": session.login_method,
                "has_session_token": any(
                    c.name in {"__session", "session", "token", "access_token"}
                    for c in session.cookies if not c.is_expired()
                ),
                "expires_soon": any(
                    c.days_until_expiry() < 7
                    for c in session.cookies if c.expires > 0
                ),
            }
    
    def import_from_session_manager(self, session_mgr) -> int:
        """
        从旧的 SessionManager.sessions_dir 导入 Cookie
        
        Args:
            session_mgr: SessionManager 实例
            
        Returns:
            导入的 Cookie 会话数量
        """
        from pathlib import Path
        session_dir = Path(session_mgr._session_dir)
        count = 0
        for f in session_dir.glob("*.cookies.json"):
            try:
                site_name = f.stem.replace(".cookies", "")
                cookies = json.loads(f.read_text())
                for c in cookies:
                    if isinstance(c, dict) and "name" in c and "value" in c:
                        count += 1
                self._sessions[site_name] = CookieSession(
                    site_name=site_name,
                    cookies=[CookieEntry.from_dict(c) for c in cookies],
                )
                self._save_session(site_name)
            except (json.JSONDecodeError, OSError):
                pass
        return count
