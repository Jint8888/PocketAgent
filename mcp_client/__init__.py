"""
MCP (Model Context Protocol) 客户端模块

本模块提供 MCP 协议的客户端实现，用于连接和调用 MCP 服务器提供的工具。

注意: 模块命名为 mcp_client 以避免与官方 mcp 包冲突。

主要组件:
- MCPManager: MCP 服务器管理器，负责加载配置、发现工具、调用工具

使用示例:
    from mcp_client import MCPManager

    # 创建管理器（自动加载 mcp.json 配置）
    manager = MCPManager()

    # 获取所有可用工具
    tools = manager.get_all_tools()

    # 调用工具
    result = manager.call_tool("tool_name", {"param": "value"})
"""

from .manager import MCPManager, MCPServerConfig, Tool

__all__ = ["MCPManager", "MCPServerConfig", "Tool"]
