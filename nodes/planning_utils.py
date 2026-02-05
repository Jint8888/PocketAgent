"""
Manus-style 规划文件操作辅助函数

包含:
- 规划文件路径和配置
- 文件读写操作
- 任务复杂度判断
- 进度和发现记录
"""

import os
import re
from datetime import datetime


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

# Progress 文件最大条目数（防止文件过大）
MAX_PROGRESS_ENTRIES = 20

# 规划文件归档目录
ARCHIVE_DIR = "sandbox/archive"

# 记忆分层保留长度（按重要性）
FINDING_LENGTH_LIMITS = {
    "critical": 1000,   # 关键发现：保留1000字符
    "important": 500,   # 重要发现：保留500字符
    "normal": 200,      # 普通发现：保留200字符（默认）
}

# 工具类型到 implications 映射（智能生成 findings）
TOOL_IMPLICATIONS_MAP = {
    # 股票/金融类工具
    "fetch_stock_quote": "实时行情数据可用于判断当前市场状态",
    "fetch_stock_kline": "K线数据可用于技术分析和趋势判断",
    "get_stock_data": "股票数据已获取，可进行进一步分析",
    "analyze_technical_indicators": "技术指标分析结果可辅助投资决策",
    "get_financial_report": "财务数据可用于基本面分析",
    "compare_stocks": "股票对比数据可用于选股决策",
    "get_dragon_tiger_list": "龙虎榜数据揭示主力资金动向",
    "wencai_query": "问财查询结果可用于筛选目标股票",

    # 搜索/爬取类工具
    "search_web": "搜索结果提供了相关信息来源",
    "crawl_url": "网页内容已提取，可进行信息整合",
    "enhanced_search": "增强搜索结果提供更全面的信息",

    # 热点/新闻类工具
    "get-weibo-trending": "微博热搜反映当前社会热点",
    "get-zhihu-trending": "知乎热榜揭示公众关注话题",
    "get-toutiao-trending": "今日头条热点反映大众兴趣",
    "get-tencent-news-trending": "腾讯新闻热点提供时事资讯",

    # 文件系统类工具
    "read_file": "文件内容已读取，可进行分析",
    "write_file": "文件已保存，操作已持久化",
    "list_directory": "目录结构已获取，可继续操作",

    # 天气/地图类工具
    "maps_weather": "天气信息可用于活动规划",
    "maps_direction_driving": "驾车路线已规划",
    "maps_text_search": "POI搜索结果可用于位置选择",

    # 代码执行类工具
    "execute_terminal": "命令已执行，结果可用于下一步操作",
    "execute_python": "Python代码已运行，输出可用于分析",
}


# ============================================================================
# 规划文件操作辅助函数
# ============================================================================

def get_planning_file_path(filename: str) -> str:
    """获取规划文件的完整路径"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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


def append_to_findings(title: str, source: str, finding: str, implications: str = "", priority: str = "normal") -> bool:
    """
    追加发现到 findings.md

    Args:
        title: 发现标题
        source: 来源（工具名或节点名）
        finding: 发现内容
        implications: 影响/意义
        priority: 优先级 ("critical", "important", "normal")
    """
    content = read_planning_file(FINDINGS_FILE)
    if not content:
        return False

    # 根据优先级截断内容
    max_length = FINDING_LENGTH_LIMITS.get(priority, 200)
    finding_truncated = finding[:max_length]
    if len(finding) > max_length:
        finding_truncated += f"\n... (truncated {len(finding) - max_length} chars)"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    priority_tag = f"[{priority.upper()}] " if priority != "normal" else ""

    new_entry = f"""
### [{timestamp}] {priority_tag}{title}
**Source**: {source}
**Finding**:
{finding_truncated}

**Implications**:
- {implications if implications else "Pending analysis"}

