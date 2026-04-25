"""
人类行为模拟 — HumanBehaviorSimulator

模拟真实用户的操作行为：
  - 打字节奏（基于字符类型变化的延迟）
  - 鼠标轨迹（贝塞尔曲线路径）
  - 页面滚动（带随机停顿的逐段滚动）
  - 页面停留（符合正态分布的延迟）
  - 操作顺序随机化（解耦固定操作顺序）

所有方法均为异步，遵循项目 asyncio 风格。
"""

import asyncio
import math
import random
from typing import Callable, List, Optional, Tuple


class HumanBehaviorSimulator:
    """
    人类行为模拟器 — 模拟真实用户操作模式

    使用方法:
        sim = HumanBehaviorSimulator()
        await sim.type_with_delay(page, "#input", "hello world")
        await sim.random_scroll(page)
        await sim.human_delay()
        points = sim.mouse_trajectory((100, 200), (500, 400))
    """

    def __init__(self, seed: Optional[int] = None):
        self._rng = random.Random(seed) if seed is not None else random

    # ── 打字节奏模拟 ──────────────────────────────

    async def type_with_delay(
        self,
        page,
        selector: str,
        text: str,
        min_delay: int = 30,
        max_delay: int = 120,
    ) -> bool:
        """
        模拟人类打字节奏，逐字符输入文本。

        字符延迟规则:
          - 普通字母/数字: 30-80ms
          - 大写字母/标点: 60-150ms（按 Shift 需要额外时间）
          - 空格: 80-200ms（思考停顿）
          - 句末标点 (.!?): 150-350ms（读完句子停顿）
          - 每 8-18 个字符随机加一个 \"思考停顿\" (200-600ms)
          - 长单词 (>6字符) 后加额外停顿 (100-250ms)

        Args:
            page: Playwright Page 对象
            selector: 目标元素选择器
            text: 要输入的文本
            min_delay: 最小字符延迟 (ms)
            max_delay: 最大字符延迟 (ms)

        Returns:
            bool: 输入是否成功
        """
        try:
            # 点击目标元素获得焦点
            await page.click(selector)
            await asyncio.sleep(self._rng.uniform(0.05, 0.2))

            # 清空已有内容
            await page.fill(selector, "")
            await asyncio.sleep(self._rng.uniform(0.05, 0.15))

            word_len = 0
            for i, char in enumerate(text):
                # 确定当前字符的延迟
                delay = self._char_delay(char, min_delay, max_delay)

                # 追踪单词长度
                if char.isalpha():
                    word_len += 1
                else:
                    # 长单词后的额外停顿
                    if word_len > 6:
                        delay += self._rng.randint(100, 250)
                    word_len = 0 if char == " " else 0

                # 随机思考停顿（每 8-18 个字符）
                if i > 0 and i % self._rng.randint(8, 18) == 0:
                    delay += self._rng.randint(200, 600)

                await page.type(selector, char, delay=delay)

            return True

        except Exception:
            return False

    def _char_delay(self, char: str, min_delay: int, max_delay: int) -> int:
        """根据字符类型计算输入延迟（毫秒）"""
        if char == " ":
            # 空格 — 思考停顿
            return self._rng.randint(max(min_delay, 80), max(max_delay, 200))
        elif char in ".!?。！？":
            # 句末标点 — 读完句子停顿
            return self._rng.randint(150, 350)
        elif char in ",;:，；：、""''":
            # 中间标点
            return self._rng.randint(max(min_delay, 50), max(max_delay, 150))
        elif char.isupper() or char in "!@#$%^&*()_+{}|:\\\"<>?~":
            # 大写字母或特殊符号 — 需要按 Shift
            return self._rng.randint(max(min_delay, 60), max(max_delay, 150))
        elif char.isdigit():
            # 数字
            return self._rng.randint(max(min_delay, 25), max(max_delay, 80))
        else:
            # 普通小写字母
            return self._rng.randint(min_delay, max(min_delay + 40, 80))

    # ── 鼠标轨迹模拟 ──────────────────────────────

    def mouse_trajectory(
        self,
        start: Tuple[int, int],
        end: Tuple[int, int],
        steps: Optional[int] = None,
        overshoot: float = 0.0,
    ) -> List[Tuple[int, int, int]]:
        """
        生成人类鼠标移动轨迹（三次贝塞尔曲线）。

        模拟人类手腕/手臂的微动和曲线移动，返回路径点序列。
        每个点包含 (x, y, delay_ms)。

        Args:
            start: 起点坐标 (x, y)
            end: 终点坐标 (x, y)
            steps: 路径点数（默认根据距离自动计算 10-30 步）
            overshoot: 过冲比例 (0.0 = 精准到达，0.05-0.15 = 略微过冲再回调)

        Returns:
            [(x, y, delay_ms), ...] 路径点序列
        """
        sx, sy = start
        ex, ey = end

        # 计算距离，决定步数
        distance = math.sqrt((ex - sx) ** 2 + (ey - sy) ** 2)
        if steps is None:
            steps = max(8, min(30, int(distance / 40)))

        # 贝塞尔曲线控制点
        # 引入随机偏移模拟手腕微动
        dx = ex - sx
        dy = ey - sy
        offset_x = self._rng.uniform(-abs(dx) * 0.2, abs(dx) * 0.2)
        offset_y = self._rng.uniform(-abs(dy) * 0.2, abs(dy) * 0.2)

        cx1 = sx + dx * 0.25 + offset_x
        cy1 = sy + dy * 0.25 + offset_y
        cx2 = sx + dx * 0.75 + offset_x
        cy2 = sy + dy * 0.75 + offset_y

        # 如果距离近 (< 100px)，使用更直接的路径
        if distance < 100:
            cx1 = sx + dx * 0.3 + self._rng.uniform(-10, 10)
            cy1 = sy + dy * 0.3 + self._rng.uniform(-5, 5)
            cx2 = sx + dx * 0.7 + self._rng.uniform(-10, 10)
            cy2 = sy + dy * 0.7 + self._rng.uniform(-5, 5)

        # 过冲支持：终点略微偏移再回调
        end_x, end_y = ex, ey
        if overshoot > 0:
            overshoot_dist = distance * overshoot
            angle = math.atan2(dy, dx)
            end_x = ex + math.cos(angle) * overshoot_dist
            end_y = ey + math.sin(angle) * overshoot_dist
            # 添加回调点
            steps += 3

        points: List[Tuple[int, int, int]] = []
        for i in range(steps + 1):
            t = i / steps
            # 三次贝塞尔: B(t) = (1-t)^3*P0 + 3(1-t)^2*t*P1 + 3(1-t)*t^2*P2 + t^3*P3
            x = (
                (1 - t) ** 3 * sx
                + 3 * (1 - t) ** 2 * t * cx1
                + 3 * (1 - t) * t ** 2 * cx2
                + t ** 3 * end_x
            )
            y = (
                (1 - t) ** 3 * sy
                + 3 * (1 - t) ** 2 * t * cy1
                + 3 * (1 - t) * t ** 2 * cy2
                + t ** 3 * end_y
            )

            # 人类鼠标移动延迟：开始和结束较慢，中间较快
            if i == 0 or i == steps:
                delay = self._rng.randint(10, 30)
            elif i < steps * 0.15 or i > steps * 0.85:
                delay = self._rng.randint(5, 15)
            else:
                delay = self._rng.randint(2, 8)

            points.append((int(x), int(y), delay))

        return points

    async def move_mouse_along(
        self,
        page,
        trajectory: List[Tuple[int, int, int]],
    ) -> None:
        """
        按轨迹点序列移动鼠标。

        Args:
            page: Playwright Page 对象
            trajectory: mouse_trajectory() 返回的路径点序列
        """
        for x, y, delay_ms in trajectory:
            await page.mouse.move(x, y)
            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000)

    async def click_humanlike(
        self,
        page,
        selector: str,
        overshoot: float = 0.05,
    ) -> bool:
        """
        人类化点击 — 先移动鼠标到目标再点击。

        模拟真实用户的鼠标移动轨迹，包括过冲和微调。

        Args:
            page: Playwright Page 对象
            selector: 目标元素选择器
            overshoot: 过冲比例

        Returns:
            bool: 点击是否成功
        """
        try:
            # 获取元素位置
            element = await page.query_selector(selector)
            if element is None:
                return False

            box = await element.bounding_box()
            if box is None:
                return False

            # 目标位置（元素中心 + 随机偏移）
            target_x = box["x"] + box["width"] / 2 + self._rng.uniform(-3, 3)
            target_y = box["y"] + box["height"] / 2 + self._rng.uniform(-3, 3)

            # 获取当前鼠标位置（假设是 viewport 中心或上次位置）
            try:
                current_pos = await page.evaluate(
                    "({x: window.__lastMouseX || window.innerWidth/2, y: window.__lastMouseY || window.innerHeight/2})"
                )
                start_pos = (current_pos["x"], current_pos["y"])
                # 如果上次位置不在屏幕上，使用 viewport 中心
                if (
                    start_pos[0] < 0
                    or start_pos[0] > (await page.evaluate("window.innerWidth"))
                    or start_pos[1] < 0
                    or start_pos[1] > (await page.evaluate("window.innerHeight"))
                ):
                    start_pos = (await page.evaluate("window.innerWidth/2"),
                                 await page.evaluate("window.innerHeight/2"))
            except Exception:
                start_pos = (
                    await page.evaluate("window.innerWidth / 2"),
                    await page.evaluate("window.innerHeight / 2"),
                )

            # 生成鼠标轨迹并移动
            trajectory = self.mouse_trajectory(
                start_pos, (target_x, target_y),
                overshoot=overshoot,
            )
            await self.move_mouse_along(page, trajectory)

            # 点击前微小延迟
            await asyncio.sleep(self._rng.uniform(0.05, 0.15))
            await page.click(selector)

            # 记录鼠标位置
            try:
                await page.evaluate(
                    f"window.__lastMouseX = {target_x}; window.__lastMouseY = {target_y}"
                )
            except Exception:
                pass

            return True

        except Exception:
            return False

    # ── 滚动模拟 ──────────────────────────────

    async def random_scroll(
        self,
        page,
        min_px: int = 100,
        max_px: int = 500,
        pause_min_ms: int = 200,
        pause_max_ms: int = 1200,
    ) -> None:
        """
        模拟人类逐段滚动页面（带随机停顿）。

        不是一次性滚到底，而是分段滚动，每段之间有随机停顿，
        模拟人眼阅读和手指滚动屏幕的节奏。

        Args:
            page: Playwright Page 对象
            min_px: 每次最小滚动距离 (px)
            max_px: 每次最大滚动距离 (px)
            pause_min_ms: 滚动间隔最小停顿 (ms)
            pause_max_ms: 滚动间隔最大停顿 (ms)
        """
        try:
            # 获取页面总高度和当前滚动位置
            scroll_height = await page.evaluate("document.body.scrollHeight")
            current_scroll = await page.evaluate("window.scrollY")
            viewport_height = await page.evaluate("window.innerHeight")

            remaining = scroll_height - current_scroll - viewport_height
            if remaining <= 0:
                return  # 已经到底

            # 分段滚动
            while remaining > 0:
                # 随机滚动距离
                scroll_by = self._rng.randint(min_px, min(max_px, remaining))

                # 滚动动画（分 3-6 小步完成）
                steps = self._rng.randint(3, 6)
                step_px = scroll_by / steps
                for _ in range(steps):
                    await page.evaluate(f"window.scrollBy(0, {step_px})")
                    await asyncio.sleep(self._rng.uniform(0.01, 0.03))

                # 滚动后停顿 （模拟阅读）
                await asyncio.sleep(
                    self._rng.uniform(pause_min_ms / 1000, pause_max_ms / 1000)
                )

                # 偶尔反向滚动一点点（人眼回看）
                if self._rng.random() < 0.1:
                    back_px = self._rng.randint(20, 80)
                    await page.evaluate(f"window.scrollBy(0, -{back_px})")
                    await asyncio.sleep(self._rng.uniform(0.1, 0.3))
                    # 再滚回来
                    await page.evaluate(f"window.scrollBy(0, {back_px})")

                # 更新剩余距离
                current_scroll = await page.evaluate("window.scrollY")
                remaining = scroll_height - current_scroll - viewport_height

                # 如果剩很少，直接结束
                if remaining < min_px * 0.5:
                    break

        except Exception:
            pass  # 滚动失败静默处理

    async def scroll_to_element(
        self,
        page,
        selector: str,
        offset: int = 0,
    ) -> bool:
        """
        滚动到指定元素位置（带人类化行为）。

        Args:
            page: Playwright Page 对象
            selector: 目标元素选择器
            offset: 额外偏移量 (px)

        Returns:
            bool: 是否成功
        """
        try:
            element = await page.query_selector(selector)
            if element is None:
                return False

            # 获取元素位置
            box = await element.bounding_box()
            if box is None:
                return False

            target_y = box["y"] + offset
            current_y = await page.evaluate("window.scrollY")

            # 计算滚动距离
            scroll_dist = abs(target_y - current_y)

            # 如果距离远，分段滚动过去
            if scroll_dist > 300:
                direction = 1 if target_y > current_y else -1
                segment = min(300, scroll_dist)
                while scroll_dist > 0:
                    move = min(segment, scroll_dist) * direction
                    await page.evaluate(f"window.scrollBy(0, {move})")
                    scroll_dist -= segment
                    await asyncio.sleep(self._rng.uniform(0.08, 0.25))
            else:
                # 距离近，平滑滚动
                await page.evaluate(
                    f"window.scrollTo({{top: {target_y}, behavior: 'smooth'}})"
                )
                await asyncio.sleep(self._rng.uniform(0.2, 0.5))

            return True

        except Exception:
            return False

    # ── 页面停留模拟 ──────────────────────────────

    async def human_delay(
        self,
        min_ms: float = 500,
        max_ms: float = 3000,
        mean_ms: Optional[float] = None,
    ) -> None:
        """
        模拟人类操作的随机延迟（符合正态分布的等候时间）。

        人类操作的间隙不是均匀分布，而是更接近正态分布：
          - 大多数操作间延迟集中在均值附近
          - 偶尔有极短或极长延迟
          - 阅读场景的延迟通常比操作间隙长

        Args:
            min_ms: 最小延迟（毫秒）
            max_ms: 最大延迟（毫秒）
            mean_ms: 均值（毫秒），默认取 (min+max)/2
        """
        if mean_ms is None:
            mean_ms = (min_ms + max_ms) / 2

        # 使用 Box-Muller 生成正态分布
        u1 = self._rng.random()
        u2 = self._rng.random()
        std = (max_ms - min_ms) / 4  # 标准偏差使得 95% 落在范围内
        normal_val = mean_ms + std * math.sqrt(-2 * math.log(u1 + 1e-10)) * math.cos(
            2 * math.pi * u2
        )

        # 裁剪到 [min_ms, max_ms] 范围内
        delay_ms = max(min_ms, min(max_ms, normal_val))
        await asyncio.sleep(delay_ms / 1000)

    # ── 操作顺序随机化 ──────────────────────────────

    async def randomized_action_sequence(
        self,
        page,
        actions: List[Callable],
        shuffle_probability: float = 0.3,
    ) -> None:
        """
        以随机化顺序执行一系列操作，模拟人类的非确定性行为。

        例如：不是每次都先点击再滚动，有时会先滚动再点击。

        Args:
            page: Playwright Page 对象（传递给每个 action）
            actions: 可调用对象列表，每个接收 page 参数
            shuffle_probability: 打乱顺序的概率（0-1）
        """
        # 复制操作列表
        action_list = list(actions)

        # 决定是否打乱顺序
        if self._rng.random() < shuffle_probability:
            self._rng.shuffle(action_list)

        # 偶尔在操作间插入随机滚动
        for i, action in enumerate(action_list):
            # 执行操作前，偶尔先滚动一下
            if self._rng.random() < 0.15:
                await self.random_scroll(page, min_px=50, max_px=200)

            # 执行操作
            if asyncio.iscoroutinefunction(action):
                await action(page)
            else:
                action(page)

            # 操作间加入人类延迟
            await self.human_delay(min_ms=200, max_ms=1500)

            # 偶尔在操作后也滚动一下
            if self._rng.random() < 0.08:
                await self.random_scroll(page, min_px=100, max_px=300)

    # ── 页面阅读模拟 ──────────────────────────────

    async def simulate_reading(
        self,
        page,
        read_duration_ms: int = 3000,
        scroll_probability: float = 0.6,
    ) -> None:
        """
        模拟人类在页面上阅读内容的行为。

        包括:
          - 随机目光移动（轻微鼠标晃动）
          - 定期滚动
          - 阅读停顿

        Args:
            page: Playwright Page 对象
            read_duration_ms: 阅读总时间（毫秒）
            scroll_probability: 阅读过程中滚动的概率
        """
        end_time = asyncio.get_event_loop().time() + read_duration_ms / 1000

        while asyncio.get_event_loop().time() < end_time:
            # 阅读停顿（视线停留）
            await self.human_delay(min_ms=800, max_ms=4000)

            # 偶尔滚动
            if self._rng.random() < scroll_probability:
                await self.random_scroll(
                    page,
                    min_px=100,
                    max_px=400,
                    pause_min_ms=300,
                    pause_max_ms=1500,
                )

            # 轻微鼠标移动（模拟目光位置）
            if self._rng.random() < 0.3:
                try:
                    vp_w = await page.evaluate("window.innerWidth")
                    vp_h = await page.evaluate("window.innerHeight")
                    mouse_x = self._rng.randint(100, vp_w - 100)
                    mouse_y = self._rng.randint(100, vp_h - 100)
                    await page.mouse.move(mouse_x, mouse_y)
                except Exception:
                    pass
