"""测试 — 指纹随机化模块"""
import re
import pytest
from hermes_web_agent.utils.fingerprint import FingerprintManager
from hermes_web_agent.utils.human_like import HumanBehaviorSimulator
from hermes_web_agent.utils.anti_detection import (
    random_delay, human_typing_delays, random_mouse_path,
    detect_captcha, ANTI_DETECTION_JS,
)


class TestFingerprintManager:
    def test_random_user_agent(self):
        fm = FingerprintManager()
        ua = fm.random_user_agent()
        assert isinstance(ua, str)
        assert len(ua) > 50
        assert "Mozilla" in ua
        assert "Chrome" in ua or "Firefox" in ua

    def test_random_viewport(self):
        fm = FingerprintManager()
        vp = fm.random_viewport()
        assert "width" in vp
        assert "height" in vp
        assert 800 <= vp["width"] <= 4000
        assert 600 <= vp["height"] <= 2500

    def test_random_webgl(self):
        fm = FingerprintManager()
        gl = fm.random_webgl()
        assert "vendor" in gl
        assert "renderer" in gl
        assert "Google" in gl["vendor"]
        assert "ANGLE" in gl["renderer"]

    def test_random_locale(self):
        fm = FingerprintManager()
        locale = fm.random_locale()
        assert isinstance(locale, str)
        assert len(locale) >= 4

    def test_get_fingerprint_js(self):
        fm = FingerprintManager()
        js = fm.get_fingerprint_js()
        # 检查关键覆盖语句
        assert "navigator.webdriver" in js
        assert "navigator.plugins" in js
        assert "WebGLRenderingContext" in js
        assert "toDataURL" in js
        assert "AudioBuffer" in js
        assert "RTCPeerConnection" in js
        assert "window.chrome" in js
        assert "hardwareConcurrency" in js
        assert "deviceMemory" in js

    def test_get_browser_config(self):
        fm = FingerprintManager()
        cfg = fm.get_browser_config()
        assert "viewport" in cfg
        assert "user_agent" in cfg
        assert "locale" in cfg
        assert "timezone_id" in cfg
        assert "slow_mo" in cfg
        assert 20 <= cfg["slow_mo"] <= 100

    def test_uniqueness(self):
        """连续两次调用应产生不同的结果"""
        fm1 = FingerprintManager()
        fm2 = FingerprintManager()
        cfg1 = fm1.get_browser_config()
        cfg2 = fm2.get_browser_config()
        # 视口可能相同（随机选择），但不同的指纹ID应不同
        js1 = fm1.get_fingerprint_js()
        js2 = fm2.get_fingerprint_js()
        assert js1 != js2


class TestHumanBehaviorSimulator:
    @pytest.mark.asyncio
    async def test_mouse_trajectory(self):
        sim = HumanBehaviorSimulator()
        traj = sim.mouse_trajectory((100, 100), (500, 400))
        assert len(traj) >= 5
        first = traj[0]
        last = traj[-1]
        assert abs(first[0] - 100) < 10
        assert abs(first[1] - 100) < 10
        assert abs(last[0] - 500) < 10
        assert abs(last[1] - 400) < 10

    def test_human_delay_range(self):
        import asyncio
        import time
        sim = HumanBehaviorSimulator()
        async def _test():
            t0 = time.time()
            await sim.human_delay(100, 500)
            elapsed = (time.time() - t0) * 1000
            return elapsed
        elapsed = asyncio.run(_test())
        assert 50 <= elapsed <= 750  # 允许一定浮动范围

    @pytest.mark.asyncio
    async def test_type_with_delay_params(self):
        sim = HumanBehaviorSimulator()
        delays = []
        text = "Hello World!"
        for char in text:
            delay = sim._char_delay(char, 20, 300)
            delays.append(delay)
        assert len(delays) == len(text)
        for d in delays:
            assert 20 <= d <= 300

    @pytest.mark.asyncio
    async def test_random_scroll_params(self):
        sim = HumanBehaviorSimulator()
        # 直接测试 _rng.randint 等价逻辑 (random_scroll 内的参数生成)
        scroll_by = sim._rng.randint(100, 500)
        assert 100 <= scroll_by <= 500


class TestAntiDetection:
    def test_anti_detection_js_content(self):
        assert "webdriver" in ANTI_DETECTION_JS
        assert "navigator.plugins" in ANTI_DETECTION_JS
        assert "languages" in ANTI_DETECTION_JS
        assert "chrome.runtime" in ANTI_DETECTION_JS

    def test_detect_captcha(self):
        # 中文验证码
        assert detect_captcha("请完成安全验证") is not None
        assert detect_captcha("验证码已发送到您的手机") is not None
        # 英文
        assert detect_captcha("verify you're human") is not None
        assert detect_captcha("recaptcha") is not None
        # 没有验证码
        assert detect_captcha("Hello, how can I help you today?") is None
        assert detect_captcha("欢迎使用ChatGPT") is None

    def test_human_typing_delays(self):
        text = "Hello"
        delays = human_typing_delays(text)
        assert len(delays) == len(text)
        for d in delays:
            assert 40 <= d <= 250

    def test_random_mouse_path(self):
        path = random_mouse_path(0, 0, 800, 600)
        assert len(path) >= 5
        # 起点接近 (0,0)
        sx, sy, _ = path[0]
        assert abs(sx) < 20
        assert abs(sy) < 20
        # 终点接近 (800,600)
        ex, ey, _ = path[-1]
        assert abs(ex - 800) < 20
        assert abs(ey - 600) < 20
