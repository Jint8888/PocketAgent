# 行为规则系统

## 目录结构

```
rules/
├── README.md        # 本文件
└── global.md        # 全局行为规则（第一步实施）
```

## 规则文件说明

### global.md
全局行为规则，适用于所有节点的通用准则。

**当前版本**：v1.0（基础版）
**加载节点**：所有节点

## 使用方式

规则文件由 `rules_engine.py` 自动加载，并注入到节点的 prompt 中。

## 规则编写规范

- 使用 Markdown 格式
- 使用清晰的祈使句（MUST, SHOULD, MAY）
- 提供具体示例
- 说明规则原因

## 后续扩展

未来将添加更多专项规则：
- `tool_calling.md` - 工具调用规则
- `reasoning.md` - 推理规则
- `memory_management.md` - 记忆管理规则
