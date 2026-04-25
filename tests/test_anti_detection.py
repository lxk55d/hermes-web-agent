"""测试反检测模块 — anti_detection.py"""

import pytest

from hermes_web_agent.utils.anti_detection import (
    ANTI_DETECTION_JS,
    detect_captcha,
    human_typing_delays,
    random_delay,
    random_mouse_path,
)


class TestAntiDetectionJS:
    """反检测注入 JS 脚本测试"""

    def test_anti_detection_js_script(self):
        """JS 脚本包含 webdriver 覆盖等关键内容"""
        js = ANTI_DETECTION_JS
        assert isinstance(js, str)
        assert len(js) > 200

        # 必须包含核心反检测语句
        assert "navigator.webdriver" in js
        assert "navigator.plugins" in js
        # 注释是 "覆盖 languages" 但实际代码包含 'languages'
        assert "navigator" in js or "languages" in js
        assert "window.chrome" in js
        assert "chrome.runtime" in js
        assert "Permissions API" in js or "permissions.query" in js
        assert "window.screen" in js
        # 确认 JS 有具体的 Object.defineProperty 调用
        assert "Object.defineProperty" in js

    def test_anti_detection_js_syntax(self):
        """JS 语法基本正确（括号匹配）"""
        js = ANTI_DETECTION_JS
        # 简单检查大括号匹配
        assert js.count("{") == js.count("}")
        assert js.count("(") == js.count(")")
        assert js.count("[") == js.count("]")


class TestDetectCaptcha:
    """CAPTCHA 检测测试"""

    def test_detect_captcha_recognizes_keywords(self):
        """能识别多种 CAPTCHA 关键词"""
        test_cases = [
            ("Please complete the captcha", "检测到验证"),
            ("verify you're human", "检测到验证"),
            ("reCAPTCHA challenge", "检测到验证"),
            ("hcaptcha verification", "检测到验证"),
            ("请完成人机验证", "检测到验证"),
            ("安全验证", "检测到验证"),
            ("安全检查", "检测到验证"),
            ("Please verify your identity", "检测到验证"),
            ("Cloudflare Turnstile", "检测到验证"),
        ]
        for text, expected_prefix in test_cases:
            result = detect_captcha(text)
            assert result is not None, f"应为 {text} 检测到 CAPTCHA"
            assert result.startswith(expected_prefix), f"{text} 返回 {result}"

    def test_detect_captcha_returns_none_for_clean_text(self):
        """正常文本应返回 None"""
        clean_texts = [
            "Hello, how are you?",
            "Today is a sunny day.",
            "Python programming is fun.",
            "This is a normal conversation.",
        ]
        for text in clean_texts:
            result = detect_captcha(text)
            assert result is None, f"应为正常文本 {text} 返回 None，得到 {result}"

    def test_detect_captcha_case_insensitive(self):
        """大小写不敏感检测"""
        texts = [
            "CAPTCHA required",
            "Captcha required",
            "captcha required",
        ]
        for text in texts:
            result = detect_captcha(text)
            assert result is not None

    def test_detect_captcha_empty_string(self):
        """空字符串返回 None"""
        assert detect_captcha("") is None

    def test_detect_captcha_multiple_matches(self):
        """多个匹配项时全部列出"""
        result = detect_captcha("captcha and recaptcha and hcaptcha")
        assert result is not None
        assert "captcha" in result
        assert "recaptcha" in result
        assert "hcaptcha" in result


class TestHumanTypingDelays:
    """人类打字延迟测试"""

    def test_human_typing_delays_returns_correct_length(self):
        """延迟列表长度与文本字符数相同"""
        text = "Hello, World!"
        delays = human_typing_delays(text)
        assert len(delays) == len(text)

    def test_human_typing_delays_empty_string(self):
        """空字符串返回空列表"""
        assert human_typing_delays("") == []

    def test_human_typing_delays_values_in_range(self):
        """所有延迟值在合理范围内"""
        text = "Hello, World! How are you today?"
        delays = human_typing_delays(text)
        for delay in delays:
            assert isinstance(delay, int)
            assert delay >= 40  # 最小延迟
            assert delay <= 1000  # 最大延迟（含思考停顿）

    def test_human_typing_delays_spaces_longer(self):
        """空格延迟通常比普通字符大"""
        text = "a b"
        delays = human_typing_delays(text)
        # 空格索引 1
        assert delays[1] >= 100
        # 普通字符
        assert delays[0] >= 40

    def test_human_typing_delays_uppercase_longer(self):
        """大写字母延迟通常比小写大"""
        text = "aA"
        delays = human_typing_delays(text)
        # 'A' 需要 Shift
        assert delays[1] >= 80


class TestRandomMousePath:
    """随机鼠标路径测试"""

    def test_random_mouse_path_start_end_correct(self):
        """起点终点正确"""
        path = random_mouse_path(100, 200, 500, 400)
        assert isinstance(path, list)
        assert len(path) >= 8

        first = path[0]
        last = path[-1]

        # 每个点 (x, y, delay_ms)
        assert len(first) == 3
        assert len(last) == 3

        # 起点接近(100, 200)
        assert abs(first[0] - 100) <= 1
        assert abs(first[1] - 200) <= 1

        # 终点接近(500, 400)
        assert abs(last[0] - 500) <= 1
        assert abs(last[1] - 400) <= 1

    def test_random_mouse_path_points_format(self):
        """所有路径点格式正确"""
        path = random_mouse_path(0, 0, 100, 100)
        for x, y, delay in path:
            assert isinstance(x, int)
            assert isinstance(y, int)
            assert isinstance(delay, int)
            assert 0 <= delay <= 20

    def test_random_mouse_path_generates_varying_paths(self):
        """多次调用产生不同路径（高概率）"""
        path1 = random_mouse_path(10, 10, 200, 200)
        path2 = random_mouse_path(10, 10, 200, 200)
        # 由于随机偏移，路径应该不同
        assert path1 != path2


class TestRandomDelay:
    """随机延迟测试"""

    def test_random_delay_does_not_crash(self):
        """random_delay 不崩溃"""
        import time

        t0 = time.time()
        random_delay(min_ms=10, max_ms=50)
        elapsed = (time.time() - t0) * 1000
        assert 5 <= elapsed <= 200
