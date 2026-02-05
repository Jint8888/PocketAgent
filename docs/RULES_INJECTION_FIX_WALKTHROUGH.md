# 规则注入修复 Walkthrough

> **日期**: 2026-01-24
> **问题**: 全局规则 (global.md) 未被注入到 LLM 决策上下文

## 问题描述

用户将 Moji 天气 cityID 获取流程作为规则添加到 `rules/global.md`，但 Agent 在执行时仍然反复使用网络搜索而非读取本地 Excel 文件。

## 根因分析

| 组件 | 现状 | 问题 |
|------|------|------|
| `ToolNode` | 加载规则到 `shared["behavior_rules"]` | 时机太晚，决策已完成 |
| `DecideNode` | 构建 LLM prompt | ❌ 未使用 `behavior_rules` |

## 修复方案

### 1. 在 DecideNode 中加载规则

```python
# nodes.py - DecideNode.prep_async()
behavior_rules = shared.get("behavior_rules", "")
if not behavior_rules:
    from rules_engine import load_rules
    behavior_rules = load_rules()
    if behavior_rules:
        shared["behavior_rules"] = behavior_rules
```

### 2. 注入规则到 LLM 上下文

```python
# 行为规则放在第三位（确保 LLM 遵循规则）
if behavior_rules:
    rules_summary = self._extract_key_rules(behavior_rules)
    if rules_summary:
        full_context += f"### Behavior Rules (MUST FOLLOW)\n{rules_summary}\n\n"
```

### 3. 新增关键规则提取方法

`_extract_key_rules()` 方法只提取工具相关规则（G-05, G-11 等），避免 token 过大。

## 修改文件

- [nodes.py](file:///e:/AI/my-pocketflow/nodes.py) - DecideNode 类
  - `prep_async()`: 添加规则加载和注入逻辑
  - `_extract_key_rules()`: 新增方法提取关键规则

- [mcp_client/manager.py](file:///e:/AI/my-pocketflow/mcp_client/manager.py)
  - `format_tools_for_prompt()`: 保留参数默认值（如 token=xxx）
  - 修复工具格式化过于激进导致 LLM 看不到默认值的问题

- [rules/global.md](file:///e:/AI/my-pocketflow/rules/global.md)
  - 新增 G-11: Moji天气工具使用规范
  - 包含 cityId 获取流程和 token 值

## 验证方法

1. 启动 Agent
2. 输入: "用 moji 工具查询上海的24小时天气预报"
3. 预期行为:
   - 日志显示 `[Decide] Behavior rules loaded`
   - Agent 调用 `excel_stdio` 读取城市ID
   - 使用正确的 cityId 调用 moji 天气工具
