# 规则草稿功能测试指南

> **版本**: v1.0
> **目的**: 验证 LLM 规则建议功能正常工作
> **预计时间**: 10 分钟

---

## 测试前准备

### 1. 验证环境

```bash
cd E:\AI\my-pocketflow

# 检查规则草稿目录
dir sandbox\rules_draft

# 应该看到：
# README.md
# global_draft.md
# tool_calling_draft.md
# reasoning_draft.md
# memory_draft.md
# CHANGELOG.md
```

### 2. 检查 MCP 配置

确认 filesystem 工具已启用：

```bash
type mcp.json | findstr "filesystem"

# 应该看到：
# "filesystem": {
#   "enabled": true,
```

### 3. 启动 Agent

```bash
python main.py
```

---

## 测试用例

### 测试 1：触发自动规则建议

**目的**: 验证 Agent 能够在遇到问题时自动建议规则

**步骤**:

```
用户输入: "请生成一张可爱的猫的图片，使用 Base64 格式返回"

预期：Agent 尝试使用 response_format="b64_json"，发现被截断

用户输入: "刚才遇到的问题很重要，请记录一条规则避免下次重复"

预期：Agent 调用 filesystem 工具记录规则建议
```

**验证**:

```bash
# 1. 查看工具调用规则草稿
cat sandbox\rules_draft\tool_calling_draft.md

# 应该看到新增的规则草稿：
## 📝 图片生成必须使用 URL 格式
...
**状态**: ⏳ 待审查

# 2. 查看变更日志
cat sandbox\rules_draft\CHANGELOG.md

# 应该看到：
- **[时间]** - [tool_calling] 图片生成必须使用 URL 格式
```

**结果**:
- ✅ 通过 - 规则草稿已创建
- ❌ 失败 - 请检查 Agent 输出和 filesystem 工具调用

---

### 测试 2：用户主动要求建议规则

**目的**: 验证用户可以主动要求 Agent 记录规则

**步骤**:

```
用户输入: "帮我记录一条规则：错误必须详细记录到 findings.md"

预期：Agent 理解用户意图，记录规则建议到 global_draft.md
```

**验证**:

```bash
cat sandbox\rules_draft\global_draft.md

# 应该看到：
## 📝 错误必须记录到 findings.md
...
```

**结果**:
- ✅ 通过
- ❌ 失败

---

### 测试 3：规则格式检查

**目的**: 验证 LLM 记录的规则格式符合模板

**检查清单**:

```markdown
## 📝 [规则标题]                       ✅ / ❌

> **建议时间**: YYYY-MM-DD HH:MM:SS     ✅ / ❌
> **要求级别**: MUST/SHOULD/MAY         ✅ / ❌
> **类别**: [category]                  ✅ / ❌

**描述**:                              ✅ / ❌
[内容]

**原因**:                              ✅ / ❌
[内容]

**示例**（可选）:                       ✅ / ❌
```
[代码]
```

**相关经验**:                          ✅ / ❌
[内容]

**状态**: ⏳ 待审查                      ✅ / ❌
```

**结果**:
- ✅ 所有字段齐全
- ❌ 部分字段缺失

---

### 测试 4：CHANGELOG 更新

**目的**: 验证规则建议会记录到 CHANGELOG

**步骤**:

```bash
# 查看 CHANGELOG
cat sandbox\rules_draft\CHANGELOG.md

# 应该看到最近的规则建议记录
```

**验证要点**:
- ✅ 包含时间戳
- ✅ 包含类别
- ✅ 包含规则标题
- ✅ 按时间顺序排列

---

### 测试 5：用户审查和采纳流程

**目的**: 验证完整的审查→采纳流程

**步骤 1**: 查看草稿

```bash
cat sandbox\rules_draft\tool_calling_draft.md
```

**步骤 2**: 评估规则（假设认为有价值）

**步骤 3**: 创建真实规则文件（如果不存在）

```bash
# 如果 rules/tool_calling.md 不存在
notepad rules\tool_calling.md
```

**步骤 4**: 复制规则内容并调整格式

```markdown
# 工具调用规则

> **版本**: v1.0
> **创建时间**: 2024-01-23

## TOOL-01: 图片生成必须使用 URL 格式

**要求**: MUST
**描述**: 调用图片生成工具时，必须使用 response_format='url'

**原因**: Base64 编码图片超过 100,000 字符限制导致截断

**示例**:
```python
# ✅ 正确
submit_generate_image(prompt="猫", response_format="url")

# ❌ 错误
submit_generate_image(prompt="猫", response_format="b64_json")
```
```

**步骤 5**: 保存文件

**步骤 6**: 重启 Agent 验证规则生效

```bash
python main.py
```

**步骤 7**: 测试规则是否生效

```
用户: "请生成一张猫的图片"

预期：Agent 自动使用 response_format="url"
```

**验证**:
- ✅ 规则生效，Agent 使用正确参数
- ❌ 规则未生效

---

## 测试结果汇总

| 测试用例 | 状态 | 备注 |
|---------|------|------|
| 测试 1: 自动规则建议 | ✅ / ❌ |  |
| 测试 2: 主动要求建议 | ✅ / ❌ |  |
| 测试 3: 规则格式检查 | ✅ / ❌ |  |
| 测试 4: CHANGELOG 更新 | ✅ / ❌ |  |
| 测试 5: 审查采纳流程 | ✅ / ❌ |  |

**总结**:
- 通过: ___ / 5
- 失败: ___ / 5

---

## 故障排查

### 问题 1: Agent 没有记录规则

**可能原因**:
1. filesystem 工具未启用
2. AGENT_SYSTEM_PROMPT 未更新
3. sandbox 目录权限问题

**解决方案**:

```bash
# 检查 filesystem 工具
type mcp.json | findstr "filesystem"

# 检查目录权限
dir sandbox\rules_draft

# 手动测试 filesystem 工具（通过 Agent）
用户: "请使用 read_file 工具读取 sandbox/rules_draft/README.md"
```

---

### 问题 2: 规则格式不正确

**可能原因**:
1. AGENT_SYSTEM_PROMPT 中的模板不清晰
2. LLM 理解偏差

**解决方案**:
- 检查 nodes.py 中的规则建议指导
- 提供更明确的示例

---

### 问题 3: CHANGELOG 未更新

**可能原因**:
1. Agent 忘记更新
2. 文件路径错误

**解决方案**:
```
用户: "刚才记录规则时，请同时更新 CHANGELOG.md"
```

---

## 性能基准

| 指标 | 预期值 | 实际值 |
|------|--------|--------|
| 规则记录耗时 | < 5 秒 |  |
| 文件读写次数 | 4 次（read_file × 2, write_file × 2） |  |
| 规则格式正确率 | 100% |  |

---

## 下一步建议

测试通过后：

1. **实际使用** - 在日常任务中观察 Agent 是否主动建议规则
2. **定期审查** - 每周查看一次 `sandbox/rules_draft/`
3. **采纳有价值规则** - 将高质量规则复制到 `rules/`
4. **反馈优化** - 根据实际效果调整规则建议机制

测试失败：

1. **查看日志** - 检查 Agent 的输出和工具调用
2. **检查配置** - 验证 mcp.json 和 AGENT_SYSTEM_PROMPT
3. **手动测试** - 直接要求 Agent 使用 filesystem 工具
4. **寻求帮助** - 查看文档或提交 issue

---

**测试完成时间**: ___________
**测试人**: ___________
**结果**: ✅ 通过 / ❌ 失败
