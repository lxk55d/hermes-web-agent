"""测试编排器 — Orchestrator 多模式执行测试"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from hermes_web_agent.core.orchestrator import (
    Orchestrator,
    OrchestratorResult,
    Task,
    CollaborationMode,
)
from hermes_web_agent.bridges.base import LLMResponse


# ── Fixtures ────────────────────────────────────────────


@pytest.fixture
def mock_bridge():
    """模拟 BaseBridge"""
    bridge = MagicMock()
    bridge.name = "mock-llm"
    bridge.send_message = AsyncMock(
        return_value=LLMResponse(
            content="Mock response",
            model_name="mock-model",
            success=True,
            elapsed_seconds=0.5,
        )
    )
    return bridge


@pytest.fixture
def mock_failing_bridge():
    """模拟失败的桥接器"""
    bridge = MagicMock()
    bridge.name = "failing-llm"
    bridge.send_message = AsyncMock(
        return_value=LLMResponse(
            success=False,
            error="API error",
            model_name="failing-model",
        )
    )
    return bridge


# ── OrchestratorResult 数据类 ───────────────────────────


class TestOrchestratorResult:
    """测试 OrchestratorResult 数据类"""

    def test_default_initialization(self):
        task = Task(prompt="hello", mode=CollaborationMode.SINGLE)
        result = OrchestratorResult(task=task)
        assert result.task == task
        assert result.responses == []
        assert result.final_output == ""
        assert result.elapsed_seconds == 0.0
        assert result.success is False
        assert result.error is None

    def test_serializable(self):
        """确认数据类可以被序列化（如 JSON）"""
        task = Task(prompt="test")
        result = OrchestratorResult(
            task=task,
            responses=[LLMResponse(content="hi", success=True)],
            final_output="hi",
            elapsed_seconds=1.5,
            success=True,
        )
        d = {
            "success": result.success,
            "final_output": result.final_output,
            "elapsed_seconds": result.elapsed_seconds,
        }
        assert d["success"] is True
        assert d["final_output"] == "hi"
        assert d["elapsed_seconds"] == 1.5


# ── Orchestrator 基础 ────────────────────────────────────


class TestOrchestrator:
    """编排器基础功能测试"""

    def test_register_and_get_bridge(self, mock_bridge):
        """注册和获取桥接器"""
        orch = Orchestrator()
        orch.register_bridge("gpt", mock_bridge)
        assert orch.get_bridge("gpt") == mock_bridge
        assert orch.get_bridge("nonexistent") is None

    def test_get_bridge_empty(self):
        """未注册时返回 None"""
        orch = Orchestrator()
        assert orch.get_bridge("anything") is None


# ── 单 LLM 模式 ────────────────────────────────────────


class TestSingleMode:
    """SINGLE 模式测试"""

    @pytest.mark.asyncio
    async def test_single_mode_success(self, mock_bridge):
        """单 LLM 执行成功"""
        orch = Orchestrator()
        task = Task(prompt="Hello", mode=CollaborationMode.SINGLE, bridges=[mock_bridge])

        result = await orch.execute(task)
        assert result.success is True
        assert result.final_output == "Mock response"
        assert len(result.responses) == 1
        mock_bridge.send_message.assert_called_once_with("Hello", timeout=300)

    @pytest.mark.asyncio
    async def test_single_mode_failure(self, mock_failing_bridge):
        """单 LLM 执行失败"""
        orch = Orchestrator()
        task = Task(
            prompt="Hello",
            mode=CollaborationMode.SINGLE,
            bridges=[mock_failing_bridge],
        )

        result = await orch.execute(task)
        assert result.success is False
        assert result.error == "API error"

    @pytest.mark.asyncio
    async def test_single_mode_no_bridges(self):
        """没有桥接器时抛出 ValueError"""
        orch = Orchestrator()
        task = Task(prompt="Hello", mode=CollaborationMode.SINGLE, bridges=[])

        result = await orch.execute(task)
        assert result.success is False
        assert result.error is not None


# ── 流水线模式 ──────────────────────────────────────────


class TestPipelineMode:
    """PIPELINE 模式测试"""

    @pytest.mark.asyncio
    async def test_pipeline_mode_two_bridges(self, mock_bridge):
        """两个桥接器的流水线"""
        bridge2 = MagicMock()
        bridge2.name = "mock-llm-2"
        bridge2.send_message = AsyncMock(
            return_value=LLMResponse(
                content="Optimized output",
                model_name="mock-model-2",
                success=True,
            )
        )

        orch = Orchestrator()
        task = Task(
            prompt="Write a poem",
            mode=CollaborationMode.PIPELINE,
            bridges=[mock_bridge, bridge2],
        )

        result = await orch.execute(task)
        assert result.success is True
        assert result.final_output == "Optimized output"
        assert len(result.responses) == 2

    @pytest.mark.asyncio
    async def test_pipeline_mode_single_bridge(self, mock_bridge):
        """只有一个桥接器时退化为单执行"""
        orch = Orchestrator()
        task = Task(
            prompt="Hello",
            mode=CollaborationMode.PIPELINE,
            bridges=[mock_bridge],
        )

        result = await orch.execute(task)
        assert result.success is True
        assert result.final_output == "Mock response"

    @pytest.mark.asyncio
    async def test_pipeline_with_context(self, mock_bridge):
        """流水线带上下文"""
        bridge2 = MagicMock()
        bridge2.name = "mock-llm-2"
        bridge2.send_message = AsyncMock(
            return_value=LLMResponse(content="Final", success=True)
        )

        orch = Orchestrator()
        task = Task(
            prompt="Analyze",
            context="Some context",
            mode=CollaborationMode.PIPELINE,
            bridges=[mock_bridge, bridge2],
        )

        result = await orch.execute(task)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_pipeline_partial_callback(self, mock_bridge):
        """流水线的部分结果回调"""
        bridge2 = MagicMock()
        bridge2.name = "mock-llm-2"
        bridge2.send_message = AsyncMock(
            return_value=LLMResponse(content="Final", success=True)
        )

        callback = AsyncMock()
        orch = Orchestrator()
        task = Task(
            prompt="Hello",
            mode=CollaborationMode.PIPELINE,
            bridges=[mock_bridge, bridge2],
            on_partial=callback,
        )

        result = await orch.execute(task)
        # 两个阶段回调（stage 0 和 stage 1）
        assert callback.call_count == 2


# ── 共识模式 ────────────────────────────────────────────


class TestConsensusMode:
    """CONSENSUS 模式测试"""

    @pytest.mark.asyncio
    async def test_consensus_mode_two_bridges(self, mock_bridge):
        """两个桥接器并行执行"""
        bridge2 = MagicMock()
        bridge2.name = "mock-llm-2"
        bridge2.send_message = AsyncMock(
            return_value=LLMResponse(
                content="Longer response from bridge 2",
                model_name="mock-model-2",
                success=True,
            )
        )

        orch = Orchestrator()
        task = Task(
            prompt="What is Python?",
            mode=CollaborationMode.CONSENSUS,
            bridges=[mock_bridge, bridge2],
        )

        result = await orch.execute(task)
        assert result.success is True
        # 取最长的回复
        assert result.final_output == "Longer response from bridge 2"
        assert len(result.responses) == 2

    @pytest.mark.asyncio
    async def test_consensus_all_fail(self, mock_failing_bridge):
        """所有桥接器都失败"""
        bridge2 = MagicMock()
        bridge2.name = "failing-2"
        bridge2.send_message = AsyncMock(
            return_value=LLMResponse(success=False, error="Error 2")
        )

        orch = Orchestrator()
        task = Task(
            prompt="Hello",
            mode=CollaborationMode.CONSENSUS,
            bridges=[mock_failing_bridge, bridge2],
        )

        result = await orch.execute(task)
        assert result.success is False
        assert result.error == "所有 LLM 均无有效回复"

    @pytest.mark.asyncio
    async def test_consensus_exception_handling(self, mock_bridge):
        """桥接器抛出异常时正确处理"""
        failing_bridge = MagicMock()
        failing_bridge.name = "crashing-llm"
        failing_bridge.send_message = AsyncMock(side_effect=Exception("Crash!"))

        orch = Orchestrator()
        task = Task(
            prompt="Hello",
            mode=CollaborationMode.CONSENSUS,
            bridges=[mock_bridge, failing_bridge],
        )

        result = await orch.execute(task)
        assert result.success is True
        assert len(result.responses) == 2
