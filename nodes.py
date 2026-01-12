"""
多步推理 Agent 节点模块

包含以下异步节点:
- InputNode: 获取用户输入
- RetrieveNode: 检索相关历史记忆
- DecideNode: 决策节点 (核心)
- ToolNode: 工具执行节点
- ThinkNode: 思考推理节点
- AnswerNode: 生成最终回答
- SupervisorNode: 答案质量监督节点
- EmbedNode: 存储对话到向量记忆
"""

import yaml
from pocketflow import AsyncNode

from utils import call_llm_async, async_input
from mcp_client import MCPManager
from memory import get_embedding, get_memory_index


# ============================================================================
# 路由动作常量
# ============================================================================

class Action:
    """节点路由动作常量"""
    TOOL = "tool"
    THINK = "think"
    ANSWER = "answer"
    INPUT = "input"
    RETRIEVE = "retrieve"
    DECIDE = "decide"
    EMBED = "embed"
    SUPERVISOR = "supervisor"  # 答案质量监督


# ============================================================================
# 辅助函数
# ============================================================================

def parse_yaml_response(response: str) -> dict:
    """
    解析 LLM 返回的 YAML 格式响应

    Args:
        response: LLM 返回的原始字符串

    Returns:
        解析后的字典

    Raises:
        ValueError: YAML 解析失败时抛出
    """
    try:
        if response and "```yaml" in response:
            yaml_str = response.split("```yaml")[1].split("```")[0].strip()
        elif response and "```" in response:
            yaml_str = response.split("```")[1].split("```")[0].strip()
        else:
            yaml_str = response or ""

        result = yaml.safe_load(yaml_str)
        if result is None:
            raise ValueError("YAML parse result is empty")
        return result
    except Exception as e:
        raise ValueError(f"YAML parse failed: {e}")


# ============================================================================
# 配置常量
# ============================================================================

# YAML 解析失败时的重试次数
YAML_PARSE_MAX_RETRIES = 2

# YAML 格式修正提示
YAML_FORMAT_REMINDER = """你的回复格式不正确。请严格按照以下格式回复：

```yaml
action: tool/think/answer
reason: 你的理由
# 根据 action 添加对应字段
```

请重新回复，只输出 YAML 代码块，不要添加其他内容。"""

# 滑动窗口大小：保留最近 N 条消息在内存中，超过的存入向量索引
MEMORY_WINDOW_SIZE = 6

# 记忆检索数量
MEMORY_RETRIEVE_K = 2

# 记忆相似度阈值（低于此值不注入）
MEMORY_SIMILARITY_THRESHOLD = 0.35

# 记忆去重阈值（高于此值认为是重复记忆，更新而非新增）
MEMORY_DEDUP_THRESHOLD = 0.85

# Supervisor 最大重试次数（避免无限循环）
SUPERVISOR_MAX_RETRIES = 2

# ============================================================================
# 系统提示词模板
# ============================================================================

AGENT_SYSTEM_PROMPT = """你是一个智能助手，可以通过 MCP 协议调用各种工具来帮助用户解决复杂问题。

### 可用工具
{tool_info}

### 决策规则
分析用户任务和当前上下文，决定下一步行动:

1. **tool**: 需要调用工具获取数据或执行操作
2. **think**: 需要对已有信息进行分析推理
3. **answer**: 已有足够信息可以回答用户

### 回复格式（极其重要，必须严格遵守！）

你的回复必须且只能是一个 YAML 代码块，格式如下：

**示例1 - 调用工具：**
```yaml
action: tool
reason: 需要获取股票数据
tool_name: get_stock_data
tool_params:
  stock_code: "600519.SH"
  data_type: "realtime"
```

**示例2 - 进行思考：**
```yaml
action: think
reason: 需要分析已收集的数据
thinking: |
  根据获取的信息进行分析...
```

**示例3 - 给出回答：**
```yaml
action: answer
reason: 已有足够信息回答用户
answer: |
  根据分析结果，回答如下...
```

### 格式强制要求
1. 必须使用 ```yaml 开头和 ``` 结尾包裹
2. action 必须是 tool、think、answer 三选一
3. 不要在 YAML 代码块外添加任何文字
4. tool_params 的值如果包含特殊字符需要用引号包裹
5. 多行文本使用 | 符号

### 注意事项
- 复杂任务需要多步完成，不要急于回答
- 先调用工具获取数据，再思考分析
- 股票代码格式说明：
  - xueqiu 工具使用前缀格式：SH600016（上海）、SZ000001（深圳）
  - financial-analysis 工具使用后缀格式：600016.SH、000001.SZ
"""

THINKING_PROMPT = """基于以下上下文信息，进行分析推理:

### 当前任务
{task}

### 已获取的信息
{context}

### 要求
请深入分析上述信息，提取关键点，形成中间结论。
如果信息不足以完成任务，说明还需要什么信息。

回复格式:
```yaml
analysis: |
    你的分析内容
conclusion: |
    中间结论
need_more_info: true/false
next_step: 如果需要更多信息，建议下一步
```
"""

