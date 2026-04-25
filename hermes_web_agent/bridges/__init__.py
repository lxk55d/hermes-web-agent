"""LLM网页版桥接模块"""
from .base import BaseBridge, LLMResponse
from .chatgpt import ChatGPTBridge
from .claude import ClaudeBridge
from .deepseek import DeepSeekBridge
from .gemini import GeminiBridge
from .grok import GrokBridge
from .perplexity import PerplexityBridge
from .copilot import CopilotBridge
from .kimi import KimiBridge

__all__ = [
    "BaseBridge",
    "LLMResponse",
    "ChatGPTBridge",
    "ClaudeBridge",
    "DeepSeekBridge",
    "GeminiBridge",
    "GrokBridge",
    "PerplexityBridge",
    "CopilotBridge",
    "KimiBridge",
]
