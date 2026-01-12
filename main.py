"""
MCP Agent 聊天机器人 (多步推理版本 + 记忆集成)

整合了 MCP 工具调用能力的智能聊天机器人。
- 使用 PocketFlow 的 AsyncNode/AsyncFlow 实现全异步架构
- 支持多步推理 (Chain of Thought)
- 自动工具调用与分析
- 复杂任务分解与执行
- 向量记忆检索与存储 (滑动窗口 + 长期记忆)

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
    RetrieveNode,
    DecideNode,
    ToolNode,
    ThinkNode,
    AnswerNode,
    EmbedNode,
)


# ============================================================================
# 主函数
# ============================================================================

async def main_async():
    """
    异步主函数

    构建多步推理 Agent 流程 (含记忆):

    InputNode -> RetrieveNode -> DecideNode --> "tool" --> ToolNode --+
                                       |                             |
                                       +--> "think" -> ThinkNode ----+
                                       |                             |
                                       +--> "answer" -> AnswerNode   v
                                       ^________________________________|
                                       ^
    EmbedNode --------------------------+ ("input" 返回等待新任务)
        ^
    AnswerNode -------------------------+ ("embed" 进入存储节点)
    """
    # ========================================
    # 创建节点实例
    # ========================================
    input_node = InputNode()
    retrieve_node = RetrieveNode()
    decide_node = DecideNode()
    tool_node = ToolNode()
    think_node = ThinkNode()
    answer_node = AnswerNode()
    embed_node = EmbedNode()

    # ========================================
    # 连接节点
    # ========================================

    # InputNode 处理完用户输入后进入记忆检索
    input_node - "retrieve" >> retrieve_node
    input_node - "input" >> input_node  # 空输入时重新获取

    # RetrieveNode 检索记忆后进入决策
    retrieve_node - "decide" >> decide_node

    # DecideNode 根据决策结果路由
    decide_node - "tool" >> tool_node
    decide_node - "think" >> think_node
    decide_node - "answer" >> answer_node

    # ToolNode 和 ThinkNode 执行完后返回 DecideNode 继续
    tool_node - "decide" >> decide_node
    think_node - "decide" >> decide_node

    # AnswerNode 完成后进入 EmbedNode 存储记忆
    answer_node - "embed" >> embed_node

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
