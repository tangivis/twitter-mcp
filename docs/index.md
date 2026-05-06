# twikit-mcp

**Twitter/X MCP server + CLI — no API key needed.**

[![PyPI](https://img.shields.io/pypi/v/twikit-mcp)](https://pypi.org/project/twikit-mcp/)
[![CI](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/tangivis/twitter-mcp/blob/main/LICENSE)

**[English](#english)** | **[中文](#zh)** | **[日本語](#ja)**

---

## English

An [MCP](https://modelcontextprotocol.io/) server that lets Claude (or any MCP-compatible AI agent) interact with Twitter/X using browser cookies. The same `twikit-mcp` binary doubles as a CLI for shell scripts and debugging.

### What you get

- **57 tools** covering tweets, users, lists, communities, scheduled tweets + polls, DMs, articles, search, trends, notifications.
- **Browser-cookie auth** — copy `ct0` + `auth_token` from your X session, you're authenticated.
- **Two transports, one binary** — MCP server (default) for AI agents; `twikit-mcp call <tool>` CLI for shells.
- **Vendored [twikit](https://github.com/d60/twikit)** with project-specific defensive patches.

### Where to go

- **[CLI mode](cli.md)** — subcommands, type coercion, exit codes, examples.
- **[MCP Tools API](api.md)** — auto-generated reference: every tool's signature + docstring + CLI example, kept in sync with code.
- **[Technical design](TECHNICAL.md)** — internals.
- **[Vendoring twikit](VENDORING.md)** — every patch and the issue that motivated it.
- **[GitHub repo](https://github.com/tangivis/twitter-mcp)** — README has full install / quickstart in three languages.

### Quick install

```bash
# 1. Drop your X cookies into ~/.config/twitter-mcp/cookies.json
mkdir -p ~/.config/twitter-mcp
cat > ~/.config/twitter-mcp/cookies.json <<'EOF'
{"ct0": "...", "auth_token": "..."}
EOF
chmod 600 ~/.config/twitter-mcp/cookies.json

# 2. Install (recommended for daily use)
uv tool install twikit-mcp

# 3. Register with Claude Code
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- twikit-mcp
```

Use `uv tool upgrade twikit-mcp` to update; full alternatives (uvx / pip / pipx) on the [GitHub README](https://github.com/tangivis/twitter-mcp#readme).

---

## 中文 { #zh }

[MCP](https://modelcontextprotocol.io/) server,让 Claude(或任何 MCP 兼容的 AI agent)用浏览器 cookies 操作 Twitter/X。同一个 `twikit-mcp` 二进制还能当 CLI 用,适合 shell 脚本和调试。

### 你能拿到什么

- **57 个工具** — 推文、用户、列表、社群、定时推文+投票、私信、文章、搜索、趋势、通知。
- **浏览器 cookie 认证** — 从你的 X 会话拷 `ct0` + `auth_token`,搞定。
- **两种传输,一个二进制** — 默认是 MCP server(给 AI agent 用),`twikit-mcp call <tool>` 是 CLI(给 shell 用)。
- **vendored 版 [twikit](https://github.com/d60/twikit)** — 带项目自己打的防御补丁。

### 文档导航

- **[CLI 模式](cli.md)** — 子命令、类型转换、退出码、例子。
- **[MCP 工具 API](api.md)** — 自动生成的参考:每个工具的签名 + docstring + CLI 调用例子,跟代码同步。
- **[技术设计](TECHNICAL.md)** — 内部实现。
- **[Vendoring twikit](VENDORING.md)** — 每个补丁和对应的 issue。
- **[GitHub repo](https://github.com/tangivis/twitter-mcp)** — README 有三语完整安装 / 快速开始。

### 快速安装

```bash
# 1. 把 X cookies 放进 ~/.config/twitter-mcp/cookies.json
mkdir -p ~/.config/twitter-mcp
cat > ~/.config/twitter-mcp/cookies.json <<'EOF'
{"ct0": "...", "auth_token": "..."}
EOF
chmod 600 ~/.config/twitter-mcp/cookies.json

# 2. 安装(日常使用推荐)
uv tool install twikit-mcp

# 3. 注册到 Claude Code
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- twikit-mcp
```

升级用 `uv tool upgrade twikit-mcp`;其他方式(uvx / pip / pipx)见 [GitHub README](https://github.com/tangivis/twitter-mcp#readme)。

---

## 日本語 { #ja }

[MCP](https://modelcontextprotocol.io/) サーバー — Claude(や MCP 対応の AI エージェント)がブラウザ cookies で Twitter/X を操作できます。同じ `twikit-mcp` バイナリは CLI としてもシェルスクリプトやデバッグに使えます。

### 得られるもの

- **57 ツール** — ツイート、ユーザー、リスト、コミュニティ、予約投稿+投票、DM、記事、検索、トレンド、通知。
- **ブラウザ cookie 認証** — X セッションから `ct0` と `auth_token` をコピーするだけ。
- **2 つのトランスポート、1 つのバイナリ** — デフォルトは MCP サーバー(AI エージェント向け)、`twikit-mcp call <tool>` は CLI(シェル向け)。
- **vendored 版 [twikit](https://github.com/d60/twikit)** — プロジェクト固有の防御パッチ付き。

### ドキュメント

- **[CLI モード](cli.md)** — サブコマンド、型変換、終了コード、例。
- **[MCP ツール API](api.md)** — 自動生成のリファレンス:各ツールのシグネチャ、docstring、CLI 例(コードと同期)。
- **[技術設計](TECHNICAL.md)** — 内部実装。
- **[twikit のベンダリング](VENDORING.md)** — すべてのパッチと対応する issue。
- **[GitHub リポジトリ](https://github.com/tangivis/twitter-mcp)** — README に三言語のフルインストール手順。

### クイックインストール

```bash
# 1. X cookies を ~/.config/twitter-mcp/cookies.json に保存
mkdir -p ~/.config/twitter-mcp
cat > ~/.config/twitter-mcp/cookies.json <<'EOF'
{"ct0": "...", "auth_token": "..."}
EOF
chmod 600 ~/.config/twitter-mcp/cookies.json

# 2. インストール(日常利用に推奨)
uv tool install twikit-mcp

# 3. Claude Code に登録
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- twikit-mcp
```

アップグレードは `uv tool upgrade twikit-mcp`;その他のオプション(uvx / pip / pipx)は [GitHub README](https://github.com/tangivis/twitter-mcp#readme) を参照。
