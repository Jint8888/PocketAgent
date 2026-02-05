"""
DecideNode - 决策节点 (核心，含计划重读)

职责:
- 决策前重读计划文件 (Manus-style 注意力操纵)
- 分析任务和上下文
- 决定下一步: tool / think / answer
"""

import re
from pocketflow import AsyncNode

from utils import call_llm_async

from .base import (
    Action,
    parse_yaml_response,
    CONTEXT_WINDOW_SIZE,
    YAML_PARSE_MAX_RETRIES,
    YAML_FORMAT_REMINDER,
)
from .planning_utils import (
    PLAN_FILE,
    FINDINGS_FILE,
    PROGRESS_FILE,
    read_planning_file,
    get_plan_completion_status,
)

# 导入日志系统
from logging_config import log_decision


class DecideNode(AsyncNode):
    """
    决策节点 (核心，含计划重读)

    职责:
    - 决策前重读计划文件 (Manus-style 注意力操纵)
    - 分析任务和上下文
    - 决定下一步: tool / think / answer
    """

    async def prep_async(self, shared):
        """准备决策所需的上下文（含计划重读）"""
        task = shared.get("current_task", "")
        context = shared.get("context", "")
        step_count = shared.get("step_count", 0)
        max_steps = shared.get("max_steps", 10)
        retrieved_memory = shared.get("retrieved_memory", "")
        has_plan = shared.get("has_plan", False)

        # ========================================
        # 方案3: 软限制 + 延长机制
        # ========================================
        if step_count >= max_steps:
            extension_count = shared.get("extension_count", 0)
            max_extensions = 2  # 最多延长2次

            if extension_count >= max_extensions:
                print(f"   [Decide] ⚠️  Maximum extensions reached ({max_extensions}), forcing answer...")
                return {"force_answer": True, "task": task, "context": context}

            # 询问 LLM 是否需要延长
            print(f"   [Decide] 📊 Step limit reached ({step_count}/{max_steps}), checking if extension needed...")
            extension_decision = await self._ask_llm_extension(shared, step_count, max_steps, extension_count, max_extensions)

            if extension_decision == "continue":
                extension_amount = 10
                shared["max_steps"] = max_steps + extension_amount
                shared["extension_count"] = extension_count + 1
                print(f"   [Decide] ✅ Extended by {extension_amount} steps, new limit: {shared['max_steps']} (extensions used: {shared['extension_count']}/{max_extensions})")
                # 继续正常流程，不强制回答
            else:
                print(f"   [Decide] 🏁 LLM chose to wrap up, forcing final answer...")
                return {"force_answer": True, "task": task, "context": context}

        # ========================================
        # Manus-style: 决策前重读计划 (注意力操纵)
        # ========================================
        plan_context = ""
        if has_plan:
            plan_content = read_planning_file(PLAN_FILE)
            if plan_content:
                # 提取关键部分：目标、当前阶段、进度
                plan_summary = self._extract_plan_summary(plan_content)
                if plan_summary:
                    plan_context = f"### Current Plan Status\n{plan_summary}\n\n"
                    print(f"   [Decide] Re-read plan for attention focus")

        # ========================================
        # 行为规则注入：确保 LLM 遵循全局规则
        # ========================================
        behavior_rules = shared.get("behavior_rules", "")
        if not behavior_rules:
            try:
                from rules_engine import load_rules
                behavior_rules = load_rules()
                if behavior_rules:
                    shared["behavior_rules"] = behavior_rules
                    print(f"   [Decide] Behavior rules loaded ({len(behavior_rules)} chars)")
            except Exception as e:
                print(f"   [WARN] Failed to load behavior rules: {e}")

        # ========================================
        # 上下文窗口管理：只保留最近 N 步操作
        # ========================================
        trimmed_context = self._trim_context(context, CONTEXT_WINDOW_SIZE)
        if trimmed_context != context:
            print(f"   [Decide] Context trimmed to last {CONTEXT_WINDOW_SIZE} steps")

        # ========================================
        # 方案1: 生成剩余步数警告信息
        # ========================================
        remaining_steps = max_steps - step_count
        steps_warning = self._get_step_warning(step_count, max_steps, remaining_steps)

        # 构建上下文，包含检索到的记忆
        full_context = ""

        # 步数警告放在最前面（确保 LLM 注意到）
        if steps_warning:
            full_context += steps_warning + "\n"

        # 计划放在第二位（推入近期注意力）
        if plan_context:
            full_context += plan_context

        # 行为规则放在第三位（确保 LLM 遵循规则）
        if behavior_rules:
            # 只提取关键规则，避免 token 过大
            rules_summary = self._extract_key_rules(behavior_rules)
            if rules_summary:
                full_context += f"### Behavior Rules (MUST FOLLOW)\n{rules_summary}\n\n"

        if retrieved_memory:
            full_context += f"### Related Past Conversations\n{retrieved_memory}\n\n"
        if trimmed_context:
            full_context += f"### Current Session Info\n{trimmed_context}"

        # 构建更清晰的决策提示
        if full_context:
            user_msg = f"""Current Task: {task}

Collected Information:
{full_context}

---
Based on the above, decide next step:
- If enough info to answer, use action: answer
- If need more data, use action: tool
- If need analysis, use action: think

Reply in YAML format."""
        else:
            user_msg = f"""Current Task: {task}

{steps_warning}

No information collected yet.

Decide first action (usually call a tool).
Reply in YAML format."""

        messages = [
            {"role": "system", "content": shared.get("system_prompt", "")},
            {"role": "user", "content": user_msg}
        ]

        # ========================================
        # 调试日志：追踪token消耗
        # ========================================
        def estimate_tokens(text: str) -> int:
            """粗略估算token数（中文1字≈1.5token，英文1词≈1.3token）"""
            chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
            english_words = len(text.split()) - chinese_chars
            return int(chinese_chars * 1.5 + english_words * 1.3)

        system_tokens = estimate_tokens(messages[0]["content"])
        user_tokens = estimate_tokens(messages[1]["content"])
        total_tokens = system_tokens + user_tokens

        print(f"   [Decide] Token estimation:")
        print(f"      System prompt: ~{system_tokens} tokens")
        print(f"      User message: ~{user_tokens} tokens")
        if plan_context:
            plan_tokens = estimate_tokens(plan_context)
            print(f"         - Plan context: ~{plan_tokens} tokens")
        if retrieved_memory:
            memory_tokens = estimate_tokens(retrieved_memory)
            print(f"         - Retrieved memory: ~{memory_tokens} tokens")
        if trimmed_context:
            context_tokens = estimate_tokens(trimmed_context)
            sections_count = len(trimmed_context.split("\n\n###"))
            print(f"         - Current context: ~{context_tokens} tokens ({sections_count} sections)")
        print(f"      TOTAL: ~{total_tokens} tokens")

        # 警告：如果预估超过50万tokens，很可能有问题
        if total_tokens > 500000:
            print(f"      ⚠️  WARNING: Estimated tokens ({total_tokens}) exceeds 500K!")
            print(f"      ⚠️  Context length: {len(context)} chars")
            print(f"      ⚠️  Trimmed context length: {len(trimmed_context)} chars")

        shared["step_count"] = step_count + 1

        return {"messages": messages, "force_answer": False, "task": task, "context": context}

    def _trim_context(self, context: str, window_size: int) -> str:
        """
        修剪上下文，只保留最近 N 步的操作记录

        Args:
            context: 完整的上下文字符串
            window_size: 保留的步骤数量

        Returns:
            修剪后的上下文
        """
        if not context:
            return ""

        # 按操作分段（每个 ### 标记一次操作）
        sections = context.split("\n\n###")

        if len(sections) <= window_size:
            return context

        # 只保留最后 window_size 个操作
        recent_sections = sections[-window_size:]

        # 重新组合，确保首个段落有 ### 前缀
        result = "###".join(recent_sections)
        if not result.startswith("###"):
            result = "###" + result

        return result

    def _extract_plan_summary(self, plan_content: str) -> str:
        """
        从计划文件中提取关键摘要（增强版：包含findings和progress）

        提取内容：
        1. task_plan.md: 目标、阶段、错误
        2. findings.md: 最近3条关键发现
        3. progress.md: 最近5步操作摘要
        """
        summary_parts = []

        # ========================================
        # Part 1: task_plan.md 核心信息
        # ========================================
        # 提取目标
        goal_match = re.search(r"## Goal\n(.+?)(?=\n##|\Z)", plan_content, re.DOTALL)
        if goal_match:
            goal = goal_match.group(1).strip()[:200]
            summary_parts.append(f"**Goal**: {goal}")

        # 提取当前阶段
        phase_match = re.search(r"## Current Phase\n(.+?)(?=\n##|\Z)", plan_content, re.DOTALL)
        if phase_match:
            phase = phase_match.group(1).strip()
            summary_parts.append(f"**Current Phase**: {phase}")

        # 提取完成状态
        completed, total, uncompleted = get_plan_completion_status()
        if total > 0:
            summary_parts.append(f"**Progress**: {completed}/{total} phases completed")
            if uncompleted and len(uncompleted) > 0:
                next_phase = uncompleted[0] if uncompleted else ""
                summary_parts.append(f"**Next**: {next_phase}")

        # 提取最近错误（帮助避免重复）
        if "## Errors Encountered" in plan_content:
            errors_section = plan_content.split("## Errors Encountered")[1].split("\n##")[0]
            error_lines = [l.strip() for l in errors_section.split("\n") if l.strip().startswith("-")]
            if error_lines:
                recent_errors = error_lines[-2:]  # 最近2个错误
                summary_parts.append(f"**Recent Errors**: {'; '.join(recent_errors)}")

        # ========================================
        # Part 2: findings.md 关键发现（优先保留高优先级）
        # ========================================
        findings_content = read_planning_file(FINDINGS_FILE)
        if findings_content:
            # 提取所有发现条目（包含优先级标签）
            findings_entries = re.findall(
                r"### \[([^\]]+)\] (\[(?:CRITICAL|IMPORTANT)\] )?(.+?)\n\*\*Finding\*\*:\n(.+?)(?=\n\*\*Implications|### |\Z)",
                findings_content,
                re.DOTALL
            )
            if findings_entries:
                # 分离高优先级和普通发现
                critical_findings = []
                important_findings = []
                normal_findings = []

                for timestamp, priority_tag, title, finding in findings_entries:
                    finding_short = finding.strip()[:200]
                    entry = f"  [{timestamp}] {priority_tag or ''}{title}: {finding_short}"

                    if priority_tag and "CRITICAL" in priority_tag:
                        critical_findings.append(entry)
                    elif priority_tag and "IMPORTANT" in priority_tag:
                        important_findings.append(entry)
                    else:
                        normal_findings.append(entry)

                # 组合：所有 CRITICAL + 最近2条 IMPORTANT + 最近2条普通
                findings_summary = []
                findings_summary.extend(critical_findings)  # 保留所有 CRITICAL
                findings_summary.extend(important_findings[-2:])  # 最近2条 IMPORTANT
                findings_summary.extend(normal_findings[-2:])  # 最近2条普通

                # 限制总数防止过长
                findings_summary = findings_summary[:6]

                if findings_summary:
                    summary_parts.append(f"**Key Findings**:\n" + "\n".join(findings_summary))

        # ========================================
        # Part 3: progress.md 最近操作
        # ========================================
        progress_content = read_planning_file(PROGRESS_FILE)
        if progress_content:
            # 提取最近5条操作记录
            progress_entries = re.findall(
                r"### \[([^\]]+)\] (.+?)\n- (.+?)(?=\n### |\Z)",
                progress_content,
                re.DOTALL
            )
            if progress_entries:
                recent_progress = progress_entries[-5:]  # 最近5条
                progress_summary = []
                for timestamp, action_type, description in recent_progress:
                    # 清理描述（移除多余空格和换行）
                    desc_clean = " ".join(description.split())[:150]
                    progress_summary.append(f"  [{timestamp}] {action_type}: {desc_clean}")

                if progress_summary:
                    summary_parts.append(f"**Recent Actions**:\n" + "\n".join(progress_summary))

        return "\n".join(summary_parts) if summary_parts else ""

    def _extract_key_rules(self, rules: str, max_length: int = 2000) -> str:
        """
        从完整规则中提取关键规则（避免 token 过大）

        Args:
            rules: 完整规则文本
            max_length: 最大字符数

        Returns:
            精简后的规则摘要
        """
        if not rules:
            return ""

        # 提取 G-11 (Moji天气) 等工具相关规则
        key_rules = []

        # 查找所有 G-XX 规则标题和内容
        rule_pattern = r"### (G-\d+): (.+?)\n(.+?)(?=\n### G-|\n---\n\*\*规则文件结束|$)"
        matches = re.findall(rule_pattern, rules, re.DOTALL)

        for rule_id, rule_title, rule_content in matches:
            # 优先提取工具相关规则 (G-05, G-11 等)
            if any(keyword in rule_title.lower() for keyword in ['工具', 'tool', 'moji', '天气']):
                # 截取规则内容的前500字符
                content_short = rule_content.strip()[:500]
                if len(rule_content.strip()) > 500:
                    content_short += "..."
                key_rules.append(f"**{rule_id}: {rule_title}**\n{content_short}")

        # 如果没有匹配到工具规则，返回前 max_length 字符
        if not key_rules:
            return rules[:max_length] + ("..." if len(rules) > max_length else "")

        result = "\n\n".join(key_rules)
        return result[:max_length] + ("..." if len(result) > max_length else "")

    def _get_step_warning(self, step_count: int, max_steps: int, remaining_steps: int) -> str:
        """
        生成分级步数警告信息（方案1）

        Args:
            step_count: 当前步数
            max_steps: 最大步数
            remaining_steps: 剩余步数

        Returns:
            格式化的警告信息
        """
        progress_pct = (step_count / max_steps * 100) if max_steps > 0 else 0

        if remaining_steps <= 3:
            return f"""🚨 **CRITICAL**: Only {remaining_steps} steps remaining! Must provide answer very soon!
Progress: Step {step_count}/{max_steps} ({progress_pct:.0f}% used)
"""
        elif remaining_steps <= 8:
            return f"""⚠️ **WARNING**: {remaining_steps} steps remaining. Please start wrapping up your analysis.
Progress: Step {step_count}/{max_steps} ({progress_pct:.0f}% used)
"""
        elif remaining_steps <= 15:
            return f"""📊 **Notice**: {remaining_steps} steps remaining. Plan your remaining actions carefully.
Progress: Step {step_count}/{max_steps} ({progress_pct:.0f}% used)
"""
        else:
            return f"📊 Progress: Step {step_count}/{max_steps} ({remaining_steps} steps remaining)"

    async def _ask_llm_extension(
        self,
        shared: dict,
        step_count: int,
        max_steps: int,
        extension_count: int,
        max_extensions: int
    ) -> str:
        """
        询问 LLM 是否需要延长步数限制（方案3）

        Args:
            shared: 共享状态
            step_count: 当前步数
            max_steps: 当前最大步数
            extension_count: 已使用的延长次数
            max_extensions: 最大延长次数

        Returns:
            "continue" 或 "answer"
        """
        task = shared.get("current_task", "")
        context = shared.get("context", "")

        # 构建延长请求的 prompt
        extension_prompt = f"""You've reached the step limit ({step_count}/{max_steps} steps used).

**Current Task**: {task}

**Progress Summary**:
{context[-1000:] if len(context) > 1000 else context}

**Extension Options**:
- You have {max_extensions - extension_count} extension(s) remaining
- Each extension grants 10 additional steps
- Maximum {max_extensions} extensions total

**Decision Required**:
Choose ONE of the following:
1. **continue** - Request extension to continue working (recommended if task is not complete)
2. **answer** - Provide final answer now with current information

**Reply Format**:
```yaml
decision: continue  # or "answer"
reason: "Brief explanation of your choice"
```

Make your decision:"""

        messages = [
            {"role": "system", "content": "You are a task completion evaluator. Decide whether to continue or wrap up based on task completion status."},
            {"role": "user", "content": extension_prompt}
        ]

        try:
            response = await call_llm_async(messages)

            # 解析 YAML 响应
            import yaml
            parsed = yaml.safe_load(response)

            if isinstance(parsed, dict) and "decision" in parsed:
                decision = parsed["decision"].lower().strip()
                reason = parsed.get("reason", "No reason provided")

                print(f"   [Decide] Extension decision: {decision}")
                print(f"   [Decide] Reason: {reason}")

                if decision in ["continue", "answer"]:
                    return decision
                else:
                    print(f"   [Decide] Invalid decision '{decision}', defaulting to 'answer'")
                    return "answer"
            else:
                # 如果解析失败，尝试简单的关键词匹配
                response_lower = response.lower()
                if "continue" in response_lower and "answer" not in response_lower:
                    print(f"   [Decide] Keyword match: continue")
                    return "continue"
                else:
                    print(f"   [Decide] Keyword match or default: answer")
                    return "answer"

        except Exception as e:
            print(f"   [Decide] Extension request failed: {e}, defaulting to 'answer'")
            return "answer"

    async def exec_async(self, prep_res):
        """调用 LLM 进行决策（含 YAML 解析重试机制）"""
        if prep_res.get("force_answer"):
            # 强制回答
            return {
                "action": Action.ANSWER,
                "reason": "Max steps reached, force answer",
                "answer": "Based on collected information..."
            }

        messages = prep_res["messages"]
        last_response = None

        # 重试循环
        for attempt in range(YAML_PARSE_MAX_RETRIES + 1):
            try:
                response = await call_llm_async(messages)
                last_response = response
            except Exception as e:
                print(f"   [ERROR] LLM call failed: {e}")
                return {
                    "action": Action.ANSWER,
                    "reason": f"LLM call failed: {e}",
                    "answer": "Sorry, AI service temporarily unavailable."
                }

            # 解析 YAML
            try:
                return parse_yaml_response(response)
            except ValueError as e:
                if attempt < YAML_PARSE_MAX_RETRIES:
                    # 还有重试机会，发送格式提醒
                    print(f"   [WARN] YAML parse failed (attempt {attempt + 1}), retrying...")
                    messages = messages + [
                        {"role": "assistant", "content": response},
                        {"role": "user", "content": YAML_FORMAT_REMINDER}
                    ]
                else:
                    # 重试用尽，回退到直接回答
                    print(f"   [WARN] YAML parse failed after {YAML_PARSE_MAX_RETRIES + 1} attempts")
                    return {
                        "action": Action.ANSWER,
                        "reason": str(e),
                        "answer": last_response if last_response else "Cannot get answer"
                    }

    async def post_async(self, shared, prep_res, exec_res):
        """根据决策结果路由到下一个节点"""
        # 处理 exec_res 为空的情况
        if exec_res is None:
            print("\n[WARN] Decision failed, try direct answer")
            exec_res = {
                "action": Action.ANSWER,
                "reason": "Decision returned empty",
                "answer": "Sorry, processing error, please retry."
            }

        # 确保 exec_res 是字典
        if not isinstance(exec_res, dict):
            exec_res = {
                "action": Action.ANSWER,
                "reason": "Decision format error",
                "answer": str(exec_res)
            }

        action = exec_res.get("action", "answer")
        reason = exec_res.get("reason", "")

        step = shared.get("step_count", 0)
        print(f"\n[Step {step}]: {action.upper()}")
        if reason:
            print(f"   Reason: {reason}")

        # 记录决策到日志
        log_decision(action, reason)

        # 保存决策到 shared
        shared["current_decision"] = exec_res

        if action == Action.TOOL:
            return Action.TOOL
        elif action == Action.THINK:
            return Action.THINK
        else:
            return Action.ANSWER
