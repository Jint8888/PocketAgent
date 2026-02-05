"""
Exceptions 模块单元测试

测试自定义异常类。

运行方式:
    pytest tests/test_exceptions.py -v
"""
import pytest


class TestPocketAgentError:
    """测试基础异常类"""

    def test_create_basic_error(self):
        """测试创建基础错误"""
        from exceptions import PocketAgentError

        error = PocketAgentError("Something went wrong")

        assert str(error) == "Something went wrong"
        assert error.message == "Something went wrong"
        assert error.context == {}

    def test_create_error_with_context(self):
        """测试创建带上下文的错误"""
        from exceptions import PocketAgentError

        error = PocketAgentError(
            "Operation failed",
            context={"operation": "save", "file": "test.json"}
        )

        assert "Operation failed" in str(error)
        assert "operation=save" in str(error)
        assert "file=test.json" in str(error)

    def test_error_is_exception(self):
        """测试错误可以被抛出和捕获"""
        from exceptions import PocketAgentError

        with pytest.raises(PocketAgentError) as exc_info:
            raise PocketAgentError("Test error")

        assert "Test error" in str(exc_info.value)


class TestMCPErrors:
    """测试 MCP 相关异常"""

    def test_mcp_connection_error(self):
        """测试 MCP 连接错误"""
        from exceptions import MCPConnectionError, MCPError, PocketAgentError

        error = MCPConnectionError(
            server_name="weather-server",
            reason="Connection refused"
        )

        assert error.server_name == "weather-server"
        assert error.reason == "Connection refused"
        assert "weather-server" in str(error)
        assert isinstance(error, MCPError)
        assert isinstance(error, PocketAgentError)

    def test_mcp_tool_error(self):
        """测试 MCP 工具错误"""
        from exceptions import MCPToolError

        error = MCPToolError(
            tool_name="fetch_weather",
            reason="Invalid city parameter"
        )

        assert error.tool_name == "fetch_weather"
        assert error.reason == "Invalid city parameter"
        assert "fetch_weather" in str(error)


class TestMemoryError:
    """测试记忆系统异常"""

    def test_memory_error(self):
        """测试记忆错误"""
        from exceptions import MemoryError, PocketAgentError

        error = MemoryError(
            operation="save",
            reason="Disk full"
        )

        assert error.operation == "save"
        assert error.reason == "Disk full"
        assert "save" in str(error)
        assert isinstance(error, PocketAgentError)


class TestLLMErrors:
    """测试 LLM 相关异常"""

    def test_llm_error(self):
        """测试 LLM 错误"""
        from exceptions import LLMError, PocketAgentError

        error = LLMError(
            reason="Rate limit exceeded",
            model="gpt-4"
        )

        assert error.reason == "Rate limit exceeded"
        assert error.model == "gpt-4"
        assert isinstance(error, PocketAgentError)

    def test_llm_parse_error(self):
        """测试 LLM 解析错误"""
        from exceptions import LLMParseError, LLMError

        error = LLMParseError(
            reason="Invalid YAML format",
            response="not valid yaml {"
        )

        assert "Invalid YAML format" in str(error)
        assert error.response == "not valid yaml {"
        assert isinstance(error, LLMError)

    def test_llm_parse_error_truncates_long_response(self):
        """测试长响应被截断"""
        from exceptions import LLMParseError

        long_response = "x" * 500
        error = LLMParseError(
            reason="Parse failed",
            response=long_response
        )

        # 上下文中的预览应该被截断
        assert len(error.context.get("response_preview", "")) <= 203  # 200 + "..."


class TestNodeError:
    """测试节点执行异常"""

    def test_node_error(self):
        """测试节点错误"""
        from exceptions import NodeError, PocketAgentError

        error = NodeError(
            node_name="DecideNode",
            phase="exec",
            reason="Timeout"
        )

        assert error.node_name == "DecideNode"
        assert error.phase == "exec"
        assert error.reason == "Timeout"
        assert "DecideNode" in str(error)
        assert "exec" in str(error)
        assert isinstance(error, PocketAgentError)


class TestConfigError:
    """测试配置异常"""

    def test_config_error(self):
        """测试配置错误"""
        from exceptions import ConfigError, PocketAgentError

        error = ConfigError(
            config_name="OPENAI_API_KEY",
            reason="Environment variable not set"
        )

        assert error.config_name == "OPENAI_API_KEY"
        assert error.reason == "Environment variable not set"
        assert isinstance(error, PocketAgentError)


class TestExceptionHierarchy:
    """测试异常继承层级"""

    def test_all_errors_inherit_from_base(self):
        """测试所有错误都继承自 PocketAgentError"""
        from exceptions import (
            PocketAgentError,
            MCPError,
            MCPConnectionError,
            MCPToolError,
            MemoryError,
            LLMError,
            LLMParseError,
            NodeError,
            ConfigError,
        )

        error_classes = [
            MCPError,
            MCPConnectionError,
            MCPToolError,
            MemoryError,
            LLMError,
            LLMParseError,
            NodeError,
            ConfigError,
        ]

        for error_class in error_classes:
            assert issubclass(error_class, PocketAgentError), \
                f"{error_class.__name__} should inherit from PocketAgentError"

    def test_can_catch_all_with_base(self):
        """测试可以用基类捕获所有错误"""
        from exceptions import (
            PocketAgentError,
            MCPConnectionError,
            LLMError,
            NodeError,
        )

        errors = [
            MCPConnectionError("test", "reason"),
            LLMError("reason"),
            NodeError("node", "phase", "reason"),
        ]

        for error in errors:
            try:
                raise error
            except PocketAgentError as e:
                assert e is error  # 成功捕获
