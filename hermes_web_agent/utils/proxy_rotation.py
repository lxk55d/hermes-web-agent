"""
代理轮换系统 — ProxyRotation

管理多个 HTTP/SOCKS 代理，实现自动轮换、健康检查和故障转移。

功能：
  1. 多代理池管理（HTTP / HTTPS / SOCKS5）
  2. 自动轮换策略（顺序 / 随机 / 最少使用 / 最快响应）
  3. 健康检查（定时测试代理连通性）
  4. 故障自动转移（死代理自动标记剔除）
  5. 代理来源（静态列表 / 环境变量 / 文件 / API）

用法:
    pool = ProxyPool()
    pool.add_proxy("http://user:pass@host:8080")
    pool.add_proxy("socks5://127.0.0.1:1080")
    
    proxy = pool.get_proxy(strategy="random")  # 随机选一个健康代理
    config = BrowserConfig(proxy=proxy.url)
"""
import asyncio
import json
import os
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Callable


@dataclass
class ProxyInfo:
    """代理信息"""
    url: str  # 完整代理 URL
    protocol: str = "http"  # http / https / socks5 / socks4
    host: str = ""
    port: int = 0
    username: Optional[str] = None
    password: Optional[str] = None
    country: Optional[str] = None  # 代理所在国家（可选）
    latency_ms: float = 0.0       # 最近延迟
    last_used: float = 0.0        # 上次使用时间戳
    fail_count: int = 0           # 连续失败次数
    max_fails: int = 3            # 最大允许失败次数
    healthy: bool = True          # 是否健康
    
    def __post_init__(self):
        if not self.host and not self.url.startswith("direct://"):
            self._parse_url()
    
    def _parse_url(self):
        """解析代理 URL"""
        pattern = r"(?P<protocol>\w+)://(?:(?P<user>[^:@]+)(?::(?P<pass>[^@]+))?@)?(?P<host>[^:]+)(?::(?P<port>\d+))?"
        m = re.match(pattern, self.url)
        if m:
            self.protocol = m.group("protocol") or self.protocol
            self.host = m.group("host") or ""
            self.port = int(m.group("port") or 0)
            self.username = m.group("user") or self.username
            self.password = m.group("pass") or self.password
    
    def mark_failure(self):
        """标记一次失败"""
        self.fail_count += 1
        if self.fail_count >= self.max_fails:
            self.healthy = False
    
    def mark_success(self):
        """标记成功（重置失败计数）"""
        self.fail_count = 0
        self.last_used = time.time()
    
    def to_playwright_format(self) -> Optional[str]:
        """转换为 Playwright 兼容的代理字符串"""
        if self.url.startswith("direct://"):
            return None
        return self.url


