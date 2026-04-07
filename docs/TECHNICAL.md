# twikit-mcp

[![CI](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/twikit-mcp)](https://pypi.org/project/twikit-mcp/)

基于 [twikit](https://github.com/d60/twikit) 的 Twitter/X MCP Server，**不需要 Twitter API Key**，通过浏览器 cookies 认证，**完全免费**。

> **vs 其他方案：** PyPI 上的 `twitter-mcp` 基于 tweepy，需要 Twitter API（$200+/月）。
> 本项目基于 twikit，用浏览器 cookies 认证，零成本。

注册到 MCP 客户端后，用自然语言操作 Twitter（发推、搜索、点赞等）。

## 快速开始（2 步）

```bash
# 1. 创建 cookies.json（从浏览器 DevTools 获取 ct0 和 auth_token）
mkdir -p ~/.config/twitter-mcp
cat > ~/.config/twitter-mcp/cookies.json << 'EOF'
{"ct0": "你的ct0", "auth_token": "你的auth_token"}
EOF
chmod 600 ~/.config/twitter-mcp/cookies.json

# 2. 安装 & 注册（任选一种）
# uvx（推荐）
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- uvx twikit-mcp

# 或 pip
pip install twikit-mcp
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- twikit-mcp
```

重启 MCP 客户端，然后直接说 "搜一下关于 AI 的推文" 就行了。
兼容 Claude Code、Claude Desktop、Cursor、Windsurf、opencode、Cline 等所有 MCP 客户端。

---

## 目录

1. [什么是 MCP](#什么是-mcp)
2. [MCP Server 的三种类型](#mcp-server-的三种类型)
3. [为什么要自己写 MCP Server](#为什么要自己写-mcp-server)
4. [MCP Server 代码放哪里](#mcp-server-代码放哪里)
5. [原理](#原理)
6. [前置条件](#前置条件)
7. [从零搭建](#从零搭建)
8. [获取 Twitter Cookies](#获取-twitter-cookies)
9. [注册到 Claude Code](#注册到-claude-code)
10. [验证](#验证)
11. [可用工具](#可用工具)
12. [项目结构](#项目结构)
13. [工作原理详解](#工作原理详解)
14. [Claude Code 中 MCP 的配置体系](#claude-code-中-mcp-的配置体系)
15. [常见问题](#常见问题)
16. [部署到其他机器](#部署到其他机器)（含 [Windows 部署](#windows-部署)）
17. [测试和 CI/CD](#测试和-cicd)（详见 [CONTRIBUTING.md](CONTRIBUTING.md)）
18. [自定义和扩展](#自定义和扩展)

---

## 什么是 MCP

**MCP (Model Context Protocol)** 是 Anthropic 定义的开放协议，让 AI 模型（如 Claude）能调用外部工具和数据源。

你可以把 MCP 理解为 **AI 的 USB 接口**：

```
没有 MCP:
  用户 → Claude → 只能生成文字

有了 MCP:
  用户 → Claude → MCP → Twitter（发推、搜索）
                      → GitHub（创建 PR、查 Issue）
                      → 文件系统（读写文件）
                      → 数据库（查询数据）
                      → 任何你封装的服务...
```

Claude 不需要知道每个服务的具体 API 细节。MCP server 把复杂的 API 调用封装成简单的工具定义（名称 + 参数 + 描述），Claude 根据用户的自然语言意图自动选择调用哪个工具。

### MCP 的核心概念

| 概念 | 说明 |
|------|------|
| **MCP Host** | 运行 AI 模型的应用（如 Claude Code、Claude Desktop） |
| **MCP Client** | Host 内部的连接器，管理与 Server 的通信 |
| **MCP Server** | 提供工具的程序（如本项目），暴露 `tools/list` 和 `tools/call` |
| **Transport** | 通信方式：`stdio`（stdin/stdout）或 `http`（网络） |
| **Tool** | Server 暴露的具体能力（如 `send_tweet`、`search_tweets`） |

---

## MCP Server 的三种类型

在 MCP 生态中，MCP server 主要有三种形态：

### 1. npm/PyPI 包 — 直接用，不需要下载代码

这是**官方和社区 MCP server 的主流方式**。代码由包管理器自动下载到缓存，你不需要关心它存在哪里。

```bash
# Node.js 生态 — 用 npx 直接运行
claude mcp add filesystem -- npx @modelcontextprotocol/server-filesystem ~/Documents
claude mcp add github -- npx @modelcontextprotocol/server-github
claude mcp add puppeteer -- npx @anthropic-ai/mcp-puppeteer

# Python 生态 — 用 uvx 直接运行
claude mcp add fetch -- uvx mcp-server-fetch
claude mcp add sqlite -- uvx mcp-server-sqlite
```

**代码在哪？** 在 npm/pip 的全局缓存里（`~/.npm/_npx/`、`~/.cache/uv/`），由包管理器自动管理。你不需要手动克隆任何仓库。

**适合：** 使用成熟的、已发布的 MCP server。

### 2. HTTP 远程服务 — 一个 URL 就够了

有些 MCP server 以 SaaS 形式运行在云端，你只需要提供 URL。

```bash
# Figma — 设计工具
claude mcp add figma --transport http https://mcp.figma.com/mcp

# Vercel — 部署平台
claude mcp add vercel --transport http https://mcp.vercel.com

# Sentry — 错误监控
claude mcp add sentry --transport http https://mcp.sentry.dev/mcp
```

**代码在哪？** 在对方的服务器上，本地没有任何代码。

**适合：** 第三方 SaaS 提供的官方 MCP 集成。

### 3. 本地项目 — 自己写的 MCP Server（本项目）

当你需要封装一个没有现成 MCP 包的服务时，自己写一个项目。

```bash
# 指向你本地的项目目录
claude mcp add twitter -s user \
  -- uv run --directory ~/mcp-servers/twitter-mcp python -m twitter_mcp.server
```

**代码在哪？** 在你自己选择的目录里。

**适合：** 定制需求、未发布的库、逆向工程的 API（比如本项目用 twikit）。

### 对比总览

| 类型 | 代码位置 | 注册方式 | 典型例子 |
|------|---------|---------|---------|
| npm/PyPI 包 | 包管理器缓存（自动） | `npx ...` / `uvx ...` | filesystem, github, fetch |
| HTTP 远程 | 对方服务器（无本地代码） | `--transport http URL` | Figma, Vercel, Sentry |
| 本地项目 | 你选的目录 | `uv run --directory ...` | **本项目 (twitter-mcp)** |

---

## 为什么要自己写 MCP Server

本项目选择自己写而不是用现成包，原因是：

1. **Twitter 没有官方 MCP server** — Anthropic 和社区都没有提供
2. **不需要 Twitter API Key** — twikit 通过逆向工程直接调用 Twitter 内部 GraphQL API，只需要浏览器 cookies
3. **修复了上游 bug** — PyPI 上的 twikit 2.3.3 有两个 bug（正则匹配失败 + 搜索 HTTP 方法错误），已通过 vendoring + PR#412 补丁修复
4. **完全可控** — 可以随时添加新工具、调整行为

本项目已发布到 PyPI（`twikit-mcp`），安装方式：
```bash
# uvx
claude mcp add twitter -- uvx twikit-mcp

# 或 pip
pip install twikit-mcp
```

---

## MCP Server 代码放哪里

**官方没有规定 MCP server 代码必须放在某个特定目录。** 代码放哪都行，`claude mcp add` 的时候指向它就好。

### 不要放在 `~/.claude/` 下

`~/.claude/` 是 Claude Code 自己管理的目录（缓存、会话历史、配置文件）。把自己的代码放进去可能会：
- 被 Claude Code 升级时清理
- 和内部文件冲突
- 混淆 Claude Code 的自有数据和你的项目代码

### 推荐的放法

| 位置 | 说明 | 适合场景 |
|------|------|---------|
| `~/mcp-servers/` | 简单直观，所有自定义 MCP 放一起 | **推荐（本项目采用）** |
| `~/.local/share/mcp-servers/` | 遵循 Linux XDG 规范 | 喜欢规范目录结构的用户 |
| `~/projects/my-mcp/` | 当作普通项目管理 | 打算开源或发布到 PyPI |
| 项目目录内 `.mcp/` | 随项目走 | 只在特定项目内使用的 MCP |

### 配置（注册信息）vs 代码 的区别

这是容易混淆的地方，要区分：

```
代码（你写的 server）:
  ~/mcp-servers/twitter-mcp/          ← 放哪都行，你自己管
  ~/mcp-servers/another-mcp/

凭证（cookies、API keys）:
  ~/.config/twitter-mcp/cookies.json  ← 推荐放 ~/.config/ 下，chmod 600

配置（告诉 Claude Code 怎么启动 server）:
  ~/.claude.json                      ← Claude Code 管理，用 `claude mcp add` 写入
```

`claude mcp add` 只是在 `~/.claude.json` 里写一条配置，告诉 Claude Code："启动时用这个命令拉起 twitter MCP server"。配置长这样：

```json
{
  "mcpServers": {
    "twitter": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "/home/你的用户名/mcp-servers/twitter-mcp", "python", "-m", "twitter_mcp.server"],
      "env": {
        "TWITTER_COOKIES": "/home/你的用户名/.config/twitter-mcp/cookies.json"
      }
    }
  }
}
```

---

## 原理

```
用户："搜一下关于 AI 的推文"
         │
         ▼
   Claude Code（理解自然语言意图）
         │
         ▼
   MCP Protocol（JSON-RPC 2.0 over stdio）
         │
         ▼
   twitter-mcp server（本项目 — FastMCP 封装）
         │
         ▼
   twikit（模拟浏览器请求，无需 API Key）
         │
         ▼
   Twitter GraphQL API（x.com 内部接口）
```

**MCP (Model Context Protocol)** 是 Anthropic 定义的协议，让 Claude 能调用外部工具。
本项目把 twikit 的 Twitter 操作封装成 MCP 工具，Claude Code 启动时自动拉起这个 server 进程，
通过 stdin/stdout 通信。你不需要手动运行任何东西。

**twikit** 是一个逆向工程 Twitter 的 Python 库，直接调用 Twitter 内部的 GraphQL API，
只需要浏览器的 `ct0` 和 `auth_token` cookies 就能认证，不需要申请 Twitter Developer API。

---

## 前置条件

- **Python 3.10+**
- **包管理器**（任选一个）：[uv](https://docs.astral.sh/uv/)（推荐）、pip、pipx
- **MCP 客户端**（任选一个）：Claude Code、Claude Desktop、Cursor、Windsurf、opencode、Cline 等
- **Twitter 账号** — 需要已登录的浏览器 cookies

```bash
# 检查
python3 --version   # >= 3.10

# 以下任选其一
uv --version         # 推荐
pip --version        # 也行
pipx --version       # 也行
```

---

## 从零搭建

### Step 1: 创建项目

```bash
# 创建 MCP servers 目录（所有自定义 MCP 放一起）
mkdir -p ~/mcp-servers
cd ~/mcp-servers

# 用 uv 初始化项目
uv init twitter-mcp
cd twitter-mcp

# 创建 Python package 目录
mkdir -p twitter_mcp
touch twitter_mcp/__init__.py
```

### Step 2: 配置依赖

编辑 `pyproject.toml`:

```toml
[project]
name = "twikit-mcp"
version = "0.1.1"
description = "Twitter/X MCP server powered by twikit — no API key needed, free forever"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "mcp[cli]",
    "httpx[socks]",
    "beautifulsoup4",
    "filetype",
    "pyotp",
    "lxml",
    "webvtt-py",
    "m3u8",
    "js2py-3-13",
]

[project.scripts]
twikit-mcp = "twitter_mcp.server:main"
```

依赖说明：
- **`mcp[cli]`** — Anthropic 官方 MCP Python SDK，包含 `FastMCP` 高层封装
- **其余依赖** — twikit 的子依赖，因为 twikit 已 vendor 进项目（见下方说明）

> **关于 twikit vendoring：** PyPI 上的 twikit 2.3.3 有两个 bug（正则匹配失败 + 搜索 HTTP 方法错误），
> PR#412 的修复尚未合并到主分支。由于 PyPI 不允许 `git+` URL 依赖，
> 我们将 twikit 整个 vendor 到 `twitter_mcp/_vendor/twikit/` 并应用了补丁。
> 详见 [VENDORING.md](VENDORING.md)。

### Step 3: 编写 MCP Server

创建 `twitter_mcp/server.py`。这是整个项目的核心文件：

```python
"""Twitter MCP Server - twikit-based, no API key needed."""

import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP    # MCP SDK 的高层封装
from twitter_mcp._vendor.twikit import Client  # vendored twikit（含 PR#412 修复）

# 创建 MCP server 实例
# "twitter" 是 server 名称，会显示在 Claude Code 的工具列表中
mcp = FastMCP("twitter")

# Cookies 文件路径
# 优先级：环境变量 TWITTER_COOKIES > 默认路径 ~/.config/twitter-mcp/cookies.json
# 环境变量在 `claude mcp add -e` 时传入
COOKIES_PATH = Path(
    os.environ.get(
        "TWITTER_COOKIES",
        os.path.expanduser("~/.config/twitter-mcp/cookies.json"),
    )
)


async def _get_client() -> Client:
    """
    创建已认证的 twikit Client。

    每次调用都重新读取 cookies 文件，这样：
    - cookies 更新后不需要重启 server
    - 不会有状态泄漏问题
    - twikit Client 本身很轻量，创建开销可忽略
    """
    cookies = json.loads(COOKIES_PATH.read_text())
    client = Client("en")
    client.set_cookies(
        {"auth_token": cookies["auth_token"], "ct0": cookies["ct0"]}
    )
    return client


# ── 工具定义 ──────────────────────────────────────────────
#
# 每个 @mcp.tool() 函数就是一个 Claude 能调用的工具。
# FastMCP 会自动：
#   1. 从函数签名生成 JSON Schema（参数类型和描述）
#   2. 从 docstring 提取工具描述（Claude 用来决定是否调用）
#   3. 注册到 tools/list 响应中
#
# Claude 看到的是工具名 + 描述 + 参数，然后根据用户意图决定调用哪个。


@mcp.tool()
async def send_tweet(text: str, reply_to: str | None = None) -> str:
    """Send a tweet. Optionally reply to a tweet by ID.

    Args:
        text: Tweet content (max 280 chars).
        reply_to: Optional tweet ID to reply to.
    """
    client = await _get_client()
    tweet = await client.create_tweet(text=text, reply_to=reply_to)
    return json.dumps({"id": tweet.id, "text": text, "status": "sent"})


@mcp.tool()
async def get_tweet(tweet_id: str) -> str:
    """Fetch a tweet by ID.

    Args:
        tweet_id: The tweet ID (numeric string) or full URL.
    """
    # 支持直接传入推文 URL，自动提取 ID
    if "/" in tweet_id:
        tweet_id = tweet_id.rstrip("/").split("/")[-1]

    client = await _get_client()
    # 注意：用 get_tweets_by_ids（复数）而不是 get_tweet_by_id（单数）
    # 后者在当前 twikit 版本有 entries 解析 bug
    tweets = await client.get_tweets_by_ids([tweet_id])
    t = tweets[0]
    return json.dumps(
        {
            "id": t.id,
            "author": t.user.screen_name,
            "author_name": t.user.name,
            "text": t.text,
            "created_at": str(t.created_at),
            "likes": t.favorite_count,
            "retweets": t.retweet_count,
        }
    )


@mcp.tool()
async def get_timeline(count: int = 20) -> str:
    """Fetch home timeline tweets.

    Args:
        count: Number of tweets to fetch (default 20).
    """
    client = await _get_client()
    tweets = await client.get_timeline(count=count)
    result = []
    for t in tweets:
        result.append(
            {
                "id": t.id,
                "author": t.user.screen_name,
                "text": t.text[:200],
                "likes": t.favorite_count,
                "retweets": t.retweet_count,
            }
        )
    return json.dumps(result)


@mcp.tool()
async def search_tweets(
    query: str, count: int = 20, product: str = "Latest"
) -> str:
    """Search tweets.

    Args:
        query: Search query string.
        count: Number of results (default 20).
        product: "Latest" or "Top" (default "Latest").
    """
    client = await _get_client()
    tweets = await client.search_tweet(query, product=product, count=count)
    result = []
    for t in tweets:
        result.append(
            {
                "id": t.id,
                "author": t.user.screen_name,
                "text": t.text[:200],
                "likes": t.favorite_count,
                "retweets": t.retweet_count,
            }
        )
    return json.dumps(result)


@mcp.tool()
async def like_tweet(tweet_id: str) -> str:
    """Like a tweet by ID.

    Args:
        tweet_id: The tweet ID.
    """
    client = await _get_client()
    await client.favorite_tweet(tweet_id)
    return json.dumps({"tweet_id": tweet_id, "status": "liked"})


@mcp.tool()
async def retweet(tweet_id: str) -> str:
    """Retweet a tweet by ID.

    Args:
        tweet_id: The tweet ID.
    """
    client = await _get_client()
    await client.retweet(tweet_id)
    return json.dumps({"tweet_id": tweet_id, "status": "retweeted"})


@mcp.tool()
async def get_user_tweets(screen_name: str, count: int = 20) -> str:
    """Get recent tweets from a specific user.

    Args:
        screen_name: Twitter username (without @).
        count: Number of tweets to fetch (default 20).
    """
    client = await _get_client()
    user = await client.get_user_by_screen_name(screen_name)
    tweets = await client.get_user_tweets(
        user.id, tweet_type="Tweets", count=count
    )
    result = []
    for t in tweets:
        result.append(
            {
                "id": t.id,
                "text": t.text[:200],
                "created_at": str(t.created_at),
                "likes": t.favorite_count,
                "retweets": t.retweet_count,
            }
        )
    return json.dumps(result)


# ── 入口 ──────────────────────────────────────────────

def main():
    # transport="stdio" 表示通过 stdin/stdout 通信
    # Claude Code 会 spawn 这个进程，用 JSON-RPC 2.0 协议通信
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
```

### Step 4: 安装依赖

```bash
cd ~/mcp-servers/twitter-mcp
uv sync
```

这会：
1. 创建 `.venv/` 虚拟环境
2. 安装 `mcp[cli]` 和 twikit 的子依赖（twikit 本身已 vendor 在项目内）
3. 生成 `uv.lock` 锁定文件

---

## 获取 Twitter Cookies

twikit 通过浏览器 cookies 认证，不需要 Twitter Developer API Key。

### 从浏览器 DevTools 提取

1. 用浏览器登录 [x.com](https://x.com)
2. 打开 DevTools（F12 或 Ctrl+Shift+I）
3. 切到 **Application** 标签页 (Chrome) 或 **Storage** 标签页 (Firefox)
4. 在左侧找到 **Cookies** → `https://x.com`
5. 复制这两个值：

| Cookie 名 | 说明 | 格式 |
|-----------|------|------|
| `ct0` | CSRF token | 长十六进制字符串（~160字符） |
| `auth_token` | 认证 token | 40字符十六进制 |

### 保存到配置文件

```bash
# 创建配置目录
mkdir -p ~/.config/twitter-mcp

# 写入 cookies（替换为你的值）
cat > ~/.config/twitter-mcp/cookies.json << 'EOF'
{
  "ct0": "你的ct0值粘贴到这里",
  "auth_token": "你的auth_token值粘贴到这里"
}
EOF

# 限制权限 — 文件包含认证信息，只允许本用户读写
chmod 600 ~/.config/twitter-mcp/cookies.json
```

> **cookies 会过期吗？** 会。`auth_token` 通常有效数月，`ct0` 可能更短。
> 过期后重新从浏览器提取即可，不需要重启 Claude Code（server 每次调用都重新读取文件）。

---

## 注册到 MCP 客户端

### Claude Code

选择以下 **任一** 安装方式：

```bash
# 方式 A: uvx（推荐，需要 uv）
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- uvx twikit-mcp

# 方式 B: pip
pip install twikit-mcp
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- twikit-mcp

# 方式 C: pipx（隔离安装）
pipx install twikit-mcp
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- twikit-mcp
```

参数详解：

| 参数 | 说明 |
|------|------|
| `twitter` | MCP server 名称（随意取，显示在 `claude mcp list` 中） |
| `-s user` | 注册范围。`user` = 用户级（所有项目可用），`local` = 仅当前项目 |
| `-e KEY=value` | 环境变量，传给 server 进程 |
| `--` | 分隔符，之后是启动命令 |
| `uvx twikit-mcp` 或 `twikit-mcp` | 启动命令 |

### 其他 MCP 客户端

这是标准的 MCP server（stdio 传输），**不限于 Claude Code**。在任何支持 MCP 的客户端配置中添加：

```json
{
  "mcpServers": {
    "twitter": {
      "command": "twikit-mcp",
      "env": {
        "TWITTER_COOKIES": "/home/你的用户名/.config/twitter-mcp/cookies.json"
      }
    }
  }
}
```

> 兼容：Claude Code、Claude Desktop、Cursor、Windsurf、opencode、Cline 等。
> 不同客户端的配置文件位置和字段名可能略有不同，请参考各客户端文档。

### 注册范围 (`-s` / `--scope`)

| Scope | 配置写入位置 | 生效范围 |
|-------|------------|---------|
| `user` | `~/.claude.json` | 所有项目、所有会话 |
| `local` | `~/.claude.json`（项目级） | 仅当前项目目录 |
| `project` | `.mcp.json`（项目根目录） | 所有使用此项目的人（可提交到 git） |

对于个人使用的 Twitter MCP，推荐 `-s user`（全局可用）。

### 验证注册

```bash
claude mcp list
# 应该显示：
# twitter: uv run --directory .../twitter-mcp python -m twitter_mcp.server - ✓ Connected
```

### 重启 Claude Code

注册后需要重启 Claude Code 才能加载新的 MCP server：

```bash
/exit    # 退出
claude   # 重新进入，MCP server 自动加载
```

### 管理 MCP Server

```bash
# 列出所有已注册的 MCP server
claude mcp list

# 删除一个 MCP server
claude mcp remove twitter

# 重新注册（先删再加）
claude mcp remove twitter && claude mcp add twitter ...
```

---

## 验证

### 方式 1: 在 Claude Code 中用自然语言

重启 Claude Code 后，直接说人话：

```
> 帮我搜索关于 Claude Code 的推文
> 看看 @elonmusk 最近发了什么
> 帮我看看这条推文 https://x.com/xxx/status/123456
> 发一条推说：Hello from Claude Code!
```

Claude 会自动识别意图并调用对应的 MCP 工具。你不需要知道工具名，不需要输入任何命令。

### 方式 2: 手动测试 MCP 协议

发送 JSON-RPC initialize 请求，验证 server 能正确响应：

```bash
cd ~/mcp-servers/twitter-mcp

echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0.1"}}}' \
  | uv run python -m twitter_mcp.server
```

应该返回包含 `capabilities` 和 `serverInfo` 的 JSON 响应。

### 方式 3: 直接调用 Python 函数

```bash
cd ~/mcp-servers/twitter-mcp

uv run python -c "
import asyncio, json
from twitter_mcp.server import get_tweet

async def test():
    result = await get_tweet('推文ID替换成真实的')
    print(json.dumps(json.loads(result), indent=2, ensure_ascii=False))

asyncio.run(test())
"
```

---

## 可用工具

| 工具 | 功能 | 参数 | 用自然语言怎么说 |
|------|------|------|----------------|
| `send_tweet` | 发推/回复 | `text`, `reply_to?` | "发一条推说..." / "回复这条推..." |
| `get_tweet` | 获取单条推文 | `tweet_id`（支持 URL） | "看看这条推文 [链接]" |
| `get_timeline` | 刷首页时间线 | `count?` (默认 20) | "看看我的时间线" |
| `search_tweets` | 搜索推文 | `query`, `count?`, `product?` | "搜一下关于 XX 的推文" |
| `like_tweet` | 点赞 | `tweet_id` | "点赞这条推" |
| `retweet` | 转推 | `tweet_id` | "转推这个" |
| `get_user_tweets` | 获取某用户推文 | `screen_name`, `count?` | "看看 @xxx 最近发了什么" |

---

## 项目结构

```
~/mcp-servers/twitter-mcp/          ← 项目根目录（代码在这里）
├── pyproject.toml                   ← 依赖声明和项目元数据
├── twitter_mcp/                     ← Python package
│   ├── __init__.py
│   ├── server.py                    ← MCP server 核心代码（7 个工具）
│   └── _vendor/                     ← vendored 第三方库
│       └── twikit/                  ← twikit 2.3.3 + PR#412 修复
│           ├── client/              ← 修复 2: gql_get → gql_post
│           ├── x_client_transaction/← 修复 1: 正则匹配
│           └── ...
├── tests/                           ← 测试文件
├── docs/                            ← 文档
├── .venv/                           ← 虚拟环境（自动生成，不提交 git）
├── uv.lock                          ← 依赖锁定文件（自动生成）
└── README.md                        ← 项目说明

~/.config/twitter-mcp/
└── cookies.json                     ← Twitter 认证 cookies（chmod 600）

~/.claude.json                       ← Claude Code 用户配置（MCP 注册信息在这里）
```

### 为什么这样组织？

- **代码** (`~/mcp-servers/`) — 和 Claude Code 配置解耦，方便管理多个 MCP server
- **凭证** (`~/.config/`) — 遵循 XDG 规范，和代码分离，避免意外提交到 git
- **配置** (`~/.claude.json`) — 由 `claude mcp add` 命令管理，不需要手动编辑

---

## 工作原理详解

### 核心机制：配置一次，永久生效

这是最重要的概念——**所有设置只需要做一次**：

```
┌─────────────────────────────────────────────────────────┐
│  一次性操作（只在首次部署时做）                             │
│                                                         │
│  1. 安装代码和依赖     → uv sync                         │
│  2. 配置认证           → cookies.json                    │
│  3. 注册到 Claude Code → claude mcp add ...              │
│                                                         │
│  这三步完成后，你再也不需要碰它们了（除非 cookies 过期）     │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  自动循环（每次你打开 Claude Code 都会自动发生）            │
│                                                         │
│  claude 启动                                             │
│    → 读 ~/.claude.json，发现 twitter MCP 配置             │
│    → 自动执行: uv run ... python -m twitter_mcp.server   │
│    → server 进程启动，等待调用                             │
│    → 你说"搜推文" → Claude 调用 search_tweets → 返回结果   │
│    → 你说"发一条推" → Claude 调用 send_tweet → 推文发出    │
│    → ...（可以反复调用，不限次数）                          │
│    → 你退出 Claude Code                                   │
│    → server 进程自动终止                                   │
│                                                         │
│  下次再打开 Claude Code → 同样的循环自动开始               │
└─────────────────────────────────────────────────────────┘
```

**`claude mcp add` 做了什么？**

它只是在 `~/.claude.json` 里写入一条 JSON 配置：

```json
{
  "mcpServers": {
    "twitter": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "...", "python", "-m", "twitter_mcp.server"],
      "env": {"TWITTER_COOKIES": "..."}
    }
  }
}
```

这条配置告诉 Claude Code："以后每次启动时，用这个命令拉起 twitter server"。
它不会启动任何进程、不会修改系统服务、不会开机自启。仅仅是一条配置。

**Server 什么时候在运行？**

- Claude Code 打开时 → server 运行中（作为 Claude Code 的子进程）
- Claude Code 关闭后 → server 不存在（进程已被终止）
- 不占用任何后台资源，不需要 systemd、不需要 Docker、不需要 tmux

### MCP 通信流程

```
Claude Code (Host)                  twitter-mcp server
    │                                      │
    │ 1. 启动时 spawn 子进程               │
    │──── uv run python -m ... ──────────>│
    │                                      │
    │ 2. 初始化握手                         │
    │──── {"method":"initialize"} ────────>│
    │<─── {"result":{capabilities}} ───────│
    │                                      │
    │ 3. 查询可用工具                       │
    │──── {"method":"tools/list"} ────────>│
    │<─── {"result":[send_tweet,...]} ─────│
    │                                      │
    │ 4. 用户说"搜推文"，Claude 决定调用     │
    │──── {"method":"tools/call",          │
    │      "params":{"name":               │
    │        "search_tweets",              │
    │        "arguments":                  │
    │          {"query":"AI"}}} ──────────>│
    │                                      │── twikit ── Twitter GraphQL API
    │<─── {"result":[{tweets}]} ───────────│
    │                                      │
    │ 5. Claude Code 退出                   │
    │──── (SIGTERM) ──────────────────────>│  进程自动结束
```

关键点：
1. **自动管理：** Claude Code 启动时自动 spawn server 进程，退出时自动终止，不留后台进程
2. **stdio 传输：** 通过 stdin 发送请求，stdout 接收响应，使用 JSON-RPC 2.0 协议
3. **无状态：** 每次调用都是独立的，server 不需要维护会话状态
4. **不需要手动运行：** 你永远不需要自己启动 MCP server

### FastMCP 框架

`mcp[cli]` 包含 `FastMCP`，是 MCP Python SDK 的高层封装（类比 FastAPI 之于 Starlette）：

```python
# FastMCP 自动做了这些事：
@mcp.tool()
async def search_tweets(query: str, count: int = 20) -> str:
    """Search tweets."""    # ← Claude 看到的工具描述
    ...

# 1. 从函数签名生成 JSON Schema:
#    {"query": {"type": "string"}, "count": {"type": "integer", "default": 20}}
# 2. 从 docstring 提取描述: "Search tweets."
# 3. 注册到 tools/list
# 4. 处理 tools/call 时的参数解析和调用分发
# 5. 处理 JSON-RPC 协议细节
```

你只需要写普通的 async Python 函数 + docstring，FastMCP 处理一切协议细节。

### 为什么每次调用都创建新 Client？

```python
async def _get_client() -> Client:
    cookies = json.loads(COOKIES_PATH.read_text())  # 每次重新读
    client = Client("en")
    client.set_cookies(...)
    return client
```

设计考量：
- **cookies 热更新** — 更新 cookies.json 后立即生效，不需要重启
- **无状态** — 不存在"上一次请求的状态影响这一次"的问题
- **轻量** — twikit Client 创建成本很低（只是设置几个属性）

---

## Claude Code 中 MCP 的配置体系

理解 Claude Code 的多层配置对管理 MCP server 很有帮助。

### 三层配置

```
优先级（从高到低）：

1. 项目级 .mcp.json（项目根目录，可提交到 git，团队共享）
   ↓
2. 项目级 ~/.claude.json（项目专属配置，私有）
   ↓
3. 用户级 ~/.claude.json（全局配置，所有项目生效）
```

### .mcp.json — 团队共享配置

如果你想让项目里的所有开发者都能用某个 MCP server，在项目根目录创建 `.mcp.json`：

```json
{
  "mcpServers": {
    "twitter": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "./mcp-servers/twitter-mcp", "python", "-m", "twitter_mcp.server"],
      "env": {
        "TWITTER_COOKIES": "${HOME}/.config/twitter-mcp/cookies.json"
      }
    }
  }
}
```

这个文件可以提交到 git，其他人 clone 项目后自动获得 MCP 配置。
注意：凭证（cookies）仍然需要每个人自己配置。

### ~/.claude.json — 用户私有配置

`claude mcp add -s user` 写入的位置。包含所有项目通用的 MCP server。
这个文件不应该提交到任何 git 仓库。

---

## 常见问题

### cookies 过期了怎么办？

重新从浏览器提取 `ct0` 和 `auth_token`，更新 `~/.config/twitter-mcp/cookies.json`。
不需要重启 Claude Code，下次调用会自动读取新的 cookies。

### MCP server 没加载？

```bash
# Step 1: 检查注册状态
claude mcp list

# Step 2: 如果显示 ✗ 或没有 twitter，重新注册
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- uvx twikit-mcp
# 或用 pip: -- twikit-mcp

# Step 3: 重启 Claude Code
/exit
claude
```

### 报错 "Couldn't get KEY_BYTE indices" 或搜索失败？

本项目已通过 vendoring 修复了 twikit 2.3.3 的两个已知 bug（正则匹配失败 + 搜索 HTTP 方法错误）。
如果仍遇到问题，请确保使用的是最新版本：

```bash
# uvx 用户
uv cache clean

# pip 用户
pip install --upgrade twikit-mcp
```

### 想让其他 Claude 实例也能用？

MCP 注册在 `~/.claude.json` 的用户级配置中（`-s user`），所以**同一台机器上所有 Claude Code 会话自动共享**。不需要额外配置。

如果是**不同机器**，需要三步：
1. 复制 `~/mcp-servers/twitter-mcp/` 目录（或发布到 git/PyPI）
2. 复制 `~/.config/twitter-mcp/cookies.json`（或重新从浏览器提取）
3. 在新机器上运行 `claude mcp add` 注册命令

### MCP server 需要一直运行吗？

**不需要。** Claude Code 使用 stdio 模式，server 是 Claude Code 的子进程：
- Claude Code 启动 → 自动 spawn server 进程
- Claude Code 退出 → server 进程自动终止
- 你永远不需要手动启动或管理 server 进程

### 和 `~/.claude/settings.json` 的关系？

`~/.claude/settings.json` 是 Claude Code 的**应用设置**（主题、语音等）。
MCP server 注册在 `~/.claude.json`（注意没有 `/` 后的子目录），这是**用户配置文件**。
两者是不同的文件，不要搞混。

---

## 部署到其他机器

### 快速部署（推荐）— 两步搞定

`uvx` 会自动从 GitHub 下载代码、创建虚拟环境、安装依赖，**不需要手动 clone 仓库或 `uv sync`**。

#### Step 1: 配置 Twitter Cookies

```bash
mkdir -p ~/.config/twitter-mcp

cat > ~/.config/twitter-mcp/cookies.json << 'EOF'
{
  "ct0": "你的ct0值",
  "auth_token": "你的auth_token值"
}
EOF

chmod 600 ~/.config/twitter-mcp/cookies.json
```

> 获取方法：浏览器登录 x.com → F12 → Application → Cookies → 复制 `ct0` 和 `auth_token`。
> 详见 [获取 Twitter Cookies](#获取-twitter-cookies) 章节。

#### Step 2: 注册到 Claude Code（一次性）

```bash
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- uvx twikit-mcp
```

完成。重启 Claude Code 即可使用。

#### 这两步分别做了什么？

```
Step 1 — 放认证文件:
  ~/.config/twitter-mcp/cookies.json  ← Twitter 登录凭证

Step 2 — claude mcp add:
  写入一条配置到 ~/.claude.json      ← 告诉 Claude Code 以后怎么启动 server
  （uvx 会在首次调用时自动从 PyPI 下载 twikit-mcp 并缓存）

之后每次启动 Claude Code:
  读配置 → uvx 启动 server（已缓存，秒开） → 可用 → 退出时自动关闭
```

#### 验证

```bash
# 检查注册
claude mcp list
# 应该显示: twitter: uvx ... - ✓ Connected

# 重启 Claude Code
/exit
claude

# 然后直接说人话测试
> 搜一下关于 AI 的推文
> 看看我的时间线
```

### 前置条件

目标机器需要：

```bash
python3 --version   # >= 3.10

# 包管理器（任选一个）
uv --version         # 推荐。没有的话: curl -LsSf https://astral.sh/uv/install.sh | sh
pip --version        # 也行
pipx --version       # 也行

# MCP 客户端（任选一个）
claude --version     # Claude Code
# 或 Cursor、Windsurf、opencode 等
```

> 不需要 git，不需要 SSH key，不需要手动 clone — `uvx` / `pip install` 从 PyPI 自动下载。

### 手动部署（备选方案）

如果你不想用 `uvx` 自动安装，或者网络环境不便访问 GitHub，也可以手动部署：

#### Step 1: 获取代码

```bash
# 方式 A: git clone
mkdir -p ~/mcp-servers && cd ~/mcp-servers
git clone git@github.com:tangivis/twitter-mcp.git

# 方式 B: 从源机器复制
rsync -avz --exclude '.venv' --exclude '__pycache__' \
  ~/mcp-servers/twitter-mcp/ user@target:~/mcp-servers/twitter-mcp/

# 方式 C: 按本文档"从零搭建"章节手动创建
```

#### Step 2: 安装依赖

```bash
cd ~/mcp-servers/twitter-mcp
uv sync
```

#### Step 3: 配置 Cookies

同快速部署的 Step 1。

#### Step 4: 注册到 MCP 客户端

```bash
# Claude Code
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- uv run --directory ~/mcp-servers/twitter-mcp python -m twitter_mcp.server

# 或其他 MCP 客户端：在配置文件中添加 mcpServers 条目
```

> 注意区别：手动部署用 `uv run --directory ...`（指向本地代码），快速部署用 `uvx twikit-mcp`（从 PyPI 自动下载）。

### 跨机器同步更新

修改了 server 代码（比如加了新工具）后：

**如果用的是 `uvx --from git+...` 方式（快速部署）：**

```bash
# 源机器: 提交并推送
cd ~/mcp-servers/twitter-mcp
git add -A && git commit -m "add follow_user tool" && git push

# 目标机器: 清除 uvx 缓存，下次调用自动拉取最新代码
uv cache clean
# 重启 Claude Code 生效
```

**如果用的是 `uv run --directory ...` 方式（手动部署）：**

```bash
# 源机器: 推送
cd ~/mcp-servers/twitter-mcp
git add -A && git commit -m "add follow_user tool" && git push

# 目标机器: 拉取并重装依赖
cd ~/mcp-servers/twitter-mcp
git pull && uv sync
# 重启 Claude Code 生效
```

> 两种方式都不需要重新 `claude mcp add`，只需重启 Claude Code。

### 部署检查清单

```
□ python3 --version                    → >= 3.10
□ uv/pip/pipx --version                → 至少一个已安装
□ MCP 客户端已安装                      → Claude Code / Cursor / opencode 等
□ cat ~/.config/twitter-mcp/cookies.json → ct0 和 auth_token 存在
□ stat -c %a ~/.config/twitter-mcp/cookies.json → 600
□ MCP server 已注册                     → claude mcp list 或检查客户端配置
□ 重启 MCP 客户端后测试                  → 能搜索/发推
```

### Windows 部署

Windows 上也能用，流程和 macOS/Linux 基本一致，只是路径和命令稍有不同。

#### 前置条件

```powershell
# 1. 安装包管理器（任选一个）
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"  # uv（推荐）
# 或直接用 pip

# 2. 确认
python --version   # >= 3.10（Windows 上是 python 不是 python3）
uv --version       # 或 pip --version
```

#### Step 1: 配置 Cookies

```powershell
# 创建目录（用 %APPDATA% 或 用户目录下的 .config 都行）
mkdir %APPDATA%\twitter-mcp

# 创建 cookies.json，写入你的 ct0 和 auth_token
# 文件内容：
# {
#   "ct0": "你的ct0值",
#   "auth_token": "你的auth_token值"
# }
```

也可以放在 `C:\Users\你的用户名\.config\twitter-mcp\cookies.json`，Python 的 `os.path.expanduser("~")` 在 Windows 上会解析到 `C:\Users\你的用户名\`。

#### Step 2: 注册到 MCP 客户端

```powershell
# uvx
claude mcp add twitter -s user ^
  -e "TWITTER_COOKIES=%APPDATA%\twitter-mcp\cookies.json" ^
  -- uvx twikit-mcp

# 或 pip
pip install twikit-mcp
claude mcp add twitter -s user ^
  -e "TWITTER_COOKIES=%APPDATA%\twitter-mcp\cookies.json" ^
  -- twikit-mcp
```

> Windows cmd 用 `^` 换行，PowerShell 用 `` ` `` 换行。

#### 验证

```powershell
claude mcp list
# twitter: uvx ... - ✓ Connected
```

#### Windows 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `uvx` 命令找不到 | uv 没加入 PATH | 重新打开终端，或手动添加 `%USERPROFILE%\.local\bin` 到 PATH |
| SSL 证书错误 | 公司网络代理 | 设置 `set REQUESTS_CA_BUNDLE=你的证书路径` |
| cookies 路径找不到 | 路径分隔符问题 | 用正斜杠 `C:/Users/.../cookies.json` 或环境变量 `%APPDATA%` |
| Python 版本太低 | Windows Store 版本旧 | 从 python.org 下载 3.10+，或 `uv python install 3.12` |

#### Windows vs macOS/Linux 路径对照

| 用途 | macOS/Linux | Windows |
|------|------------|---------|
| Cookies | `~/.config/twitter-mcp/cookies.json` | `%APPDATA%\twitter-mcp\cookies.json` |
| Claude 配置 | `~/.claude.json` | `%USERPROFILE%\.claude.json` |
| uv 缓存 | `~/.cache/uv/` | `%LOCALAPPDATA%\uv\cache\` |

---

## 测试和 CI/CD

```bash
# 本地运行测试
uv sync --group dev
uv run pytest -v
uv run ruff check . && uv run ruff format --check .
```

- **CI：** 每次 push/PR 自动跑 lint + pytest（Linux/macOS/Windows）+ MCP 协议握手
- **CD：** 打 `v*` tag 自动发布到 PyPI

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 自定义和扩展

### 添加新工具

在 `server.py` 中添加一个 `@mcp.tool()` 函数：

```python
@mcp.tool()
async def follow_user(screen_name: str) -> str:
    """Follow a Twitter user.

    Args:
        screen_name: Username to follow (without @).
    """
    client = await _get_client()
    user = await client.get_user_by_screen_name(screen_name)
    await client.follow_user(user.id)
    return json.dumps({"screen_name": screen_name, "status": "followed"})
```

重启 Claude Code 即可使用。

### 支持多账号

修改 cookies.json 结构和 `_get_client()`：

```json
{
  "default": {"ct0": "...", "auth_token": "..."},
  "bot_account": {"ct0": "...", "auth_token": "..."}
}
```

```python
async def _get_client(account: str = "default") -> Client:
    cookies = json.loads(COOKIES_PATH.read_text())
    creds = cookies[account]
    client = Client("en")
    client.set_cookies({"auth_token": creds["auth_token"], "ct0": creds["ct0"]})
    return client
```

### 发布新版本到 PyPI

本项目通过 GitHub Actions 自动发布。打 tag 即可触发：

```bash
# 1. 更新 pyproject.toml 里的 version
# 2. 提交并打 tag
git add -A && git commit -m "release: v0.2.0"
git tag v0.2.0
git push && git push --tags
# 3. GitHub Actions 自动: 跑测试 → 构建 → 发布到 PyPI
```

> 首次发布需要在 PyPI 上配置 Trusted Publisher（见下方说明）。

### 写其他 MCP Server

同样的模式可以封装任何服务：

```bash
cd ~/mcp-servers
uv init my-service-mcp
cd my-service-mcp
mkdir my_service_mcp
touch my_service_mcp/__init__.py
```

```python
# my_service_mcp/server.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("my-service")

@mcp.tool()
async def do_something(param: str) -> str:
    """Description for Claude to understand when to use this tool."""
    # 你的逻辑
    return json.dumps({"result": "..."})

def main():
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
```

```bash
uv sync
claude mcp add my-service -s user -- uv run --directory ~/mcp-servers/my-service-mcp python -m my_service_mcp.server
```
