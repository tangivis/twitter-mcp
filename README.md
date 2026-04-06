<div align="center">

# twikit-mcp

**Twitter/X MCP Server — No API Key Required**

[![CI](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/twikit-mcp)](https://pypi.org/project/twikit-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/twikit-mcp)](https://pypi.org/project/twikit-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An [MCP](https://modelcontextprotocol.io/) server that lets Claude interact with Twitter/X using browser cookies.
No Twitter API key needed. Free forever.

**[English](#english)** | **[中文](#中文)** | **[日本語](#日本語)**

</div>

---

<a id="english"></a>

## English

### Why twikit-mcp?

|  | twikit-mcp (this project) | Other Twitter MCP servers |
|--|---------------------------|--------------------------|
| **Auth** | Browser cookies | Twitter API Key |
| **Cost** | Free | $200+/month |
| **Setup** | 2 steps, 2 minutes | Apply for developer account, wait for approval |
| **Library** | [twikit](https://github.com/d60/twikit) (reverse-engineered) | [tweepy](https://github.com/tweepy/tweepy) (official API) |

### Quick Start

**Prerequisites:** [uv](https://docs.astral.sh/uv/), [Claude Code](https://claude.ai/code)

#### 1. Get your Twitter cookies

1. Log in to [x.com](https://x.com) in your browser
2. Open DevTools (F12) → **Application** → **Cookies** → `https://x.com`
3. Copy `ct0` and `auth_token`

```bash
mkdir -p ~/.config/twitter-mcp
cat > ~/.config/twitter-mcp/cookies.json << 'EOF'
{"ct0": "YOUR_CT0", "auth_token": "YOUR_AUTH_TOKEN"}
EOF
chmod 600 ~/.config/twitter-mcp/cookies.json
```

#### 2. Register with Claude Code (one-time)

```bash
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- uvx twikit-mcp
```

That's it. Restart Claude Code and start talking:

```
> Search tweets about AI
> What did @elonmusk post recently?
> Send a tweet saying: Hello from Claude!
```

### Available Tools

| Tool | Description |
|------|-------------|
| `send_tweet` | Post a tweet or reply |
| `get_tweet` | Fetch a tweet by ID or URL |
| `get_timeline` | Get home timeline |
| `search_tweets` | Search tweets (Latest/Top) |
| `like_tweet` | Like a tweet |
| `retweet` | Retweet a tweet |
| `get_user_tweets` | Get tweets from a specific user |

### How It Works

```
You: "Search tweets about AI"
 → Claude Code (understands intent)
 → MCP Protocol (JSON-RPC over stdio)
 → twikit-mcp (this server)
 → twikit (browser-like requests)
 → Twitter GraphQL API
```

Claude Code automatically manages the server process — it starts when Claude Code launches and stops when it exits. No background services, no manual setup.

### Windows

```powershell
mkdir %APPDATA%\twitter-mcp
# Create cookies.json with your ct0 and auth_token

claude mcp add twitter -s user ^
  -e "TWITTER_COOKIES=%APPDATA%\twitter-mcp\cookies.json" ^
  -- uvx twikit-mcp
```

### Documentation

- **[Technical Guide](docs/TECHNICAL.md)** — Architecture, MCP internals, configuration details
- **[Contributing](CONTRIBUTING.md)** — Testing, CI/CD, how to add new tools

---

<a id="中文"></a>

## 中文

### 为什么选 twikit-mcp？

|  | twikit-mcp（本项目） | 其他 Twitter MCP |
|--|---------------------|-----------------|
| **认证** | 浏览器 Cookies | Twitter API Key |
| **费用** | 免费 | $200+/月 |
| **配置** | 2 步，2 分钟 | 申请开发者账号，等审批 |
| **底层** | [twikit](https://github.com/d60/twikit)（逆向工程） | [tweepy](https://github.com/tweepy/tweepy)（官方 API） |

### 快速开始

**前置条件：** [uv](https://docs.astral.sh/uv/)、[Claude Code](https://claude.ai/code)

#### 1. 获取 Twitter Cookies

1. 用浏览器登录 [x.com](https://x.com)
2. F12 打开 DevTools → **Application** → **Cookies** → `https://x.com`
3. 复制 `ct0` 和 `auth_token`

```bash
mkdir -p ~/.config/twitter-mcp
cat > ~/.config/twitter-mcp/cookies.json << 'EOF'
{"ct0": "你的ct0", "auth_token": "你的auth_token"}
EOF
chmod 600 ~/.config/twitter-mcp/cookies.json
```

#### 2. 注册到 Claude Code（一次性）

```bash
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- uvx twikit-mcp
```

搞定。重启 Claude Code，直接说人话：

```
> 搜一下关于 AI 的推文
> 看看 @elonmusk 最近发了什么
> 发一条推说：Hello from Claude!
```

### 可用工具

| 工具 | 功能 | 怎么用 |
|------|------|--------|
| `send_tweet` | 发推/回复 | "发一条推说..." |
| `get_tweet` | 获取推文 | "看看这条推文 [链接]" |
| `get_timeline` | 刷时间线 | "看看我的时间线" |
| `search_tweets` | 搜索推文 | "搜一下关于 XX 的推文" |
| `like_tweet` | 点赞 | "点赞这条推" |
| `retweet` | 转推 | "转推这个" |
| `get_user_tweets` | 看某人的推 | "看看 @xxx 最近发了什么" |

### 工作原理

```
你："搜一下关于 AI 的推文"
 → Claude Code（理解意图）
 → MCP 协议（JSON-RPC，stdio 通信）
 → twikit-mcp（本 server）
 → twikit（模拟浏览器请求）
 → Twitter GraphQL API
```

Claude Code 自动管理 server 进程——启动时拉起，退出时关闭。不需要手动运行任何东西，不占后台资源。

### Windows

```powershell
mkdir %APPDATA%\twitter-mcp
# 创建 cookies.json，写入 ct0 和 auth_token

claude mcp add twitter -s user ^
  -e "TWITTER_COOKIES=%APPDATA%\twitter-mcp\cookies.json" ^
  -- uvx twikit-mcp
```

### 文档

- **[技术文档](docs/TECHNICAL.md)** — 架构、MCP 原理、配置详解、跨机器部署
- **[贡献指南](CONTRIBUTING.md)** — 测试、CI/CD、如何添加新工具

---

<a id="日本語"></a>

## 日本語

### なぜ twikit-mcp？

|  | twikit-mcp（本プロジェクト） | 他の Twitter MCP |
|--|---------------------------|-----------------|
| **認証** | ブラウザ Cookie | Twitter API Key |
| **料金** | 無料 | $200+/月 |
| **セットアップ** | 2ステップ、2分 | 開発者アカウント申請、承認待ち |
| **ライブラリ** | [twikit](https://github.com/d60/twikit)（リバースエンジニアリング） | [tweepy](https://github.com/tweepy/tweepy)（公式 API） |

### クイックスタート

**前提条件：** [uv](https://docs.astral.sh/uv/)、[Claude Code](https://claude.ai/code)

#### 1. Twitter Cookie の取得

1. ブラウザで [x.com](https://x.com) にログイン
2. F12 で DevTools を開く → **Application** → **Cookies** → `https://x.com`
3. `ct0` と `auth_token` をコピー

```bash
mkdir -p ~/.config/twitter-mcp
cat > ~/.config/twitter-mcp/cookies.json << 'EOF'
{"ct0": "あなたのct0", "auth_token": "あなたのauth_token"}
EOF
chmod 600 ~/.config/twitter-mcp/cookies.json
```

#### 2. Claude Code に登録（一度だけ）

```bash
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- uvx twikit-mcp
```

以上です。Claude Code を再起動して、自然言語で話しかけてください：

```
> AIに関するツイートを検索して
> @elonmusk の最近の投稿を見せて
> 「Hello from Claude!」とツイートして
```

### 利用可能なツール

| ツール | 機能 | 使い方 |
|--------|------|--------|
| `send_tweet` | ツイート投稿・返信 | 「〜とツイートして」 |
| `get_tweet` | ツイート取得 | 「このツイートを見て [URL]」 |
| `get_timeline` | タイムライン取得 | 「タイムラインを見せて」 |
| `search_tweets` | ツイート検索 | 「〜について検索して」 |
| `like_tweet` | いいね | 「このツイートにいいねして」 |
| `retweet` | リツイート | 「これをリツイートして」 |
| `get_user_tweets` | ユーザーのツイート取得 | 「@xxx の最近の投稿を見せて」 |

### 仕組み

```
あなた：「AIに関するツイートを検索して」
 → Claude Code（意図を理解）
 → MCP プロトコル（JSON-RPC、stdio 通信）
 → twikit-mcp（本サーバー）
 → twikit（ブラウザリクエストをシミュレート）
 → Twitter GraphQL API
```

Claude Code がサーバープロセスを自動管理します。起動時にプロセスを立ち上げ、終了時に自動停止。手動操作やバックグラウンドサービスは不要です。

### Windows

```powershell
mkdir %APPDATA%\twitter-mcp
# cookies.json を作成し、ct0 と auth_token を記入

claude mcp add twitter -s user ^
  -e "TWITTER_COOKIES=%APPDATA%\twitter-mcp\cookies.json" ^
  -- uvx twikit-mcp
```

### ドキュメント

- **[技術ドキュメント](docs/TECHNICAL.md)** — アーキテクチャ、MCP の仕組み、設定詳細
- **[コントリビューションガイド](CONTRIBUTING.md)** — テスト、CI/CD、新しいツールの追加方法

---

<div align="center">

## License

MIT

Built with [twikit](https://github.com/d60/twikit) and [MCP](https://modelcontextprotocol.io/)

</div>
