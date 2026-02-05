"""
SupervisorNode - 答案质量监督节点 (含 Manus-style 计划完成度检查)

职责:
- 检查 AnswerNode 生成的答案质量
- 检查计划完成度 (Manus-style)
- 质量不合格则返回 DecideNode 重试
- 超过最大重试次数则强制通过
- 任务完成后更新 Phase 4 并清理规划文件
"""

import re
from pocketflow import AsyncNode

from .base import Action, SUPERVISOR_MAX_RETRIES, REJECT_PATTERNS
from .planning_utils import (
    get_plan_completion_status,
    update_plan_phase,
    append_to_progress,
    record_error_in_plan,
    archive_planning_files,
)


class SupervisorNode(AsyncNode):
    """
    答案质量监督节点 (含 Manus-style 计划完成度检查)

    职责:
    - 检查 AnswerNode 生成的答案质量
    - 检查计划完成度 (Manus-style)
    - 质量不合格则返回 DecideNode 重试
    - 超过最大重试次数则强制通过
    - 任务完成后更新 Phase 4 并清理规划文件
    """

    async def prep_async(self, shared):
        """获取答案和相关上下文"""
        messages = shared.get("messages", [])
        if not messages:
            return None

        # 获取最新的 assistant 回答
        latest_answer = None
        for msg in reversed(messages):
            if msg["role"] == "assistant":
                latest_answer = msg["content"]
                break

        if not latest_answer:
            return None

        # 获取重试计数
        retry_count = shared.get("supervisor_retry_count", 0)

        # 获取计划状态
        has_plan = shared.get("has_plan", False)

        return {
            "answer": latest_answer,
            "task": shared.get("current_task", ""),
            "retry_count": retry_count,
            "has_plan": has_plan
        }

    async def exec_async(self, prep_res):
        """检查答案质量（含计划完成度检查）"""
        if not prep_res:
            return {"valid": True, "reason": "No answer to check"}

        answer = prep_res["answer"]
        task = prep_res["task"]
        retry_count = prep_res["retry_count"]
        has_plan = prep_res.get("has_plan", False)

        # 超过最大重试次数，强制通过
        if retry_count >= SUPERVISOR_MAX_RETRIES:
            return {
                "valid": True,
                "reason": "Max retries reached, force approve",
                "forced": True
            }

        # 基础质量检查
        issues = []

        # 检查1: 答案长度
        if len(answer) < 20:
            issues.append("答案过短")

        # 检查2: 拒绝模式检测（使用正则表达式，更精确）
        # 只在短回复时检测，避免误判详细回答中包含的道歉词
        if len(answer) < 120:
            answer_start = answer[:200].lower().strip()
            for pattern in REJECT_PATTERNS:
                if re.search(pattern, answer_start, re.IGNORECASE):
                    issues.append("答案可能是拒绝回复")
                    break

        # 检查3: 错误标记 (仅检查明确的错误前缀，避免误判正常讨论错误的回答)
        error_patterns = ["[error]", "[错误]", "error:", "错误:", "failed:", "失败:"]
        if any(pattern in answer.lower() for pattern in error_patterns):
            issues.append("答案包含错误标记")

        # 检查4: 不完整标记 (移除 "..." 避免误判，只检查明确的未完成标记)
        incomplete_markers = ["待续", "to be continued", "未完", "[未完]"]
        if any(marker in answer.lower() for marker in incomplete_markers):
            issues.append("答案可能不完整")

        # ========================================
        # Manus-style: 检查计划完成度
        # ========================================
        plan_status = None
        if has_plan:
            completed, total, uncompleted = get_plan_completion_status()
            plan_status = {"completed": completed, "total": total, "uncompleted": uncompleted}

            # 如果关键阶段未完成，可以作为参考（但不强制拒绝）
            if total > 0 and completed < total - 1:  # 允许最后一个验证阶段未完成
                # 只记录，不作为拒绝理由（避免死循环）
                print(f"   [Supervisor] Plan progress: {completed}/{total} phases")

        if issues:
            return {
                "valid": False,
                "reason": "; ".join(issues),
                "forced": False,
                "plan_status": plan_status
            }

        return {
            "valid": True,
            "reason": "答案质量检查通过",
            "forced": False,
            "plan_status": plan_status
        }

    async def post_async(self, shared, prep_res, exec_res):
        """根据检查结果路由（含计划完成更新）"""
        if not exec_res:
            exec_res = {"valid": True, "reason": "No check result"}

        is_valid = exec_res.get("valid", True)
        reason = exec_res.get("reason", "")
        is_forced = exec_res.get("forced", False)
        has_plan = shared.get("has_plan", False)

        if is_valid:
            if is_forced:
                print(f"   [Supervisor] Force approved: {reason}")
            else:
                print(f"   [Supervisor] Approved: {reason}")

            # ========================================
            # Manus-style: 更新计划完成状态
            # ========================================
            if has_plan:
                # 标记 Phase 3 (Synthesis) 和 Phase 4 (Verification) 完成
                update_plan_phase(2, completed=True)  # 分析完成
                update_plan_phase(3, completed=True)  # 综合完成
                update_plan_phase(4, completed=True)  # 验证完成

                # 记录最终进度
                append_to_progress(
                    action_type="Task Completed",
                    description="Answer approved by Supervisor",
                    result="All phases completed"
                )

                # 显示最终计划状态
                completed, total, _ = get_plan_completion_status()
                print(f"   [Planning] Final status: {completed}/{total} phases completed")

                # 归档规划文件（保留历史记录）
                task = shared.get("current_task", "")
                archive_planning_files(task)

            # 重置重试计数
            shared["supervisor_retry_count"] = 0
            return Action.EMBED
        else:
            print(f"   [Supervisor] Rejected: {reason}")

            # Manus-style: 记录拒绝到计划文件
            if has_plan:
                record_error_in_plan(f"Answer rejected: {reason}")
                append_to_progress(
                    action_type="Rejection",
                    description=f"Answer rejected by Supervisor: {reason}"
                )

            # 增加重试计数
            retry_count = shared.get("supervisor_retry_count", 0) + 1
            shared["supervisor_retry_count"] = retry_count
            print(f"   [Supervisor] Retry {retry_count}/{SUPERVISOR_MAX_RETRIES}")

            # 从对话历史中移除被拒绝的答案
            messages = shared.get("messages", [])
            if messages and messages[-1]["role"] == "assistant":
                messages.pop()

            # 在上下文中添加拒绝原因（先移除之前的反馈，避免累积）
            context = shared.get("context", "")
            supervisor_marker = "\n\n[Supervisor] Previous answer rejected:"
            # 移除之前的 Supervisor 反馈，只保留最新一条
            if supervisor_marker in context:
                context = context[:context.rfind(supervisor_marker)]
            supervisor_feedback = f"{supervisor_marker} {reason}"
            shared["context"] = context + supervisor_feedback

            return Action.DECIDE
