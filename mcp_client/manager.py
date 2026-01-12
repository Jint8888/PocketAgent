"""
MCP 管理器模块 (异步版本)

本模块实现了 MCP (Model Context Protocol) 客户端的核心功能：
1. 从 mcp.json 配置文件加载 MCP 服务器配置
2. 连接 MCP 服务器并发现可用工具
3. 调用 MCP 服务器上的工具

支持的传输类型:
- stdio: 通过启动子进程，使用 stdin/stdout 通信
- sse: 通过 HTTP Server-Sent Events 连接远程服务器

架构示意图:
    ┌──────────────┐
    │  MCPManager  │
    │   (Client)   │
    └──────┬───────┘
           │
     ┌─────┴─────┐
     │           │
     ▼           ▼
  ┌──────┐   ┌──────┐
  │stdio │   │ sse  │
  │Server│   │Server│
  └──────┘   └──────┘

依赖:
    pip install mcp httpx-sse
"""

import json
import asyncio
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Literal


# ============================================================================
# 数据类定义
# ============================================================================

@dataclass
class MCPServerConfig:
    """
    MCP 服务器配置数据类

    Attributes:
        name: 服务器名称
        server_type: 服务器类型 ("stdio" 或 "sse")
        command: 启动命令（stdio 类型）
        args: 命令行参数（stdio 类型）
        env: 环境变量（stdio 类型）
        url: SSE 服务器地址（sse 类型）
        description: 服务器描述
        enabled: 是否启用
        timeout: 工具调用超时时间（秒），默认 60 秒
    """
    name: str
    server_type: Literal["stdio", "sse"] = "stdio"
    command: str = ""
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    url: str = ""
    description: str = ""
    enabled: bool = True
    timeout: float = 60.0


@dataclass
class Tool:
    """
    MCP 工具信息数据类

    Attributes:
        name: 工具名称
        description: 工具描述
        input_schema: 输入参数的 JSON Schema
        server_name: 该工具所属的服务器名称
    """
    name: str
    description: str
    input_schema: Dict[str, Any]
    server_name: str


# ============================================================================
# MCP 管理器类 (支持同步和异步两种模式)
# ============================================================================

