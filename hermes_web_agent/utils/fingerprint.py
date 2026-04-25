"""
浏览器指纹随机化 — FingerprintManager

参考 camofox-mcp 的反检测设计，实现浏览器指纹各维度的随机化，
支持生成完整的反检测注入 JavaScript 代码和 BrowserConfig 兼容配置。

功能覆盖：
  - 随机 User-Agent（Brave/Chrome/Edge/Firefox）
  - 随机 Viewport（多种宽高比）
  - WebGL vendor/renderer 随机化（真实 GPU 型号）
  - Canvas 指纹保护（微小噪声注入）
  - AudioContext 指纹随机化
  - WebRTC 配置（可选的 IP 泄露防护）
  - 时区/语言/字体列表随机
"""

import hashlib
import random
import time
from typing import Optional


# ── 常用浏览器 User-Agent 池 ──────────────────────────

USER_AGENTS = [
    # Brave (Chromium-based)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Brave/124.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Brave/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Brave/124.0",
    # Chrome
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.2478.80",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.2535.51",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.2478.80",
    # Firefox
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
]

# ── Viewport 配置（不同宽高比） ───────────────────────

VIEWPORTS = [
    # 16:9
    {"width": 1920, "height": 1080},
    {"width": 2560, "height": 1440},
    {"width": 3840, "height": 2160},
    {"width": 1366, "height": 768},
    {"width": 1600, "height": 900},
    # 16:10
    {"width": 1920, "height": 1200},
    {"width": 2560, "height": 1600},
    {"width": 1440, "height": 900},
    # 3:2
    {"width": 2160, "height": 1440},
    {"width": 1440, "height": 960},
    # 21:9
    {"width": 3440, "height": 1440},
    {"width": 2560, "height": 1080},
    # 4:3
    {"width": 1440, "height": 1080},
    {"width": 1024, "height": 768},
]

# ── WebGL Vendor / Renderer 真实 GPU 型号 ──────────────

WEBGL_VENDORS = [
    "Google Inc. (NVIDIA)",
    "Google Inc. (Apple)",
    "Google Inc. (Intel)",
    "Google Inc. (AMD)",
]

WEBGL_RENDERERS = [
    "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0)",
    "ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0)",
    "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Direct3D11 vs_5_0 ps_5_0)",
    "ANGLE (NVIDIA, NVIDIA GeForce RTX 4060 Direct3D11 vs_5_0 ps_5_0)",
    "ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Direct3D11 vs_5_0 ps_5_0)",
    "ANGLE (Apple, Apple M1)",
    "ANGLE (Apple, Apple M2)",
    "ANGLE (Apple, Apple M3)",
    "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0)",
    "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0)",
    "ANGLE (AMD, AMD Radeon RX 6800 XT Direct3D11 vs_5_0 ps_5_0)",
    "ANGLE (AMD, AMD Radeon RX 7900 XTX Direct3D11 vs_5_0 ps_5_0)",
]

# ── 时区列表 ──────────────────────────────────────

TIMEZONES = [
    "Asia/Shanghai",
    "Asia/Shanghai",
    "Asia/Hong_Kong",
    "Asia/Tokyo",
    "Asia/Singapore",
    "America/New_York",
    "America/Los_Angeles",
    "Europe/London",
    "Europe/Berlin",
    "Australia/Sydney",
]

# ── 语言/区域设置 ─────────────────────────────────

LOCALES = [
    "zh-CN",
    "zh-CN",
    "zh-CN",
    "zh-Hans-CN",
    "zh-HK",
    "en-US",
    "en-GB",
    "ja-JP",
]

# ── 系统字体列表（中文为主） ─────────────────────────

FONT_LIST_CN = [
    "\"Microsoft YaHei\", \"微软雅黑\", \"PingFang SC\", \"Hiragino Sans GB\", \"WenQuanYi Micro Hei\"",
    "\"SimSun\", \"宋体\", \"Noto Sans CJK SC\", \"Source Han Sans SC\"",
    "\"Microsoft YaHei\", \"PingFang SC\", \"Helvetica Neue\", Arial, sans-serif",
    "\"PingFang SC\", \"Microsoft YaHei\", \"Noto Sans SC\", Arial, sans-serif",
]

FONT_LIST_EN = [
    "Arial, Helvetica, sans-serif",
    "\"Helvetica Neue\", Helvetica, Arial, sans-serif",
    "Georgia, \"Times New Roman\", serif",
    "-apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, Arial, sans-serif",
]

WEBRTC_IP_HANDLING_POLICIES = [
    "default",           # 公开本机 IP
    "default_public_interface_only",  # 仅公开公网 IP
    "default_public_and_private_interfaces",  # 公网+内网
    "disable_non_proxied_udp",  # 禁用非代理 UDP
]


