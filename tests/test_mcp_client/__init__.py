"""
MCP 客户端模块测试 (TDD RED Phase)

验证 MCP 客户端模块的导入兼容性和基本功能。

运行方式:
    pytest tests/test_mcp_client/test_mcp_imports.py -v
"""
import pytest


class TestMCPClientImportCompatibility:
    """测试 mcp_client 模块导入兼容性"""

    def test_import_mcp_manager(self):
        """测试导入 MCPManager 类"""
        from mcp_client import MCPManager
        assert MCPManager is not None

    def test_import_mcp_server_config(self):
        """测试导入 MCPServerConfig 数据类"""
        from mcp_client import MCPServerConfig
        assert MCPServerConfig is not None

    def test_import_tool(self):
        """测试导入 Tool 数据类"""
        from mcp_client import Tool
        assert Tool is not None

    def test_import_from_manager(self):
        """测试从 manager 模块直接导入"""
        from mcp_client.manager import MCPManager, MCPServerConfig, Tool
        assert MCPManager is not None
        assert MCPServerConfig is not None
        assert Tool is not None


class TestMCPServerConfig:
    """测试 MCPServerConfig 数据类"""

    def test_create_stdio_config(self):
        """测试创建 stdio 类型配置"""
        from mcp_client import MCPServerConfig

        config = MCPServerConfig(
            name="test-server",
            server_type="stdio",
            command="python",
            args=["-m", "test_module"],
            description="Test server"
        )

        assert config.name == "test-server"
        assert config.server_type == "stdio"
        assert config.command == "python"
        assert config.args == ["-m", "test_module"]
        assert config.enabled == True  # 默认值
        assert config.timeout == 60.0  # 默认值

    def test_create_sse_config(self):
        """测试创建 sse 类型配置"""
        from mcp_client import MCPServerConfig

        config = MCPServerConfig(
            name="sse-server",
            server_type="sse",
            url="http://localhost:8000/sse",
            description="SSE server"
        )

        assert config.name == "sse-server"
        assert config.server_type == "sse"
        assert config.url == "http://localhost:8000/sse"


class TestTool:
    """测试 Tool 数据类"""

    def test_create_tool(self):
        """测试创建 Tool 实例"""
        from mcp_client import Tool

        tool = Tool(
            name="weather_query",
            description="查询天气信息",
            input_schema={
                "type": "object",
                "properties": {
                    "city": {"type": "string"}
                },
                "required": ["city"]
            },
            server_name="weather-server"
        )

        assert tool.name == "weather_query"
        assert tool.description == "查询天气信息"
        assert tool.server_name == "weather-server"
        assert "city" in tool.input_schema["properties"]


class TestMCPManagerInstantiation:
    """测试 MCPManager 实例化"""

    def test_manager_instantiation_with_missing_config(self):
        """测试配置文件不存在时的处理"""
        from mcp_client import MCPManager

        # 使用不存在的配置文件
        manager = MCPManager("nonexistent_config.json")

        # 应该能正常创建，只是没有服务器配置
        assert manager is not None
        assert len(manager.servers) == 0

    def test_manager_has_required_methods(self):
        """测试 MCPManager 有必需的方法"""
        from mcp_client import MCPManager

        manager = MCPManager("nonexistent_config.json")

        # 验证必需方法存在
        assert hasattr(manager, 'get_all_tools_async')
        assert hasattr(manager, 'call_tool_async')
        assert hasattr(manager, 'get_all_tools')
        assert hasattr(manager, 'call_tool')
        assert hasattr(manager, 'format_tools_for_prompt')

        # 验证方法可调用
        assert callable(manager.get_all_tools_async)
        assert callable(manager.call_tool_async)
        assert callable(manager.format_tools_for_prompt)
