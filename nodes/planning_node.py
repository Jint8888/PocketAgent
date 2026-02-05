"""
PlanningNode - 任务规划节点 (Manus-style)

职责:
- 判断任务复杂度
- 为复杂任务创建规划文件 (task_plan.md, findings.md, progress.md)
- 简单任务直接跳过
"""

import os
from datetime import datetime
from pocketflow import AsyncNode

from .base import Action
from .planning_utils import (
    PLANNING_DIR,
    PLAN_FILE,
    FINDINGS_FILE,
    PROGRESS_FILE,
    is_complex_task,
    write_planning_file,
)


class PlanningNode(AsyncNode):
    """
    任务规划节点 (Manus-style)

    职责:
    - 判断任务复杂度
    - 为复杂任务创建规划文件 (task_plan.md, findings.md, progress.md)
    - 简单任务直接跳过
    """

    async def prep_async(self, shared):
        """准备规划所需信息"""
        task = shared.get("current_task", "")
        return {"task": task}

    async def exec_async(self, prep_res):
        """判断是否需要规划并创建文件"""
        task = prep_res.get("task", "")

        # 判断任务复杂度
        needs_planning = is_complex_task(task)

        if not needs_planning:
            return {"needs_planning": False}

        # 确定任务类型
        task_lower = task.lower()
        if any(kw in task_lower for kw in ["分析", "analyze", "研究", "research"]):
            task_type = "Research & Analysis"
        elif any(kw in task_lower for kw in ["比较", "compare", "对比"]):
            task_type = "Comparison"
        elif any(kw in task_lower for kw in ["总结", "summarize", "汇总"]):
            task_type = "Summarization"
        else:
            task_type = "Multi-step Task"

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        return {
            "needs_planning": True,
            "task": task,
            "task_type": task_type,
            "timestamp": timestamp
        }

    async def post_async(self, shared, prep_res, exec_res):
        """创建规划文件或跳过"""
        if not exec_res.get("needs_planning"):
            print("   [Planning] Simple task, skipping planning files")
            shared["has_plan"] = False
            return Action.RETRIEVE

        task = exec_res["task"]
        task_type = exec_res["task_type"]
        timestamp = exec_res["timestamp"]

        # 读取模板并填充
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        templates_dir = os.path.join(base_dir, "templates")

        # 创建 task_plan.md
        try:
            with open(os.path.join(templates_dir, "task_plan.md"), "r", encoding="utf-8") as f:
                plan_template = f.read()
            plan_content = plan_template.format(
                goal=task,
                task_type=task_type,
                timestamp=timestamp
            )
            write_planning_file(PLAN_FILE, plan_content)
            print(f"   [Planning] Created {PLAN_FILE}")
        except Exception as e:
            print(f"   [WARN] Failed to create {PLAN_FILE}: {e}")

        # 创建 findings.md
        try:
            with open(os.path.join(templates_dir, "findings.md"), "r", encoding="utf-8") as f:
                findings_template = f.read()
            findings_content = findings_template.format(
                task=task,
                timestamp=timestamp,
                initial_finding="Task analysis initiated"
            )
            write_planning_file(FINDINGS_FILE, findings_content)
            print(f"   [Planning] Created {FINDINGS_FILE}")
        except Exception as e:
            print(f"   [WARN] Failed to create {FINDINGS_FILE}: {e}")

        # 创建 progress.md
        try:
            with open(os.path.join(templates_dir, "progress.md"), "r", encoding="utf-8") as f:
                progress_template = f.read()
            progress_content = progress_template.format(
                task=task,
                timestamp=timestamp
            )
            write_planning_file(PROGRESS_FILE, progress_content)
            print(f"   [Planning] Created {PROGRESS_FILE}")
        except Exception as e:
            print(f"   [WARN] Failed to create {PROGRESS_FILE}: {e}")

        # 标记已创建规划
        shared["has_plan"] = True
        shared["tool_call_count"] = 0  # 用于 2-动作规则

        print(f"   [Planning] Task type: {task_type}")
        print(f"   [Planning] Planning files created in {PLANNING_DIR}/")

        return Action.RETRIEVE
