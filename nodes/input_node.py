"""
InputNode - 用户输入节点

职责:
- 首次运行时初始化 MCP Manager
- 获取用户输入
- 处理控制命令 (/clear, /new, /reset, /forget)
- 重置任务状态
"""

import os
from datetime import datetime
from pocketflow import AsyncNode

from utils import async_input
from mcp_client import MCPManager
from memory import get_memory_index

from .base import Action
from .prompts import AGENT_SYSTEM_PROMPT
from .planning_utils import PLANNING_DIR, cleanup_planning_files

# 导入日志系统
from logging_config import log_user_input


class InputNode(AsyncNode):
    """
    用户输入节点

    职责:
    - 首次运行时初始化 MCP Manager
    - 获取用户输入
    - 处理控制命令 (/clear, /new, /reset, /forget)
    - 重置任务状态
    """

    async def prep_async(self, shared):
        """初始化并获取用户输入"""
        # ========================================
        # 首次运行：初始化 MCP Manager 和记忆索引
        # ========================================
        if "mcp_manager" not in shared:
            print("\n[INFO] Initializing MCP tool system...")

            # 获取当前时间（用于系统提示词和欢迎消息）
            # 使用 astimezone() 获取带时区的本地时间
            current_dt = datetime.now().astimezone()
            utc_offset = current_dt.strftime("%z")  # 如 +0800
            utc_offset_formatted = f"UTC{utc_offset[:3]}:{utc_offset[3:]}"  # 格式化为 UTC+08:00
            current_datetime_str = current_dt.strftime("%Y-%m-%d %H:%M:%S (%A)") + f" [{utc_offset_formatted}]"
            shared["current_datetime"] = current_datetime_str

            # 获取项目路径（用于系统提示词）
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            sandbox_path = os.path.join(project_root, PLANNING_DIR)
            shared["project_root"] = project_root
            shared["sandbox_path"] = sandbox_path

            try:
                manager = MCPManager("mcp.json")
                await manager.get_all_tools_async()
                shared["mcp_manager"] = manager

                if manager.tools:
                    tool_info = manager.format_tools_for_prompt()
                    shared["system_prompt"] = AGENT_SYSTEM_PROMPT.format(
                        tool_info=tool_info,
                        current_datetime=current_datetime_str,
                        project_root=project_root,
                        sandbox_path=sandbox_path
                    )
                    print(f"[OK] Loaded {len(manager.tools)} tools")
                else:
                    shared["system_prompt"] = AGENT_SYSTEM_PROMPT.format(
                        tool_info="(no tools)",
                        current_datetime=current_datetime_str,
                        project_root=project_root,
                        sandbox_path=sandbox_path
                    )
                    print("[WARN] No tools available")

            except Exception as e:
                print(f"[WARN] MCP initialization failed: {e}")
                shared["mcp_manager"] = None
                shared["system_prompt"] = AGENT_SYSTEM_PROMPT.format(
                    tool_info="(init failed)",
                    current_datetime=current_datetime_str,
                    project_root=project_root,
                    sandbox_path=sandbox_path
                )

            # 初始化对话历史
            shared["messages"] = []

            # 初始化记忆索引
            shared["memory_index"] = get_memory_index()
            print(f"[OK] Memory index ready ({len(shared['memory_index'])} items)")

            print("\n" + "=" * 50)
            print("Welcome! Multi-step reasoning assistant ready.")
            print(f"Current time: {current_datetime_str}")
            print("Type 'exit' to quit.")
            print("=" * 50)

        # ========================================
        # 获取用户输入
        # ========================================
        user_input = await async_input("\n[User]: ")

        # 处理退出命令
        if user_input.lower() in ['exit', 'quit', 'q', 'bye']:
            return None

        # 处理空输入
        if not user_input:
            return "empty"

        # ========================================
        # 处理控制命令
        # ========================================
        if user_input.startswith('/'):
            return {"type": "command", "command": user_input}

        return user_input

    async def exec_async(self, user_input):
        """直接传递用户输入"""
        return user_input

    async def post_async(self, shared, prep_res, exec_res):
        """保存用户输入并开始任务"""
        if prep_res is None:
            # 保存记忆索引
            memory_index = shared.get("memory_index")
            if memory_index and len(memory_index) > 0:
                memory_index.save("memory_index.json")
            print("\n[INFO] Goodbye!")
            return None  # 结束流程

        if prep_res == "empty":
            return Action.INPUT  # 重新获取输入

        # ========================================
        # 处理控制命令
        # ========================================
        if isinstance(exec_res, dict) and exec_res.get("type") == "command":
            command = exec_res.get("command", "").lower()

            if command == "/clear":
                # 清除当前任务上下文
                shared["context"] = ""
                shared["step_count"] = 0
                shared["supervisor_retry_count"] = 0
                print("\n✓ [Command] Current task context cleared")
                print("   - Tool call history: cleared")
                print("   - Think analysis: cleared")
                print("   - Step count: reset to 0")
                return Action.INPUT

            elif command in ["/new", "/newtask"]:
                # 开始新任务：清除上下文 + 规划文件
                shared["context"] = ""
                shared["step_count"] = 0
                shared["supervisor_retry_count"] = 0
                shared["has_plan"] = False
                shared["tool_call_count"] = 0
                cleanup_planning_files()
                print("\n✓ [Command] New task started")
                print("   - Current context: cleared")
                print("   - Planning files: removed")
                print("   - Dialog history: preserved")
                return Action.INPUT

            elif command == "/reset":
                # 完全重置：清除所有历史
                shared["context"] = ""
                shared["step_count"] = 0
                shared["supervisor_retry_count"] = 0
                shared["has_plan"] = False
                shared["tool_call_count"] = 0
                shared["messages"] = []
                cleanup_planning_files()
                print("\n✓ [Command] System fully reset")
                print("   - All context: cleared")
                print("   - Dialog history: cleared")
                print("   - Planning files: removed")
                print("   - Long-term memory: preserved")
                return Action.INPUT

            elif command == "/forget":
                # 清除长期记忆
                memory_index = shared.get("memory_index")
                if memory_index:
                    count = len(memory_index)
                    shared["memory_index"] = get_memory_index.__class__(dimension=384)
                    # 删除记忆文件
                    if os.path.exists("memory_index.json"):
                        os.remove("memory_index.json")
                    print(f"\n✓ [Command] Long-term memory cleared ({count} items removed)")
                else:
                    print("\n✓ [Command] No memory to clear")
                return Action.INPUT

            elif command == "/logoff":
                # 关闭日志记录
                from logging_config import disable_logging, is_logging_enabled
                if is_logging_enabled():
                    disable_logging()
                    print("\n✓ [Command] Logging disabled")
                    print("   - All log functions will not write to files")
                    print("   - Use /logon to re-enable logging")
                else:
                    print("\n✓ [Command] Logging is already disabled")
                return Action.INPUT

            elif command == "/logon":
                # 启用日志记录
                from logging_config import enable_logging, is_logging_enabled
                if not is_logging_enabled():
                    enable_logging()
                    print("\n✓ [Command] Logging enabled")
                    print("   - All operations will be logged to files")
                    print("   - Log files location: logs/")
                else:
                    print("\n✓ [Command] Logging is already enabled")
                return Action.INPUT

            elif command == "/help":
                # 显示帮助信息
                print("\n" + "=" * 50)
                print("Available Commands:")
                print("=" * 50)
                print("/clear      - Clear current task context only")
                print("/new        - Start a new task (clear context + plans)")
                print("/newtask    - Alias for /new")
                print("/reset      - Full reset (clear everything except memory)")
                print("/forget     - Clear long-term memory index")
                print("/logoff     - Disable logging to files")
                print("/logon      - Enable logging to files")
                print("/help       - Show this help message")
                print("exit/quit   - Exit the program")
                print("=" * 50)
                return Action.INPUT

            else:
                print(f"\n✗ [Command] Unknown command: {command}")
                print("   Type /help to see available commands")
                return Action.INPUT

        # ========================================
        # 正常任务处理
        # ========================================
        # 重置任务状态
        shared["current_task"] = exec_res
        shared["context"] = ""
        shared["step_count"] = 0
        shared["max_steps"] = 25  # 复杂任务需要更多步骤
        shared["extension_count"] = 0  # 初始化延长计数器

        # 添加到对话历史
        shared["messages"].append({"role": "user", "content": exec_res})

        # 记录用户输入到日志
        log_user_input(exec_res)

        print(f"\n[Task]: {exec_res}")
        print("-" * 40)

        return Action.PLANNING  # 先进入规划节点
