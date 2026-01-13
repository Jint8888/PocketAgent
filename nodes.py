"""
多步推理 Agent 节点模块 (Manus-style Planning Enhanced)

包含以下异步节点:
- InputNode: 获取用户输入
- PlanningNode: 任务规划节点 (Manus-style)
- RetrieveNode: 检索相关历史记忆
- DecideNode: 决策节点 (核心，含计划重读)
- ToolNode: 工具执行节点
- ThinkNode: 思考推理节点
- AnswerNode: 生成最终回答
- SupervisorNode: 答案质量监督节点 (含计划完成度检查)
- EmbedNode: 存储对话到向量记忆

Manus-style Planning Features:
- 三文件模式: task_plan.md, findings.md, progress.md
- 决策前重读计划 (注意力操纵)
- 错误持久化记录
- 计划完成度验证
"""

import os
import re
import yaml
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
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
    PLANNING = "planning"  # 任务规划 (Manus-style)
    RETRIEVE = "retrieve"
    DECIDE = "decide"
    EMBED = "embed"
    SUPERVISOR = "supervisor"  # 答案质量监督


# ============================================================================
# 辅助函数
# ============================================================================

def _extract_yaml_block(response: str) -> str:
    """
    智能提取 YAML 代码块，正确处理嵌套的 ``` 标记

    LLM 返回的 answer 字段可能包含 markdown 代码块（如 ```json），
    简单的 split("```") 会错误截断。此函数通过计算嵌套层级来正确提取。
    """
    if not response:
        return ""

    # 查找 ```yaml 或 ``` 开始位置
    start_marker = "```yaml"
    start_idx = response.find(start_marker)
    if start_idx == -1:
        start_marker = "```"
        start_idx = response.find(start_marker)
        if start_idx == -1:
            return response

    # 跳过开始标记
    content_start = start_idx + len(start_marker)
    # 跳过开始标记后的换行
    if content_start < len(response) and response[content_start] == '\n':
        content_start += 1

    # 查找配对的结束 ```
    # 策略：从内容开始位置向后搜索，跟踪嵌套的代码块
    content = response[content_start:]
    nesting_level = 0
    i = 0
    while i < len(content):
        # 检查是否是 ``` 标记（可能带语言标识符）
        if content[i:i+3] == "```":
            # 检查是否在行首或前面是换行
            is_line_start = (i == 0) or (content[i-1] == '\n')
            if is_line_start:
                # 检查这是开始标记还是结束标记
                # 如果 ``` 后面跟着字母（语言名），是开始标记
                rest = content[i+3:]
                if rest and (rest[0].isalpha() or rest[0] == '\n' or rest[0] == ' '):
                    if rest[0].isalpha():
                        nesting_level += 1
                    elif nesting_level > 0:
                        nesting_level -= 1
                    else:
                        # 找到了配对的结束标记
                        return content[:i].strip()
                elif nesting_level > 0:
                    nesting_level -= 1
                else:
                    # 找到了配对的结束标记
                    return content[:i].strip()
            i += 3
        else:
            i += 1

    # 如果没找到结束标记，返回全部内容
    return content.strip()


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
        # 使用智能提取，正确处理嵌套的代码块
        yaml_str = _extract_yaml_block(response)

        result = yaml.safe_load(yaml_str)
        if result is None:
            raise ValueError("YAML parse result is empty")

        # 备用：检查 answer 字段是否被 YAML 解析截断（防御性代码）
        # 正常情况下 _extract_yaml_block 已经正确处理了嵌套代码块
        if result.get("action") == "answer":
            parsed_answer = str(result.get("answer", ""))
            full_answer = _extract_full_answer(yaml_str)
            if full_answer and len(full_answer) > len(parsed_answer):
                print(f"   [YAML] Recovered truncated answer: {len(parsed_answer)} -> {len(full_answer)} chars")
                result["answer"] = full_answer

        return result
    except Exception as e:
        raise ValueError(f"YAML parse failed: {e}")


