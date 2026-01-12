# Supervisor 模式实现记录

## 修改日期
2025-01-12

## 修改概述
为 PocketAgent 添加 Supervisor 模式，在 AnswerNode 生成答案后进行质量验证。

## 架构变更

### 修改前
```
InputNode → RetrieveNode → DecideNode ─┬─→ ToolNode  ──┐
                              ↑        ├─→ ThinkNode ──┤
                              │        └─→ AnswerNode ─┼→ EmbedNode → InputNode
                              └────────────────────────┘
```

### 修改后
```
InputNode → RetrieveNode → DecideNode ─┬─→ ToolNode  ──┐
                              ↑        ├─→ ThinkNode ──┤
                              │        └─→ AnswerNode ─┼→ SupervisorNode
                              │                                    │
                              │        ┌───────────────────────────┤
                              │        ↓ (retry)                   ↓ (approve)
                              └────────┘                      EmbedNode → InputNode
```

## 文件修改清单

### 1. nodes.py

#### 添加的代码

**Action 类新增常量** (约第36行后):
```python
SUPERVISOR = "supervisor"
```

**新增配置常量** (约第100行后):
```python
# Supervisor 最大重试次数
SUPERVISOR_MAX_RETRIES = 2

# Supervisor 答案质量检查提示
SUPERVISOR_CHECK_PROMPT = """..."""
```

**新增 SupervisorNode 类** (约第770行后):
```python
class SupervisorNode(AsyncNode):
    """答案质量监督节点"""
    ...
```

#### 修改的代码

**AnswerNode.post_async** 返回值变更:
- 修改前: `return Action.EMBED`
- 修改后: `return Action.SUPERVISOR`

### 2. main.py

#### 添加的导入
```python
from nodes import SupervisorNode
```

#### 添加的节点实例
```python
supervisor_node = SupervisorNode()
```

#### 添加的流程连接
```python
# AnswerNode 完成后进入 SupervisorNode 验证
answer_node - "supervisor" >> supervisor_node

# SupervisorNode 验证通过进入 EmbedNode
supervisor_node - "embed" >> embed_node

# SupervisorNode 验证失败返回 DecideNode 重试
supervisor_node - "decide" >> decide_node
```

#### 删除的流程连接
```python
# 原: answer_node - "embed" >> embed_node
```

## 回滚步骤

### 方法1: Git 回滚 (推荐)
```bash
cd E:/AI/my-pocketflow
git log --oneline -5  # 查看提交历史
git revert <commit-hash>  # 回滚指定提交
# 或
git reset --hard <commit-hash>  # 强制回滚到指定提交
```

### 方法2: 手动回滚

#### 步骤1: 还原 nodes.py

1. 删除 `Action.SUPERVISOR = "supervisor"` 行
2. 删除 `SUPERVISOR_MAX_RETRIES` 和 `SUPERVISOR_CHECK_PROMPT` 常量
3. 删除整个 `SupervisorNode` 类
4. 将 `AnswerNode.post_async` 的返回值从 `Action.SUPERVISOR` 改回 `Action.EMBED`

#### 步骤2: 还原 main.py

1. 删除 `from nodes import SupervisorNode` 中的 `SupervisorNode`
2. 删除 `supervisor_node = SupervisorNode()` 行
3. 删除以下连接:
   - `answer_node - "supervisor" >> supervisor_node`
   - `supervisor_node - "embed" >> embed_node`
   - `supervisor_node - "decide" >> decide_node`
4. 恢复: `answer_node - "embed" >> embed_node`

## 新增功能说明

### SupervisorNode 检查项
1. 答案长度 >= 20 字符
2. 不包含拒绝性关键词 (sorry, cannot, unable 等)
3. 不包含错误标记 (error, failed 等)
4. 可选: LLM 评估答案质量和相关性

### 重试机制
- 最大重试次数: 2 次 (SUPERVISOR_MAX_RETRIES)
- 超过重试次数强制通过，避免死循环
- 重试时会在 context 中添加拒绝原因提示
