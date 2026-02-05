"""
ThinkNode - 思考推理节点 (含 Manus-style 进度记录)

职责:
- 分析已收集的信息
- 生成中间结论
- 更新 Phase 2 进度
"""

from pocketflow import AsyncNode

from utils import call_llm_async

from .base import Action, parse_yaml_response, CONTEXT_WINDOW_SIZE
from .prompts import THINKING_PROMPT
from .planning_utils import (
    update_plan_phase,
    append_to_findings,
    append_to_progress,
)


class ThinkNode(AsyncNode):
    """
    思考推理节点 (含 Manus-style 进度记录)

    职责:
    - 分析已收集的信息
    - 生成中间结论
    - 更新 Phase 2 进度
    """

    async def prep_async(self, shared):
        """准备思考所需信息"""
        task = shared.get("current_task", "")
        context = shared.get("context", "")
        decision = shared.get("current_decision", {})
        thinking_hint = decision.get("thinking", "")

        # ========================================
        # 上下文修剪：与 DecideNode 保持一致
        # ========================================
        trimmed_context = self._trim_context(context, CONTEXT_WINDOW_SIZE)
        if trimmed_context != context:
            print(f"   [Think] Context trimmed to last {CONTEXT_WINDOW_SIZE} steps")

        prompt = THINKING_PROMPT.format(task=task, context=trimmed_context)
        if thinking_hint:
            prompt += f"\n\nHint: {thinking_hint}"

        messages = [{"role": "user", "content": prompt}]

        # 调试日志
        self._log_token_estimation("Think", messages[0]["content"])

        return messages

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

    async def exec_async(self, messages):
        """调用 LLM 进行思考"""
        try:
            response = await call_llm_async(messages)
            return response
        except Exception as e:
            print(f"   [ERROR] Think LLM call failed: {e}")
            return f"Think failed: {e}"

    async def post_async(self, shared, prep_res, exec_res):
        """保存思考结果"""
        print(f"   [Think] Processing...")
        has_plan = shared.get("has_plan", False)

        # 处理空值
        if exec_res is None:
            exec_res = "Think process returned empty"

        # 解析思考结果
        try:
            if "```yaml" in exec_res:
                result = parse_yaml_response(exec_res)
                analysis = result.get("analysis", "")
                conclusion = result.get("conclusion", "")
                thinking_text = f"Analysis: {analysis}\nConclusion: {conclusion}"
            else:
                thinking_text = exec_res
        except Exception as e:
            print(f"   [WARN] Think YAML parse failed: {e}")
            thinking_text = exec_res

        print(f"   [Insight] {thinking_text[:100]}..." if len(thinking_text) > 100 else f"   [Insight] {thinking_text}")

        # 添加到上下文
        context = shared.get("context", "")
        shared["context"] = context + f"\n\n### Think Analysis\n{thinking_text}"

        # ========================================
        # Manus-style: 记录分析进度
        # ========================================
        if has_plan:
            # 更新阶段状态（思考 = Phase 2 分析）
            update_plan_phase(1, completed=True)  # 完成信息收集
            update_plan_phase(2, completed=False)  # 进入分析阶段

            # 记录分析到 findings
            append_to_findings(
                title="Analysis Result",
                source="Think Node",
                finding=thinking_text[:500],
                implications="Intermediate conclusion formed"
            )

            # 记录进度
            append_to_progress(
                action_type="Analysis",
                description="Performed analysis on collected data",
                result=thinking_text[:100]
            )

        return Action.DECIDE
