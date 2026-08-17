# twikit-mcp

**Twitter/X MCP サーバー + CLI — API キー不要。**

[![PyPI](https://img.shields.io/pypi/v/twikit-mcp)](https://pypi.org/project/twikit-mcp/)
[![CI](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/tangivis/twitter-mcp/blob/main/LICENSE)

[MCP](https://modelcontextprotocol.io/) サーバー — Claude(や MCP 対応の AI エージェント)がブラウザ cookies で Twitter/X を操作できます。同じ `twikit-mcp` バイナリは CLI としてもシェルスクリプトやデバッグに使えます。

## 0.1.43 の新機能

- **README のクライアント一覧の陳腐化を解消** — Pi(0.1.34 で文書化)と DeepSeek Harness(0.1.40)が 3 言語すべての "Works with" 一行要約から漏れていました。その行とインストールページを結ぶ仕組みが無かったためです。両方を追記し、インストールページの各クライアントカードがすべての README 要約に現れることを検証するセンチネルテストを追加しました。次のクライアントが静かに漏れることはありません。ドキュメント + テストのみ。

## 0.1.42 の新機能

- **凍結アカウント 1 つで `get_retweeters` 全体が落ちる問題を修正** — リツイート者の誰かが凍結・削除されていると、X はそのエントリを `__typename: UserUnavailable` として返し、そこには `rest_id` がありません。twikit の `User.__init__` はこのキーを無条件に読むため、**死んだアカウント 1 つで呼び出し全体が `KeyError: 'rest_id'`** で落ちていました。解析できないエントリはスキップし、残りを返すようになりました。`get_favoriters` も同じコードパスなので同時に修正されます。2026-08-17 の live-smoke(実 X)で検出。(issue #37)
- 同じ関数の 1 行隣も併せて堅牢化:カーソル抽出が「末尾 2 件は必ずカーソル」を前提にしており、カーソルを含まない応答で `KeyError` になっていました。取得できない場合は `None` を返します。

アップグレード:`uv tool upgrade twikit-mcp`(または `pip install --upgrade twikit-mcp`)。

## 0.1.41 の新機能

- **XChat(暗号化 DM)をローカルで読む** — 新ツール 3 つでレジストリは 62 に:`xchat_status`、`xchat_list_conversations`、`xchat_get_history`。X の web クライアントは会話を復号して平文をローカルの SQLite に保存しており、これらはそれを読みます。**新規依存なし、ネットワークなし、認証情報なし、書き込み経路なし** — DB は `mode=ro&immutable=1` で開き、全ステートメントが SELECT、暗号鍵は決して読まず、ここで読んでも X 上で既読になりません。`XCHAT_BROWSER`(chrome/chromium/edge/brave/aside)、`XCHAT_BROWSER_PROFILE`、`XCHAT_DATABASE_PATH` で設定します。未設定ならツールは休止し、server の他の部分に影響しません。[XChat ページ](xchat.md)を参照。(closes #118)
- [@DJNgoma](https://github.com/DJNgoma) に感謝 — SQLite 読み取りとブラウザプロファイル探索は PR #107 の彼の実装に基づいています。

アップグレード:`uv tool upgrade twikit-mcp`(または `pip install --upgrade twikit-mcp`)。

## 0.1.40 の新機能

- **DeepSeek Harness(dsh)のセットアップ手順** — [インストールページ](install.md)に [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) を追加。Pi と違い dsh は公式の MCP クライアント(`@deepseek-ai/dsh-mcp-client`)を同梱しているためコミュニティ拡張は不要ですが、設定は通常の `mcpServers` マップではなく `cordis.yml` のプラグインエントリで、**ツールの許可リストがない**ため 59 ツールすべてが登録されます。カードではその両方に加え、知っておく価値のある `failOnStartupError` と `toolCallTimeoutMs` にも触れています。ドキュメントのみの変更 — コードは変更なし、`twikit-mcp` は標準的な stdio MCP server なので特別な対応は不要です。

## 0.1.39 の新機能

- **MCP Python SDK v2 へ移行** — server は削除された `FastMCP` ではなく `MCPServer`(`mcp.server.mcpserver`)ベースになり、依存は `mcp[cli]>=1.27,<2` から `>=2,<3` へ移りました。**プロトコルレベルでの変更はありません**:`tools/list` の完全なペイロード —— ネゴシエートされたプロトコルバージョン、capabilities、59 ツールすべての入出力スキーマ —— は 0.1.38 とバイト単位で同一です(58,843 バイト、実際の stdio ハンドシェイクで両 SDK を比較検証)。アップグレードすると SDK 2.x が入ります。自分で `mcp<2` を固定している場合は 0.1.38 に留まってください。(closes #109)
- **`serverInfo.version` が実際のパッケージバージョンを返すように** — SDK v1 はこのフィールドを自身のバージョンで埋めており、v2 は未設定だと空になります。クライアントは initialize 応答で `twikit-mcp` の実バージョンを見られるようになりました。

アップグレード:`uv tool upgrade twikit-mcp`(または `pip install --upgrade twikit-mcp`)。

## 0.1.38 の新機能

- **MCP 2026-07-28 仕様への地ならし** — MCP Python SDK 2.0.0 が正式リリースされ、本 server が依存するクラスがリネームされました(`FastMCP` → `MCPServer`)。既存のインストールに影響はありません:0.1.35 以降、依存は SDK 1.x に固定されています。今回のリリースでは SDK のプライベートなツールレジストリへのアクセスをすべて単一の内部アクセサに集約し、今後の v2 移行を約 70 箇所の書き換えから 1 行の変更に変えました。純粋な内部リファクタリング —— 動作の変更はなく、生成されるドキュメントと CLI 出力はバイト単位で同一です。(issue #109 phase 2)

アップグレード:`uv tool upgrade twikit-mcp`(または `pip install --upgrade twikit-mcp`)。

## 0.1.37 の新機能

- **`get_dm_history` が message request でクラッシュしなくなりました** — 知らない人の message request を承認すると、X は会話タイムラインに `trust_conversation` システムエントリを挿入し、旧版は `KeyError: 'message'` で落ちていました。非メッセージエントリはスキップして新フィールド `timeline_events` で返し、`warnings` フィールドでエンドツーエンド暗号化(X Chat)会話の履歴が不完全な可能性を警告します — legacy DM API は暗号化本文を取得できないため、agent は「返信が無かった」と断定すべきではありません。通常の会話の JSON 形状は従来と完全に同一です。(closes #104)
- **初回 DM 直後の履歴取得で "User not found" と誤報しません** — 最初の DM を送った直後の読み取りは X 側で一時的に 404 になることがあります。最大 3 回の短いバックオフ付きリトライを行い、それでも失敗する場合はユーザーではなく会話が利用不可であると正しく報告します。(closes #102)
- 実機での診断と両パッチ(PR #103、#105)を提供してくれた [@DJNgoma](https://github.com/DJNgoma) に感謝します。

アップグレード:`uv tool upgrade twikit-mcp`(または `pip install --upgrade twikit-mcp`)。

## 0.1.36 の新機能

- **整数 ID を全ツールで受け付け** — X はツイート/ユーザー/リスト ID を JSON の**数値**として返します(`"id": 2087887408440164663`、その隣に `"id_str"`)。数値の `id` をそのまま渡すクライアント(`str()` なしの `{"tweet_id": id}`)は、これまでツールコードが動く前にバリデーションで拒否されていました(`Input should be a valid string`)。今回、snowflake 形の全パラメータ(59 ツール中 37 箇所:`tweet_id`、`user_id`、`list_id`、`media_ids` など)が int / string の両方を受け付け、無損失で文字列に変換します。float は引き続き拒否:これらの ID は 2^53 を超えるため float は既に精度が壊れており、黙って受け付けると別のツイートを操作してしまいます。(closes #111)

アップグレード:`uv tool upgrade twikit-mcp`(または `pip install --upgrade twikit-mcp`)。

## 0.1.35 の新機能

- **MCP SDK を v2 未満に固定** — `mcp[cli]` に上限がなく、2.0.0 がプレリリースを抜けた時点で新規の `uv tool install twikit-mcp` が SDK v2 を取得してしまう状態でした。v2([2026-07-28 仕様](https://blog.modelcontextprotocol.io/posts/2026-07-28/)実装)は `FastMCP` を `MCPServer` にリネームし `mcp.server.fastmcp.*` を `mcp.server.mcpserver.*` へ移動するため、本 server は import 時点で落ちます。`>=1.27,<2` に固定し、センチネルテストで保護しました。既存インストールの挙動は変わりません。移行は issue #109 で追跡。

## 0.1.34 の新機能

- **Pi のセットアップ手順** — [インストールページ](install.md)に [Pi](https://github.com/earendil-works/pi) を追加。Pi には MCP が組み込まれていないため、コミュニティ製 MCP 拡張(`pi-mcp-adapter`)の導入と、その `directTools` 許可リストで本 server の 59 ツールがコーディングセッションのコンテキストを圧迫しないようにする手順を記載しました。ドキュメントのみの変更 — コードは変更なし、`twikit-mcp` は標準的な stdio MCP server なので特別な対応は不要です。

## 0.1.33 の新機能

- **200 文字の切り捨てを廃止** — `get_timeline` / `search_tweets` / `get_user_tweets` / `get_bookmarks` / `get_list_tweets` / `get_scheduled_tweets` / `get_community_tweets` / `get_communities_timeline` / `search_community_tweet` がツイート本文を 200 文字でカットしなくなりました。`get_tweet` と `get_tweet_replies` も `Tweet.full_text` を使用し、X のノートツイート(長文投稿、最大 4000 文字)も完全に取得できます。レスポンスサイズは `count` 引数で制御。(closes #97)
- **`get_article_preview` の引用ツイート対応** — 入力が引用リツイートの場合、エラーが「これは引用ツイートで、記事ではありません。引用内容は get_tweet で読んでください」に変わり、汎用の "does not embed an article" は出なくなりました。

## 0.1.32 の新機能

- **ツイート返信の取得** — 新規 `get_tweet_replies(tweet_id, cursor=None)` ツールでツイートへのコメント / リプライを取得。vendored twikit 経由で X の TweetDetail GraphQL を使用、1 ページごとに `next_cursor` で次ページ。リプライアイテムは `get_user_tweets` / `get_timeline` と同じコンパクト形式。(closes #94)

## 0.1.31 の新機能

- **クライアント別インストール手順を文書化** — 新規[インストールページ](install.md)で Claude Code / Claude Desktop / Cursor / Windsurf / Cline / opencode 6 クライアントへの登録手順を整理(クライアントあたり ≤ 12 行、設定ファイルパス + JSON スニペットのみ)。インストールコマンドは `uv tool install twikit-mcp` 統一、JSON の形はどのクライアントでも共通。(closes #92)

## 0.1.30 の新機能

- **API ドキュメントページのローカライズ** — `/zh/api/` と `/ja/api/` で中国語 / 日本語の chrome(タイトル、イントロ、テーブルヘッダ、セクション名)を表示するようになりました。英語へフォールバックしません。ツールの docstring は Python ソースのまま(`mkdocstrings` と同じトレードオフ)。(closes #90)

## 0.1.29 の新機能

- **Community と article-preview の信頼性向上** — `get_community` / `get_community_tweets` / `get_community_members` / `get_community_moderators` / `search_community_tweet` が `KeyError: 'rest_id'` / `IndexError` でクラッシュしなくなりました。`get_article_preview` は syndication エンドポイントが 404(X が古い記事を削除)を返した場合、`HTTPStatusError` のスタックトレースを漏らさずクリーンな `ToolError` を返します。`_vendor/twikit/community.py` + `client.py` の全面 `.get()` 防御化。**Issue #76 完了** — `T_DRIFT` は空集合になりました。(issue #76 parts 2 + 3)

## 0.1.28 の新機能

- **List ツールの信頼性向上** — `get_list` / `get_list_tweets` / `get_list_members` / `get_list_subscribers` がバーナー識別子で X にゲートされたレスポンス上で `KeyError: 'created_at'` / `IndexError` / `Invalid list id` でクラッシュしなくなりました。`_vendor/twikit/list.py` + `client.py` の全面 `.get()` 防御化:欠損フィールドは `None`/`""`/`0`、空 entries は空の `Result` を返します。live-smoke の `T_LIST` から `T_DRIFT` フォールバックも除去 — このクラスの再発を即座に検知できます。(issue #76 part 1)

## 0.1.27 の新機能

- **ツイート動画のダウンロード(yt-dlp)** — 新規 MCP ツール `download_tweet_video` と人間向け CLI `twikit-mcp video <id>` を追加。デフォルトでは `~/Downloads/twikit-mcp/` に保存し、既存の `cookies.json` で認証します。PATH に [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) が必要(`uv tool install yt-dlp`)。`ffmpeg` は `bestvideo+bestaudio` のような複数ストリームのマージが必要な format を渡したときだけ必要です。(closes #84)

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
