# twikit-mcp

**Twitter/X MCP サーバー + CLI — API キー不要。**

[![PyPI](https://img.shields.io/pypi/v/twikit-mcp)](https://pypi.org/project/twikit-mcp/)
[![CI](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/tangivis/twitter-mcp/blob/main/LICENSE)

[MCP](https://modelcontextprotocol.io/) サーバー — Claude(や MCP 対応の AI エージェント)がブラウザ cookies で Twitter/X を操作できます。同じ `twikit-mcp` バイナリは CLI としてもシェルスクリプトやデバッグに使えます。

## 得られるもの

- **57 ツール** — ツイート、ユーザー、リスト、コミュニティ、予約投稿+投票、DM、記事、検索、トレンド、通知。
- **ブラウザ cookie 認証** — X セッションから `ct0` と `auth_token` をコピーするだけ。
- **2 つのトランスポート、1 つのバイナリ** — デフォルトは MCP サーバー(AI エージェント向け)、`twikit-mcp call <tool>` は CLI(シェル向け)。
- **vendored 版 [twikit](https://github.com/d60/twikit)** — プロジェクト固有の防御パッチ付き。

## ドキュメント

- **[CLI モード](cli.md)** — サブコマンド、型変換、終了コード、例。
- **[MCP ツール API](api.md)** — 自動生成のリファレンス:各ツールのシグネチャ、docstring、CLI 例(コードと同期)。
- **[技術設計](TECHNICAL.md)** — 内部実装(現在は中国語のみ — 翻訳歓迎)。
- **[twikit のベンダリング](VENDORING.md)** — すべてのパッチと対応する issue(現在は中国語のみ)。
- **[GitHub リポジトリ](https://github.com/tangivis/twitter-mcp)** — README に三言語のフルインストール手順。

## クイックインストール

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
