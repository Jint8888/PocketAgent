"""
PocketAgent 自定义异常模块

提供统一的异常处理和错误传播机制。

异常层级:
- PocketAgentError (基础异常)
  ├── MCPError (MCP 相关)
  │   ├── MCPConnectionError
  │   └── MCPToolError
  ├── MemoryError (记忆系统)
  ├── LLMError (LLM 调用)
  └── NodeError (节点执行)
"""


class PocketAgentError(Exception):
    """
    PocketAgent 基础异常类

    所有自定义异常的基类，便于统一捕获和处理。

    Attributes:
        message: 错误消息
        context: 错误上下文信息 (可选)
    """

    def __init__(self, message: str, context: dict | None = None):
        self.message = message
        self.context = context or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            return f"{self.message} [{context_str}]"
        return self.message


# ============================================================================
# MCP 相关异常
# ============================================================================

class MCPError(PocketAgentError):
    """MCP 相关错误的基类"""
    pass


class MCPConnectionError(MCPError):
    """
    MCP 服务器连接错误

    当无法连接到 MCP 服务器时抛出。

    Examples:
        - 服务器未启动
        - 网络连接失败
        - 配置文件错误
    """

    def __init__(self, server_name: str, reason: str, context: dict | None = None):
        ctx = context or {}
        ctx["server"] = server_name
        super().__init__(f"Failed to connect to MCP server '{server_name}': {reason}", ctx)
        self.server_name = server_name
        self.reason = reason


class MCPToolError(MCPError):
    """
    MCP 工具调用错误

    当 MCP 工具调用失败时抛出。

    Examples:
        - 工具不存在
        - 参数错误
        - 工具执行超时
    """

    def __init__(self, tool_name: str, reason: str, context: dict | None = None):
        ctx = context or {}
        ctx["tool"] = tool_name
        super().__init__(f"Tool '{tool_name}' failed: {reason}", ctx)
        self.tool_name = tool_name
        self.reason = reason


# ============================================================================
# 记忆系统异常
# ============================================================================

class VectorMemoryError(PocketAgentError):
    """
    向量记忆系统错误

    当向量记忆操作失败时抛出。

    注意：使用 VectorMemoryError 而非 MemoryError，
    避免与 Python 内置的 MemoryError 冲突。

    Examples:
        - 嵌入模型加载失败
        - 向量索引损坏
        - 保存/加载失败
    """

    def __init__(self, operation: str, reason: str, context: dict | None = None):
        ctx = context or {}
        ctx["operation"] = operation
        super().__init__(f"Memory {operation} failed: {reason}", ctx)
        self.operation = operation
        self.reason = reason


# 向后兼容别名（将在未来版本中移除）
MemoryError = VectorMemoryError


# ============================================================================
# LLM 调用异常
# ============================================================================

class LLMError(PocketAgentError):
    """
    LLM 调用错误

    当 LLM API 调用失败时抛出。

    Examples:
        - API 密钥无效
        - 请求超时
        - 速率限制
    """

    def __init__(self, reason: str, model: str | None = None, context: dict | None = None):
        ctx = context or {}
        if model:
            ctx["model"] = model
        super().__init__(f"LLM call failed: {reason}", ctx)
        self.reason = reason
        self.model = model


class LLMParseError(LLMError):
    """
    LLM 响应解析错误

    当无法解析 LLM 返回的响应时抛出。

    Examples:
        - YAML 格式错误
        - 缺少必需字段
        - 响应为空
    """

    def __init__(self, reason: str, response: str | None = None, context: dict | None = None):
        ctx = context or {}
        if response:
            # 只保留前 200 字符用于调试
            ctx["response_preview"] = response[:200] + "..." if len(response) > 200 else response
        super().__init__(f"Failed to parse LLM response: {reason}", context=ctx)
        self.response = response


# ============================================================================
# 节点执行异常
# ============================================================================

class NodeError(PocketAgentError):
    """
    节点执行错误

    当工作流节点执行失败时抛出。

    Examples:
        - 节点初始化失败
        - 执行超时
        - 状态不一致
    """

    def __init__(self, node_name: str, phase: str, reason: str, context: dict | None = None):
        ctx = context or {}
        ctx["node"] = node_name
        ctx["phase"] = phase
        super().__init__(f"Node '{node_name}' failed in {phase}: {reason}", ctx)
        self.node_name = node_name
        self.phase = phase
        self.reason = reason


# ============================================================================
# 配置异常
# ============================================================================

class ConfigError(PocketAgentError):
    """
    配置错误

    当配置文件或环境变量有问题时抛出。

    Examples:
        - 配置文件不存在
        - 必需的环境变量缺失
        - 配置格式错误
    """

    def __init__(self, config_name: str, reason: str, context: dict | None = None):
        ctx = context or {}
        ctx["config"] = config_name
        super().__init__(f"Configuration error for '{config_name}': {reason}", ctx)
        self.config_name = config_name
        self.reason = reason
