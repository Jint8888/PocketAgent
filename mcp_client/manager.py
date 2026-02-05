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
import logging
import traceback
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Literal

# ============================================================================
# 日志配置
# ============================================================================

# 创建日志记录器
logger = logging.getLogger("mcp_manager")
logger.setLevel(logging.INFO)  # 生产环境使用 INFO 级别

# 创建文件处理器，写入日志文件
log_file = Path(__file__).parent.parent / "logs" / "mcp_manager.log"
log_file.parent.mkdir(parents=True, exist_ok=True)
file_handler = logging.FileHandler(log_file, encoding="utf-8", mode="a")
file_handler.setLevel(logging.INFO)  # 只记录 INFO 及以上级别

# 创建控制台处理器（只显示错误）
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.ERROR)  # 生产环境只显示错误

# 设置日志格式
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# 添加处理器
if not logger.handlers:
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


# ============================================================================
# 安全环境变量白名单
# ============================================================================

SAFE_ENV_VARS = [
    # 系统必需
    "PATH", "HOME", "USER", "SHELL", "LANG", "LC_ALL", "LC_CTYPE", "TERM",
    # Windows 必需
    "SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP", "USERPROFILE",
    "APPDATA", "LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)",
    "COMMONPROGRAMFILES", "COMSPEC", "WINDIR", "PATHEXT",
    # Node.js / Python 运行时
    "NODE_PATH", "NODE_ENV", "PYTHONPATH", "VIRTUAL_ENV", "CONDA_PREFIX",
    # 代理设置（某些工具需要）
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "no_proxy",
]


# ============================================================================
# Stderr 过滤模式（这些是已知的无害信息，不需要显示警告）
# ============================================================================

STDERR_IGNORE_PATTERNS = [
    # MCP 服务器正常启动信息
    "Secure MCP Filesystem Server running",
    "running on stdio",
    "MCP Server",
    # Context7 相关
    "CLIENT_IP_ENCRYPTION_KEY",
    "Context7 Documentation MCP Server",
    # UV/Python 相关的信息性输出
    "Using Python",
    "Resolved",
    "Installed",
    # 一般性的调试/信息输出
    "DEBUG:",
    "INFO:",
    # Excel-MCP 服务器内部已处理的异常（服务器仍然正常工作）
    "excel_mcp",
    "traceback.print_exc()",
    # 常见的 finally 块输出（通常是清理消息）
    "finally:",
]


# ============================================================================
# 工具 Schema 补丁（用于修复已知有问题的工具 schema）
# ============================================================================