def _extract_full_answer(yaml_str: str) -> str | None:
    """
    从 YAML 字符串中直接提取完整的 answer 内容

    当 YAML 解析器因格式问题截断多行文本时，使用正则表达式恢复完整内容。
    支持多种 YAML 格式：
    - answer: |  （块标量，保留换行）
    - answer: >  （折叠标量）
    - answer: "..." （引号包裹）
    - answer: 直接内容
    """
    # 方法1：匹配 answer: | 或 answer: > 后的多行内容
    # 使用贪婪匹配获取所有缩进的行
    match = re.search(r'answer:\s*[|>]\s*\n((?:[ \t]+[^\n]*\n?)+)', yaml_str)
    if match:
        content = match.group(1)
        # 移除公共缩进
        lines = content.split('\n')
        non_empty_lines = [l for l in lines if l.strip()]
        if non_empty_lines:
            min_indent = min(len(l) - len(l.lstrip()) for l in non_empty_lines)
            result = '\n'.join(
                line[min_indent:] if len(line) >= min_indent else line
                for line in lines
            ).strip()
            if result:
                return result

    # 方法2：从 "answer:" 提取到 yaml_str 末尾（最宽松的提取）
    # 查找 answer: 后面的所有内容
    match = re.search(r'answer:\s*\|?\s*\n?([\s\S]+)$', yaml_str)
    if match:
        content = match.group(1)
        # 如果内容有缩进，移除公共缩进
        lines = content.split('\n')
        non_empty_lines = [l for l in lines if l.strip()]
        if non_empty_lines:
            min_indent = min(len(l) - len(l.lstrip()) for l in non_empty_lines if l.strip())
            result = '\n'.join(
                line[min_indent:] if len(line) >= min_indent else line
                for line in lines
            ).strip()
            if result:
                return result
        return content.strip()

    # 方法3：单行 answer（引号包裹或直接值）
    match = re.search(r'answer:\s*["\']?(.*?)["\']?\s*$', yaml_str, re.MULTILINE)
    if match and match.group(1).strip():
        return match.group(1).strip()

    return None


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

# 拒绝回复检测模式（更精确的正则表达式，减少误判）
REJECT_PATTERNS = [
    r"^(sorry|抱歉|对不起)[,，]?\s*(i\s*)?(cannot|can't|couldn't|无法|不能)",
    r"^(i\s*)?(cannot|can't|couldn't|无法|不能).{0,30}(sorry|抱歉)",
    r"^(unable|无法)\s+to\s+",
    r"^(i\s+)?(don't|do not|没有|不)\s+(have|know|了解|知道)",
]

# ============================================================================
# Manus-style Planning 配置
# ============================================================================

# 规划文件存放目录 (相对于项目根目录的 sandbox)
PLANNING_DIR = "sandbox"

# 规划文件名
PLAN_FILE = "task_plan.md"
FINDINGS_FILE = "findings.md"
PROGRESS_FILE = "progress.md"

# 复杂任务判定阈值
COMPLEX_TASK_MIN_LENGTH = 15  # 降低阈值，更多任务会被认为是复杂任务

# 复杂任务关键词（按类别组织）
COMPLEX_TASK_KEYWORDS = [
    # 分析类动词
    "分析", "比较", "研究", "调查", "评估", "总结", "解读", "解析", "诊断",
    "analyze", "compare", "research", "investigate", "evaluate", "summarize",

    # 建议/推荐类
    "建议", "推荐", "评级", "评价", "判断", "预测", "展望",
    "suggest", "recommend", "rate", "rating", "predict", "forecast",

    # 数量词（暗示多步骤）
    "多个", "几个", "所有", "各个", "每个", "一系列",
    "multiple", "several", "all", "each", "various",

    # 流程/规划类
    "步骤", "流程", "方案", "计划", "策略", "规划",
    "steps", "process", "plan", "strategy", "procedure",

    # 金融/投资领域（通常需要数据获取+分析）
    "股价", "行情", "走势", "涨跌", "买入", "卖出", "持有",
    "K线", "均线", "指标", "估值", "市盈率", "市值",
    "stock", "price", "trend", "buy", "sell", "hold",

    # 数据处理类
    "统计", "汇总", "整理", "对比", "排序", "筛选",
    "statistics", "aggregate", "sort", "filter",

    # 问题解决类
    "怎么", "如何", "为什么", "什么原因", "怎样",
    "how", "why", "what cause",
]