class MCPManager:
    """
    MCP 服务器管理器

    支持 stdio 和 sse 两种传输类型的 MCP 服务器。
    提供同步和异步两套 API，推荐使用异步版本以获得更好的性能。

    异步使用示例:
        manager = MCPManager("mcp.json")
        tools = await manager.get_all_tools_async()
        result = await manager.call_tool_async("tool_name", {"param": "value"})

    同步使用示例 (兼容旧代码):
        manager = MCPManager("mcp.json")
        tools = manager.get_all_tools()
        result = manager.call_tool("tool_name", {"param": "value"})
    """

    def __init__(self, config_path: str = "mcp.json"):
        """初始化 MCP 管理器"""
        self.config_path = config_path
        self.servers: Dict[str, MCPServerConfig] = {}
        self.tools: Dict[str, Tool] = {}
        self._load_config()

    # ========================================================================
    # 配置加载 (同步，只在初始化时调用一次)
    # ========================================================================

    def _load_config(self) -> None:
        """从 mcp.json 加载服务器配置"""
        config_file = Path(self.config_path)

        if not config_file.exists():
            print(f"⚠️ MCP 配置文件不存在: {self.config_path}")
            return

        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        for name, server_config in config.get("mcpServers", {}).items():
            if not server_config.get("enabled", True):
                print(f"   ⏭️ {name}: 已禁用")
                continue

            self.servers[name] = MCPServerConfig(
                name=name,
                server_type=server_config.get("type", "stdio"),
                command=server_config.get("command", ""),
                args=server_config.get("args", []),
                env=server_config.get("env", {}),
                url=server_config.get("url", ""),
                description=server_config.get("description", ""),
                enabled=server_config.get("enabled", True),
                timeout=server_config.get("timeout", 60.0)
            )

        print(f"📋 已加载 {len(self.servers)} 个 MCP 服务器配置")
        for name, cfg in self.servers.items():
            type_icon = "🖥️" if cfg.server_type == "stdio" else "🌐"
            print(f"   {type_icon} {name} ({cfg.server_type}): {cfg.description or '无描述'}")

    # ========================================================================
    # 异步工具发现 (推荐使用)
    # ========================================================================

    async def get_all_tools_async(self) -> List[Tool]:
        """
        【异步】从所有配置的 MCP 服务器获取可用工具

        使用 asyncio.gather 并发连接所有服务器，提高发现速度。
        """
        print("\n🔍 正在发现 MCP 工具 (异步模式)...")

        # 创建所有服务器的发现任务，并发执行
        tasks = []
        for server_name, config in self.servers.items():
            if config.server_type == "stdio":
                tasks.append(self._get_tools_stdio_async(server_name))
            elif config.server_type == "sse":
                tasks.append(self._get_tools_sse_async(server_name))
            else:
                print(f"  ❌ {server_name}: 未知类型 {config.server_type}")

        # 使用 asyncio.gather 并发执行所有任务
        # return_exceptions=True 确保单个失败不会影响其他任务
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 收集所有工具
        all_tools: List[Tool] = []
        tools_count_by_server: Dict[str, int] = {}

        for result in results:
            if isinstance(result, Exception):
                print(f"  ❌ 发现工具时出错: {result}")
            elif isinstance(result, list):
                all_tools.extend(result)
                if result:
                    server_name = result[0].server_name
                    tools_count_by_server[server_name] = len(result)

        # 缓存工具映射
        self.tools = {tool.name: tool for tool in all_tools}
        
        # 手动修复工具 schema
        self._patch_tool_schema(all_tools)

        # 显示汇总
        print(f"\n📦 共发现 {len(all_tools)} 个工具:")
        for server_name, count in tools_count_by_server.items():
            print(f"   - {server_name}: {count} 个工具")
        print()

        return all_tools

    def _patch_tool_schema(self, tools: List[Tool]):
        """手动修复某些工具的 schema 问题"""
        for tool in tools:
            # 修复 xueqiu fetch_stock_quote 缺少参数的问题
            # 只有当 input_schema 为空或者缺少 properties 时才修复
            if tool.name == "fetch_stock_quote" and (not tool.input_schema or "properties" not in tool.input_schema):
                print(f"🔧 [Fix] 自动修复工具 schema: {tool.name}")
                tool.input_schema = {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Stock symbol (e.g., SH600016, SZ000001)"
                        }
                    },
                    "required": ["symbol"]
                }

    async def _get_tools_stdio_async(self, server_name: str) -> List[Tool]:
        """【异步】通过 stdio 协议获取工具"""
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            print(f"  ❌ {server_name}: 未安装 mcp 库")
            return []

        config = self.servers[server_name]
        tools: List[Tool] = []

        try:
            server_params = StdioServerParameters(
                command=config.command,
                args=config.args,
                env={**os.environ, **config.env}
            )

            # 使用 async with 管理连接生命周期
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    response = await session.list_tools()

                    for tool in response.tools:
                        tools.append(Tool(
                            name=tool.name,
                            description=tool.description or "",
                            input_schema=tool.inputSchema or {},
                            server_name=server_name
                        ))

            print(f"  ✅ {server_name} (stdio): {len(tools)} 个工具")
        except Exception as e:
            print(f"  ❌ {server_name} (stdio): {e}")

        return tools

    async def _get_tools_sse_async(self, server_name: str) -> List[Tool]:
        """【异步】通过 SSE 协议获取工具"""
        try:
            from mcp import ClientSession
            from mcp.client.sse import sse_client
        except ImportError:
            print(f"  ❌ {server_name}: 未安装 mcp 库")
            return []

        config = self.servers[server_name]
        tools: List[Tool] = []

        try:
            async with sse_client(config.url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    response = await session.list_tools()

                    for tool in response.tools:
                        tools.append(Tool(
                            name=tool.name,
                            description=tool.description or "",
                            input_schema=tool.inputSchema or {},
                            server_name=server_name
                        ))

            print(f"  ✅ {server_name} (sse): {len(tools)} 个工具")
        except Exception as e:
            print(f"  ❌ {server_name} (sse): {e}")

        return tools

    # ========================================================================
    # 异步工具调用 (推荐使用)
    # ========================================================================

    async def call_tool_async(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        【异步】调用指定的工具

        Args:
            tool_name: 工具名称
            arguments: 工具参数字典

        Returns:
            工具执行结果（字符串）
        """
        if tool_name not in self.tools:
            raise ValueError(f"未知工具: {tool_name}，可用工具: {list(self.tools.keys())}")

        tool = self.tools[tool_name]
        config = self.servers[tool.server_name]

        print(f"🔧 调用工具: {tool_name}")
        print(f"   参数: {arguments}")
        print(f"   服务器: {tool.server_name} ({config.server_type})")

        # 根据服务器类型选择调用方式
        if config.server_type == "stdio":
            result = await self._call_tool_stdio_async(tool.server_name, tool_name, arguments)
        elif config.server_type == "sse":
            result = await self._call_tool_sse_async(tool.server_name, tool_name, arguments)
        else:
            raise ValueError(f"未知服务器类型: {config.server_type}")

        # 截断过长的结果显示
        display_result = result[:200] + "..." if len(str(result)) > 200 else result
        print(f"   结果: {display_result}")

        return result

    async def _call_tool_stdio_async(
        self, server_name: str, tool_name: str, arguments: Dict[str, Any]
    ) -> Any:
        """【异步】通过 stdio 协议调用工具（带超时）"""
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        config = self.servers[server_name]

        async def _call():
            server_params = StdioServerParameters(
                command=config.command,
                args=config.args,
                env={**os.environ, **config.env}
            )

            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
                    return result.content[0].text

        # 使用 asyncio.wait_for 实现超时控制
        try:
            return await asyncio.wait_for(_call(), timeout=config.timeout)
        except asyncio.TimeoutError:
            return f'{{"error": "工具调用超时（{config.timeout}秒）"}}'

    async def _call_tool_sse_async(
        self, server_name: str, tool_name: str, arguments: Dict[str, Any]
    ) -> Any:
        """【异步】通过 SSE 协议调用工具（带超时）"""
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        config = self.servers[server_name]

        async def _call():
            async with sse_client(config.url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
                    return result.content[0].text

        try:
            return await asyncio.wait_for(_call(), timeout=config.timeout)
        except asyncio.TimeoutError:
            return f'{{"error": "工具调用超时（{config.timeout}秒）"}}'

    # ========================================================================
    # 同步 API (兼容旧代码，内部调用异步方法)
    # ========================================================================

    def get_all_tools(self) -> List[Tool]:
        """【同步】从所有服务器获取工具 (内部使用 asyncio.run)"""
        return asyncio.run(self.get_all_tools_async())

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """【同步】调用工具 (内部使用 asyncio.run)"""
        return asyncio.run(self.call_tool_async(tool_name, arguments))

    # ========================================================================
    # 辅助方法
    # ========================================================================

    def format_tools_for_prompt(self) -> str:
        """将工具信息格式化为 LLM 可理解的文本（按服务器分组）"""
        tools_by_server: Dict[str, List[Tool]] = {}
        for tool in self.tools.values():
            if tool.server_name not in tools_by_server:
                tools_by_server[tool.server_name] = []
            tools_by_server[tool.server_name].append(tool)

        output_parts = []
        global_index = 1

        for server_name, tools in tools_by_server.items():
            server_config = self.servers.get(server_name)
            server_desc = server_config.description if server_config else ""

            server_section = [f"## 【{server_name}】 - {server_desc}"]
            server_section.append(f"   共 {len(tools)} 个工具:")

            for tool in tools:
                properties = tool.input_schema.get("properties", {})
                required = tool.input_schema.get("required", [])

                params = []
                for param_name, param_info in properties.items():
                    param_type = param_info.get("type", "unknown")
                    param_desc = param_info.get("description", "")
                    req_status = "[必填]" if param_name in required else "[可选]"
                    params.append(f"      - {param_name} ({param_type}): {param_desc} {req_status}")

                tool_info = f"\n   [{global_index}] {tool.name}\n"
                tool_info += f"       描述: {tool.description}\n"
                if params:
                    tool_info += f"       参数:\n" + "\n".join(params)
                else:
                    tool_info += f"       参数: 无"

                server_section.append(tool_info)
                global_index += 1

            output_parts.append("\n".join(server_section))

        return "\n\n".join(output_parts)


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == "__main__":
    async def test_async():
        """异步测试函数"""
        print("=" * 60)
        print("MCP Manager 异步测试")
        print("=" * 60)

        manager = MCPManager("mcp.json")

        # 使用异步方法获取工具
        tools = await manager.get_all_tools_async()

        print("\n可用工具:")
        print(manager.format_tools_for_prompt())

    # 运行异步测试
    asyncio.run(test_async())
