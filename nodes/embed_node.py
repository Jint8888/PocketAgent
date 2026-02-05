"""
EmbedNode - 记忆存储节点

职责:
- 实现滑动窗口记忆管理
- 将超出窗口的对话存入向量索引
"""

from pocketflow import AsyncNode

from memory import get_embedding, get_memory_index

from .base import Action, MEMORY_WINDOW_SIZE, MEMORY_DEDUP_THRESHOLD


class EmbedNode(AsyncNode):
    """
    记忆存储节点

    职责:
    - 实现滑动窗口记忆管理
    - 将超出窗口的对话存入向量索引
    """

    async def prep_async(self, shared):
        """检查是否需要存储记忆"""
        messages = shared.get("messages", [])

        # 如果消息数量未超过窗口大小，不需要存储
        if len(messages) <= MEMORY_WINDOW_SIZE:
            return None

        # 寻找完整的对话轮次（user + assistant）
        # 不再假设消息总是成对出现
        user_msg = None
        assistant_msg = None
        consumed_count = 0

        for i, msg in enumerate(messages):
            role = msg.get("role", "")
            if role == "user" and user_msg is None:
                user_msg = msg
                consumed_count = i + 1
            elif role == "assistant" and user_msg is not None:
                assistant_msg = msg
                consumed_count = i + 1
                break  # 找到完整的一轮对话

        # 只有找到完整的 user + assistant 对话才存储
        if user_msg and assistant_msg:
            shared["messages"] = messages[consumed_count:]
            return [user_msg, assistant_msg]

        return None

    async def exec_async(self, prep_res):
        """生成对话的嵌入向量"""
        if not prep_res:
            return None

        conversation = prep_res

        # 组合对话内容
        user_msg = ""
        assistant_msg = ""
        for msg in conversation:
            if msg["role"] == "user":
                user_msg = msg["content"]
            elif msg["role"] == "assistant":
                assistant_msg = msg["content"]

        combined = f"User: {user_msg}\nAssistant: {assistant_msg}"

        # 生成嵌入
        embedding = get_embedding(combined)

        return {
            "conversation": conversation,
            "embedding": embedding,
            "content": combined
        }

    async def post_async(self, shared, prep_res, exec_res):
        """将对话存入向量索引（带去重）"""
        if not exec_res:
            return Action.INPUT

        memory_index = shared.get("memory_index")
        if not memory_index:
            memory_index = get_memory_index()
            shared["memory_index"] = memory_index

        # 使用去重存储：如果存在相似记忆则更新，否则新增
        idx, is_new = memory_index.add_or_update(
            exec_res["embedding"],
            {
                "content": exec_res["content"],
                "conversation": exec_res["conversation"]
            },
            dedup_threshold=MEMORY_DEDUP_THRESHOLD
        )

        if is_new:
            print(f"[Memory] Added new memory (total: {len(memory_index)} items)")
        else:
            print(f"[Memory] Updated similar memory at index {idx} (total: {len(memory_index)} items)")

        # 每次存储后立即保存到文件（防止异常退出丢失数据）
        memory_index.save("memory_index.json")

        return Action.INPUT