# 复杂任务句式模式（正则表达式）
COMPLEX_TASK_PATTERNS = [
    r"给.{0,10}(建议|推荐|评级|分析)",  # "给xxx建议"
    r"(帮我|请|麻烦).{0,15}(分析|研究|查|找|整理)",  # "帮我分析xxx"
    r"\d{6}.{0,10}(股|价|行情|走势|建议)",  # 股票代码 + 相关词
    r"(对比|比较).{0,10}(和|与|跟)",  # "对比A和B"
]

# 2-动作规则：每 N 次工具调用后更新 findings
FINDINGS_UPDATE_INTERVAL = 2

# ============================================================================
# 内置时钟工具 - 城市/地区到时区映射
# ============================================================================

CITY_TIMEZONE_MAP = {
    # 中国
    "北京": "Asia/Shanghai", "上海": "Asia/Shanghai", "深圳": "Asia/Shanghai",
    "广州": "Asia/Shanghai", "成都": "Asia/Shanghai", "重庆": "Asia/Shanghai",
    "香港": "Asia/Hong_Kong", "澳门": "Asia/Macau", "台北": "Asia/Taipei",

    # 亚洲
    "东京": "Asia/Tokyo", "大阪": "Asia/Tokyo",
    "首尔": "Asia/Seoul", "釜山": "Asia/Seoul",
    "新加坡": "Asia/Singapore",
    "曼谷": "Asia/Bangkok",
    "雅加达": "Asia/Jakarta",
    "马尼拉": "Asia/Manila",
    "吉隆坡": "Asia/Kuala_Lumpur",
    "河内": "Asia/Ho_Chi_Minh",
    "胡志明": "Asia/Ho_Chi_Minh",
    "新德里": "Asia/Kolkata", "孟买": "Asia/Kolkata",
    "迪拜": "Asia/Dubai",

    # 欧洲
    "伦敦": "Europe/London",
    "巴黎": "Europe/Paris",
    "柏林": "Europe/Berlin", "法兰克福": "Europe/Berlin",
    "罗马": "Europe/Rome", "米兰": "Europe/Rome",
    "马德里": "Europe/Madrid", "巴塞罗那": "Europe/Madrid",
    "阿姆斯特丹": "Europe/Amsterdam",
    "布鲁塞尔": "Europe/Brussels",
    "苏黎世": "Europe/Zurich",
    "莫斯科": "Europe/Moscow",

    # 美洲
    "纽约": "America/New_York", "华盛顿": "America/New_York", "波士顿": "America/New_York",
    "洛杉矶": "America/Los_Angeles", "旧金山": "America/Los_Angeles", "西雅图": "America/Los_Angeles",
    "芝加哥": "America/Chicago",
    "多伦多": "America/Toronto",
    "温哥华": "America/Vancouver",
    "墨西哥城": "America/Mexico_City",
    "圣保罗": "America/Sao_Paulo",
    "布宜诺斯艾利斯": "America/Argentina/Buenos_Aires",

    # 大洋洲
    "悉尼": "Australia/Sydney", "墨尔本": "Australia/Melbourne",
    "奥克兰": "Pacific/Auckland",

    # 英文城市名
    "beijing": "Asia/Shanghai", "shanghai": "Asia/Shanghai",
    "tokyo": "Asia/Tokyo", "seoul": "Asia/Seoul",
    "singapore": "Asia/Singapore", "hong kong": "Asia/Hong_Kong",
    "london": "Europe/London", "paris": "Europe/Paris",
    "berlin": "Europe/Berlin", "moscow": "Europe/Moscow",
    "new york": "America/New_York", "los angeles": "America/Los_Angeles",
    "chicago": "America/Chicago", "toronto": "America/Toronto",
    "sydney": "Australia/Sydney", "auckland": "Pacific/Auckland",
}


# ============================================================================
# 规划文件操作辅助函数
# ============================================================================