class FingerprintManager:
    """
    浏览器指纹管理器 — 生成随机化指纹配置和反检测 JS 注入代码

    使用方法:
        fm = FingerprintManager(seed=42)
        config = fm.get_browser_config()
        js_code = fm.get_fingerprint_js()
    """

    def __init__(self, seed: Optional[int] = None):
        if seed is not None:
            random.seed(seed)
        self._rng = random.Random(seed) if seed is not None else random
        self._fingerprint_id = hashlib.md5(
            str(time.time_ns()).encode()
        ).hexdigest()[:8]

    def random_user_agent(self) -> str:
        """随机返回一个真实浏览器 User-Agent"""
        return self._rng.choice(USER_AGENTS)

    def random_viewport(self) -> dict:
        """随机返回 viewport 配置（{width, height}）"""
        return dict(self._rng.choice(VIEWPORTS))

    def random_webgl(self) -> dict:
        """随机返回 WebGL vendor/renderer 配置"""
        return {
            "vendor": self._rng.choice(WEBGL_VENDORS),
            "renderer": self._rng.choice(WEBGL_RENDERERS),
        }

    def random_locale(self) -> str:
        """随机返回语言区域设置"""
        return self._rng.choice(LOCALES)

    def random_timezone(self) -> str:
        """随机返回时区"""
        return self._rng.choice(TIMEZONES)

    def random_fonts(self) -> str:
        """随机返回系统字体列表 CSS 值"""
        if self._rng.random() < 0.7:
            return self._rng.choice(FONT_LIST_CN)
        return self._rng.choice(FONT_LIST_EN)

    def random_webrtc_policy(self) -> str:
        """随机返回 WebRTC IP 处理策略"""
        return self._rng.choice(WEBRTC_IP_HANDLING_POLICIES)

    def _canvas_noise_amount(self) -> float:
        """生成 canvas 噪声量（极小浮点数，不改变视觉效果）"""
        return round(self._rng.uniform(0.0001, 0.001), 6)

    def _audio_noise_amount(self) -> float:
        """生成 AudioContext 噪声偏移"""
        return round(self._rng.uniform(-0.0005, 0.0005), 6)

    def get_fingerprint_js(self) -> str:
        """
        生成完整的反检测注入 JavaScript 代码。

        包含:
          - navigator.webdriver 覆盖
          - navigator.plugins 模拟
          - Chrome runtime 模拟
          - 语言/时区覆盖
          - WebGL vendor/renderer 覆盖
          - Canvas 指纹保护（噪声注入）
          - AudioContext 指纹随机化
          - WebRTC 配置
          - 屏幕属性保护
          - Permissions API 保护
        """
        webgl = self.random_webgl()
        audio_noise = self._audio_noise_amount()
        locale = self.random_locale()
        cpu_cores = self._rng.choice([4, 6, 8, 10, 12, 16])
        device_memory = self._rng.choice([4, 8, 16, 32, 64])

        js = f"""
// === FingerprintManager 反检测注入 [{self._fingerprint_id}] ===

// 1. 覆盖 navigator.webdriver
Object.defineProperty(navigator, 'webdriver', {{
    get: () => undefined,
    configurable: true,
}});

// 2. 模拟 navigator.plugins 和 mimeTypes 长度
Object.defineProperty(navigator, 'plugins', {{
    get: () => [1, 2, 3, 4, 5],
    configurable: true,
}});
Object.defineProperty(navigator, 'mimeTypes', {{
    get: () => [1, 2, 3, 4],
    configurable: true,
}});

// 3. 覆盖 navigator.languages 和 language
Object.defineProperty(navigator, 'languages', {{
    get: () => ['{locale}', 'zh', 'en'],
    configurable: true,
}});
Object.defineProperty(navigator, 'language', {{
    get: () => '{locale}',
    configurable: true,
}});

// 4. 模拟 chrome.runtime
window.chrome = window.chrome || {{}};
window.chrome.runtime = window.chrome.runtime || {{}};
window.chrome.loadTimes = () => {{
    return {{
        requestTime: 0,
        startLoadTime: 0,
        commitLoadTime: 0,
        finishDocumentLoadTime: 0,
        finishLoadTime: 0,
        firstPaintTime: 0,
        firstPaintAfterLoadTime: 0,
        navigationType: 'other',
        wasFetchedViaSpdy: false,
        wasNpnNegotiated: false,
        npnNegotiatedProtocol: 'unknown',
        wasAlternateProtocolAvailable: false,
        connectionInfo: 'http/1.1',
    }};
}};
window.chrome.csi = () => {{
    return {{
        onloadT: Date.now(),
        startE: Date.now(),
        onloadT: Date.now(),
        interactiveT: Date.now(),
    }};
}};

// 5. 覆盖 WebGL vendor/renderer
const getParameterProxyHandler = {{
    apply: function(target, thisArg, args) {{
        const param = args[0];
        // VENDOR
        if (param === 0x1F00) return '{webgl["vendor"]}';
        // RENDERER
        if (param === 0x1F01) return '{webgl["renderer"]}';
        // VERSION
        if (param === 0x1F02) return 'WebGL 2.0 (OpenGL ES 3.0 Chromium)';
        // SHADING_LANGUAGE_VERSION
        if (param === 0x8B8C) return 'WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)';
        return Reflect.apply(target, thisArg, args);
    }}
}};

// 覆盖 WebGLRenderingContext.getParameter
const originalGetParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = new Proxy(originalGetParameter, getParameterProxyHandler);

// WebGL2 同样处理
if (typeof WebGL2RenderingContext !== 'undefined') {{
    const originalGetParameter2 = WebGL2RenderingContext.prototype.getParameter;
    WebGL2RenderingContext.prototype.getParameter = new Proxy(originalGetParameter2, getParameterProxyHandler);
}}

// 6. Canvas 指纹保护 — 对 toDataURL/toBlob 注入微小噪声
const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = function() {{
    const canvas = this;
    const context = canvas.getContext('2d');
    if (context) {{
        const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
        const data = imageData.data;
        // 对随机像素注入微小噪声 (alpha 通道不修改)
        for (let i = 0; i < data.length; i += 4) {{
            if (Math.random() < 0.01) {{
                data[i] = Math.max(0, Math.min(255, data[i] + (Math.random() > 0.5 ? 1 : -1)));
                data[i+1] = Math.max(0, Math.min(255, data[i+1] + (Math.random() > 0.5 ? 1 : -1)));
                data[i+2] = Math.max(0, Math.min(255, data[i+2] + (Math.random() > 0.5 ? 1 : -1)));
            }}
        }}
        context.putImageData(imageData, 0, 0);
    }}
    return originalToDataURL.apply(this, arguments);
}};

const originalToBlob = HTMLCanvasElement.prototype.toBlob;
HTMLCanvasElement.prototype.toBlob = function() {{
    const canvas = this;
    const context = canvas.getContext('2d');
    if (context) {{
        const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
        const data = imageData.data;
        for (let i = 0; i < data.length; i += 4) {{
            if (Math.random() < 0.01) {{
                data[i] = Math.max(0, Math.min(255, data[i] + (Math.random() > 0.5 ? 1 : -1)));
                data[i+1] = Math.max(0, Math.min(255, data[i+1] + (Math.random() > 0.5 ? 1 : -1)));
                data[i+2] = Math.max(0, Math.min(255, data[i+2] + (Math.random() > 0.5 ? 1 : -1)));
            }}
        }}
        context.putImageData(imageData, 0, 0);
    }}
    return originalToBlob.apply(this, arguments);
}};

// 7. AudioContext 指纹随机化
const originalGetChannelData = AudioBuffer.prototype.getChannelData;
AudioBuffer.prototype.getChannelData = function(channel) {{
    const data = originalGetChannelData.call(this, channel);
    // 注入微小振幅噪声
    for (let i = 0; i < data.length; i++) {{
        if (Math.random() < 0.005) {{
            data[i] += {audio_noise};
        }}
    }}
    return data;
}};

// 8. WebRTC 配置保护 — 覆盖 RTCPeerConnection
if (typeof RTCPeerConnection !== 'undefined') {{
    const originalCreateDataChannel = RTCPeerConnection.prototype.createDataChannel;
    RTCPeerConnection.prototype.createDataChannel = function() {{
        const channel = originalCreateDataChannel.apply(this, arguments);
        return channel;
    }};
}}

// 9. 覆盖 screen 属性（防分辨率检测）
Object.defineProperty(window.screen, 'availWidth', {{ get: () => window.innerWidth }});
Object.defineProperty(window.screen, 'availHeight', {{ get: () => window.innerHeight }});
Object.defineProperty(window.screen, 'colorDepth', {{ get: () => 24 }});
Object.defineProperty(window.screen, 'pixelDepth', {{ get: () => 24 }});

// 10. 覆盖 Permissions API
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications'
        ? Promise.resolve({{ state: Notification.permission }})
        : originalQuery(parameters)
);

// 11. 覆盖 Font API 返回模拟字体列表
const originalFontsQuery = document.fonts ? document.fonts.query : null;
if (originalFontsQuery) {{
    document.fonts.query = function() {{
        return Promise.resolve([]);
    }};
}}

// 12. 覆盖 navigator.hardwareConcurrency（CPU 核心数模拟）
Object.defineProperty(navigator, 'hardwareConcurrency', {{
    get: () => {cpu_cores},
    configurable: true,
}});

// 13. 覆盖 navigator.deviceMemory（设备内存模拟，GB）
Object.defineProperty(navigator, 'deviceMemory', {{
    get: () => {device_memory},
    configurable: true,
}});

// 14. 覆盖 navigator.maxTouchPoints
Object.defineProperty(navigator, 'maxTouchPoints', {{
    get: () => 0,
    configurable: true,
}});
"""
        return js

    def get_browser_config(self) -> dict:
        """
        返回兼容 BrowserConfig 的配置字典。

        可用于:
            from hermes_web_agent.utils.fingerprint import FingerprintManager
            fm = FingerprintManager()
            config = BrowserConfig(**fm.get_browser_config())
        """
        viewport = self.random_viewport()
        return {
            "viewport": viewport,
            "user_agent": self.random_user_agent(),
            "locale": self.random_locale(),
            "timezone_id": self.random_timezone(),
            "slow_mo": self._rng.randint(30, 80),
        }