---
"""
    content += new_entry
    return write_planning_file(FINDINGS_FILE, content)


def append_to_progress(action_type: str, description: str, tool_name: str = "", result: str = "") -> bool:
    """追加进度到 progress.md，并限制最大条目数防止文件过大"""
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

    # ========================================
    # 限制 progress 条目数量，防止文件过大
    # ========================================
    entries = re.findall(r'### \[[^\]]+\] .+?(?=### \[|## Errors|## Test|$)', content, re.DOTALL)
    if len(entries) > MAX_PROGRESS_ENTRIES:
        # 保留头部（标题和任务信息）+ 最近 N 条记录
        header_match = re.match(r'(.*?## Log Entries\s*)', content, re.DOTALL)
        header = header_match.group(1) if header_match else ""

        # 只保留最近的条目
        recent_entries = entries[-MAX_PROGRESS_ENTRIES:]
        content = header + "\n" + "\n".join(recent_entries)

        # 保留尾部（Errors Log 和 Test Results）
        footer_match = re.search(r'(## Errors Log.*)', content, re.DOTALL)
        if not footer_match:
            content += "\n## Errors Log\n<!-- Track errors to avoid repeating -->\n\n## Test Results\n<!-- Record any validation or test outcomes -->\n"

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


def archive_planning_files(task_summary: str = "") -> str | None:
    """
    归档规划文件到 archive 目录（而非删除）

    Args:
        task_summary: 任务摘要，用于归档文件名

    Returns:
        归档目录路径，失败返回 None
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    archive_base = os.path.join(base_dir, ARCHIVE_DIR)

    # 创建带时间戳的归档目录
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 清理 task_summary，移除特殊字符
    safe_summary = re.sub(r'[\\/:*?"<>|]', '_', task_summary[:30]) if task_summary else "task"
    archive_dir = os.path.join(archive_base, f"{timestamp}_{safe_summary}")

    try:
        os.makedirs(archive_dir, exist_ok=True)

        archived_count = 0
        for filename in [PLAN_FILE, FINDINGS_FILE, PROGRESS_FILE]:
            src_path = get_planning_file_path(filename)
            if os.path.exists(src_path):
                dst_path = os.path.join(archive_dir, filename)
                # 复制而非移动，保留原文件以便调试
                import shutil
                shutil.copy2(src_path, dst_path)
                archived_count += 1

        if archived_count > 0:
            print(f"   [Archive] Saved {archived_count} planning files to {archive_dir}")
            return archive_dir
        return None
    except Exception as e:
        print(f"   [WARN] Failed to archive planning files: {e}")
        return None


def get_smart_implications(tool_name: str, result_str: str = "") -> str:
    """
    根据工具类型智能生成 implications

    Args:
        tool_name: 工具名称
        result_str: 工具返回结果（可选，用于更智能的推断）

    Returns:
        智能生成的 implications 文本
    """
    # 首先检查精确匹配
    if tool_name in TOOL_IMPLICATIONS_MAP:
        return TOOL_IMPLICATIONS_MAP[tool_name]

    # 模糊匹配：检查工具名是否包含关键词
    tool_lower = tool_name.lower()

    # 金融/股票类
    if any(kw in tool_lower for kw in ["stock", "quote", "kline", "financial", "price"]):
        return "金融数据已获取，可用于市场分析"

    # 搜索类
    if any(kw in tool_lower for kw in ["search", "query", "find"]):
        return "搜索结果已获取，可提取相关信息"

    # 新闻/热点类
    if any(kw in tool_lower for kw in ["news", "trending", "hot", "rank"]):
        return "热点信息已获取，可了解当前趋势"

    # 天气类
    if any(kw in tool_lower for kw in ["weather", "天气", "forecast"]):
        return "天气信息已获取，可用于规划"

    # 地图/导航类
    if any(kw in tool_lower for kw in ["map", "direction", "route", "geo"]):
        return "地理信息已获取，可用于导航决策"

    # 文件操作类
    if any(kw in tool_lower for kw in ["file", "read", "write", "directory"]):
        return "文件操作已完成"

    # 代码执行类
    if any(kw in tool_lower for kw in ["execute", "run", "code", "python", "terminal"]):
        return "代码已执行，输出可用于下一步分析"

    # 图像类
    if any(kw in tool_lower for kw in ["image", "generate", "edit", "画"]):
        return "图像处理完成"

    # 默认
    return "数据已收集，待进一步分析"