ANSWER_PROMPT = """基于以下所有信息，生成最终回答:

### 用户任务
{task}

### 收集的信息和分析
{context}

### 要求
综合所有信息，生成一个完整、专业的回答。
"""


# ============================================================================
# 节点类定义
# ============================================================================

class InputNode(AsyncNode):
    """
    用户输入节点

    职责:
    - 首次运行时初始化 MCP Manager
    - 获取用户输入
    - 重置任务状态
    """

    async def prep_async(self, shared):
        """初始化并获取用户输入"""
        # ========================================
        # 首次运行：初始化 MCP Manager 和记忆索引
        # ========================================
        if "mcp_manager" not in shared:
            print("\n[INFO] Initializing MCP tool system...")
            try:
                manager = MCPManager("mcp.json")
                await manager.get_all_tools_async()
                shared["mcp_manager"] = manager

                if manager.tools:
                    tool_info = manager.format_tools_for_prompt()
                    shared["system_prompt"] = AGENT_SYSTEM_PROMPT.format(tool_info=tool_info)
                    print(f"[OK] Loaded {len(manager.tools)} tools")
                else:
                    shared["system_prompt"] = AGENT_SYSTEM_PROMPT.format(tool_info="(no tools)")
                    print("[WARN] No tools available")

            except Exception as e:
                print(f"[WARN] MCP initialization failed: {e}")
                shared["mcp_manager"] = None
                shared["system_prompt"] = AGENT_SYSTEM_PROMPT.format(tool_info="(init failed)")

            # 初始化对话历史
            shared["messages"] = []

            # 初始化记忆索引
            shared["memory_index"] = get_memory_index()
            print(f"[OK] Memory index ready ({len(shared['memory_index'])} items)")

            print("\n" + "=" * 50)
            print("Welcome! Multi-step reasoning assistant ready.")
            print("Type 'exit' to quit.")
            print("=" * 50)

        # ========================================
        # 获取用户输入
        # ========================================
        user_input = await async_input("\n[User]: ")

        if user_input.lower() in ['exit', 'quit', 'q', 'bye']:
            return None

        if not user_input:
            return "empty"

        return user_input

    async def exec_async(self, user_input):
        """直接传递用户输入"""
        return user_input

    async def post_async(self, shared, prep_res, exec_res):
        """保存用户输入并开始任务"""
        if prep_res is None:
            # 保存记忆索引
            memory_index = shared.get("memory_index")
            if memory_index and len(memory_index) > 0:
                memory_index.save("memory_index.json")
            print("\n[INFO] Goodbye!")
            return None  # 结束流程

        if prep_res == "empty":
            return Action.INPUT  # 重新获取输入

        # 重置任务状态
        shared["current_task"] = exec_res
        shared["context"] = ""
        shared["step_count"] = 0
        shared["max_steps"] = 10

        # 添加到对话历史
        shared["messages"].append({"role": "user", "content": exec_res})

        print(f"\n[Task]: {exec_res}")
        print("-" * 40)

        return Action.RETRIEVE  # 先检索记忆


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


class DecideNode(AsyncNode):
    """
    决策节点 (核心)

    职责:
    - 分析任务和上下文
    - 决定下一步: tool / think / answer
    """

    async def prep_async(self, shared):
        """准备决策所需的上下文"""
        task = shared.get("current_task", "")
        context = shared.get("context", "")
        step_count = shared.get("step_count", 0)
        max_steps = shared.get("max_steps", 10)
        retrieved_memory = shared.get("retrieved_memory", "")

        # 检查步数限制
        if step_count >= max_steps:
            return {"force_answer": True, "task": task, "context": context}

        # 构建上下文，包含检索到的记忆
        full_context = ""
        if retrieved_memory:
            full_context += f"### Related Past Conversations\n{retrieved_memory}\n\n"
        if context:
            full_context += f"### Current Session Info\n{context}"

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

No information collected yet.

