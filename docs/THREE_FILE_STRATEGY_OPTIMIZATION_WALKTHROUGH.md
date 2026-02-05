# Three-File Memory Strategy Optimization Walkthrough

> **Date**: 2026-01-24  
> **Scope**: `nodes.py` - 三文件记忆策略 (task_plan.md, findings.md, progress.md) 优化

## 背景

三文件策略是 Manus-style Planning 的核心机制，通过外部文件持久化任务状态，解决 LLM 上下文限制问题。

### 原有架构

| 文件 | 用途 |
|------|------|
| `task_plan.md` | 任务目标、阶段状态、错误记录 |
| `findings.md` | 工具调用后的关键发现 |
| `progress.md` | 操作日志记录 |

---

## 实施的改进

### 1️⃣ 智能 Findings 生成

**问题**：原实现使用固定文本 `"Data collected for analysis"` 作为所有工具的 implications。

**解决方案**：添加工具类型映射和智能推断函数。

#### 新增配置

```python
TOOL_IMPLICATIONS_MAP = {
    # 金融类
    "fetch_stock_quote": "实时行情数据可用于判断当前市场状态",
    "analyze_technical_indicators": "技术指标分析结果可辅助投资决策",
    # 搜索类
    "search_web": "搜索结果提供了相关信息来源",
    # ... 更多映射
}
```

#### 新增函数

```python
def get_smart_implications(tool_name: str, result_str: str = "") -> str:
    """根据工具类型智能生成 implications"""
    # 1. 精确匹配
    if tool_name in TOOL_IMPLICATIONS_MAP:
        return TOOL_IMPLICATIONS_MAP[tool_name]
    
    # 2. 模糊匹配
    if any(kw in tool_name.lower() for kw in ["stock", "quote"]):
        return "金融数据已获取，可用于市场分析"
    # ...
```

#### 调用点更新

```diff
# ToolNode (line ~2090)
- implications="Data collected for analysis"
+ smart_impl = get_smart_implications(tool_name, result_str)
+ implications=smart_impl
```

---

### 2️⃣ Progress 条目限制

**问题**：`progress.md` 无限追加，长任务会导致文件过大。

**解决方案**：限制最大条目数为 20。

#### 新增配置

```python
MAX_PROGRESS_ENTRIES = 20
```

#### 函数修改

```python
def append_to_progress(...):
    # ... 原有逻辑
    
    # 新增：限制条目数量
    entries = re.findall(r'### \[[^\]]+\] .+?(?=### \[|## Errors|$)', content, re.DOTALL)
    if len(entries) > MAX_PROGRESS_ENTRIES:
        # 保留头部 + 最近 N 条记录
        recent_entries = entries[-MAX_PROGRESS_ENTRIES:]
        content = header + "\n" + "\n".join(recent_entries)
```

---

### 3️⃣ 优先级保留

**问题**：`_extract_plan_summary()` 只保留最近 3 条 findings，高优先级发现可能被覆盖。

**解决方案**：优先保留 CRITICAL 和 IMPORTANT 级别的 findings。

#### 新逻辑

```python
# 分离优先级
for timestamp, priority_tag, title, finding in findings_entries:
    if "CRITICAL" in priority_tag:
        critical_findings.append(entry)
    elif "IMPORTANT" in priority_tag:
        important_findings.append(entry)
    else:
        normal_findings.append(entry)

# 组合：所有 CRITICAL + 最近2条 IMPORTANT + 最近2条普通
findings_summary = []
findings_summary.extend(critical_findings)       # 保留全部
findings_summary.extend(important_findings[-2:]) # 最近2条
findings_summary.extend(normal_findings[-2:])    # 最近2条
findings_summary = findings_summary[:6]          # 限制总数
```

---

### 4️⃣ 自动归档

**问题**：原 `cleanup_planning_files()` 被注释掉，规划文件永久保留占用空间。

**解决方案**：任务完成后归档到 `sandbox/archive/` 目录。

#### 新增配置

```python
ARCHIVE_DIR = "sandbox/archive"
```

#### 新增函数

```python
def archive_planning_files(task_summary: str = "") -> str | None:
    """归档规划文件到 archive 目录"""
    # 创建带时间戳的目录：20260124_153000_任务摘要
    archive_dir = f"{timestamp}_{safe_summary}"
    
    # 复制文件到归档目录
    for filename in [PLAN_FILE, FINDINGS_FILE, PROGRESS_FILE]:
        shutil.copy2(src_path, dst_path)
```

#### SupervisorNode 调用

```diff
# 任务完成时
- # cleanup_planning_files()
+ task = shared.get("current_task", "")
+ archive_planning_files(task)
```

---

## 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| [nodes.py](file:///e:/AI/my-pocketflow/nodes.py) | 所有改动 |

### 具体行号变更

render_diffs(file:///e:/AI/my-pocketflow/nodes.py)

---

## 验证方法

1. 运行 Agent 并执行一个复杂任务（如股票分析）
2. 检查 `sandbox/findings.md` 中的 implications 是否智能生成
3. 检查 `sandbox/progress.md` 条目是否被限制
4. 任务完成后检查 `sandbox/archive/` 目录是否有归档文件

---

## 归档目录结构示例

```
sandbox/
├── archive/
│   ├── 20260124_153000_分析茅台股票/
│   │   ├── task_plan.md
│   │   ├── findings.md  
│   │   └── progress.md
│   └── 20260124_160000_查询天气/
│       └── ...
├── task_plan.md      # 当前任务
├── findings.md
└── progress.md
```