def get_planning_file_path(filename: str) -> str:
    """获取规划文件的完整路径"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, PLANNING_DIR, filename)


def read_planning_file(filename: str) -> str | None:
    """读取规划文件内容"""
    filepath = get_planning_file_path(filename)
    try:
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()
    except Exception as e:
        print(f"   [WARN] Failed to read {filename}: {e}")
    return None


def write_planning_file(filename: str, content: str) -> bool:
    """写入规划文件"""
    filepath = get_planning_file_path(filename)
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"   [WARN] Failed to write {filename}: {e}")
        return False


def update_plan_phase(phase_num: int, completed: bool = False) -> bool:
    """更新计划文件中的阶段状态"""
    content = read_planning_file(PLAN_FILE)
    if not content:
        return False

    # 更新复选框状态
    old_marker = f"- [ ] Phase {phase_num}:"
    new_marker = f"- [x] Phase {phase_num}:" if completed else f"- [ ] Phase {phase_num}:"

    if old_marker in content or f"- [x] Phase {phase_num}:" in content:
        content = content.replace(f"- [ ] Phase {phase_num}:", new_marker)
        content = content.replace(f"- [x] Phase {phase_num}:", new_marker)

        # 更新当前阶段
        if not completed:
            # 使用 [^\n]* 替代 .* 避免贪婪匹配跨行
            content = re.sub(r"## Current Phase\n[^\n]*", f"## Current Phase\nPhase {phase_num}", content)

        return write_planning_file(PLAN_FILE, content)
    return False


def append_to_findings(title: str, source: str, finding: str, implications: str = "") -> bool:
    """追加发现到 findings.md"""
    content = read_planning_file(FINDINGS_FILE)
    if not content:
        return False

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_entry = f"""
### [{timestamp}] {title}
**Source**: {source}
**Finding**:
{finding}

**Implications**:
- {implications if implications else "Pending analysis"}

---
"""
    content += new_entry
    return write_planning_file(FINDINGS_FILE, content)


def append_to_progress(action_type: str, description: str, tool_name: str = "", result: str = "") -> bool:
    """追加进度到 progress.md"""
    content = read_planning_file(PROGRESS_FILE)
    if not content:
        return False

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    tool_line = f"\n- Tool: {tool_name}" if tool_name else ""
    result_line = f"\n- Result: {result[:100]}..." if result and len(result) > 100 else (f"\n- Result: {result}" if result else "")

    new_entry = f"""
### [{timestamp}] {action_type}
- {description}{tool_line}{result_line}

"""
    content += new_entry
    return write_planning_file(PROGRESS_FILE, content)


def record_error_in_plan(error: str) -> bool:
    """在计划文件中记录错误（避免重复）"""
    content = read_planning_file(PLAN_FILE)
    if not content:
        return False

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    error_entry = f"\n- [{timestamp}] {error}"

    # 在 Errors Encountered 部分追加
    if "## Errors Encountered" in content:
        parts = content.split("## Errors Encountered")
        if len(parts) == 2:
            content = parts[0] + "## Errors Encountered" + parts[1].split("\n##")[0] + error_entry
            if "\n##" in parts[1]:
                content += "\n##" + "\n##".join(parts[1].split("\n##")[1:])
            return write_planning_file(PLAN_FILE, content)
    return False


def get_plan_completion_status() -> tuple[int, int, list[str]]:
    """获取计划完成状态: (已完成数, 总数, 未完成阶段列表)"""
    content = read_planning_file(PLAN_FILE)
    if not content:
        return 0, 0, []

    completed = len(re.findall(r"- \[x\] Phase \d+:", content))
    total = len(re.findall(r"- \[.\] Phase \d+:", content))

    # 获取未完成阶段
    uncompleted = re.findall(r"- \[ \] (Phase \d+:[^-\n]+)", content)

    return completed, total, uncompleted


def is_complex_task(task: str) -> bool:
    """
    判断是否为复杂任务，需要创建规划文件

    判断条件（满足任一即为复杂任务）：
    1. 任务长度 >= 15 字符
    2. 包含复杂任务关键词
    3. 匹配复杂任务句式模式（正则）

    Returns:
        True: 复杂任务，需要创建规划文件
        False: 简单任务，跳过规划
    """
    # 条件1: 长度检查
    if len(task) >= COMPLEX_TASK_MIN_LENGTH:
        return True

    task_lower = task.lower()

    # 条件2: 关键词检查
    for keyword in COMPLEX_TASK_KEYWORDS:
        if keyword.lower() in task_lower:
            return True

    # 条件3: 句式模式匹配（正则表达式）
    for pattern in COMPLEX_TASK_PATTERNS:
        if re.search(pattern, task, re.IGNORECASE):
            return True

    return False


def cleanup_planning_files() -> None:
    """清理规划文件（任务完成后）"""
    for filename in [PLAN_FILE, FINDINGS_FILE, PROGRESS_FILE]:
        filepath = get_planning_file_path(filename)
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass


# ============================================================================
# 系统提示词模板
# ============================================================================

AGENT_SYSTEM_PROMPT = """你是一个智能助手，可以通过 MCP 协议调用各种工具来帮助用户解决复杂问题。

