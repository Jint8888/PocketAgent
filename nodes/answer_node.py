"""
AnswerNode - 回答节点

职责:
- 综合所有信息生成最终回答
"""

from pocketflow import AsyncNode

from utils import call_llm_async

from .base import Action, CONTEXT_WINDOW_SIZE
from .prompts import ANSWER_PROMPT

# 导入日志系统
from logging_config import log_agent_response


class AnswerNode(AsyncNode):
    """
    回答节点

    职责:
    - 综合所有信息生成最终回答
    """

    async def prep_async(self, shared):
        """准备回答所需信息"""
        decision = shared.get("current_decision", {})

        # 如果决策中已有答案，直接使用
        if decision.get("answer"):
            return {"direct_answer": decision.get("answer")}

        # 否则生成答案
        task = shared.get("current_task", "")
        context = shared.get("context", "")

        # ========================================
        # 上下文修剪：与 DecideNode 保持一致
        # ========================================
        trimmed_context = self._trim_context(context, CONTEXT_WINDOW_SIZE)
        if trimmed_context != context:
            print(f"   [Answer] Context trimmed to last {CONTEXT_WINDOW_SIZE} steps")

        prompt = ANSWER_PROMPT.format(task=task, context=trimmed_context)
        messages = [{"role": "user", "content": prompt}]

        # 调试日志
        self._log_token_estimation("Answer", messages[0]["content"])

        return {"messages": messages}

    def _trim_context(self, context: str, window_size: int) -> str:
        """修剪上下文，只保留最近 N 步的操作记录"""
        if not context:
            return ""

        sections = context.split("\n\n###")
        if len(sections) <= window_size:
            return context

        recent_sections = sections[-window_size:]
        result = "###".join(recent_sections)
        if not result.startswith("###"):
            result = "###" + result

        return result

    def _log_token_estimation(self, node_name: str, content: str):
        """记录token估算（调试用）"""
        def estimate_tokens(text: str) -> int:
            chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
            english_words = len(text.split()) - chinese_chars
            return int(chinese_chars * 1.5 + english_words * 1.3)

        tokens = estimate_tokens(content)
        print(f"   [{node_name}] Token estimation: ~{tokens} tokens")
        if tokens > 500000:
            print(f"      ⚠️  WARNING: Estimated tokens ({tokens}) exceeds 500K!")

    async def exec_async(self, prep_res):
        """生成最终回答"""
        if prep_res.get("direct_answer"):
            return prep_res["direct_answer"]

        messages = prep_res.get("messages", [])
        try:
            response = await call_llm_async(messages)
            return response
        except Exception as e:
            print(f"   [ERROR] Answer LLM call failed: {e}")
            return f"Sorry, answer generation failed: {e}"

    async def post_async(self, shared, prep_res, exec_res):
        """输出回答并返回等待新输入"""
        # 处理空值
        if exec_res is None:
            exec_res = "Cannot generate answer"

        print(f"\n[Assistant]:\n{exec_res}")

        # 记录Agent响应到日志
        log_agent_response(exec_res)

        # 添加到对话历史
        shared["messages"].append({"role": "assistant", "content": exec_res})

        print("\n" + "=" * 50)

        return Action.SUPERVISOR  # 回答后进入监督节点验证
