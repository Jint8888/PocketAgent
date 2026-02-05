"""
ToolNode - 工具执行节点 (含 Manus-style 2-动作规则)

职责:
- 调用 MCP 工具
- 将结果添加到上下文
- 实现 2-动作规则：每 N 次工具调用后更新 findings
- 记录进度到 progress.md
"""

import subprocess
import sys
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from pocketflow import AsyncNode

from memory import get_embedding, get_memory_index

from .base import (
    Action,
    CITY_TIMEZONE_MAP,
    MAX_TOOL_RESULT_LENGTH,
    MEMORY_DEDUP_THRESHOLD,
)
from .planning_utils import (
    FINDINGS_UPDATE_INTERVAL,
    update_plan_phase,
    append_to_findings,
    append_to_progress,
    record_error_in_plan,
    get_smart_implications,
)

# 导入日志系统
from logging_config import log_tool_call, log_tool_result, log_error


# ============================================================================
# 内置代码执行工具配置
# ============================================================================

# 项目虚拟环境的 Python 路径
PROJECT_PYTHON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".venv", "Scripts", "python.exe"
)
# 如果 Windows 路径不存在，尝试 Linux/Mac 路径
if not os.path.exists(PROJECT_PYTHON):
    PROJECT_PYTHON = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        ".venv", "bin", "python"
    )
# 如果还是不存在，使用系统 Python
if not os.path.exists(PROJECT_PYTHON):
    PROJECT_PYTHON = sys.executable

# 代码执行超时（秒）
CODE_EXECUTION_TIMEOUT = 120


