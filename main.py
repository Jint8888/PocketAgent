"""
MCP Agent 聊天机器人 (多步推理版本 + Manus-style Planning)

整合了 MCP 工具调用能力的智能聊天机器人。
- 使用 PocketFlow 的 AsyncNode/AsyncFlow 实现全异步架构
- 支持多步推理 (Chain of Thought)
- 自动工具调用与分析
- 复杂任务分解与执行
- 向量记忆检索与存储 (滑动窗口 + 长期记忆)
- Manus-style Planning: 三文件模式 (task_plan.md, findings.md, progress.md)

Manus-style Features:
- 复杂任务自动创建规划文件
- 决策前重读计划 (注意力操纵)
- 2-动作规则：每 2 次工具调用后更新 findings
- 错误持久化记录 (避免重复失败)
- 计划完成度验证

运行方式:
    uv run python main.py
"""

import asyncio
import warnings
from pocketflow import AsyncFlow

# 忽略 PocketFlow 在流程正常结束时的警告（返回 None 表示退出是预期行为）
warnings.filterwarnings("ignore", message="Flow ends:.*not found in", module="pocketflow")

from nodes import (
    InputNode,
    PlanningNode,
    RetrieveNode,
    DecideNode,
    ToolNode,
    ThinkNode,
    AnswerNode,
    EmbedNode,
    SupervisorNode,
)


# ============================================================================
# 主函数
# ============================================================================

async def main_async():
    """
    异步主函数

    构建多步推理 Agent 流程 (含记忆 + Manus-style Planning + Supervisor):

    InputNode -> PlanningNode -> RetrieveNode -> DecideNode --> "tool" --> ToolNode --+
                                                       |                              |
                                                       +--> "think" -> ThinkNode -----+
                                                       |                              |
                                                       +--> "answer" -> AnswerNode    v
                                                       ^                              |
                                                       |                              v
                                                       |                      SupervisorNode
                                                       |                         /            \
                                                       +--- "decide" (retry) ---+              |
                                                                                         "embed" v
                                                                                          EmbedNode
                                                                                              |
    InputNode <----------------------- "input" -----------------------------------------------+

    Manus-style Planning Flow:
    - PlanningNode: 判断任务复杂度，创建规划文件 (task_plan.md, findings.md, progress.md)
    - DecideNode: 决策前重读计划 (注意力操纵)
    - ToolNode: 2-动作规则，记录进度和发现
    - ThinkNode: 更新分析阶段状态
    - SupervisorNode: 检查计划完成度，记录错误
    """
    # ========================================
    # 创建节点实例
    # ========================================
    input_node = InputNode()
    planning_node = PlanningNode()
    retrieve_node = RetrieveNode()
    decide_node = DecideNode()
    tool_node = ToolNode()
    think_node = ThinkNode()
    answer_node = AnswerNode()
    supervisor_node = SupervisorNode()
    embed_node = EmbedNode()

    # ========================================
    # 连接节点
    # ========================================

    # InputNode 处理完用户输入后进入规划节点
    input_node - "planning" >> planning_node
    input_node - "input" >> input_node  # 空输入时重新获取

    # PlanningNode 创建规划后进入记忆检索
    planning_node - "retrieve" >> retrieve_node

    # RetrieveNode 检索记忆后进入决策
    retrieve_node - "decide" >> decide_node

    # DecideNode 根据决策结果路由
    decide_node - "tool" >> tool_node
    decide_node - "think" >> think_node
    decide_node - "answer" >> answer_node

    # ToolNode 和 ThinkNode 执行完后返回 DecideNode 继续
    tool_node - "decide" >> decide_node
    think_node - "decide" >> decide_node

    # AnswerNode 完成后进入 SupervisorNode 验证
    answer_node - "supervisor" >> supervisor_node

    # SupervisorNode 验证通过进入 EmbedNode 存储记忆
    supervisor_node - "embed" >> embed_node

    # SupervisorNode 验证失败返回 DecideNode 重试
    supervisor_node - "decide" >> decide_node

    # EmbedNode 完成后返回 InputNode 等待新任务
    embed_node - "input" >> input_node

    # ========================================
    # 创建并运行异步流程
    # ========================================
    flow = AsyncFlow(start=input_node)

    shared = {}
    await flow.run_async(shared)


def main():
    """
    同步入口点

    使用 asyncio.run() 启动异步主函数。
    包含顶层异常处理，确保程序优雅退出。
    """
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user, exiting...")
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
