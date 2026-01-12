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

### 1. 安装 uv (如未安装)

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. 创建虚拟环境并安装依赖

```bash
# 创建虚拟环境
uv venv

# 激活虚拟环境
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# Windows (CMD)
.venv\Scripts\activate.bat
# macOS / Linux
source .venv/bin/activate

# 安装依赖
uv sync
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入你的 API Key
```

### 4. 配置 MCP 工具 (可选)

创建 `mcp.json` 配置文件，参考下方配置说明。

### 5. 运行

```bash
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

## Embedding 模型

向量记忆使用本地 [Sentence Transformers](https://sbert.net/) 模型，**无需 API 调用**。

**默认模型**: `paraphrase-multilingual-MiniLM-L12-v2`
- 维度: 384
- 特点: 多语言支持，中文语义理解优秀

> 💡 **自动下载**: 首次运行时，模型会自动从 HuggingFace Hub 下载到本地缓存 (`~/.cache/huggingface/`)，约 500MB，之后离线可用。

### 替换模型

修改 `memory.py` 中的 `_get_embedding_model()` 函数：

```python
def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        # 替换为你需要的模型
        _embedding_model = SentenceTransformer('your-model-name')
    return _embedding_model
```

**推荐模型**:
| 模型 | 维度 | 特点 |
|------|------|------|
| `paraphrase-multilingual-MiniLM-L12-v2` | 384 | 多语言，中文友好 (默认) |
| `all-MiniLM-L6-v2` | 384 | 英文，速度快 |
| `text2vec-base-chinese` | 768 | 纯中文，效果好 |
| `bge-small-zh-v1.5` | 512 | 中文，SOTA |

> ⚠️ 更换模型后需删除 `memory_index.json`，因为向量维度可能不同。

## 项目结构

```
├── main.py          # 入口文件，定义工作流
├── nodes.py         # 核心节点实现
├── memory.py        # 向量记忆模块 (Embedding 配置在此)
├── utils.py         # LLM 调用工具
├── mcp_client/      # MCP 客户端封装
└── .env.example     # 环境变量示例
```

## 致谢

- [PocketFlow](https://github.com/The-Pocket/PocketFlow) - 轻量级 LLM 工作流框架
- [MCP](https://modelcontextprotocol.io/) - Model Context Protocol
- [Sentence Transformers](https://sbert.net/) - 文本向量化

## License

MIT