TOOL_SCHEMA_PATCHES: Dict[str, Dict[str, Any]] = {
    # 修复 xueqiu fetch_stock_quote 缺少参数的问题
    "fetch_stock_quote": {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Stock symbol (e.g., SH600016, SZ000001)"
            }
        },
        "required": ["symbol"]
    },
    # 可以在此添加更多工具的 schema 修复
}


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
        """
        修复已知有问题的工具 schema

        使用 TOOL_SCHEMA_PATCHES 常量中定义的补丁，
        只有当工具的 input_schema 为空或缺少 properties 时才应用。
        """
        for tool in tools:
            if tool.name in TOOL_SCHEMA_PATCHES:
                # 只在 schema 缺失或不完整时修复
                if not tool.input_schema or "properties" not in tool.input_schema:
                    print(f"   [Fix] Auto-patching schema for: {tool.name}")
                    tool.input_schema = TOOL_SCHEMA_PATCHES[tool.name]

    async def _get_tools_stdio_async(self, server_name: str) -> List[Tool]:
        """【异步】通过 stdio 协议获取工具"""
        logger.debug(f"[{server_name}] Starting stdio tool discovery")
        
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            logger.debug(f"[{server_name}] MCP imports successful")
        except ImportError as e:
            logger.error(f"[{server_name}] MCP import failed: {e}")
            print(f"  ❌ {server_name}: 未安装 mcp 库")
            return []

        config = self.servers[server_name]
        tools: List[Tool] = []

        try:
            logger.debug(f"[{server_name}] Creating StdioServerParameters: command={config.command}, args={config.args}")
            logger.debug(f"[{server_name}] Environment variables: {list(self._get_safe_env(config.env).keys())}")
            
            server_params = StdioServerParameters(
                command=config.command,
                args=config.args,
                env=self._get_safe_env(config.env)
            )
            logger.debug(f"[{server_name}] StdioServerParameters created successfully")

            # 方案B修复：使用临时文件捕获 stderr，避免干扰 MCP 协议通信
            import tempfile
            errlog_file = tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors='replace')
            
            # 使用 async with 管理连接生命周期
            logger.debug(f"[{server_name}] Entering stdio_client context with errlog...")
            async with stdio_client(server_params, errlog=errlog_file) as (read, write):
                logger.debug(f"[{server_name}] stdio_client connected, entering ClientSession...")
                async with ClientSession(read, write) as session:
                    logger.debug(f"[{server_name}] ClientSession created, initializing...")
                    await session.initialize()
                    logger.debug(f"[{server_name}] Session initialized, listing tools...")
                    response = await session.list_tools()
                    logger.debug(f"[{server_name}] Got {len(response.tools)} tools")

                    for tool in response.tools:
                        tools.append(Tool(
                            name=tool.name,
                            description=tool.description or "",
                            input_schema=tool.inputSchema or {},
                            server_name=server_name
                        ))
                    logger.debug(f"[{server_name}] Exiting ClientSession...")
                logger.debug(f"[{server_name}] ClientSession closed")
            logger.debug(f"[{server_name}] stdio_client context exited successfully")
            
            # 读取并记录 stderr 输出（如果有且需要关注）
            try:
                errlog_file.seek(0)
                stderr_content = errlog_file.read()
                if stderr_content.strip():
                    # 检查是否应该忽略这些输出
                    should_warn = not any(
                        pattern in stderr_content for pattern in STDERR_IGNORE_PATTERNS
                    )
                    if should_warn:
                        logger.warning(f"[{server_name}] Server stderr output: {stderr_content[:500]}")
                    else:
                        # 只记录到 debug 级别，不显示在控制台
                        logger.debug(f"[{server_name}] Server stderr (ignored): {stderr_content[:200]}")
            finally:
                errlog_file.close()

            print(f"  ✅ {server_name} (stdio): {len(tools)} 个工具")
            logger.info(f"[{server_name}] Successfully discovered {len(tools)} tools")
            
        except BaseException as e:
            # 捕获包括 ExceptionGroup 在内的所有异常
            error_msg = str(e)
            full_traceback = traceback.format_exc()
            
            logger.error(f"[{server_name}] Exception type: {type(e).__name__}")
            logger.error(f"[{server_name}] Exception message: {error_msg}")
            logger.error(f"[{server_name}] Full traceback:\n{full_traceback}")
            
            if hasattr(e, 'exceptions'):
                # Python 3.11+ ExceptionGroup - 提取内部异常
                logger.error(f"[{server_name}] ExceptionGroup with {len(e.exceptions)} sub-exceptions:")
                for i, ex in enumerate(e.exceptions):
                    logger.error(f"[{server_name}]   Sub-exception {i+1}: {type(ex).__name__}: {ex}")
                    logger.error(f"[{server_name}]   Sub-traceback:\n{''.join(traceback.format_exception(type(ex), ex, ex.__traceback__))}")
                inner_errors = [str(ex) for ex in e.exceptions]
                error_msg = f"{'; '.join(inner_errors)}"
            
            print(f"  ❌ {server_name} (stdio): {error_msg}")

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
        import tempfile

        config = self.servers[server_name]

        async def _call():
            server_params = StdioServerParameters(
                command=config.command,
                args=config.args,
                env=self._get_safe_env(config.env)
            )

            # 方案B修复：使用临时文件捕获 stderr
            errlog_file = tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors='replace')
            
            try:
                async with stdio_client(server_params, errlog=errlog_file) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(tool_name, arguments)
                        return self._extract_tool_result(result)
            finally:
                # 记录 stderr 输出（如果有且需要关注）
                try:
                    errlog_file.seek(0)
                    stderr_content = errlog_file.read()
                    if stderr_content.strip():
                        should_warn = not any(
                            pattern in stderr_content for pattern in STDERR_IGNORE_PATTERNS
                        )
                        if should_warn:
                            logger.warning(f"[{server_name}] Tool call stderr: {stderr_content[:500]}")
                        else:
                            logger.debug(f"[{server_name}] Tool stderr (ignored): {stderr_content[:200]}")
                finally:
                    errlog_file.close()

        # 使用 asyncio.wait_for 实现超时控制
        try:
            return await asyncio.wait_for(_call(), timeout=config.timeout)
        except asyncio.TimeoutError:
            return f'{{"error": "工具调用超时（{config.timeout}秒）"}}'
        except asyncio.CancelledError:
            return f'{{"error": "工具调用被取消"}}'
        except BaseException as e:
            # 捕获 ExceptionGroup / BaseExceptionGroup (Python 3.11+ TaskGroup 异常)
            error_msg = str(e)
            if "TaskGroup" in error_msg or "ExceptionGroup" in type(e).__name__:
                # 尝试提取内部异常
                if hasattr(e, 'exceptions'):
                    inner_errors = [str(ex) for ex in e.exceptions]
                    error_msg = f"TaskGroup errors: {'; '.join(inner_errors)}"
            return f'{{"error": "{error_msg}"}}'

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
                    return self._extract_tool_result(result)

        try:
            return await asyncio.wait_for(_call(), timeout=config.timeout)
        except asyncio.TimeoutError:
            return f'{{"error": "工具调用超时（{config.timeout}秒）"}}'

    # ========================================================================
    # 同步 API (兼容旧代码，内部调用异步方法)
    # ========================================================================

    def _get_safe_env(self, config_env: Dict[str, str]) -> Dict[str, str]:
        """
        获取环境变量

        方案A修复：传递完整的系统环境变量，而非白名单过滤。
        这样可以确保子进程（如 uvx）能够获得所有必要的环境变量。
        
        配置文件中明确指定的变量会覆盖系统环境变量。
        """
        # 方案A：传递完整的系统环境变量
        full_env = dict(os.environ)
        
        # 配置文件中的变量覆盖/添加（这些是用户明确指定的）
        full_env.update(config_env)
        
        return full_env
        
        # ====================================================================
        # 原方案：白名单过滤（已弃用，保留供参考）
        # ====================================================================
        # safe_env = {}
        # 
        # for key in SAFE_ENV_VARS:
        #     # 直接匹配
        #     if key in os.environ:
        #         safe_env[key] = os.environ[key]
        #     # Windows 环境变量不区分大小写，尝试大写匹配
        #     elif key.upper() in os.environ:
        #         safe_env[key] = os.environ[key.upper()]
        # 
        # # 配置文件中的变量覆盖/添加（这些是用户明确指定的，可信任）
        # safe_env.update(config_env)
        # 
        # return safe_env

    def _run_sync(self, coro):
        """
        安全地在同步上下文中运行协程

        处理已有事件循环运行的情况（如 Jupyter Notebook、某些 Web 框架）。
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 没有运行中的事件循环，安全使用 asyncio.run
            return asyncio.run(coro)
        else:
            # 已有事件循环，创建新线程执行
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()

    def get_all_tools(self) -> List[Tool]:
        """【同步】从所有服务器获取工具"""
        return self._run_sync(self.get_all_tools_async())

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """【同步】调用工具"""
        return self._run_sync(self.call_tool_async(tool_name, arguments))

    # ========================================================================
    # 辅助方法
    # ========================================================================

    def _extract_tool_result(self, result) -> str:
        """
        安全提取工具调用结果

        处理各种可能的返回格式：文本、二进制数据、空结果等。
        """
        if not result.content:
            return '{"error": "Tool returned empty content"}'

        first_content = result.content[0]

        # 尝试获取文本内容
        if hasattr(first_content, 'text') and first_content.text is not None:
            return first_content.text

        # 尝试获取二进制数据
        if hasattr(first_content, 'data') and first_content.data is not None:
            import base64
            data_len = len(first_content.data)
            preview = base64.b64encode(first_content.data[:100]).decode() if data_len > 0 else ""
            return f'{{"type": "binary", "size": {data_len}, "preview": "{preview}..."}}'

        # 尝试获取 blob 类型
        if hasattr(first_content, 'blob') and first_content.blob is not None:
            return f'{{"type": "blob", "mimeType": "{getattr(first_content, "mimeType", "unknown")}"}}'

        # 兜底：转换为字符串
        return str(first_content)

    def format_tools_for_prompt(self) -> str:
        """将工具信息格式化为精简格式，大幅减少 token 消耗
        
        优化策略：
        1. 使用单行格式：tool_name(param1*, param2?): 简短描述
        2. 参数用 * 表示必填，? 表示可选
        3. 描述截断到第一行或前80字符
        4. 移除冗余的类型信息和详细说明
        5. **保留参数默认值**（如 token），确保 LLM 能使用正确的配置
        """
        tools_by_server: Dict[str, List[Tool]] = {}
        for tool in self.tools.values():
            if tool.server_name not in tools_by_server:
                tools_by_server[tool.server_name] = []
            tools_by_server[tool.server_name].append(tool)

        output_parts = []

        for server_name, tools in tools_by_server.items():
            server_config = self.servers.get(server_name)
            server_desc = server_config.description if server_config else ""
            # 截断服务器描述
            short_server_desc = server_desc.split('\n')[0][:60] if server_desc else ""

            # 服务器标题行（紧凑格式）
            server_lines = [f"## 【{server_name}】({len(tools)}个工具) - {short_server_desc}"]

            for tool in tools:
                properties = tool.input_schema.get("properties", {})
                required = tool.input_schema.get("required", [])

                # 参数列表（紧凑格式：name* 必填，name? 可选，有默认值显示 =value）
                param_parts = []
                for param_name, param_info in properties.items():
                    suffix = "*" if param_name in required else "?"
                    # 检查是否有默认值
                    default_value = param_info.get("default")
                    if default_value is not None:
                        # 有默认值时显示：param=value
                        param_parts.append(f"{param_name}={default_value}")
                    else:
                        param_parts.append(f"{param_name}{suffix}")
                param_str = ", ".join(param_parts) if param_parts else ""

                # 工具描述（截断到第一行或前80字符）
                desc = tool.description or ""
                # 取第一行
                first_line = desc.split('\n')[0].strip()
                # 截断
                if len(first_line) > 80:
                    short_desc = first_line[:77] + "..."
                else:
                    short_desc = first_line

                # 单行工具格式
                tool_line = f"  - {tool.name}({param_str}): {short_desc}"
                server_lines.append(tool_line)

            output_parts.append("\n".join(server_lines))

        return "\n\n".join(output_parts)

