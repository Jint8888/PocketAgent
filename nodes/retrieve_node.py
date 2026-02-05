"""
RetrieveNode - 记忆检索节点

职责:
- 根据用户输入检索相关历史记忆
- 将相关记忆注入到上下文中
"""

from pocketflow import AsyncNode
from memory import get_embedding

from .base import Action, MEMORY_RETRIEVE_K, MEMORY_SIMILARITY_THRESHOLD


class RetrieveNode(AsyncNode):
    """
    记忆检索节点

    职责:
    - 根据用户输入检索相关历史记忆
    - 将相关记忆注入到上下文中
    """

    async def prep_async(self, shared):
        """获取检索所需信息"""
        # 获取最新用户消息
        messages = shared.get("messages", [])
        if not messages:
            return None

        # 找最近的用户消息
        latest_user_msg = None
        for msg in reversed(messages):
            if msg["role"] == "user":
                latest_user_msg = msg["content"]
                break

        if not latest_user_msg:
            return None

        # 检查记忆索引
        memory_index = shared.get("memory_index")
        if not memory_index or len(memory_index) == 0:
            return None

        return {
            "query": latest_user_msg,
            "memory_index": memory_index
        }

    async def exec_async(self, prep_res):
        """执行记忆检索"""
        if not prep_res:
            return None

        query = prep_res["query"]
        memory_index = prep_res["memory_index"]

        # 获取查询向量
        query_embedding = get_embedding(query)

        # 搜索相关记忆
        results = memory_index.search(query_embedding, k=MEMORY_RETRIEVE_K)

        # 过滤低相似度结果
        filtered = []
        for item, similarity in results:
            if similarity >= MEMORY_SIMILARITY_THRESHOLD:
                filtered.append((item, similarity))

        return filtered if filtered else None

    async def post_async(self, shared, prep_res, exec_res):
        """将检索结果注入上下文"""
        if exec_res:
            # 有相关记忆
            memory_text = []
            for item, similarity in exec_res:
                content = item.get("content", "")
                memory_text.append(f"[Similarity: {similarity:.2f}] {content}")

            shared["retrieved_memory"] = "\n".join(memory_text)
            print(f"[Memory] Retrieved {len(exec_res)} relevant memories")
        else:
            shared["retrieved_memory"] = None

        return Action.DECIDE
