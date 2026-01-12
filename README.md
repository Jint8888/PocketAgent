# PocketAgent

基于 [PocketFlow](https://github.com/The-Pocket/PocketFlow) 的多步推理 AI Agent，支持 MCP 工具调用和向量记忆。

## 特性

- **多步推理** - 自动分解复杂任务，支持 tool → think → answer 的推理链
- **MCP 工具集成** - 通过 MCP 协议调用外部工具（如金融数据、搜索等）
- **向量记忆** - 滑动窗口 + 长期记忆，支持语义检索历史对话
- **全异步架构** - 基于 PocketFlow 的 AsyncNode/AsyncFlow 实现

## 架构

```
InputNode → RetrieveNode → DecideNode ─┬─→ ToolNode  ──┐
                              ↑        ├─→ ThinkNode ──┤
                              │        └─→ AnswerNode ─┼→ EmbedNode
                              └────────────────────────┘      ↓
                                                           (循环)
```

## 快速开始

```bash
# 1. 安装依赖
uv sync

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的 API Key

# 3. 配置 MCP 工具 (可选)
# 创建 mcp.json 配置文件

# 4. 运行
uv run python main.py
```

## 配置说明

### .env

```bash
DEEPSEEK_API_KEY=your-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
```

### mcp.json (可选)

```json
{
  "mcpServers": {
    "your-server": {
      "command": "...",
      "args": ["..."]
    }
  }
}
```

## 项目结构

```
├── main.py          # 入口文件，定义工作流
├── nodes.py         # 核心节点实现
├── memory.py        # 向量记忆模块
├── utils.py         # LLM 调用工具
├── mcp_client/      # MCP 客户端封装
└── .env.example     # 环境变量示例
```

## 致谢

- [PocketFlow](https://github.com/The-Pocket/PocketFlow) - 轻量级 LLM 工作流框架
- [MCP](https://modelcontextprotocol.io/) - Model Context Protocol

## License

MIT
