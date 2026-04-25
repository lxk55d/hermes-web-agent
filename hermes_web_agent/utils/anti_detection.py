"""
抗检测工具 — 浏览器指纹随机化、请求拦截

参考 camofox-mcp 的 anti-detection 策略：
  1. 指纹随机化：随机 User-Agent、Viewport、时区、语言
  2. 请求拦截：屏蔽跟踪器、WebDriver 检测脚本
  3. 人类行为模拟：随机鼠标轨迹、输入节奏、滚动模式
  4. CAPTCHA 检测：识别并提示手动验证
"""
import random
import time
from typing import Optional


def random_delay(min_ms: float = 100, max_ms: float = 500):
    """随机延时（模仿人类操作间隙）"""
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


def human_typing_delays(text: str) -> list:
    """
    生成人类打字的每字延迟（毫秒）
    
    规律：
      - 普通字符: 40-120ms
      - 大写字母/标点: 80-180ms（按Shift需要额外时间）
      - 空格: 100-250ms（思考停顿）
      - 长单词后: 150-300ms（看完下一个词）
    """
    delays = []
    for i, char in enumerate(text):
        if char == " ":
            delays.append(random.randint(100, 250))
        elif char.isupper() or char in "!@#$%^&*()_+{}|:\"<>?~":
            delays.append(random.randint(80, 180))
        elif char in ".,!?;:":
            delays.append(random.randint(60, 150))
        else:
            delays.append(random.randint(40, 120))

        # 每 10-20 个字符加一个"思考停顿"
        if random.random() < 0.08:
            delays[-1] += random.randint(200, 600)

    return delays


def random_mouse_path(
    start_x: int, start_y: int, end_x: int, end_y: int
) -> list:
    """
    生成人类鼠标移动路径（贝塞尔曲线模拟）
    
    返回 [(x, y, delay_ms), ...] 路径点序列
    """

    points = []
    steps = random.randint(8, 20)

    # 控制点随机偏移（模拟人类手腕微动）
    cx1 = (start_x + end_x) / 2 + random.randint(-50, 50)
    cy1 = (start_y + end_y) / 2 + random.randint(-30, 30)
    cx2 = (start_x + end_x) / 2 + random.randint(-50, 50)
    cy2 = (start_y + end_y) / 2 + random.randint(-30, 30)

    for i in range(steps + 1):
        t = i / steps
        # 三次贝塞尔曲线
        x = (1 - t) ** 3 * start_x + 3 * (1 - t) ** 2 * t * cx1 \
            + 3 * (1 - t) * t ** 2 * cx2 + t ** 3 * end_x
        y = (1 - t) ** 3 * start_y + 3 * (1 - t) ** 2 * t * cy1 \
            + 3 * (1 - t) * t ** 2 * cy2 + t ** 3 * end_y

        delay = random.randint(5, 15)
        points.append((int(x), int(y), delay))

    return points


def detect_captcha(page_text: str) -> Optional[str]:
    """检测页面是否出现 CAPTCHA"""
    captcha_indicators = [
        "captcha",
        "verify you're human",
        "验证码",
        "人机验证",
        "安全验证",
        "请完成安全验证",
        "verify your identity",
        "安全检查",
        "安全检测",
        "challenge",
        "recaptcha",
        "hcaptcha",
        "turnstile",
    ]

    lower_text = page_text.lower()
    found = [ind for ind in captcha_indicators if ind in lower_text]

    if found:
        return f"检测到验证: {', '.join(found)}"
    return None


# ── 浏览器注入脚本 ──────────────────────────

ANTI_DETECTION_JS = """
// 覆盖 navigator.webdriver
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
    configurable: true,
});

// 覆盖 navigator.plugins 长度
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
    configurable: true,
});

// 覆盖 languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['zh-CN', 'zh', 'en'],
    configurable: true,
});

// 覆盖 chrome.runtime
window.chrome = window.chrome || {};
window.chrome.runtime = window.chrome.runtime || {};

// 覆盖 Permissions API
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
    Promise.resolve({ state: Notification.permission }) :
    originalQuery(parameters)
);

// 覆盖屏幕尺寸相关（避免分辨率检测）
Object.defineProperty(window.screen, 'availWidth', { get: () => window.innerWidth });
Object.defineProperty(window.screen, 'availHeight', { get: () => window.innerHeight });
"""
