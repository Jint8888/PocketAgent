# Tool Prompt Optimization Walkthrough

> **Date**: 2026-01-24  
> **Issue**: 系统提示词因包含 124 个 MCP 工具的完整描述导致约 35K 字符，引发 LLM 上下文超限错误

## 问题分析

### 症状
- Agent 频繁返回 "Sorry, AI service temporarily unavailable..."
- 错误发生在 `nodes.py` 的 `call_llm_async` 调用中

### 根本原因
`mcp_client/manager.py` 中的 `format_tools_for_prompt()` 方法生成的工具描述过于冗长：

**原格式示例（每个工具约 300-500 字符）：**
```
## 【xueqiu】 - 雪球股票数据MCP服务器，提供实时行情、K线数据、财务数据...
   共 10 个工具:

   [1] fetch_stock_quote
       描述: 获取股票实时行情数据 (无需 Token)
       参数:
      - symbol (string): 股票代码，如 SH600519 或 SZ000001 [必填]
```

---

## 解决方案

### 修改文件
[manager.py](file:///e:/AI/my-pocketflow/mcp_client/manager.py#L660-L714)

### 核心改动

将 `format_tools_for_prompt()` 方法从冗长的多行格式改为紧凑的单行格式：

**新格式示例（每个工具约 60-100 字符）：**
```
## 【xueqiu】(10个工具) - 雪球股票数据MCP服务器
  - fetch_stock_quote(symbol*): 获取股票实时行情数据 (无需 Token)
  - search_stocks(keyword*, count?): 股票搜索 (需要 Token)
```

### 优化策略

| 策略 | 说明 |
|------|------|
| 单行格式 | `tool_name(params): description` |
| 参数标记 | `*` = 必填，`?` = 可选 |
| 描述截断 | 保留第一行，最多 80 字符 |
| 移除冗余 | 省略参数类型、详细说明 |

---

## 代码变更

```diff
def format_tools_for_prompt(self) -> str:
-    """将工具信息格式化为 LLM 可理解的文本（按服务器分组）"""
+    """将工具信息格式化为精简格式，大幅减少 token 消耗
+    
+    优化策略：
+    1. 使用单行格式：tool_name(param1*, param2?): 简短描述
+    2. 参数用 * 表示必填，? 表示可选
+    3. 描述截断到第一行或前80字符
+    4. 移除冗余的类型信息和详细说明
+    """
     ...
-    server_section = [f"## 【{server_name}】 - {server_desc}"]
-    server_section.append(f"   共 {len(tools)} 个工具:")
+    short_server_desc = server_desc.split('\n')[0][:60]
+    server_lines = [f"## 【{server_name}】({len(tools)}个工具) - {short_server_desc}"]
     
-    tool_info = f"\n   [{global_index}] {tool.name}\n"
-    tool_info += f"       描述: {tool.description}\n"
-    tool_info += f"       参数:\n" + "\n".join(params)
+    param_str = ", ".join([f"{p}*" if p in required else f"{p}?" for p in properties])
+    short_desc = desc.split('\n')[0][:80]
+    tool_line = f"  - {tool.name}({param_str}): {short_desc}"
```

---

## 预期效果

| 指标 | 优化前 | 优化后 | 改进 |
|------|--------|--------|------|
| 工具信息字符数 | ~35,000 | ~8,000-10,000 | **-70%** |
| 估算 Token | ~15,000 | ~4,000-5,000 | **-70%** |
| 单工具平均 | ~300-500 字符 | ~60-100 字符 | **-75%** |

---

## 验证方法

1. 重启 Agent 服务
2. 发送简单测试消息（如 "hello"）
3. 检查是否仍出现 "AI service temporarily unavailable" 错误
4. 可在代理端日志查看请求报文大小是否显著减少
