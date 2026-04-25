"""
任务编排器 — 多 LLM 协作完成复杂任务

核心创新：
  1. 多模型分工：根据任务特性分配合适的 LLM
     - 创意/写作 → ChatGPT
     - 代码/分析 → Claude
     - 快速查询 → DeepSeek
     - 多模态 → Gemini
  2. 流水线模式: LLM_A 输出 → LLM_B 审查 → LLM_C 优化
  3. 共识模式: 多个 LLM 独立回答 → 汇总最佳结果
"""
import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Callable

from ..bridges.base import BaseBridge, LLMResponse


class CollaborationMode(Enum):
    """协作模式"""
    SINGLE = "single"           # 单个 LLM 执行
    PIPELINE = "pipeline"       # 流水线: A→B→C
    CONSENSUS = "consensus"     # 共识: A+B+C → 汇总最佳
    ROUNDTABLE = "roundtable"   # 圆桌: 多轮讨论直到达成一致


@dataclass
class Task:
    """任务定义"""
    prompt: str
    context: str = ""
    mode: CollaborationMode = CollaborationMode.SINGLE
    bridges: List[BaseBridge] = field(default_factory=list)
    on_partial: Optional[Callable] = None  # 部分结果回调
    timeout: int = 300


@dataclass
class OrchestratorResult:
    """编排结果"""
    task: Task
    responses: List[LLMResponse] = field(default_factory=list)
    final_output: str = ""
    elapsed_seconds: float = 0.0
    success: bool = False
    error: Optional[str] = None


class Orchestrator:
    """任务编排器"""

    def __init__(self):
        self._bridges: dict = {}

    def register_bridge(self, name: str, bridge: BaseBridge):
        """注册 LLM 桥接器"""
        self._bridges[name] = bridge

    def get_bridge(self, name: str) -> Optional[BaseBridge]:
        """获取已注册的桥接器"""
        return self._bridges.get(name)

    async def execute(self, task: Task) -> OrchestratorResult:
        """执行任务"""
        result = OrchestratorResult(task=task)
        start = time.time()

        try:
            if task.mode == CollaborationMode.SINGLE:
                result = await self._execute_single(task)
            elif task.mode == CollaborationMode.PIPELINE:
                result = await self._execute_pipeline(task)
            elif task.mode == CollaborationMode.CONSENSUS:
                result = await self._execute_consensus(task)
            elif task.mode == CollaborationMode.ROUNDTABLE:
                result = await self._execute_roundtable(task)

            result.elapsed_seconds = time.time() - start
            result.success = bool(result.final_output)

        except Exception as e:
            result.success = False
            result.error = str(e)
            result.elapsed_seconds = time.time() - start

        return result

    async def _execute_single(self, task: Task) -> OrchestratorResult:
        """单 LLM 执行"""
        result = OrchestratorResult(task=task)

        if not task.bridges:
            raise ValueError("至少需要一个桥接器")

        bridge = task.bridges[0]
        response = await bridge.send_message(task.prompt, timeout=task.timeout)
        result.responses = [response]

        if response.success:
            result.final_output = response.content
        else:
            result.error = response.error

        return result

    async def _execute_pipeline(self, task: Task) -> OrchestratorResult:
        """
        流水线执行: LLM_A 输出 → LLM_B 审查 → LLM_C 优化
        
        适合：代码审查、文章审核、多轮润色
        """
        result = OrchestratorResult(task=task)
        if len(task.bridges) < 2:
            return await self._execute_single(task)

        current_prompt = task.prompt
        if task.context:
            current_prompt = f"[上下文]\n{task.context}\n\n[任务]\n{current_prompt}"

        for i, bridge in enumerate(task.bridges):
            # 根据阶段调整 prompt
            if i == len(task.bridges) - 1:
                # 最后一个桥接器：优化输出
                stage_prompt = (
                    f"[当前结果]\n{current_prompt}\n\n"
                    f"[任务]\n请优化、润色、完善上述内容，保持核心信息不变，"
                    f"使其结构清晰、语言流畅。"
                )
            elif i > 0:
                stage_prompt = (
                    f"[前一阶段输出]\n{current_prompt}\n\n"
                    f"[任务]\n请仔细审查上述内容，找出问题、补充遗漏、"
                    f"修正错误。输出改进版本。"
                )
            else:
                stage_prompt = current_prompt

            response = await bridge.send_message(stage_prompt)
            result.responses.append(response)

            if response.success:
                current_prompt = response.content
            else:
                result.error = f"阶段 {bridge.name} 失败: {response.error}"
                result.final_output = current_prompt
                return result

            if task.on_partial:
                await task.on_partial({
                    "stage": i,
                    "bridge": bridge.name,
                    "response": response,
                })

        result.final_output = current_prompt
        return result

    async def _execute_consensus(self, task: Task) -> OrchestratorResult:
        """
        共识模式: 多个 LLM 独立回答 → 汇总最佳结果
        
        适合：需要高准确性的问题（数学、逻辑、事实查询）
        """
        result = OrchestratorResult(task=task)

        # 所有桥接器并行执行
        tasks = [
            bridge.send_message(task.prompt, timeout=task.timeout)
            for bridge in task.bridges
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        for bridge, resp in zip(task.bridges, responses):
            if isinstance(resp, Exception):
                result.responses.append(LLMResponse(
                    success=False,
                    error=str(resp),
                    model_name=bridge.name,
                ))
            else:
                result.responses.append(resp)

        # 汇总：取最长最常见的回答（通常最完整）
        valid_responses = [
            r for r in result.responses if r.success
        ]

        if valid_responses:
            if len(valid_responses) == 1:
                result.final_output = valid_responses[0].content
            else:
                # 多个回答 → 选内容最长的（通常最详尽）
                best = max(valid_responses, key=lambda r: len(r.content))
                result.final_output = best.content

        if not result.final_output:
            result.error = "所有 LLM 均无有效回复"

        return result

    async def _execute_roundtable(self, task: Task) -> OrchestratorResult:
        """
        圆桌讨论: 多轮对话，直到达成共识
        
        适合：需要深度讨论的复杂问题
        """
        result = OrchestratorResult(task=task)
        max_rounds = 3
        discussion = []

        for rnd in range(max_rounds):
            round_responses = []
            for bridge in task.bridges:
                if rnd == 0:
                    prompt = task.prompt
                else:
                    # 参考上轮其他 LLM 的回答继续讨论
                    prev_summary = "\n".join(
                        f"[{r.model_name}]: {r.content[:200]}..."
                        for r in discussion[-1] if r.success
                    ) if discussion else ""
                    prompt = (
                        f"[原始问题]\n{task.prompt}\n\n"
                        f"[前一轮讨论]\n{prev_summary}\n\n"
                        f"[任务]\n请参考上述讨论，补充你的观点。"
                        f"如果与其他意见不一致，请解释原因。"
                        f"最终尝试达成共识。"
                    )

                resp = await bridge.send_message(prompt)
                round_responses.append(resp)

            discussion.append(round_responses)
            result.responses.extend(round_responses)

            if task.on_partial:
                await task.on_partial({
                    "round": rnd + 1,
                    "responses": round_responses,
                })

            # 检查是否已有一致答案
            success_count = sum(1 for r in round_responses if r.success)
            if success_count == len(task.bridges):
                # 所有 LLM 都成功，可能是最后一轮了
                break

        # 最终输出：取最后一轮最长的回答
        if discussion:
            last_round = discussion[-1]
            valid = [r for r in last_round if r.success]
            if valid:
                best = max(valid, key=lambda r: len(r.content))
                result.final_output = best.content

        return result
