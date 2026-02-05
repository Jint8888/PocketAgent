# 规则草稿功能 Walkthrough

> **文档版本**: v1.0
> **功能**: LLM 自动记录规则建议到草稿文件
> **创建日期**: 2024-01-23
> **目标用户**: 开发者和使用者

---

## 概述

规则草稿功能允许 **LLM 自动将规则建议写入草稿文件**，用户审查后手动复制到真实规则文件。

### 核心优势

✅ **安全性** - LLM 只写草稿，不影响真实规则
✅ **质量控制** - 用户人工审查，确保规则质量
✅ **知识积累** - 持续记录 LLM 的观察和建议
✅ **实施简单** - 使用现有的 filesystem 工具
✅ **零风险** - 草稿不会自动生效

---

## 目录

1. [快速开始](#快速开始)
2. [工作原理](#工作原理)
3. [文件结构](#文件结构)
4. [LLM 使用指南](#llm-使用指南)
5. [用户审查指南](#用户审查指南)
6. [实际使用示例](#实际使用示例)
7. [常见问题](#常见问题)
8. [最佳实践](#最佳实践)

---

## 快速开始

### 1. 验证目录结构

检查规则草稿目录是否已创建：

```bash
cd E:\AI\my-pocketflow

# 检查目录
dir sandbox\rules_draft

# 应该看到以下文件：
# README.md
# global_draft.md
# tool_calling_draft.md
# reasoning_draft.md
# memory_draft.md
# CHANGELOG.md
```

### 2. 测试 Agent 记录规则

启动 Agent 并触发规则建议：

```bash
python main.py
```

**测试对话**：

```
用户: "请生成一张猫的图片，使用 response_format='b64_json'"

Agent: [执行，发现 Base64 被截断]

用户: "这个问题很重要，帮我记录一条规则建议"

Agent:
[调用 filesystem 工具]
- read_file("sandbox/rules_draft/tool_calling_draft.md")
- write_file("sandbox/rules_draft/tool_calling_draft.md", ...)

"✅ 规则建议已记录到 sandbox/rules_draft/tool_calling_draft.md

   规则标题：图片生成必须使用 URL 格式
   类别：tool_calling
   要求级别：MUST

   请稍后审查此规则，如果有价值请手动复制到 rules/tool_calling.md"
```

### 3. 审查规则草稿

```bash
# 查看规则草稿
cat sandbox\rules_draft\tool_calling_draft.md

# 如果规则有价值，手动复制到真实规则文件
# (编辑 rules/tool_calling.md)
```

---

## 工作原理

### 架构流程图

```
┌─────────────────────────────────────────────────────────┐
│                    LLM Agent                             │
│                                                          │
│  1. 发现问题/最佳实践                                     │
│     ↓                                                    │
│  2. 判断是否需要记录规则                                  │
│     ↓                                                    │
│  3. 调用 filesystem 工具                                 │
│     - read_file("sandbox/rules_draft/xxx_draft.md")     │
│     - write_file("sandbox/rules_draft/xxx_draft.md")    │
│     ↓                                                    │
│  4. 追加规则草稿                                         │
│     ↓                                                    │
│  5. 更新 CHANGELOG.md                                    │
│     ↓                                                    │
│  6. 通知用户                                             │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
              ┌──────────────────────┐
              │  sandbox/rules_draft/ │
              │  ├── global_draft.md  │  ← 草稿文件
              │  ├── tool_calling_draft.md
              │  └── CHANGELOG.md     │
              └──────────────────────┘
                          │
                          │ 用户审查
                          ▼
              ┌──────────────────────┐
              │      rules/          │
              │  ├── global.md       │  ← 真实规则
              │  └── tool_calling.md │
              └──────────────────────┘
                          │
                          │ 生效
                          ▼
                    Agent 遵守规则
```

### 核心机制

1. **LLM 自主判断** - Agent 根据 AGENT_SYSTEM_PROMPT 中的指导判断何时记录规则
2. **Filesystem 工具** - 使用现有的 MCP filesystem 工具写入文件
3. **人工审查** - 用户定期查看草稿，手动复制有价值的规则
4. **完全隔离** - 草稿目录与真实规则目录分离，零风险

---

## 文件结构

### 目录树

```
my-pocketflow/
├── rules/                          # 真实规则（生效）
│   ├── README.md
│   └── global.md                   # 10 条全局规则
│
├── sandbox/
│   ├── rules_draft/                # ⭐ 规则草稿（LLM 写入）
│   │   ├── README.md               # 草稿目录说明
│   │   ├── global_draft.md         # 全局规则草稿
│   │   ├── tool_calling_draft.md   # 工具调用规则草稿
│   │   ├── reasoning_draft.md      # 推理规则草稿
│   │   ├── memory_draft.md         # 记忆管理规则草稿
│   │   └── CHANGELOG.md            # 变更日志
│   │
│   ├── task_plan.md                # Manus-style 规划文件
│   ├── findings.md
│   └── progress.md
│
└── rules_engine.py                 # 规则引擎
```

### 文件说明

| 文件 | 作用 | LLM 权限 | 用户权限 |
|------|------|---------|---------|
| `sandbox/rules_draft/*.md` | 规则草稿 | ✅ 读写 | ✅ 读写 |
| `rules/*.md` | 真实规则 | ❌ 只读 | ✅ 读写 |

---

## LLM 使用指南

### 何时建议规则

LLM 应该在以下情况下记录规则建议：

| 场景 | 示例 |
|------|------|
| **发现重复错误** | 同样的 Base64 截断错误出现 2 次 |
| **找到最佳实践** | 发现使用 URL 格式能避免问题 |
| **遇到边界情况** | 特殊参数组合导致的问题 |
| **总结经验教训** | 从失败任务中学到的经验 |
| **用户明确要求** | 用户说"记录这个规则" |

### 使用 Filesystem 工具记录

**完整流程示例**：

```yaml
# 步骤 1: 读取现有草稿
action: tool
reason: 读取工具调用规则草稿
tool_name: read_file
tool_params:
  path: "sandbox/rules_draft/tool_calling_draft.md"

# [LLM 收到文件内容]

# 步骤 2: 追加新规则
action: tool
reason: 记录规则建议 - 图片生成必须使用 URL 格式
tool_name: write_file
tool_params:
  path: "sandbox/rules_draft/tool_calling_draft.md"
  content: |
    [原有文件内容...]

    ## 📝 图片生成必须使用 URL 格式

    > **建议时间**: 2024-01-23 22:15:30
    > **要求级别**: MUST
    > **类别**: tool_calling

    **描述**:
    调用图片生成工具时，必须使用 response_format='url'，
    禁止使用 response_format='b64_json'。

    **原因**:
    1. Base64 编码图片超过 MAX_TOOL_RESULT_LENGTH (100,000 字符)
    2. 导致结果被截断，图片数据不完整
    3. URL 格式仅占几十字符，简洁高效

    **示例**:
    ```
    # ✅ 正确
    submit_generate_image(prompt="猫", response_format="url")

    # ❌ 错误
    submit_generate_image(prompt="猫", response_format="b64_json")
    ```

    **相关经验**:
    2024-01-23 用户请求生成图片，使用 b64_json 导致截断。
    切换为 URL 后成功。

    **状态**: ⏳ 待审查

    ---

# 步骤 3: 更新变更日志
action: tool
reason: 读取变更日志
tool_name: read_file
tool_params:
  path: "sandbox/rules_draft/CHANGELOG.md"

# 步骤 4: 追加日志
action: tool
reason: 记录到变更日志
tool_name: write_file
tool_params:
  path: "sandbox/rules_draft/CHANGELOG.md"
  content: |
    [原有内容...]
    - **2024-01-23 22:15** - [tool_calling] 图片生成必须使用 URL 格式

# 步骤 5: 通知用户
action: answer
reason: 告知用户规则已记录
answer: |
  ✅ 规则建议已记录

  **位置**: sandbox/rules_draft/tool_calling_draft.md
  **标题**: 图片生成必须使用 URL 格式
  **类别**: tool_calling
  **要求级别**: MUST

  此规则建议仅供参考，不会自动生效。
  请您稍后审查，如果认为有价值，请手动复制到 rules/tool_calling.md。
```

### 规则格式模板

```markdown
## 📝 [规则标题]

> **建议时间**: YYYY-MM-DD HH:MM:SS
> **要求级别**: MUST / SHOULD / MAY
> **类别**: global / tool_calling / reasoning / memory

**描述**:
[规则的详细描述，说明什么情况下应该怎么做]

**原因**:
[为什么需要这个规则？解决什么问题？]

**示例**（可选）:
```
[示例代码或场景]
```

**相关经验**:
[触发此规则建议的具体场景或错误]

**状态**: ⏳ 待审查

---
```

---

## 用户审查指南

### 定期审查

建议每周审查一次规则草稿：

```bash
# 1. 查看各个草稿文件
cat sandbox/rules_draft/global_draft.md
cat sandbox/rules_draft/tool_calling_draft.md
cat sandbox/rules_draft/reasoning_draft.md
cat sandbox/rules_draft/memory_draft.md

# 2. 查看变更日志（快速浏览）
cat sandbox/rules_draft/CHANGELOG.md
```

### 评估标准

审查每条规则时，问自己：

| 评估维度 | 问题 | 标准 |
|---------|------|------|
| **普遍性** | 适用于多个场景？ | ✅ 是 → 采纳 |
| **有效性** | 能避免问题？ | ✅ 是 → 采纳 |
| **清晰性** | 表述清晰明确？ | ✅ 是 → 采纳 |
| **优先级** | MUST/SHOULD/MAY 合理？ | ✅ 是 → 采纳 |
| **冲突性** | 与现有规则冲突？ | ❌ 是 → 拒绝 |

### 采纳规则流程

**步骤 1**: 打开草稿文件

```bash
cat sandbox/rules_draft/tool_calling_draft.md
```

**步骤 2**: 复制规则内容

```markdown
## 📝 图片生成必须使用 URL 格式

> **建议时间**: 2024-01-23 22:15:30
> **要求级别**: MUST
> **类别**: tool_calling

**描述**: ...
```

**步骤 3**: 编辑真实规则文件

```bash
# 如果 rules/tool_calling.md 不存在，先创建
# 如果已存在，直接编辑

vim rules/tool_calling.md
# 或使用任何文本编辑器
```

**步骤 4**: 粘贴并调整格式

```markdown
# 工具调用规则

## TOOL-01: 图片生成必须使用 URL 格式

**要求**: MUST
**描述**: 调用图片生成工具时，必须使用 response_format='url'

**原因**: ...

**示例**:
```python
# ✅ 正确
submit_generate_image(prompt="猫", response_format="url")
```
```

**步骤 5**: 保存文件

**步骤 6**: 重启 Agent 使规则生效

```bash
python main.py
```

**步骤 7**: 清理草稿

在草稿文件中标记为已采纳：

```markdown
**状态**: ✅ 已采纳（2024-01-23，编号 TOOL-01）
```

或直接删除该规则草稿。

---

## 实际使用示例

### 示例 1：自动发现错误并建议规则

**场景**: Agent 执行图片生成，发现 Base64 截断

```
用户: "请生成一张猫的图片"

Agent 内部推理:
"我将调用 submit_generate_image...
[执行工具，发现 Base64 被截断]

这是一个重要问题，我应该记录规则建议。"

Agent 执行:
1. read_file("sandbox/rules_draft/tool_calling_draft.md")
2. write_file(...) 追加规则
3. write_file("sandbox/rules_draft/CHANGELOG.md") 更新日志

Agent 回复:
"抱歉，图片生成遇到问题（Base64 截断）。

我已将此问题记录为规则建议：
📍 位置: sandbox/rules_draft/tool_calling_draft.md
📋 标题: 图片生成必须使用 URL 格式
⚠️  要求级别: MUST

让我使用正确的方法重新生成图片..."

[重新调用，使用 response_format="url"]
```

### 示例 2：用户主动要求建议规则

```
用户: "刚才的错误处理经验很重要，帮我记录一条规则"

Agent:
"好的，我将记录这条规则建议。

[分析刚才的错误处理经验]
[调用 filesystem 工具记录]

✅ 规则建议已记录

📍 位置: sandbox/rules_draft/global_draft.md
📋 标题: 错误必须记录到 findings.md
⚠️  要求级别: MUST
📝 描述: 遇到错误时，必须详细记录到 findings.md（critical 级别）

请您稍后审查此规则，如有价值请复制到 rules/global.md"
```

### 示例 3：用户审查并采纳规则

```bash
# 用户操作

# 1. 查看草稿
$ cat sandbox/rules_draft/tool_calling_draft.md

## 📝 图片生成必须使用 URL 格式
...
**状态**: ⏳ 待审查

# 2. 评估：这个规则很有价值，应该采纳

# 3. 创建真实规则文件（如果不存在）
$ vim rules/tool_calling.md

# 4. 粘贴规则内容并调整格式
# 工具调用规则

## TOOL-01: 图片生成必须使用 URL 格式
...

# 5. 保存并重启 Agent
$ python main.py

# 6. 验证规则是否生效
用户: "请生成图片"
Agent: [自动使用 response_format="url"]  ← 规则生效！
```

---

## 常见问题

### Q1: LLM 会自动记录规则吗？

**A**: 会的，但有判断机制。

LLM 根据 AGENT_SYSTEM_PROMPT 中的指导，在以下情况下自动记录：
- 发现重复错误
- 找到有效的解决方案
- 遇到重要的边界情况

用户也可以明确要求："帮我记录一条规则"

---

### Q2: 规则草稿会自动生效吗？

**A**: 不会，完全不会。

- 草稿文件在 `sandbox/rules_draft/` 目录
- 真实规则在 `rules/` 目录
- 规则引擎只读取 `rules/` 目录
- 草稿仅供参考，需要人工审查后手动复制

---

### Q3: 如何查看 LLM 记录了哪些规则？

**A**: 查看变更日志或草稿文件。

```bash
# 快速查看日志
cat sandbox/rules_draft/CHANGELOG.md

# 查看具体草稿
cat sandbox/rules_draft/global_draft.md
cat sandbox/rules_draft/tool_calling_draft.md
```

---

### Q4: 草稿文件太多怎么办？

**A**: 定期清理。

**方式 1**: 标记状态
```markdown
**状态**: ✅ 已采纳（2024-01-23）
**状态**: ❌ 已拒绝（不适用）
```

**方式 2**: 直接删除
```bash
# 删除已处理的规则草稿
# （保留文件框架）
```

---

### Q5: 如何禁用规则建议功能？

**A**: 修改 AGENT_SYSTEM_PROMPT。

在 `nodes.py` 中注释掉规则建议相关的指导，或者告诉 Agent：

```
用户: "暂时不要记录规则建议"

Agent: "好的，我不会主动记录规则建议。"
```

---

## 最佳实践

### 1. 定期审查

- **频率**: 每周一次，或每次重要更新后
- **时长**: 10-15 分钟
- **重点**: 查看 CHANGELOG，筛选高价值规则

### 2. 质量优先

不要急于采纳所有规则：
- 验证规则的普遍性
- 确认不与现有规则冲突
- 调整表述使其更清晰

### 3. 版本控制

虽然草稿会频繁变化，但重要的规则建议可以：
- 提交到 Git（可选）
- 定期备份 CHANGELOG

### 4. 反馈循环

采纳规则后观察效果：
- Agent 是否遵守？
- 是否解决了问题？
- 是否需要调整？

### 5. 知识沉淀

将规则草稿作为知识库：
- 分析高频问题
- 总结最佳实践
- 培训新用户

---

## 附录

### A. 快速参考

#### Filesystem 工具调用

```yaml
# 读取文件
action: tool
tool_name: read_file
tool_params:
  path: "sandbox/rules_draft/global_draft.md"

# 写入文件（覆盖）
action: tool
tool_name: write_file
tool_params:
  path: "sandbox/rules_draft/global_draft.md"
  content: "..."
```

#### 规则草稿文件路径

```
sandbox/rules_draft/global_draft.md       # 全局规则
sandbox/rules_draft/tool_calling_draft.md # 工具调用
sandbox/rules_draft/reasoning_draft.md    # 推理规则
sandbox/rules_draft/memory_draft.md       # 记忆管理
sandbox/rules_draft/CHANGELOG.md          # 变更日志
```

### B. 统计命令

```bash
# 统计规则草稿数量
grep -c "^## 📝" sandbox/rules_draft/*.md

# 查看最近的规则建议
tail -20 sandbox/rules_draft/CHANGELOG.md

# 统计要求级别分布
grep "要求级别" sandbox/rules_draft/*.md | grep -c "MUST"
grep "要求级别" sandbox/rules_draft/*.md | grep -c "SHOULD"
```

### C. 相关文档

- **规则系统开发文档**: `docs/BEHAVIOR_RULES_DEVELOPMENT.md`
- **规则系统 Walkthrough**: `docs/BEHAVIOR_RULES_WALKTHROUGH.md`
- **草稿目录说明**: `sandbox/rules_draft/README.md`
- **真实规则**: `rules/global.md`

---

## 总结

规则草稿功能实现了：

✅ **LLM 自主学习** - 从错误和经验中学习
✅ **知识积累** - 持续积累规则库
✅ **质量保证** - 人工审查确保质量
✅ **零风险** - 草稿不会自动生效
✅ **简单易用** - 使用现有 filesystem 工具

**下一步**：
1. 启动 Agent 观察规则建议功能
2. 定期审查 `sandbox/rules_draft/` 目录
3. 采纳有价值的规则到 `rules/` 目录

---

**文档版本**: v1.0
**最后更新**: 2024-01-23
**作者**: AI Assistant
**维护者**: 项目团队
