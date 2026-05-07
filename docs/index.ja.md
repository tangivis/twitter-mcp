# twikit-mcp

**Twitter/X MCP サーバー + CLI — API キー不要。**

[![PyPI](https://img.shields.io/pypi/v/twikit-mcp)](https://pypi.org/project/twikit-mcp/)
[![CI](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/tangivis/twitter-mcp/blob/main/LICENSE)

[MCP](https://modelcontextprotocol.io/) サーバー — Claude(や MCP 対応の AI エージェント)がブラウザ cookies で Twitter/X を操作できます。同じ `twikit-mcp` バイナリは CLI としてもシェルスクリプトやデバッグに使えます。

## 0.1.27 の新機能

- **ツイート動画のダウンロード(yt-dlp)** — 新規 MCP ツール `download_tweet_video` と人間向け CLI `twikit-mcp video <id>` を追加。デフォルトでは `~/Downloads/twikit-mcp/` に保存し、既存の `cookies.json` で認証します。PATH に [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) が必要(`uv tool install yt-dlp`)。`ffmpeg` は `bestvideo+bestaudio` のような複数ストリームのマージが必要な format を渡したときだけ必要です。(closes #84)

アップグレード:`uv tool upgrade twikit-mcp`(または `pip install --upgrade twikit-mcp`)。

## 0.1.26 の新機能

- **`get_tweet` で引用ツイートを公開** — レスポンスに `is_quote_status` / `quoted_id` / `quoted_author` / `quoted_text` が含まれるようになりました。引用リツイートの場合、引用元の作者と本文を即座に確認でき、エージェントが追加で `get_tweet` を呼ぶ必要がありません。これらは元から同じ GraphQL レスポンスに含まれていたものを取り出して公開しただけ。(closes #82)

## 0.1.25 の新機能

- **`get_tweet` に会話コンテキストを追加** — レスポンスに `in_reply_to`(リプライ元ツイートID)と `conversation_id`(スレッドのルートツイートID)が含まれるようになりました。エージェントは1つのリプライから親リンクをユーザーに尋ねることなくスレッド全体を遡れます。(closes #77)

## 0.1.24 の新機能

- **Rich レンダリングのカード** — 0.1.23 のターミナルカードを [Rich](https://github.com/Textualize/rich) が描画するようになりました。emoji と CJK の**列幅計測が正確**(`❤ 🔁` 行で右ボーダーがずれない)、ツイート / プロフィール / bio URL は **OSC 8 でクリッカブル**(iTerm2 / kitty / WezTerm / Windows Terminal / gnome-terminal ≥ 3.36 で cmd-クリックで開きます)。トレンドは真の Table レイアウトに。
- プレーンテキスト出力(非 TTY)は無変更:`| jq` / `> file` / `NO_COLOR=1` の消費者にとってバイト安定が保たれます。

## 0.1.23 の新機能

- **ASCII Twitter カード UI** — `twikit-mcp tweet` / `user` / `tl` / `search` / `trends` がターミナルで box-drawing のカード表示になりました(太字の作者名、薄い表示の作成日時、本文 / カウント / URL の区切り線)。ファイルやパイプへリダイレクト、または `NO_COLOR=1` を設定すると、従来通りのバイト安定なプレーンテキストへ自動フォールバック。出力例は [CLI モード](cli.md)。

## 0.1.22 の新機能

- **ヒューマン CLI サブコマンド** — シェルから直接ツイート / プロフィール / タイムライン / 検索 / トレンドを読めます:

  ```bash
  twikit-mcp tweet 20
  twikit-mcp user elonmusk
  twikit-mcp tl 10
  ```

  プレーンテキスト出力、ネイティブ Unicode、ちょうどいいデフォルト値。詳細は [CLI モード](cli.md)。
- **エンドツーエンド UTF-8 出力** — `\uXXXX` エスケープはもうありません。中文 / 日本語 / Ελληνικά / emoji はすべて読める形でツール出力されます。
- **三言語ドキュメントサイト** — 今ご覧のこのページ。上部で言語を切り替えてください。

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
