# MCP 协议介绍及本项目实现分析

## MCP 协议简介

MCP（Model Context Protocol）是 Anthropic 于 2024 年 11 月发布的开源标准协议，让 AI 模型能够调用外部工具。核心思路类似 HTTP 的 client-server 模型：

```
AI 应用 (Client)  ←──stdio/SSE──→  MCP Server  ←──→  外部服务(Twitter等)
(Claude, Cursor...)                  (本项目)
```

### 核心概念

- **Tools** — server 向 client 声明"我能做什么"（函数名、参数、描述），AI 根据用户意图自动选择调用
- **Transport** — 通信方式，主要是 `stdio`（本地进程间管道）和 `SSE`（HTTP 远程）
- **JSON-RPC 2.0** — 底层消息格式

---

## 本项目的具体实现

整个项目用 `mcp` 官方 Python SDK 的 `FastMCP` 高层 API，实现非常简洁。

### 1. 创建 Server（server.py:11）

```python
mcp = FastMCP("twitter")
```

声明一个名为 `"twitter"` 的 MCP server。`FastMCP` 封装了底层的 JSON-RPC 协议处理、tool 注册、schema 生成等。

### 2. 注册 Tool（server.py:33-167）

```python
@mcp.tool()
async def search_tweets(query: str, count: int = 20, product: str = "Latest") -> str:
    """Search tweets.
    Args:
        query: Search query string.
        ...
    """
```

`@mcp.tool()` 装饰器做了三件事：

- **函数名** → tool name（如 `search_tweets`）
- **docstring** → tool description（AI 根据这个决定何时调用）
- **类型注解** → JSON Schema 参数定义（AI 知道传什么参数）

AI client 连接时会收到类似这样的声明：

```json
{
  "name": "search_tweets",
  "description": "Search tweets.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {"type": "string"},
      "count": {"type": "integer", "default": 20},
      "product": {"type": "string", "default": "Latest"}
    },
    "required": ["query"]
  }
}
```

### 3. 启动 Transport（server.py:170-171）

```python
def main():
    mcp.run(transport="stdio")
```

用 **stdio** 模式启动——AI 应用以子进程方式启动本 server，通过 stdin/stdout 交换 JSON-RPC 消息。

### 4. 调用链路

一次完整调用的流程：

```
用户: "搜索关于 MCP 的推文"
  ↓
Claude (Client): 根据 tool description 选择 search_tweets
  ↓ JSON-RPC via stdio
MCP Server: 收到调用 → _get_client() 读 cookies 创建 twikit Client
  ↓
twikit: 用 cookie 模拟浏览器请求 Twitter GraphQL API
  ↓
MCP Server: 格式化结果 → 返回 JSON 字符串
  ↓ JSON-RPC via stdio
Claude: 解析结果，生成自然语言回复给用户
```

### 5. 认证层（server.py:14-27）

```python
COOKIES_PATH = Path(os.environ.get("TWITTER_COOKIES", "~/.config/twitter-mcp/cookies.json"))

async def _get_client() -> Client:
    cookies = json.loads(COOKIES_PATH.read_text())
    client.set_cookies({"auth_token": ..., "ct0": ...})
```

不走 Twitter 官方 API（需要开发者账号+付费），而是用浏览器 cookie 直接调 Twitter 内部 GraphQL 接口，这就是 twikit 的核心卖点——**免费、无需 API key**。

---

## 总结

整个项目本质上是一个 **协议适配层**——把 twikit 的 Python API 包装成 MCP 标准 tool，让任何支持 MCP 的 AI 客户端都能调用 Twitter 功能。核心代码量很少（176 行），大部分复杂度在 vendored 的 twikit 里。
