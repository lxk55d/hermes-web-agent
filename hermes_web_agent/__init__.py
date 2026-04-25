"""
Hermes Web Agent — 通过浏览器操控LLM网页版完成任务

Features:
  - 多LLM桥接: ChatGPT, Claude, DeepSeek, Gemini, Grok, Perplexity, Copilot 网页版
  - MCP Server: 集成到 Hermes / Claude Desktop / Cursor
  - Anti-detection: 浏览器指纹随机化、代理轮换、Cookie池、人类行为模拟
  - 多LLM协作: 流水线/共识/圆桌模式协同完成复杂任务
  - 会话持久化: Cookie自动保存复用，一次登录持续使用
  - MCP客户端集成: 通过 MCP Tool 直接调用桥接器
"""