### 当前时间
{current_datetime}

### 项目路径
- 项目根目录: {project_root}
- sandbox 目录: {sandbox_path}
- 当用户提到 "sandbox"、"沙盒" 或 "工作目录" 时，使用上述 sandbox 路径

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

### 内置工具（无需 MCP，随时可用）
- **get_current_time**: 获取当前准确时间
  - 无参数: 返回本地时间
  - 参数 city: 返回指定城市的时间 (如 "北京", "东京", "纽约", "伦敦" 等)
  - 参数 timezone: 返回指定时区的时间 (如 "Asia/Shanghai", "America/New_York" 等)
  - 示例: `tool_params: {{city: "东京"}}` 或 `tool_params: {{timezone: "Asia/Tokyo"}}`

- **save_to_memory**: 将重要内容保存到长期记忆
  - 当用户明确要求保存某些重要信息、结果或结论时使用
  - 参数 content (必需): 要保存的内容
  - 参数 tag (可选): 记忆标签，便于后续检索 (如 "股票分析", "会议记录")
  - 示例: `tool_params: {{content: "茅台股票分析结论...", tag: "股票分析"}}`

### 注意事项
- 复杂任务需要多步完成，不要急于回答
- 先调用工具获取数据，再思考分析
- 需要知道当前时间时，调用 get_current_time 工具
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

            # 获取当前时间（用于系统提示词和欢迎消息）
            # 使用 astimezone() 获取带时区的本地时间
            current_dt = datetime.now().astimezone()
            utc_offset = current_dt.strftime("%z")  # 如 +0800
            utc_offset_formatted = f"UTC{utc_offset[:3]}:{utc_offset[3:]}"  # 格式化为 UTC+08:00
            current_datetime_str = current_dt.strftime("%Y-%m-%d %H:%M:%S (%A)") + f" [{utc_offset_formatted}]"
            shared["current_datetime"] = current_datetime_str

            # 获取项目路径（用于系统提示词）
            project_root = os.path.dirname(os.path.abspath(__file__))
            sandbox_path = os.path.join(project_root, PLANNING_DIR)
            shared["project_root"] = project_root
            shared["sandbox_path"] = sandbox_path

            try:
                manager = MCPManager("mcp.json")
                await manager.get_all_tools_async()
                shared["mcp_manager"] = manager

                if manager.tools:
                    tool_info = manager.format_tools_for_prompt()
                    shared["system_prompt"] = AGENT_SYSTEM_PROMPT.format(
                        tool_info=tool_info,
                        current_datetime=current_datetime_str,
                        project_root=project_root,
                        sandbox_path=sandbox_path
                    )
                    print(f"[OK] Loaded {len(manager.tools)} tools")
                else:
                    shared["system_prompt"] = AGENT_SYSTEM_PROMPT.format(
                        tool_info="(no tools)",
                        current_datetime=current_datetime_str,
                        project_root=project_root,
                        sandbox_path=sandbox_path
                    )
                    print("[WARN] No tools available")

            except Exception as e:
                print(f"[WARN] MCP initialization failed: {e}")
                shared["mcp_manager"] = None
                shared["system_prompt"] = AGENT_SYSTEM_PROMPT.format(
                    tool_info="(init failed)",
                    current_datetime=current_datetime_str,
                    project_root=project_root,
                    sandbox_path=sandbox_path
                )

            # 初始化对话历史
            shared["messages"] = []

            # 初始化记忆索引
            shared["memory_index"] = get_memory_index()
            print(f"[OK] Memory index ready ({len(shared['memory_index'])} items)")

            print("\n" + "=" * 50)
            print("Welcome! Multi-step reasoning assistant ready.")
            print(f"Current time: {current_datetime_str}")
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
        shared["max_steps"] = 25  # 复杂任务需要更多步骤

        # 添加到对话历史
        shared["messages"].append({"role": "user", "content": exec_res})

        print(f"\n[Task]: {exec_res}")
        print("-" * 40)

        return Action.PLANNING  # 先进入规划节点


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
        base_dir = os.path.dirname(os.path.abspath(__file__))
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

        # 检查步数限制
        if step_count >= max_steps:
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

        # 构建上下文，包含检索到的记忆
        full_context = ""

        # 计划放在最前面（推入近期注意力）
        if plan_context:
            full_context += plan_context

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

    def _extract_plan_summary(self, plan_content: str) -> str:
        """从计划文件中提取关键摘要"""
        summary_parts = []

        # 提取目标
        goal_match = re.search(r"## Goal\n(.+?)(?=\n##|\Z)", plan_content, re.DOTALL)
        if goal_match:
            goal = goal_match.group(1).strip()[:200]
            summary_parts.append(f"Goal: {goal}")

        # 提取当前阶段
        phase_match = re.search(r"## Current Phase\n(.+?)(?=\n##|\Z)", plan_content, re.DOTALL)
        if phase_match:
            phase = phase_match.group(1).strip()
            summary_parts.append(f"Current: {phase}")

        # 提取完成状态
        completed, total, uncompleted = get_plan_completion_status()
        if total > 0:
            summary_parts.append(f"Progress: {completed}/{total} phases completed")
            if uncompleted:
                next_phase = uncompleted[0] if uncompleted else ""
                summary_parts.append(f"Next: {next_phase}")

        # 提取最近错误（帮助避免重复）
        if "## Errors Encountered" in plan_content:
            errors_section = plan_content.split("## Errors Encountered")[1].split("\n##")[0]
            error_lines = [l.strip() for l in errors_section.split("\n") if l.strip().startswith("-")]
            if error_lines:
                recent_error = error_lines[-1][:100]
                summary_parts.append(f"Recent Error: {recent_error}")

        return "\n".join(summary_parts) if summary_parts else ""

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
    工具执行节点 (含 Manus-style 2-动作规则)

    职责:
    - 调用 MCP 工具
    - 将结果添加到上下文
    - 实现 2-动作规则：每 N 次工具调用后更新 findings
    - 记录进度到 progress.md
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
        tool_name = exec_res.get("tool_name", "")
        tool_params = exec_res.get("tool_params", {})
        has_plan = shared.get("has_plan", False)

        # ========================================
        # 内置工具处理（不需要 MCP）
        # ========================================
        if tool_name == "get_current_time":
            # 内置时钟工具：返回当前准确时间（支持多时区）
            city = tool_params.get("city", "")
            tz_name = tool_params.get("timezone", "")
            location_info = ""

            # 确定时区
            target_tz = None
            if city:
                # 从城市映射查找时区
                city_lower = city.lower()
                tz_name = CITY_TIMEZONE_MAP.get(city) or CITY_TIMEZONE_MAP.get(city_lower)
                if tz_name:
                    try:
                        target_tz = ZoneInfo(tz_name)
                        location_info = f" [{city}]"
                    except Exception:
                        location_info = f" [Unknown city: {city}, using local time]"
                else:
                    location_info = f" [Unknown city: {city}, using local time]"
            elif tz_name:
                # 直接使用时区名称
                try:
                    target_tz = ZoneInfo(tz_name)
                    location_info = f" [{tz_name}]"
                except Exception:
                    location_info = f" [Invalid timezone: {tz_name}, using local time]"

            # 获取时间
            if target_tz:
                current_dt = datetime.now(target_tz)
                result_str = current_dt.strftime("%Y-%m-%d %H:%M:%S (%A)") + location_info
            else:
                # 本地时间：附加系统时区信息，让 Agent 知道基准时区
                current_dt = datetime.now().astimezone()  # 带时区的本地时间
                utc_offset = current_dt.strftime("%z")  # 如 +0800
                utc_offset_formatted = f"UTC{utc_offset[:3]}:{utc_offset[3:]}"  # 格式化为 UTC+08:00
                result_str = current_dt.strftime("%Y-%m-%d %H:%M:%S (%A)") + f" [Local: {utc_offset_formatted}]"
            print(f"   [OK] Built-in tool result: {result_str}")

            # 添加到上下文
            context = shared.get("context", "")
            shared["context"] = context + f"\n\n### Tool Call: {tool_name} (Built-in)\nResult: {result_str}"

            # Manus-style 进度记录
            if has_plan:
                append_to_progress(
                    action_type="Built-in Tool",
                    description=f"Called get_current_time{location_info}",
                    result=result_str
                )

            return Action.DECIDE

        # ========================================
        # 内置工具: save_to_memory - 用户主动保存到长期记忆
        # ========================================
        if tool_name == "save_to_memory":
            content = tool_params.get("content", "")
            tag = tool_params.get("tag", "用户保存")

            if not content:
                result_str = "Error: content parameter is required"
                print(f"   [ERROR] {result_str}")
            else:
                # 获取记忆索引
                memory_index = shared.get("memory_index")
                if not memory_index:
                    memory_index = get_memory_index()
                    shared["memory_index"] = memory_index

                # 添加时间戳和标签
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                memory_content = f"[{tag}] [{timestamp}]\n{content}"

                # 生成嵌入并存储
                embedding = get_embedding(memory_content)
                idx, is_new = memory_index.add_or_update(
                    embedding,
                    {"content": memory_content, "tag": tag, "timestamp": timestamp},
                    dedup_threshold=MEMORY_DEDUP_THRESHOLD
                )

                # 立即保存到文件
                memory_index.save("memory_index.json")

                if is_new:
                    result_str = f"Successfully saved to long-term memory (index: {idx}, tag: {tag})"
                else:
                    result_str = f"Updated existing similar memory (index: {idx}, tag: {tag})"

                print(f"   [OK] Built-in tool result: {result_str}")

            # 添加到上下文
            context = shared.get("context", "")
            shared["context"] = context + f"\n\n### Tool Call: {tool_name} (Built-in)\nResult: {result_str}"

            # Manus-style 进度记录
            if has_plan:
                append_to_progress(
                    action_type="Built-in Tool",
                    description=f"Saved to memory with tag: {tag}",
                    result=result_str
                )

            return Action.DECIDE

        # ========================================
        # MCP 工具处理
        # ========================================
        manager = shared.get("mcp_manager")
        if not manager:
            print("   [ERROR] MCP Manager not initialized")
            shared["context"] += "\n\n[Tool call failed: MCP Manager not initialized]"
            # 记录错误到计划文件
            if shared.get("has_plan"):
                record_error_in_plan("MCP Manager not initialized")
            return Action.DECIDE

        try:
            result = await manager.call_tool_async(tool_name, tool_params)
            result_str = str(result)
            print(f"   [OK] Tool result: {result_str[:200]}..." if len(result_str) > 200 else f"   [OK] Tool result: {result_str}")

            # 添加到上下文
            context = shared.get("context", "")
            shared["context"] = context + f"\n\n### Tool Call: {tool_name}\nParams: {tool_params}\nResult:\n{result_str}"

            # ========================================
            # Manus-style: 2-动作规则 + 进度记录
            # ========================================
            if has_plan:
                # 更新工具调用计数
                tool_call_count = shared.get("tool_call_count", 0) + 1
                shared["tool_call_count"] = tool_call_count

                # 记录进度
                append_to_progress(
                    action_type="Tool Call",
                    description=f"Called {tool_name}",
                    tool_name=tool_name,
                    result=result_str[:200]
                )

                # 2-动作规则：每 N 次工具调用后更新 findings
                if tool_call_count % FINDINGS_UPDATE_INTERVAL == 0:
                    finding_title = f"Tool Result: {tool_name}"
                    append_to_findings(
                        title=finding_title,
                        source=f"Tool: {tool_name}",
                        finding=result_str[:500],
                        implications="Data collected for analysis"
                    )
                    print(f"   [Planning] Updated findings (2-action rule)")

                # 更新阶段状态（工具调用 = Phase 1 信息收集）
                update_plan_phase(1, completed=False)

        except Exception as e:
            error_msg = str(e)
            print(f"   [ERROR] Tool call failed: {error_msg}")
            shared["context"] += f"\n\n[Tool call failed: {tool_name} - {error_msg}]"

            # Manus-style: 记录错误到计划文件（避免重复失败）
            if has_plan:
                record_error_in_plan(f"Tool {tool_name} failed: {error_msg[:100]}")
                append_to_progress(
                    action_type="Error",
                    description=f"Tool call failed: {tool_name}",
                    result=error_msg[:100]
                )

        return Action.DECIDE


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

                # 清理规划文件（可选，保留用于调试）
                # cleanup_planning_files()

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
