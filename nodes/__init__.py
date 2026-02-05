"""
节点模块包 - 向后兼容导入层

此包将原 nodes.py 大文件(2700+行)拆分为多个独立模块，
同时保持 `from nodes import *` 的向后兼容性。

模块结构:
- base.py: 共享常量、辅助函数、配置
- planning_utils.py: Manus-style 规划文件操作
- prompts.py: 系统提示词模板
- input_node.py: InputNode
- planning_node.py: PlanningNode
- retrieve_node.py: RetrieveNode
- decide_node.py: DecideNode
- tool_node.py: ToolNode
- think_node.py: ThinkNode
- answer_node.py: AnswerNode
- embed_node.py: EmbedNode
- supervisor_node.py: SupervisorNode

使用方式 (向后兼容):
    from nodes import InputNode, DecideNode, ToolNode, ...
    from nodes import Action, parse_yaml_response
"""

# 从 base 模块导入共享组件
from .base import (
    Action,
    parse_yaml_response,
    MEMORY_WINDOW_SIZE,
    CONTEXT_WINDOW_SIZE,
    MAX_TOOL_RESULT_LENGTH,
    MEMORY_RETRIEVE_K,
    MEMORY_SIMILARITY_THRESHOLD,
    MEMORY_DEDUP_THRESHOLD,
    SUPERVISOR_MAX_RETRIES,
    YAML_PARSE_MAX_RETRIES,
    YAML_FORMAT_REMINDER,
)

# 从 planning_utils 导入规划相关函数
from .planning_utils import (
    PLANNING_DIR,
    PLAN_FILE,
    FINDINGS_FILE,
    PROGRESS_FILE,
    get_planning_file_path,
    read_planning_file,
    write_planning_file,
    update_plan_phase,
    append_to_findings,
    append_to_progress,
    record_error_in_plan,
    get_plan_completion_status,
    is_complex_task,
    cleanup_planning_files,
    archive_planning_files,
    get_smart_implications,
)

# 导入所有节点类
from .input_node import InputNode
from .planning_node import PlanningNode
from .retrieve_node import RetrieveNode
from .decide_node import DecideNode
from .tool_node import ToolNode
from .think_node import ThinkNode
from .answer_node import AnswerNode
from .embed_node import EmbedNode
from .supervisor_node import SupervisorNode

__all__ = [
    # 节点类
    "InputNode",
    "PlanningNode",
    "RetrieveNode",
    "DecideNode",
    "ToolNode",
    "ThinkNode",
    "AnswerNode",
    "EmbedNode",
    "SupervisorNode",
    # 常量和工具
    "Action",
    "parse_yaml_response",
    # 配置常量
    "MEMORY_WINDOW_SIZE",
    "CONTEXT_WINDOW_SIZE",
    "MAX_TOOL_RESULT_LENGTH",
    "MEMORY_RETRIEVE_K",
    "MEMORY_SIMILARITY_THRESHOLD",
    "MEMORY_DEDUP_THRESHOLD",
    "SUPERVISOR_MAX_RETRIES",
    # 规划相关
    "PLANNING_DIR",
    "PLAN_FILE",
    "FINDINGS_FILE",
    "PROGRESS_FILE",
    "get_planning_file_path",
    "read_planning_file",
    "write_planning_file",
    "is_complex_task",
    "cleanup_planning_files",
]
