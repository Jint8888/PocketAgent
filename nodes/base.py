"""
节点模块基础组件

包含:
- Action 路由常量
- YAML 解析工具函数
- 配置常量
- 城市时区映射
"""

import re
import yaml


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

# 上下文历史窗口大小：保留最近 N 步的操作记录，防止token累积
CONTEXT_WINDOW_SIZE = 5

# 工具返回结果最大长度（字符数）
MAX_TOOL_RESULT_LENGTH = 100000  # 限制工具结果最多100000字符（支持 Base64 图片 ~75KB）

# 记忆检索数量
MEMORY_RETRIEVE_K = 2

# 记忆相似度阈值（低于此值的检索结果将被过滤）
MEMORY_SIMILARITY_THRESHOLD = 0.65

# 记忆分层保留长度（按重要性）
FINDING_LENGTH_LIMITS = {
    "critical": 1000,   # 关键发现：保留1000字符
    "important": 500,   # 重要发现：保留500字符
    "normal": 200,      # 普通发现：保留200字符（默认）
}

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
# YAML 解析辅助函数
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