Decide first action (usually call a tool).
Reply in YAML format."""

        messages = [
            {"role": "system", "content": shared.get("system_prompt", "")},
            {"role": "user", "content": user_msg}
        ]

        shared["step_count"] = step_count + 1

        return {"messages": messages, "force_answer": False, "task": task, "context": context}

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

        # 保存决策到 shared
        shared["current_decision"] = exec_res

        if action == Action.TOOL:
            return Action.TOOL
        elif action == Action.THINK:
            return Action.THINK
        else:
            return Action.ANSWER


class ToolNode(AsyncNode):
    """
    工具执行节点

    职责:
    - 调用 MCP 工具
    - 将结果添加到上下文
    """

    async def prep_async(self, shared):
        """获取工具调用信息"""
        decision = shared.get("current_decision", {})
        tool_name = decision.get("tool_name", "")
        tool_params = decision.get("tool_params", {})
        return {"tool_name": tool_name, "tool_params": tool_params}

    async def exec_async(self, prep_res):
        """执行工具调用"""
        tool_name = prep_res.get("tool_name", "")
        tool_params = prep_res.get("tool_params", {})

        if not tool_name:
            return {"success": False, "error": "No tool name specified"}

        print(f"   [Tool]: {tool_name}")
        print(f"      Params: {tool_params}")

        # 这里需要从 shared 获取 manager，但 exec 无法访问 shared
        # 返回调用信息，在 post 中执行
        return {"tool_name": tool_name, "tool_params": tool_params}

    async def post_async(self, shared, prep_res, exec_res):
        """在 post 中执行工具调用（可以访问 shared）"""
        manager = shared.get("mcp_manager")
        if not manager:
            print("   [ERROR] MCP Manager not initialized")
            shared["context"] += "\n\n[Tool call failed: MCP Manager not initialized]"
            return Action.DECIDE

        tool_name = exec_res.get("tool_name", "")
        tool_params = exec_res.get("tool_params", {})

        try:
            result = await manager.call_tool_async(tool_name, tool_params)
            print(f"   [OK] Tool result: {result[:200]}..." if len(str(result)) > 200 else f"   [OK] Tool result: {result}")

            # 添加到上下文
            context = shared.get("context", "")
            shared["context"] = context + f"\n\n### Tool Call: {tool_name}\nParams: {tool_params}\nResult:\n{result}"

        except Exception as e:
            print(f"   [ERROR] Tool call failed: {e}")
            shared["context"] += f"\n\n[Tool call failed: {tool_name} - {e}]"

        return Action.DECIDE


class ThinkNode(AsyncNode):
    """
    思考推理节点

    职责:
    - 分析已收集的信息
    - 生成中间结论
    """

    async def prep_async(self, shared):
        """准备思考所需信息"""
        task = shared.get("current_task", "")
        context = shared.get("context", "")
        decision = shared.get("current_decision", {})
        thinking_hint = decision.get("thinking", "")

        prompt = THINKING_PROMPT.format(task=task, context=context)
        if thinking_hint:
            prompt += f"\n\nHint: {thinking_hint}"

        messages = [{"role": "user", "content": prompt}]
        return messages

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

        return Action.DECIDE


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

        prompt = ANSWER_PROMPT.format(task=task, context=context)
        messages = [{"role": "user", "content": prompt}]

        return {"messages": messages}

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

        # 添加到对话历史
        shared["messages"].append({"role": "assistant", "content": exec_res})

        print("\n" + "=" * 50)

        return Action.SUPERVISOR  # 回答后进入监督节点验证


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

        # 取出最旧的一对对话 (user + assistant)
        oldest_pair = messages[:2]

        # 从 messages 中移除
        shared["messages"] = messages[2:]

        return oldest_pair

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

class SupervisorNode(AsyncNode):
    """
    答案质量监督节点

    职责:
    - 检查 AnswerNode 生成的答案质量
    - 质量不合格则返回 DecideNode 重试
    - 超过最大重试次数则强制通过
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

        return {
            "answer": latest_answer,
            "task": shared.get("current_task", ""),
            "retry_count": retry_count
        }

    async def exec_async(self, prep_res):
        """检查答案质量"""
        if not prep_res:
            return {"valid": True, "reason": "No answer to check"}

        answer = prep_res["answer"]
        task = prep_res["task"]
        retry_count = prep_res["retry_count"]

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

        # 检查2: 拒绝性关键词 (仅当答案很短时才判定为拒绝)
        reject_keywords = ["sorry", "cannot", "unable", "无法", "抱歉", "不能"]
        if any(kw in answer.lower() for kw in reject_keywords):
            if len(answer) < 80:  # 短回复 + 拒绝词 = 可能是拒绝
                issues.append("答案可能是拒绝回复")

        # 检查3: 错误标记 (仅检查明确的错误前缀，避免误判正常讨论错误的回答)
        error_patterns = ["[error]", "[错误]", "error:", "错误:", "failed:", "失败:"]
        if any(pattern in answer.lower() for pattern in error_patterns):
            issues.append("答案包含错误标记")

        # 检查4: 不完整标记 (移除 "..." 避免误判，只检查明确的未完成标记)
        incomplete_markers = ["待续", "to be continued", "未完", "[未完]"]
        if any(marker in answer.lower() for marker in incomplete_markers):
            issues.append("答案可能不完整")

        if issues:
            return {
                "valid": False,
                "reason": "; ".join(issues),
                "forced": False
            }

        return {
            "valid": True,
            "reason": "答案质量检查通过",
            "forced": False
        }

    async def post_async(self, shared, prep_res, exec_res):
        """根据检查结果路由"""
        if not exec_res:
            exec_res = {"valid": True, "reason": "No check result"}

        is_valid = exec_res.get("valid", True)
        reason = exec_res.get("reason", "")
        is_forced = exec_res.get("forced", False)

        if is_valid:
            if is_forced:
                print(f"   [Supervisor] Force approved: {reason}")
            else:
                print(f"   [Supervisor] Approved: {reason}")
            # 重置重试计数
            shared["supervisor_retry_count"] = 0
            return Action.EMBED
        else:
            print(f"   [Supervisor] Rejected: {reason}")
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
