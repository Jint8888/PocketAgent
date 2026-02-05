# 行为规则系统开发指南

## 文档信息

- **版本**: v1.0
- **创建日期**: 2024-01-23
- **最后更新**: 2024-01-23
- **状态**: 设计文档

---

## 目录

1. [概述](#概述)
2. [设计目标](#设计目标)
3. [架构设计](#架构设计)
4. [实现方案对比](#实现方案对比)
5. [推荐方案详细设计](#推荐方案详细设计)
6. [规则文件格式规范](#规则文件格式规范)
7. [代码集成指南](#代码集成指南)
8. [配置项说明](#配置项说明)
9. [使用示例](#使用示例)
10. [最佳实践](#最佳实践)
11. [测试方案](#测试方案)
12. [扩展建议](#扩展建议)
13. [FAQ](#faq)

---

## 概述

### 什么是行为规则系统？

行为规则系统是一套**声明式的指令集合**，用于规范 Agent 在不同场景下的行为准则。通过将最佳实践、约束条件、优先级策略等固化为规则文件，确保 LLM 在执行任务时遵循统一的标准。

### 为什么需要行为规则？

当前项目面临以下挑战：

1. **行为一致性问题**
   - LLM 在不同会话中可能做出不一致的决策
   - 同样的场景可能采用不同的处理方式
   - 缺乏明确的优先级指导

2. **知识固化需求**
   - 最佳实践依赖开发者记忆，易遗忘
   - 错误处理经验无法沉淀
   - 领域知识（如 MCP 工具规范）需要反复说明

3. **可维护性问题**
   - 行为调整需要修改代码
   - 难以快速实验不同策略
   - 规则散落在各处，难以审查

### 核心价值

✅ **一致性保证** - 所有操作遵循统一准则
✅ **可配置性** - 不修改代码即可调整行为
✅ **可维护性** - 规则集中管理，易于审查和更新
✅ **可调试性** - 出问题时可以检查规则是否被遵守
✅ **知识沉淀** - 将最佳实践固化为规则，持续积累

---

## 设计目标

### 功能目标

1. **规则定义** - 支持声明式规则语法，易读易写
2. **规则加载** - 在节点执行前自动加载相关规则
3. **规则注入** - 将规则注入到 LLM 的 prompt 中
4. **规则管理** - 支持规则分类、优先级、条件激活
5. **规则验证** - 可以验证 LLM 是否遵守规则（可选）

### 非功能目标

1. **性能** - 规则加载对性能影响可忽略（< 50ms）
2. **兼容性** - 不破坏现有架构，渐进式集成
3. **可扩展性** - 支持新规则类型、新节点
4. **可维护性** - 规则文件结构清晰，注释完善

---

## 架构设计

### 系统架构图

```
┌─────────────────────────────────────────────────────────┐
│                   Pocketflow Agent                       │
│                                                           │
│  ┌────────────┐    ┌──────────────┐    ┌────────────┐  │
│  │ InputNode  │───▶│ PlanningNode │───▶│RetrieveNode│  │
│  └────────────┘    └──────────────┘    └────────────┘  │
│         │                  │                   │         │
│         ▼                  ▼                   ▼         │
│  ┌─────────────────────────────────────────────────┐   │
│  │         Rules Engine (行为规则引擎)              │   │
│  │                                                   │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐      │   │
│  │  │ Loader   │  │ Selector │  │ Injector │      │   │
│  │  │ 加载器   │  │ 选择器   │  │ 注入器   │      │   │
│  │  └──────────┘  └──────────┘  └──────────┘      │   │
│  └─────────────────────────────────────────────────┘   │
│         │                  │                   │         │
│         ▼                  ▼                   ▼         │
│  ┌────────────┐    ┌──────────┐    ┌────────────┐     │
│  │ DecideNode │───▶│ ToolNode │───▶│ ThinkNode  │     │
│  └────────────┘    └──────────┘    └────────────┘     │
│                                                          │
└──────────────────────────────────────────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │   Rules Directory      │
              │   (/rules)             │
              │                        │
              │  - global.md           │
              │  - tool_calling.md     │
              │  - reasoning.md        │
              │  - image_generation.md │
              │  - memory_management.md│
              └───────────────────────┘
```

### 核心组件

#### 1. Rules Loader（规则加载器）

**职责**：
- 从文件系统加载规则文件
- 解析规则内容（Markdown 格式）
- 缓存规则内容（避免重复读取）

**接口**：
```python
class RulesLoader:
    def load_rule(self, rule_name: str) -> str:
        """加载单个规则文件"""
        pass

    def load_rules(self, rule_names: List[str]) -> Dict[str, str]:
        """批量加载多个规则"""
        pass

    def reload(self):
        """清除缓存，重新加载"""
        pass
```

#### 2. Rules Selector（规则选择器）

**职责**：
- 根据节点类型选择适用规则
- 根据上下文条件激活规则
- 处理规则优先级

**接口**：
```python
class RulesSelector:
    def select_for_node(self, node_name: str, context: dict) -> List[str]:
        """为指定节点选择规则"""
        pass

    def filter_by_condition(self, rules: List[str], context: dict) -> List[str]:
        """根据条件过滤规则"""
        pass
```

#### 3. Rules Injector（规则注入器）

**职责**：
- 将规则文本注入到 LLM prompt
- 格式化规则展示
- 控制规则注入位置（system/user）

**接口**：
```python
class RulesInjector:
    def inject_to_prompt(self, prompt: str, rules: List[str]) -> str:
        """将规则注入到 prompt"""
        pass

    def format_rules(self, rules: Dict[str, str]) -> str:
        """格式化规则文本"""
        pass
```

### 数据流

```
1. 节点启动（prep_async）
   ↓
2. 规则选择器根据节点类型选择规则
   ↓
3. 规则加载器加载规则文件内容
   ↓
4. 规则注入器将规则注入到 prompt
   ↓
5. 调用 LLM（规则已在 prompt 中）
   ↓
6. LLM 遵循规则生成输出
   ↓
7. 节点执行（exec_async）
```

---

## 实现方案对比

### 方案 1：全局规则文件（单文件模式）⭐

**实现方式**：
- 创建 `rules/global.md` 存储所有规则
- 在关键节点的 `prep_async` 中读取并注入

**优点**：
- ✅ 实现简单，工作量最小
- ✅ 规则集中，易于查看全貌
- ✅ 适合规则量较少的场景（< 50 条）

**缺点**：
- ❌ 规则混在一起，难以定位
- ❌ 所有节点都加载全部规则，效率低
- ❌ 规则冲突难以管理

**适用场景**：
- 项目初期，规则量少
- 快速原型验证

---

### 方案 2：节点级规则（多文件模式）⭐⭐

**实现方式**：
- 为每个节点创建专属规则文件
  ```
  rules/
    ├── input_rules.md
    ├── planning_rules.md
    ├── decide_rules.md
    ├── tool_rules.md
    ├── think_rules.md
    └── answer_rules.md
  ```
- 每个节点只加载自己的规则

**优点**：
- ✅ 规则与节点强关联，清晰明确
- ✅ 避免不相关规则干扰
- ✅ 性能更好（只加载需要的规则）

**缺点**：
- ❌ 通用规则需要重复定义
- ❌ 文件数量多，管理成本增加
- ❌ 跨节点规则难以共享

**适用场景**：
- 规则量中等（50-200 条）
- 节点行为差异大

---

### 方案 3：分层规则系统（推荐）⭐⭐⭐

**实现方式**：
```
rules/
  ├── global.md              # 全局规则（所有节点）
  ├── tool_calling.md        # 工具调用规则（ToolNode）
  ├── reasoning.md           # 推理规则（ThinkNode, DecideNode）
  ├── planning.md            # 规划规则（PlanningNode）
  ├── memory_management.md   # 记忆管理规则（RetrieveNode, EmbedNode）
  └── domain/                # 领域特定规则
      ├── image_generation.md
      ├── mcp_integration.md
      └── error_handling.md
```

**规则映射配置**：
```python
RULES_MAPPING = {
    "InputNode": ["global"],
    "PlanningNode": ["global", "planning"],
    "RetrieveNode": ["global", "memory_management"],
    "DecideNode": ["global", "reasoning"],
    "ToolNode": ["global", "tool_calling", "domain/mcp_integration"],
    "ThinkNode": ["global", "reasoning"],
    "AnswerNode": ["global"],
    "EmbedNode": ["global", "memory_management"],
}
```

**优点**：
- ✅ 兼顾集中管理和分类组织
- ✅ 全局规则避免重复
- ✅ 节点按需加载，性能和清晰度平衡
- ✅ 支持领域知识扩展
- ✅ 最灵活、最强大

**缺点**：
- ❌ 实现复杂度稍高
- ❌ 需要维护映射配置

**适用场景**：
- **推荐用于本项目**
- 规则量大（> 100 条）
- 需要长期维护和扩展

---

### 方案 4：规则即常量（代码模式）

**实现方式**：
```python
# 在 nodes.py 中定义
TOOL_CALLING_RULES = """
1. 生成图片时，ALWAYS 使用 response_format="url"
2. 避免返回 Base64 超过 100,000 字符
3. 优先使用异步工具
"""
```

**优点**：
- ✅ 性能最好（无 I/O）
- ✅ 代码即文档
- ✅ 类型安全

**缺点**：
- ❌ 修改规则需要改代码
- ❌ 不够灵活
- ❌ 规则混在代码中，难以管理

**适用场景**：
- 规则非常少（< 10 条）
- 规则几乎不变化

---

### 推荐方案

**本项目推荐使用：方案 3 - 分层规则系统**

**理由**：
1. 当前项目已有 Manus-style 三文件模式，架构契合
2. 规则量预计会持续增长（工具调用、推理、记忆等）
3. 需要灵活性（实验不同策略）
4. 长期维护和扩展需求

---

## 推荐方案详细设计

### 目录结构

```
my-pocketflow/
├── rules/                     # 行为规则目录（新增）
│   ├── README.md              # 规则系统说明文档
│   ├── global.md              # 全局规则（必读）
│   ├── tool_calling.md        # 工具调用规则
│   ├── reasoning.md           # 推理规则
│   ├── planning.md            # 规划规则
│   ├── memory_management.md   # 记忆管理规则
│   └── domain/                # 领域特定规则
│       ├── image_generation.md
│       ├── mcp_integration.md
│       └── error_handling.md
├── nodes.py                   # 节点定义（需修改）
├── main.py
└── ...
```

### 核心代码结构

#### 1. 规则引擎模块（新增文件：`rules_engine.py`）

```python
"""
行为规则引擎

提供规则加载、选择、注入功能
"""
import os
from typing import Dict, List, Optional
from pathlib import Path


# 规则目录路径
RULES_DIR = Path(__file__).parent / "rules"

# 规则映射配置：节点名称 -> 规则文件列表
RULES_MAPPING = {
    "InputNode": ["global"],
    "PlanningNode": ["global", "planning"],
    "RetrieveNode": ["global", "memory_management"],
    "DecideNode": ["global", "reasoning"],
    "ToolNode": ["global", "tool_calling", "domain/mcp_integration", "domain/image_generation"],
    "ThinkNode": ["global", "reasoning"],
    "AnswerNode": ["global"],
    "SupervisorNode": ["global", "reasoning"],
    "EmbedNode": ["global", "memory_management"],
}


class RulesEngine:
    """行为规则引擎"""

    def __init__(self):
        self._cache: Dict[str, str] = {}  # 规则缓存

    def load_rules_for_node(self, node_name: str) -> str:
        """
        加载指定节点的规则

        Args:
            node_name: 节点类名（如 "ToolNode"）

        Returns:
            格式化的规则文本
        """
        rule_files = RULES_MAPPING.get(node_name, ["global"])

        rules_content = []
        for rule_file in rule_files:
            content = self._load_rule_file(rule_file)
            if content:
                rules_content.append(content)

        if not rules_content:
            return ""

        # 格式化规则
        formatted = "\n\n".join([
            "=" * 60,
            "📋 BEHAVIOR RULES (行为准则)",
            "=" * 60,
            "\n\n".join(rules_content),
            "=" * 60,
        ])

        return formatted

    def _load_rule_file(self, rule_file: str) -> Optional[str]:
        """
        加载单个规则文件（带缓存）

        Args:
            rule_file: 规则文件名（相对于 rules/ 目录）

        Returns:
            规则内容，如果文件不存在则返回 None
        """
        # 检查缓存
        if rule_file in self._cache:
            return self._cache[rule_file]

        # 构建文件路径
        file_path = RULES_DIR / f"{rule_file}.md" if not rule_file.endswith('.md') else RULES_DIR / rule_file

        # 读取文件
        if not file_path.exists():
            print(f"[WARN] Rule file not found: {file_path}")
            return None

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()

            # 缓存
            self._cache[rule_file] = content
            return content

        except Exception as e:
            print(f"[ERROR] Failed to load rule file {file_path}: {e}")
            return None

    def reload(self):
        """清除缓存，重新加载所有规则"""
        self._cache.clear()

    def inject_rules_to_prompt(self, prompt: str, rules: str) -> str:
        """
        将规则注入到 prompt

        Args:
            prompt: 原始 prompt
            rules: 规则文本

        Returns:
            注入规则后的 prompt
        """
        if not rules:
            return prompt

        # 在 prompt 前注入规则
        return f"{rules}\n\n{prompt}"


# 全局单例
_rules_engine: Optional[RulesEngine] = None

def get_rules_engine() -> RulesEngine:
    """获取规则引擎单例"""
    global _rules_engine
    if _rules_engine is None:
        _rules_engine = RulesEngine()
    return _rules_engine
```

#### 2. 节点集成（修改 `nodes.py`）

在每个节点的 `prep_async` 方法中加载规则：

```python
from rules_engine import get_rules_engine

class ToolNode(AsyncNode):
    """工具执行节点"""

    async def prep_async(self, shared):
        """准备阶段：加载规则和构建 prompt"""
        # 加载行为规则
        rules_engine = get_rules_engine()
        rules = rules_engine.load_rules_for_node("ToolNode")

        # 构建 prompt（包含规则）
        base_prompt = """你是一个工具执行专家..."""

        # 注入规则
        full_prompt = rules_engine.inject_rules_to_prompt(base_prompt, rules)

        return {
            "prompt": full_prompt,
            "tool_name": shared.get("selected_tool"),
            # ...
        }

    async def exec_async(self, prep_res):
        """执行工具调用"""
        # ... 原有逻辑
```

---

## 规则文件格式规范

### 基本格式

所有规则文件使用 **Markdown** 格式，结构如下：

```markdown
# 规则类别名称

## 优先级：HIGH / MEDIUM / LOW

## 适用场景
描述此规则适用的场景和条件

## 规则列表

### 1. 规则名称

**要求**：MUST / SHOULD / MAY
**描述**：规则的详细说明
**示例**：（可选）示例代码或场景

---

### 2. 第二条规则

...
```

### 字段说明

| 字段 | 说明 | 示例 |
|------|------|------|
| **优先级** | 规则重要性 | HIGH, MEDIUM, LOW |
| **要求级别** | 强制程度 | MUST（必须）, SHOULD（应该）, MAY（可以） |
| **适用场景** | 何时应用此规则 | "当调用图片生成工具时" |
| **描述** | 规则的详细说明 | "始终使用 URL 格式返回图片" |
| **示例** | 示例代码或场景 | `response_format="url"` |

### 规则编号规范

- 使用层级编号：`1.`, `1.1`, `1.1.1`
- 全局规则：`G-01`, `G-02`
- 领域规则：`TOOL-01`, `MEMORY-01`

---

## 配置项说明

### 规则引擎配置

在 `nodes.py` 或单独的 `config.py` 中：

```python
# ============================================================================
# 规则引擎配置
# ============================================================================

# 是否启用规则系统
ENABLE_RULES_SYSTEM = True

# 规则注入模式："system" (system prompt) 或 "user" (user prompt)
RULES_INJECTION_MODE = "user"

# 是否缓存规则内容（提升性能）
RULES_CACHE_ENABLED = True

# 规则文件热加载（开发模式下使用，生产环境关闭）
RULES_HOT_RELOAD = False

# 规则验证模式（实验性功能）
RULES_VALIDATION_ENABLED = False
```

### 节点规则映射配置

在 `rules_engine.py` 中：

```python
RULES_MAPPING = {
    "InputNode": ["global"],
    "PlanningNode": ["global", "planning"],
    "DecideNode": ["global", "reasoning"],
    "ToolNode": ["global", "tool_calling", "domain/mcp_integration"],
    # ... 按需扩展
}
```

---

## 使用示例

### 示例 1：全局规则文件

**文件路径**：`rules/global.md`

```markdown
# 全局行为规则

## 优先级：HIGH

## 适用场景
所有节点，所有操作

## 规则列表

### G-01: 上下文窗口管理

**要求**：MUST
**描述**：始终遵守上下文窗口大小限制，保留最近 5 步操作记录
**配置**：`CONTEXT_WINDOW_SIZE = 5`

---

### G-02: 错误处理

**要求**：MUST
**描述**：遇到错误时，必须将错误信息记录到 findings.md，避免重复相同错误

**步骤**：
1. 捕获异常详细信息
2. 分析根本原因
3. 记录到 findings.md（critical 级别）
4. 提供用户友好的错误提示

---

### G-03: 输出格式

**要求**：SHOULD
**描述**：所有输出应使用 Markdown 格式，结构清晰

**示例**：
```markdown
## 分析结果

- 发现问题：XXX
- 建议方案：YYY
```

---

### G-04: 中文优先

**要求**：SHOULD
**描述**：所有用户可见的输出应使用中文（除非用户明确要求英文）

---
```

### 示例 2：工具调用规则

**文件路径**：`rules/tool_calling.md`

```markdown
# 工具调用规则

## 优先级：HIGH

## 适用场景
ToolNode 执行工具调用时

## 规则列表

### TOOL-01: 图片生成格式优先级

**要求**：MUST
**描述**：调用图片生成工具时，始终使用 URL 格式返回，避免 Base64 截断

**参数设置**：
- `response_format="url"` ✅ 优先使用
- `response_format="b64_json"` ❌ 仅在 URL 不可用时使用

**原因**：
- Base64 编码图片占用大量字符（> 100,000）
- 容易被 `MAX_TOOL_RESULT_LENGTH` 截断
- URL 格式更简洁高效

**示例**：
```python
# ✅ 正确
submit_generate_image(
    prompt="一只可爱的猫",
    response_format="url"  # 使用 URL
)

# ❌ 错误
submit_generate_image(
    prompt="一只可爱的猫",
    response_format="b64_json"  # 避免使用
)
```

---

### TOOL-02: 异步工具优先

**要求**：SHOULD
**描述**：对于耗时操作（如图片生成），优先使用异步工具避免超时

**异步工具列表**：
- `submit_generate_image` + `get_task_result`
- `submit_edit_image` + `get_task_result`

**同步工具**（仅用于快速操作）：
- `generate_image`（已弃用）
- `edit_image`（已弃用）

**流程**：
1. 调用 `submit_xxx` 提交任务，获取 `task_id`
2. 等待 5-10 秒
3. 调用 `get_task_result(task_id)` 查询结果
4. 如果未完成，继续等待并重试

---

### TOOL-03: 工具结果长度限制

**要求**：MUST
**描述**：注意工具返回结果的长度限制

**当前限制**：
- `MAX_TOOL_RESULT_LENGTH = 100,000` 字符

**处理策略**：
- 如果结果过长，要求工具返回摘要或 URL
- 对于大文件（如图片、视频），使用 URL 而非内容

---

### TOOL-04: MCP 工具调用规范

**要求**：MUST
**描述**：调用 MCP 工具时，严格遵守工具的参数规范

**检查清单**：
- ✅ 必填参数是否提供
- ✅ 参数类型是否正确（string, number, boolean）
- ✅ 枚举值是否在允许范围内
- ✅ 参数格式是否符合要求（如 URL, file path）

**错误示例**：
```python
# ❌ 错误：缺少必填参数 prompt
generate_image(size="1024x1024")

# ✅ 正确
generate_image(prompt="一只猫", size="1024x1024")
```

---
```

### 示例 3：推理规则

**文件路径**：`rules/reasoning.md`

```markdown
# 推理规则

## 优先级：HIGH

## 适用场景
ThinkNode, DecideNode 进行推理和决策时

## 规则列表

### REASON-01: 思维链（Chain of Thought）

**要求**：SHOULD
**描述**：复杂问题必须使用思维链推理，逐步分解

**步骤**：
1. 理解问题
2. 识别关键要素
3. 分解子问题
4. 逐步推理
5. 综合结论

**示例**：
```markdown
## 问题分析

1. 用户需求：生成一张图片并保存
2. 分解任务：
   - 调用图片生成工具
   - 获取图片 URL
   - 下载图片到本地
   - 保存文件
3. 工具选择：
   - submit_generate_image（异步生成）
   - get_task_result（获取结果）
   - （需要文件下载工具，待确认）
4. 结论：需要先确认是否有文件下载工具
```

---

### REASON-02: 记忆检索利用

**要求**：SHOULD
**描述**：决策前检查相关历史记忆，避免重复错误

**检查项**：
- 是否有相似任务的历史记录？
- 之前遇到过类似错误吗？
- 有最佳实践可以借鉴吗？

**利用方式**：
- 如果找到相关记忆，优先参考
- 如果发现错误记录，避免重复

---

### REASON-03: 计划重读

**要求**：MUST
**描述**：每次决策前必须重读 task_plan.md，确保符合总体计划

**Manus-style 注意力操纵**：
- 决策前读取 task_plan.md
- 检查当前步骤是否在计划中
- 确认计划完成度

---

### REASON-04: 不确定性处理

**要求**：MUST
**描述**：当存在不确定性时，必须明确说明并提供选项

**处理方式**：
- 列出所有可能选项
- 说明每个选项的优缺点
- 提供推荐方案（标注为 "推荐"）
- 询问用户偏好

**示例**：
```markdown
## 方案选择

存在两种方案：

### 方案 A：使用 URL 格式（推荐）
- 优点：简洁高效，不会截断
- 缺点：需要网络访问

### 方案 B：使用 Base64 格式
- 优点：自包含，离线可用
- 缺点：可能被截断（超过 100,000 字符）

**推荐**：使用方案 A
```

---
```

### 示例 4：记忆管理规则

**文件路径**：`rules/memory_management.md`

```markdown
# 记忆管理规则

## 优先级：MEDIUM

## 适用场景
RetrieveNode（记忆检索）和 EmbedNode（记忆存储）

## 规则列表

### MEMORY-01: 相似度阈值

**要求**：MUST
**描述**：严格遵守相似度阈值设定

**阈值配置**：
- `MEMORY_SIMILARITY_THRESHOLD = 0.65` - 检索过滤阈值
- `MEMORY_DEDUP_THRESHOLD = 0.85` - 去重阈值

**规则**：
- 相似度 >= 0.65：认为相关，返回给决策节点
- 相似度 >= 0.85：认为重复，更新而非新增
- 相似度 < 0.65：不相关，过滤掉

---

### MEMORY-02: 记忆分层

**要求**：SHOULD
**描述**：根据重要性分层存储记忆

**分层标准**：
- **critical**（关键发现）：重大错误、关键决策、重要结论
  - 保留长度：1000 字符
  - 优先级：最高

- **important**（重要发现）：有价值的观察、次要结论
  - 保留长度：500 字符
  - 优先级：中等

- **normal**（普通发现）：一般信息、临时记录
  - 保留长度：200 字符
  - 优先级：普通

**存储策略**：
- 超过长度限制时，保留关键信息，截断次要内容
- 使用摘要技术（可选）

---

### MEMORY-03: 记忆更新策略

**要求**：MUST
**描述**：发现重复记忆时，使用更新而非新增

**更新条件**：
- 相似度 >= 0.85

**更新内容**：
- 合并新旧信息
- 更新时间戳
- 增加出现次数（频率）

**示例**：
```python
# 旧记忆
{
    "content": "图片生成使用 URL 格式",
    "timestamp": "2024-01-20",
    "frequency": 1
}

# 新记忆（相似度 0.90）
{
    "content": "图片生成务必使用 response_format='url'",
    "timestamp": "2024-01-23"
}

# 合并后
{
    "content": "图片生成务必使用 response_format='url'，避免 Base64 截断",
    "timestamp": "2024-01-23",  # 更新为最新
    "frequency": 2  # 增加频率
}
```

---

### MEMORY-04: 记忆检索数量

**要求**：SHOULD
**描述**：控制检索数量，避免上下文过载

**配置**：
- `MEMORY_RETRIEVE_K = 2` - 每次最多检索 2 条相关记忆

**调整建议**：
- 简单任务：K=1
- 复杂任务：K=3
- 避免 K > 5（会稀释注意力）

---
```

---

## 代码集成指南

### 步骤 1：创建规则引擎模块

创建 `rules_engine.py`，参考前面的"核心代码结构"部分。

### 步骤 2：创建规则文件

在 `rules/` 目录下创建规则文件：

```bash
mkdir rules
mkdir rules/domain

# 创建基础规则文件
touch rules/global.md
touch rules/tool_calling.md
touch rules/reasoning.md
touch rules/planning.md
touch rules/memory_management.md

# 创建领域规则
touch rules/domain/image_generation.md
touch rules/domain/mcp_integration.md
touch rules/domain/error_handling.md
```

### 步骤 3：修改节点代码

在 `nodes.py` 中，为需要规则的节点添加规则加载逻辑：

```python
from rules_engine import get_rules_engine

class DecideNode(AsyncNode):
    """决策节点"""

    async def prep_async(self, shared):
        """准备阶段：加载规则"""
        # 加载行为规则
        rules_engine = get_rules_engine()
        rules = rules_engine.load_rules_for_node("DecideNode")

        # 原有逻辑...
        context = self._build_context(shared)

        # 构建 prompt（包含规则）
        base_prompt = f"""你是一个任务决策专家...

当前上下文：
{context}

请决策下一步行动。
"""

        # 注入规则
        full_prompt = rules_engine.inject_rules_to_prompt(base_prompt, rules)

        return {
            "prompt": full_prompt,
            # ...
        }
```

### 步骤 4：配置规则映射

在 `rules_engine.py` 中配置 `RULES_MAPPING`：

```python
RULES_MAPPING = {
    "ToolNode": ["global", "tool_calling", "domain/mcp_integration"],
    "DecideNode": ["global", "reasoning"],
    # ... 其他节点
}
```

### 步骤 5：测试验证

```python
# 测试规则加载
from rules_engine import get_rules_engine

engine = get_rules_engine()
rules = engine.load_rules_for_node("ToolNode")
print(rules)
```

### 步骤 6：渐进式部署

**阶段 1**：先为关键节点添加规则（ToolNode, DecideNode）
**阶段 2**：观察效果，调整规则内容
**阶段 3**：扩展到其他节点
**阶段 4**：添加领域规则

---

## 最佳实践

### 1. 规则编写原则

✅ **DO（推荐做法）**：
- 使用清晰的祈使句（"必须"、"应该"、"可以"）
- 提供具体示例
- 说明规则背后的原因
- 使用分层编号
- 保持规则原子性（一条规则只做一件事）

❌ **DON'T（避免做法）**：
- 规则模糊不清（"尽量"、"最好"）
- 规则冲突
- 规则过于复杂
- 缺少上下文说明

### 2. 规则优先级管理

| 优先级 | 含义 | 示例 |
|-------|------|------|
| **HIGH** | 必须遵守 | 安全规则、数据完整性规则 |
| **MEDIUM** | 应该遵守 | 性能优化、最佳实践 |
| **LOW** | 可选建议 | 代码风格、命名规范 |

### 3. 规则冲突处理

**规则优先级**：
1. 领域规则 > 全局规则
2. 节点规则 > 通用规则
3. 新规则 > 旧规则（注释旧规则）

**冲突示例**：
```markdown
# 全局规则：使用中文输出
# 领域规则（MCP 工具）：工具参数使用英文

# 解决方案：明确场景
- 用户可见内容：中文
- 工具参数、代码：英文
```

### 4. 规则维护

**定期审查**（每月）：
- 移除过时规则
- 合并重复规则
- 更新示例代码
- 补充新发现的最佳实践

**版本控制**：
- 规则文件使用 Git 管理
- 重大修改记录 changelog
- 标注修改原因和日期

### 5. 规则测试

**验证方法**：
- 手动测试：观察 LLM 是否遵守规则
- 自动化测试：检查输出是否符合规则约束
- A/B 测试：对比有/无规则的效果差异

**测试示例**：
```python
# 测试规则：图片生成必须使用 URL 格式
def test_image_generation_uses_url():
    result = call_tool("generate_image", {
        "prompt": "一只猫"
    })

    # 验证返回参数
    assert result["metadata"]["format"] == "url"
    assert "url" in result["images"][0]
    assert "b64_json" not in result["images"][0]
```

---

## 测试方案

### 单元测试

```python
# tests/test_rules_engine.py

import pytest
from rules_engine import RulesEngine

def test_load_global_rules():
    """测试加载全局规则"""
    engine = RulesEngine()
    rules = engine.load_rules_for_node("InputNode")

    assert rules is not None
    assert "BEHAVIOR RULES" in rules
    assert "全局" in rules or "global" in rules.lower()

def test_load_tool_rules():
    """测试加载工具调用规则"""
    engine = RulesEngine()
    rules = engine.load_rules_for_node("ToolNode")

    assert "工具调用" in rules or "tool" in rules.lower()
    assert "response_format" in rules.lower()

def test_rules_caching():
    """测试规则缓存"""
    engine = RulesEngine()

    # 第一次加载
    rules1 = engine.load_rules_for_node("ToolNode")

    # 第二次加载（应从缓存读取）
    rules2 = engine.load_rules_for_node("ToolNode")

    assert rules1 == rules2
    assert len(engine._cache) > 0

def test_reload_rules():
    """测试重新加载"""
    engine = RulesEngine()

    # 加载规则
    engine.load_rules_for_node("ToolNode")
    assert len(engine._cache) > 0

    # 重新加载
    engine.reload()
    assert len(engine._cache) == 0
```

### 集成测试

```python
# tests/test_rules_integration.py

import pytest
from nodes import ToolNode
from rules_engine import get_rules_engine

@pytest.mark.asyncio
async def test_tool_node_with_rules():
    """测试 ToolNode 集成规则系统"""
    node = ToolNode()
    shared = {
        "selected_tool": "generate_image",
        "tool_args": {"prompt": "一只猫"}
    }

    # 调用 prep_async
    prep_res = await node.prep_async(shared)

    # 验证规则已加载
    assert "prompt" in prep_res
    assert "BEHAVIOR RULES" in prep_res["prompt"]
    assert "response_format" in prep_res["prompt"].lower()
```

### 行为验证测试

```python
# tests/test_rules_compliance.py

import pytest
from main import main_async

@pytest.mark.asyncio
async def test_image_generation_compliance():
    """测试图片生成是否遵守规则"""
    # 模拟用户输入
    user_input = "请生成一张猫的图片"

    # 运行 Agent
    # （需要 mock LLM 响应）
    result = await run_agent_with_mock(user_input)

    # 验证是否遵守规则
    # TOOL-01: 使用 URL 格式
    assert "response_format" in result["tool_calls"][0]["args"]
    assert result["tool_calls"][0]["args"]["response_format"] == "url"
```

---

## 扩展建议

### 1. 规则条件激活

**目标**：根据上下文条件动态激活规则

**实现**：
```python
# 规则文件中定义条件
"""
## 条件
- 当 shared["task_type"] == "image_generation" 时激活
"""

# 规则选择器中解析条件
class RulesSelector:
    def filter_by_condition(self, rules, context):
        # 解析规则中的条件标记
        # 匹配 context 激活规则
        pass
```

### 2. 规则验证器

**目标**：自动验证 LLM 输出是否遵守规则

**实现**：
```python
class RulesValidator:
    def validate(self, output: str, rules: List[str]) -> List[str]:
        """
        验证输出是否符合规则

        Returns:
            违反的规则列表
        """
        violations = []

        # 使用 LLM 或正则表达式验证
        # 例如：检查是否使用了 response_format="url"

        return violations
```

### 3. 规则学习和优化

**目标**：根据历史执行结果优化规则

**实现**：
- 记录规则执行效果（成功/失败）
- 分析哪些规则被频繁违反
- 调整规则表述或优先级
- A/B 测试不同规则版本

### 4. 可视化规则管理

**目标**：提供 Web UI 管理规则

**功能**：
- 查看所有规则
- 在线编辑规则
- 规则版本对比
- 规则生效统计

### 5. 多语言规则支持

**目标**：支持中英文规则

**实现**：
```
rules/
  ├── zh/  # 中文规则
  │   ├── global.md
  │   └── tool_calling.md
  └── en/  # 英文规则
      ├── global.md
      └── tool_calling.md
```

---

## FAQ

### Q1: 规则是否会增加 Token 消耗？

**A**: 会，但影响可控。

- 单个规则文件通常 500-1000 tokens
- 每个节点加载 2-3 个规则文件 ≈ 1500-3000 tokens
- 相比总 prompt（通常 5000-10000 tokens），增加约 20-30%

**优化建议**：
- 精简规则表述
- 只加载必要规则
- 使用摘要版规则（生产环境）

### Q2: 规则修改后是否需要重启？

**A**: 取决于配置。

- `RULES_CACHE_ENABLED = True`：需要重启或调用 `reload()`
- `RULES_HOT_RELOAD = True`：每次自动重新加载（开发模式）

**推荐**：
- 开发环境：启用热加载
- 生产环境：关闭热加载，使用缓存

### Q3: 如何处理规则冲突？

**A**: 使用优先级和场景限定。

**示例**：
```markdown
# 全局规则（优先级 LOW）
使用中文输出

# 工具调用规则（优先级 HIGH）
工具参数使用英文

# 实际应用：
# - 用户消息：中文
# - 工具参数：英文
```

### Q4: 规则能否保证 LLM 100% 遵守？

**A**: 不能保证，但能显著提升一致性。

**原因**：
- LLM 可能"忘记"规则
- 复杂场景下规则可能冲突
- LLM 理解可能有偏差

**缓解措施**：
- 规则表述清晰明确
- 使用示例强化理解
- 关键规则多次重复
- 启用规则验证器（可选）

### Q5: 规则系统是否影响性能？

**A**: 影响极小（< 50ms）。

**性能分析**：
- 文件读取：< 10ms（有缓存后接近 0）
- 字符串拼接：< 1ms
- 总开销：< 50ms

**建议**：
- 启用缓存
- 避免在循环中加载规则

---

## 附录

### A. 规则模板

#### 全局规则模板

```markdown
# 全局行为规则

## 优先级：HIGH

## 适用场景
所有节点，所有操作

## 规则列表

### G-XX: 规则名称

**要求**：MUST / SHOULD / MAY
**描述**：规则的详细说明
**示例**：（可选）示例代码或场景

---
```

#### 领域规则模板

```markdown
# XXX 领域规则

## 优先级：MEDIUM

## 适用场景
描述适用的节点和场景

## 规则列表

### DOMAIN-XX: 规则名称

**要求**：MUST / SHOULD / MAY
**描述**：规则的详细说明
**原因**：为什么需要这个规则
**示例**：

```python
# ✅ 正确示例
...

# ❌ 错误示例
...
```

---
```

### B. 实现清单

- [ ] 创建 `rules/` 目录
- [ ] 创建 `rules_engine.py` 模块
- [ ] 编写全局规则 `rules/global.md`
- [ ] 编写工具调用规则 `rules/tool_calling.md`
- [ ] 编写推理规则 `rules/reasoning.md`
- [ ] 编写记忆管理规则 `rules/memory_management.md`
- [ ] 编写领域规则（按需）
- [ ] 修改 `nodes.py` 集成规则引擎
- [ ] 配置 `RULES_MAPPING`
- [ ] 编写单元测试
- [ ] 编写集成测试
- [ ] 性能测试和优化
- [ ] 文档更新（README.md）

### C. 参考资料

- [Manus Planning](https://github.com/example/manus) - 三文件模式灵感来源
- [LangChain Prompt Templates](https://python.langchain.com/docs/modules/model_io/prompts/) - Prompt 管理
- [RFC 2119: Key words for RFCs](https://www.ietf.org/rfc/rfc2119.txt) - MUST/SHOULD/MAY 规范

---

## 变更日志

| 版本 | 日期 | 变更说明 | 作者 |
|------|------|---------|------|
| v1.0 | 2024-01-23 | 初始版本，完整设计文档 | AI Assistant |

---

**文档结束**