class ToolNode(AsyncNode):
    """
    工具执行节点 (含 Manus-style 2-动作规则)

    职责:
    - 调用 MCP 工具
    - 将结果添加到上下文
    - 实现 2-动作规则：每 N 次工具调用后更新 findings
    - 记录进度到 progress.md
    """

    async def prep_async(self, shared):
        """获取工具调用信息（集成行为规则）"""
        # 加载全局行为规则（第一步实施）
        try:
            from rules_engine import load_rules
            rules = load_rules()
            if rules:
                # 将规则存入 shared，供后续节点使用
                shared["behavior_rules"] = rules
                # 首次加载时打印确认信息
                if "rules_loaded" not in shared:
                    print("[OK] Behavior rules loaded and active")
                    shared["rules_loaded"] = True
        except Exception as e:
            # 规则加载失败不影响主流程
            print(f"[WARN] Failed to load behavior rules: {e}")

        decision = shared.get("current_decision", {})
        tool_name = decision.get("tool_name", "")
        tool_params = decision.get("tool_params", {})
        return {"tool_name": tool_name, "tool_params": tool_params}

    async def exec_async(self, prep_res):
        """执行工具调用"""
        tool_name = prep_res.get("tool_name", "")
        tool_params = prep_res.get("tool_params", {})

        if not tool_name:
            return {"success": False, "error": "No tool name specified"}

        # 记录工具调用到日志
        log_tool_call(tool_name, tool_params)

        print(f"   [Tool]: {tool_name}")
        print(f"      Params: {tool_params}")

        # 这里需要从 shared 获取 manager，但 exec 无法访问 shared
        # 返回调用信息，在 post 中执行
        return {"tool_name": tool_name, "tool_params": tool_params}

    async def post_async(self, shared, prep_res, exec_res):
        """在 post 中执行工具调用（可以访问 shared）"""
        tool_name = exec_res.get("tool_name", "")
        tool_params = exec_res.get("tool_params", {})
        has_plan = shared.get("has_plan", False)

        # ========================================
        # 内置工具处理（不需要 MCP）
        # ========================================
        if tool_name == "get_current_time":
            # 内置时钟工具：返回当前准确时间（支持多时区）
            city = tool_params.get("city", "")
            tz_name = tool_params.get("timezone", "")
            location_info = ""

            # 确定时区
            target_tz = None
            if city:
                # 从城市映射查找时区
                city_lower = city.lower()
                tz_name = CITY_TIMEZONE_MAP.get(city) or CITY_TIMEZONE_MAP.get(city_lower)
                if tz_name:
                    try:
                        target_tz = ZoneInfo(tz_name)
                        location_info = f" [{city}]"
                    except Exception:
                        location_info = f" [Unknown city: {city}, using local time]"
                else:
                    location_info = f" [Unknown city: {city}, using local time]"
            elif tz_name:
                # 直接使用时区名称
                try:
                    target_tz = ZoneInfo(tz_name)
                    location_info = f" [{tz_name}]"
                except Exception:
                    location_info = f" [Invalid timezone: {tz_name}, using local time]"

            # 获取时间
            if target_tz:
                current_dt = datetime.now(target_tz)
                result_str = current_dt.strftime("%Y-%m-%d %H:%M:%S (%A)") + location_info
            else:
                # 本地时间：附加系统时区信息，让 Agent 知道基准时区
                current_dt = datetime.now().astimezone()  # 带时区的本地时间
                utc_offset = current_dt.strftime("%z")  # 如 +0800
                utc_offset_formatted = f"UTC{utc_offset[:3]}:{utc_offset[3:]}"  # 格式化为 UTC+08:00
                result_str = current_dt.strftime("%Y-%m-%d %H:%M:%S (%A)") + f" [Local: {utc_offset_formatted}]"
            print(f"   [OK] Built-in tool result: {result_str}")

            # 添加到上下文
            context = shared.get("context", "")
            shared["context"] = context + f"\n\n### Tool Call: {tool_name} (Built-in)\nResult: {result_str}"

            # Manus-style 进度记录
            if has_plan:
                append_to_progress(
                    action_type="Built-in Tool",
                    description=f"Called get_current_time{location_info}",
                    result=result_str
                )

            return Action.DECIDE

        # ========================================
        # 内置工具: save_to_memory - 用户主动保存到长期记忆
        # ========================================
        if tool_name == "save_to_memory":
            content = tool_params.get("content", "")
            tag = tool_params.get("tag", "用户保存")

            if not content:
                result_str = "Error: content parameter is required"
                print(f"   [ERROR] {result_str}")
            else:
                # 获取记忆索引
                memory_index = shared.get("memory_index")
                if not memory_index:
                    memory_index = get_memory_index()
                    shared["memory_index"] = memory_index

                # 添加时间戳和标签
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                memory_content = f"[{tag}] [{timestamp}]\n{content}"

                # 生成嵌入并存储
                embedding = get_embedding(memory_content)
                idx, is_new = memory_index.add_or_update(
                    embedding,
                    {"content": memory_content, "tag": tag, "timestamp": timestamp},
                    dedup_threshold=MEMORY_DEDUP_THRESHOLD
                )

                # 立即保存到文件
                memory_index.save("memory_index.json")

                if is_new:
                    result_str = f"Successfully saved to long-term memory (index: {idx}, tag: {tag})"
                else:
                    result_str = f"Updated existing similar memory (index: {idx}, tag: {tag})"

                print(f"   [OK] Built-in tool result: {result_str}")

            # 记录工具结果到日志
            log_tool_result(tool_name, True, result_str)

            # 添加到上下文
            context = shared.get("context", "")
            shared["context"] = context + f"\n\n### Tool Call: {tool_name} (Built-in)\nResult: {result_str}"

            # Manus-style 进度记录
            if has_plan:
                append_to_progress(
                    action_type="Built-in Tool",
                    description=f"Saved to memory with tag: {tag}",
                    result=result_str
                )

            return Action.DECIDE

        # ========================================
        # 内置工具: execute_python - 本地执行 Python 代码
        # 使用项目虚拟环境，可访问 akshare 等已安装库
        # ========================================
        if tool_name == "execute_python":
            code = tool_params.get("code", "")
            if not code:
                result_str = "Error: code parameter is required"
                print(f"   [ERROR] {result_str}")
            else:
                try:
                    # 使用项目虚拟环境的 Python 执行代码
                    result = subprocess.run(
                        [PROJECT_PYTHON, "-c", code],
                        capture_output=True,
                        text=True,
                        timeout=CODE_EXECUTION_TIMEOUT,
                        encoding='utf-8',
                        errors='replace',
                        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    )

                    output_parts = []
                    if result.stdout:
                        output_parts.append(result.stdout)
                    if result.stderr:
                        output_parts.append(f"[STDERR] {result.stderr}")
                    if result.returncode != 0:
                        output_parts.append(f"[Exit Code: {result.returncode}]")

                    result_str = "\n".join(output_parts) if output_parts else "(No output)"

                except subprocess.TimeoutExpired:
                    result_str = f"[ERROR] Code execution timed out after {CODE_EXECUTION_TIMEOUT} seconds"
                except Exception as e:
                    result_str = f"[ERROR] {str(e)}"

            # 记录工具结果到日志
            log_tool_result(tool_name, True, result_str[:500] if len(result_str) > 500 else result_str)

            # 截断过大的结果
            if len(result_str) > MAX_TOOL_RESULT_LENGTH:
                result_str = result_str[:MAX_TOOL_RESULT_LENGTH] + f"\n... (truncated)"

            # 添加到上下文
            context = shared.get("context", "")
            shared["context"] = context + f"\n\n### Tool Call: {tool_name} (Built-in)\nCode:\n```python\n{code[:500]}{'...' if len(code) > 500 else ''}\n```\nResult:\n{result_str}"

            # Manus-style 进度记录
            if has_plan:
                append_to_progress(
                    action_type="Built-in Tool",
                    description=f"Executed Python code",
                    result=result_str[:200]
                )

            return Action.DECIDE

        # ========================================
        # 内置工具: execute_terminal - 本地执行终端命令
        # 使用 subprocess 执行 shell 命令
        # ========================================
        if tool_name == "execute_terminal":
            command = tool_params.get("command", "")
            if not command:
                result_str = "Error: command parameter is required"
                print(f"   [ERROR] {result_str}")
            else:
                try:
                    result = subprocess.run(
                        command,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=CODE_EXECUTION_TIMEOUT,
                        encoding='utf-8',
                        errors='replace',
                        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    )

                    output_parts = []
                    if result.stdout:
                        output_parts.append(result.stdout)
                    if result.stderr:
                        output_parts.append(f"[STDERR] {result.stderr}")
                    if result.returncode != 0:
                        output_parts.append(f"[Exit Code: {result.returncode}]")

                    result_str = "\n".join(output_parts) if output_parts else "(No output)"

                except subprocess.TimeoutExpired:
                    result_str = f"[ERROR] Command timed out after {CODE_EXECUTION_TIMEOUT} seconds"
                except Exception as e:
                    result_str = f"[ERROR] {str(e)}"

            # 记录工具结果到日志
            log_tool_result(tool_name, True, result_str[:500] if len(result_str) > 500 else result_str)

            # 截断过大的结果
            if len(result_str) > MAX_TOOL_RESULT_LENGTH:
                result_str = result_str[:MAX_TOOL_RESULT_LENGTH] + f"\n... (truncated)"

            # 添加到上下文
            context = shared.get("context", "")
            shared["context"] = context + f"\n\n### Tool Call: {tool_name} (Built-in)\nCommand: {command}\nResult:\n{result_str}"

            # Manus-style 进度记录
            if has_plan:
                append_to_progress(
                    action_type="Built-in Tool",
                    description=f"Executed: {command[:50]}",
                    result=result_str[:200]
                )

            return Action.DECIDE

        # ========================================
        # MCP 工具处理
        # ========================================
        manager = shared.get("mcp_manager")
        if not manager:
            shared["context"] += "\n\n[Tool call failed: MCP Manager not initialized]"
            # 记录错误到计划文件
            if shared.get("has_plan"):
                record_error_in_plan("MCP Manager not initialized")
            return Action.DECIDE

        try:
            result = await manager.call_tool_async(tool_name, tool_params)
            result_str = str(result)

            # ========================================
            # 截断过大的工具结果，防止上下文爆炸
            # ========================================
            original_length = len(result_str)
            if len(result_str) > MAX_TOOL_RESULT_LENGTH:
                result_str = result_str[:MAX_TOOL_RESULT_LENGTH] + f"\n\n... (truncated {original_length - MAX_TOOL_RESULT_LENGTH} chars)"
                print(f"   [WARN] Tool result truncated: {original_length} -> {MAX_TOOL_RESULT_LENGTH} chars")

            print(f"   [OK] Tool result: {result_str[:200]}..." if len(result_str) > 200 else f"   [OK] Tool result: {result_str}")

            # 记录工具结果到日志（使用预览）
            log_tool_result(tool_name, True, result_str[:500] if len(result_str) > 500 else result_str)

            # 添加到上下文（使用截断后的结果）
            context = shared.get("context", "")
            shared["context"] = context + f"\n\n### Tool Call: {tool_name}\nParams: {tool_params}\nResult:\n{result_str}"

            # ========================================
            # Manus-style: 2-动作规则 + 进度记录
            # ========================================
            if has_plan:
                # 更新工具调用计数
                tool_call_count = shared.get("tool_call_count", 0) + 1
                shared["tool_call_count"] = tool_call_count

                # 记录进度
                append_to_progress(
                    action_type="Tool Call",
                    description=f"Called {tool_name}",
                    tool_name=tool_name,
                    result=result_str[:200]
                )

                # 2-动作规则：每 N 次工具调用后更新 findings
                if tool_call_count % FINDINGS_UPDATE_INTERVAL == 0:
                    finding_title = f"Tool Result: {tool_name}"
                    smart_impl = get_smart_implications(tool_name, result_str)
                    append_to_findings(
                        title=finding_title,
                        source=f"Tool: {tool_name}",
                        finding=result_str[:500],
                        implications=smart_impl
                    )
                    print(f"   [Planning] Updated findings (2-action rule)")

                # 更新阶段状态（工具调用 = Phase 1 信息收集）
                update_plan_phase(1, completed=False)

        except Exception as e:
            error_msg = str(e)
            print(f"   [ERROR] Tool call failed: {error_msg}")

            # 记录工具失败到日志
            log_tool_result(tool_name, False, error_msg)
            log_error(f"Tool call failed: {tool_name} - {error_msg}", exc_info=False)

            shared["context"] += f"\n\n[Tool call failed: {tool_name} - {error_msg}]"

            # Manus-style: 记录错误到计划文件（避免重复失败）
            if has_plan:
                record_error_in_plan(f"Tool {tool_name} failed: {error_msg[:100]}")
                append_to_progress(
                    action_type="Error",
                    description=f"Tool call failed: {tool_name}",
                    result=error_msg[:100]
                )

        return Action.DECIDE