class ProxyPool:
    """
    代理池管理器
    
    支持多个代理来源：
      - 静态添加 (add_proxy)
      - 环境变量 (PROXY_LIST, PROXY_URL)
      - 文件 (load_from_file)
      - 自定义来源 (add_source)
    """
    
    def __init__(self, health_check_interval: int = 300):
        self._proxies: List[ProxyInfo] = []
        self._use_count: Dict[str, int] = {}  # url -> 使用次数
        self._health_check_interval = health_check_interval
        self._last_health_check = 0.0
        self._loaded_from_env = False
    
    def add_proxy(self, url: str, max_fails: int = 3) -> ProxyInfo:
        """添加一个代理到池中"""
        proxy = ProxyInfo(url=url, max_fails=max_fails)
        self._proxies.append(proxy)
        self._use_count[url] = 0
        return proxy
    
    def add_proxies(self, urls: List[str]):
        """批量添加代理"""
        for url in urls:
            self.add_proxy(url)
    
    def remove_proxy(self, url: str) -> bool:
        """移除代理"""
        for i, p in enumerate(self._proxies):
            if p.url == url:
                self._proxies.pop(i)
                self._use_count.pop(url, None)
                return True
        return False
    
    def get_proxy(
        self,
        strategy: str = "random",
        require_healthy: bool = True,
    ) -> Optional[ProxyInfo]:
        """
        获取一个代理（按策略选择）
        
        策略:
          - "random":     随机选取健康代理
          - "round_robin": 轮询选取
          - "least_used":  使用次数最少的
          - "fastest":     延迟最低的
        """
        self._ensure_env_loaded()
        
        candidates = [p for p in self._proxies if not require_healthy or p.healthy]
        if not candidates:
            return None
        
        if strategy == "random":
            proxy = random.choice(candidates)
        elif strategy == "round_robin":
            # 按使用次数排序，选最少的
            candidates.sort(key=lambda p: self._use_count.get(p.url, 0))
            proxy = candidates[0]
        elif strategy == "least_used":
            candidates.sort(key=lambda p: self._use_count.get(p.url, 0))
            proxy = candidates[0]
        elif strategy == "fastest":
            candidates.sort(key=lambda p: p.latency_ms if p.latency_ms > 0 else float("inf"))
            proxy = candidates[0]
        else:
            proxy = random.choice(candidates)
        
        self._use_count[proxy.url] = self._use_count.get(proxy.url, 0) + 1
        proxy.last_used = time.time()
        return proxy
    
    def get_all_proxies(self, healthy_only: bool = False) -> List[ProxyInfo]:
        """获取所有代理"""
        self._ensure_env_loaded()
        if healthy_only:
            return [p for p in self._proxies if p.healthy]
        return list(self._proxies)
    
    def count(self, healthy_only: bool = True) -> int:
        """返回代理数量"""
        return len(self.get_all_proxies(healthy_only=healthy_only))
    
    def _ensure_env_loaded(self):
        """从环境变量加载代理（懒加载一次）"""
        if self._loaded_from_env:
            return
        self._loaded_from_env = True
        
        # PROXY_URL 单代理
        proxy_url = os.environ.get("PROXY_URL")
        if proxy_url:
            self.add_proxy(proxy_url)
        
        # PROXY_LIST JSON 多代理
        proxy_list = os.environ.get("PROXY_LIST")
        if proxy_list:
            try:
                urls = json.loads(proxy_list)
                if isinstance(urls, list):
                    self.add_proxies(urls)
            except (json.JSONDecodeError, TypeError):
                pass
        
        # PROXY_FILE 文件路径
        proxy_file = os.environ.get("PROXY_FILE")
        if proxy_file:
            path = Path(proxy_file)
            if path.exists():
                self.load_from_file(str(path))
    
    def load_from_file(self, path: str):
        """从文件加载代理列表（每行一个代理URL）"""
        p = Path(path)
        if not p.exists():
            return
        urls = []
        for line in p.read_text().strip().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
        self.add_proxies(urls)
    
    def load_from_api(self, api_url: str, parser: Optional[Callable] = None):
        """
        从 API 加载代理
        可通过 parser 自定义解析逻辑
        默认假设返回 JSON 数组: ["http://...", ...]
        """
        # 懒导入
        import urllib.request
        try:
            resp = urllib.request.urlopen(api_url, timeout=10)
            data = json.loads(resp.read().decode())
            if parser:
                urls = parser(data)
            elif isinstance(data, list):
                urls = data
            else:
                urls = []
            self.add_proxies(urls)
        except Exception:
            pass
    
    async def check_health(self, proxy: ProxyInfo, timeout: float = 5.0) -> bool:
        """
        检查单个代理健康状态
        连接一个公共目标（http://httpbin.org/ip）测试连通性
        """
        try:
            import aiohttp
            if proxy.protocol in ("http", "https"):
                pass
            
            t0 = time.time()
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "http://httpbin.org/ip",
                    proxy=proxy.url if not proxy.url.startswith("direct://") else None,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as resp:
                    proxy.latency_ms = (time.time() - t0) * 1000
                    if resp.status == 200:
                        proxy.mark_success()
                        return True
                    proxy.mark_failure()
                    return False
        except Exception:
            proxy.mark_failure()
            return False
    
    async def health_check_all(self, force: bool = False):
        """健康检查所有代理"""
        now = time.time()
        if not force and (now - self._last_health_check) < self._health_check_interval:
            return
        
        self._last_health_check = now
        tasks = [self.check_health(p) for p in self._proxies]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    def healthy_count(self) -> int:
        """健康代理数量"""
        return sum(1 for p in self._proxies if p.healthy)
    
    def to_dict(self) -> list:
        """导出为字典列表（序列化）"""
        return [
            {
                "url": p.url,
                "protocol": p.protocol,
                "healthy": p.healthy,
                "latency_ms": round(p.latency_ms, 1),
                "fail_count": p.fail_count,
                "use_count": self._use_count.get(p.url, 0),
            }
            for p in self._proxies
        ]
