# PocketAgent 改进开发计划

> **文档版本**: v1.0
> **创建日期**: 2025-02-05
> **目标用户**: 开发者
> **优先级说明**: 🔴 HIGH | 🟡 MEDIUM | 🟢 LOW

---

## 概述

本文档是 PocketAgent 项目的**改进开发计划**，基于代码审查结果制定。通过本计划，您将：

✅ 了解当前项目存在的改进空间
✅ 掌握每个改进项的具体实施步骤
✅ 理解改进的优先级和依赖关系
✅ 获得可量化的验收标准

---

## 目录

1. [改进概览](#改进概览)
2. [Phase 1: 代码模块化重构](#phase-1-代码模块化重构)
3. [Phase 2: 测试覆盖增强](#phase-2-测试覆盖增强)
4. [Phase 3: 代码质量优化](#phase-3-代码质量优化)
5. [Phase 4: 文档完善](#phase-4-文档完善)
6. [实施时间线](#实施时间线)
7. [风险评估](#风险评估)

---

## 改进概览

| 编号 | 改进项 | 优先级 | 复杂度 | 影响范围 |
|------|--------|--------|--------|----------|
| 1.1 | 拆分 nodes.py 大文件 | 🟡 MEDIUM | 高 | 核心模块 |
| 1.2 | 拆分 mcp_client/manager.py | 🟡 MEDIUM | 中 | MCP 模块 |
| 2.1 | 增加单元测试覆盖 | 🟡 MEDIUM | 中 | 全局 |
| 2.2 | 增加集成测试 | 🟢 LOW | 高 | 全局 |
| 3.1 | 统一错误处理模式 | 🟢 LOW | 低 | 全局 |
| 3.2 | 类型注解完善 | 🟢 LOW | 低 | 全局 |
| 4.1 | API 文档生成 | 🟢 LOW | 低 | 文档 |

---

## Phase 1: 代码模块化重构

### 1.1 拆分 nodes.py (103KB)

**问题描述**：
`nodes.py` 文件包含所有工作流节点实现，文件过大（103KB），违反单一职责原则，不利于维护和测试。

**目标**：
将单一大文件拆分为按职责划分的多个模块，每个文件控制在 400 行以内。

**实施步骤**：

```
Step 1: 创建 nodes/ 目录结构
────────────────────────────
nodes/
├── __init__.py          # 导出所有节点类
├── base.py              # 基础节点类和共享工具
├── input_node.py        # InputNode
├── retrieve_node.py     # RetrieveNode
├── decide_node.py       # DecideNode
├── tool_node.py         # ToolNode
├── think_node.py        # ThinkNode
├── answer_node.py       # AnswerNode
└── embed_node.py        # EmbedNode

Step 2: 迁移代码
────────────────
1. 识别各节点类的边界
2. 提取共享依赖到 base.py
3. 逐个迁移节点类到独立文件
4. 更新导入语句

Step 3: 更新引用
────────────────
1. 修改 main.py 的导入方式
2. 确保 from nodes import * 兼容性
3. 运行测试验证功能完整

Step 4: 清理
────────────
1. 删除原 nodes.py
2. 更新相关文档
```

**验收标准**：
- [ ] 每个节点文件 < 400 行
- [ ] 所有现有功能正常工作
- [ ] 导入方式向后兼容
- [ ] 通过所有现有测试

**兼容性保证**：
```python
# nodes/__init__.py
from .input_node import InputNode
from .retrieve_node import RetrieveNode
from .decide_node import DecideNode
from .tool_node import ToolNode
from .think_node import ThinkNode
from .answer_node import AnswerNode
from .embed_node import EmbedNode

__all__ = [
    "InputNode",
    "RetrieveNode",
    "DecideNode",
    "ToolNode",
    "ThinkNode",
    "AnswerNode",
    "EmbedNode",
]
```

---

### 1.2 拆分 mcp_client/manager.py (29KB)

**问题描述**：
`manager.py` 承担了多个职责：服务器连接管理、工具调用、会话管理，建议拆分。

**目标**：
按职责拆分为独立模块，提高可维护性。

**实施步骤**：

```
Step 1: 创建模块结构
────────────────────
mcp_client/
├── __init__.py          # 导出主要接口
├── manager.py           # MCPManager 主类（精简版）
├── connection.py        # 服务器连接管理
├── tools.py             # 工具调用逻辑
└── session.py           # 会话状态管理

Step 2: 职责划分
────────────────
- connection.py: 服务器发现、连接、断开、健康检查
- tools.py: 工具列表获取、工具调用、结果解析
- session.py: 会话创建、状态维护、上下文管理
- manager.py: 组合上述模块，提供统一接口

Step 3: 迁移和测试
─────────────────
1. 逐个模块迁移
2. 保持 MCPManager 接口不变
3. 增加模块级单元测试
```

**验收标准**：
- [ ] manager.py < 300 行
- [ ] 各模块职责单一
- [ ] MCPManager 公共接口不变
- [ ] MCP 工具调用功能正常

---

## Phase 2: 测试覆盖增强

### 2.1 增加单元测试覆盖

**问题描述**：
当前仅有 `test_rules.py`，核心模块缺少测试覆盖。

**目标**：
达到 80% 以上测试覆盖率。

**测试文件规划**：

```
tests/
├── __init__.py
├── conftest.py              # pytest 配置和共享 fixtures
├── test_rules.py            # 已有 - 规则引擎测试
├── test_memory.py           # 新增 - 向量记忆测试
├── test_utils.py            # 新增 - LLM 工具测试
├── test_nodes/              # 新增 - 节点测试
│   ├── test_input_node.py
│   ├── test_retrieve_node.py
│   ├── test_decide_node.py
│   ├── test_tool_node.py
│   ├── test_think_node.py
│   ├── test_answer_node.py
│   └── test_embed_node.py
└── test_mcp_client/         # 新增 - MCP 客户端测试
    ├── test_connection.py
    ├── test_tools.py
    └── test_session.py
```

**优先级排序**：

| 优先级 | 模块 | 原因 |
|--------|------|------|
| 1 | memory.py | 核心功能，向量计算逻辑复杂 |
| 2 | nodes/* | 业务核心，决策逻辑关键 |
| 3 | mcp_client/* | 外部依赖多，需 mock 测试 |
| 4 | utils.py | 相对简单，工具函数 |

**验收标准**：
- [ ] 测试覆盖率 ≥ 80%
- [ ] 所有测试通过 CI
- [ ] 关键路径 100% 覆盖

---

### 2.2 增加集成测试

**目标**：
验证完整工作流的端到端功能。

**测试场景**：

```python
# tests/integration/test_workflow.py

class TestAgentWorkflow:
    """端到端工作流测试"""

    async def test_simple_question_flow(self):
        """测试简单问答流程: Input → Decide → Answer"""
        pass

    async def test_tool_calling_flow(self):
        """测试工具调用流程: Input → Decide → Tool → Answer"""
        pass

    async def test_multi_step_reasoning(self):
        """测试多步推理: Input → Decide → Think → Tool → Answer"""
        pass

    async def test_memory_retrieval(self):
        """测试记忆检索: 验证历史对话影响当前回答"""
        pass
```

---

## Phase 3: 代码质量优化

### 3.1 统一错误处理模式

**目标**：
建立统一的异常处理和错误传播机制。

**实施方案**：

```python
# exceptions.py - 新增自定义异常模块

class PocketAgentError(Exception):
    """基础异常类"""
    pass

class MCPConnectionError(PocketAgentError):
    """MCP 连接错误"""
    pass

class ToolExecutionError(PocketAgentError):
    """工具执行错误"""
    pass

class MemoryError(PocketAgentError):
    """记忆系统错误"""
    pass

class LLMAPIError(PocketAgentError):
    """LLM API 调用错误"""
    pass
```

**错误处理规范**：
1. 所有模块使用自定义异常
2. 异常信息包含上下文
3. 日志记录错误详情
4. 向上层传播时包装异常

---

### 3.2 类型注解完善

**目标**：
所有公共接口添加完整类型注解，支持静态类型检查。

**实施步骤**：

```bash
# 1. 配置 mypy
pip install mypy

# 2. 添加 pyproject.toml 配置
[tool.mypy]
python_version = "3.12"
strict = true
ignore_missing_imports = true

# 3. 逐模块添加类型注解
# 4. 运行类型检查
mypy .
```

**示例改进**：

```python
# Before
def call_llm(prompt, model=None):
    ...

# After
from typing import Optional

def call_llm(
    prompt: str,
    model: Optional[str] = None
) -> dict[str, Any]:
    ...
```

---

## Phase 4: 文档完善

### 4.1 API 文档生成

**目标**：
使用 Sphinx 或 MkDocs 生成 API 参考文档。

**实施步骤**：

```bash
# 1. 安装 mkdocs
pip install mkdocs mkdocs-material mkdocstrings[python]

# 2. 初始化文档项目
mkdocs new .

# 3. 配置 mkdocs.yml
site_name: PocketAgent API Reference
theme:
  name: material

plugins:
  - mkdocstrings:
      handlers:
        python:
          paths: [.]

# 4. 添加 docstrings 到代码
# 5. 生成文档
mkdocs build
```

---

## 实施时间线

```
Week 1-2: Phase 1 - 代码模块化重构
├── Day 1-3: 分析 nodes.py 依赖关系
├── Day 4-7: 拆分 nodes.py
├── Day 8-10: 拆分 mcp_client/manager.py
└── Day 11-14: 测试验证和文档更新

Week 3-4: Phase 2 - 测试覆盖增强
├── Day 1-4: 配置测试框架，编写 fixtures
├── Day 5-8: memory.py 和 nodes 测试
├── Day 9-12: mcp_client 和 utils 测试
└── Day 13-14: 集成测试

Week 5: Phase 3 - 代码质量优化
├── Day 1-2: 异常处理统一
├── Day 3-4: 类型注解添加
└── Day 5: mypy 配置和检查

Week 6: Phase 4 - 文档完善
├── Day 1-2: MkDocs 配置
├── Day 3-4: Docstrings 补充
└── Day 5: 文档生成和部署
```

---

## 风险评估

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 模块拆分引入 bug | 中 | 高 | 增量迁移，每步测试验证 |
| 循环导入问题 | 中 | 中 | 仔细规划模块依赖，使用延迟导入 |
| 测试编写耗时超预期 | 高 | 低 | 优先核心路径，逐步提升覆盖率 |
| 类型注解与动态特性冲突 | 低 | 低 | 使用 typing.Any 和 type: ignore |

---

## 附录

### A. 相关文档

- [行为规则系统 Walkthrough](./BEHAVIOR_RULES_WALKTHROUGH.md)
- [日志系统演练](./LOGGING_WALKTHROUGH.md)
- [MCP Unicode 修复](./MCP_UNICODE_FIX_WALKTHROUGH.md)

### B. 参考资源

- [Python 项目结构最佳实践](https://docs.python-guide.org/writing/structure/)
- [pytest 文档](https://docs.pytest.org/)
- [mypy 文档](https://mypy.readthedocs.io/)
- [MkDocs Material 主题](https://squidfunk.github.io/mkdocs-material/)

---

> **维护说明**: 本文档应随项目进展持续更新，完成的改进项应标记为 ✅ 完成。
