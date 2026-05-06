# CLI モード

`twikit-mcp` はマルチモードのバイナリです。同じインストールで、3 種類の使い方:

| モード | コマンド | 使う場面 |
|---|---|---|
| **MCP サーバー**(デフォルト) | `twikit-mcp` または `twikit-mcp serve` | AI エージェント(Claude Code、Cursor、Cline など)、LLM が stdio 経由で JSON-RPC を送る |
| **ヒューマン CLI** | `twikit-mcp tweet 20`、`twikit-mcp user elonmusk` など | シェルでツイート / プロフィール / タイムラインを直接読みたいとき。出力はプレーンテキスト、ネイティブ Unicode |
| **マシン CLI** | `twikit-mcp list` / `twikit-mcp call <tool> key=value …` | シェルスクリプト、自動化、デバッグ。生 JSON 出力、57 ツール全部呼べる |

3 モードとも**同じ cookies ファイル**(`~/.config/twitter-mcp/cookies.json`)を共有します。

## ヒューマン用サブコマンド

整形済みテキスト、位置引数、JSON なし。「X を読みたい」の典型ケースを 5 つカバー:

```bash
twikit-mcp tweet 20                       # 1 ツイートを整形表示
twikit-mcp tweet https://x.com/jack/status/20  # URL も可
twikit-mcp user elonmusk                  # 1 プロフィール
twikit-mcp tl 10                          # 自分のホームタイムライン直近 10 件
twikit-mcp search "AI" 5                  # "AI" のトップ 5 検索結果
twikit-mcp trends 20                      # トップ 20 トレンド
```

ターミナルでの出力例(0.1.23+ ASCII Twitter カード):

```text
╭──────────────────────────────────────────────────────────────────────────────╮
│ Pathfinder Sports · @pathfinderSport                                         │
│ Sat Feb 21 16:55:22 +0000 2009                                               │
├──────────────────────────────────────────────────────────────────────────────┤
│ Άρσεναλ - Σάντερλαντ: (X) 0-0 τελικό                                         │
├──────────────────────────────────────────────────────────────────────────────┤
│ ❤ 7,269    🔁 5,473                                                          │
│ https://x.com/pathfinderSport/status/1234567890                              │
╰──────────────────────────────────────────────────────────────────────────────╯
```

幅はターミナルの列数に合わせて [60, 100] にクランプされます。**ファイルやパイプにリダイレクト、または `NO_COLOR=1` を設定するとバイト安定なプレーンテキストへ自動フォールバック** — 形は 0.1.22 と同じで、`jq` / `grep` / diff にそのまま使えます:

```text
@pathfinderSport · Pathfinder Sports
Άρσεναλ - Σάντερλαντ: (X) 0-0 τελικό
❤ 7,269  🔁 5,473  · Sat Feb 21 16:55:22 +0000 2009
https://x.com/pathfinderSport/status/1234567890
```

これらは同じ MCP ツール群の薄いラッパーです。より細かな引数(`product=Latest` / カスタム `cursor` など)が必要なら `call` を使ってください。

## マシン用サブコマンド

### `serve`(デフォルト)

MCP サーバーを stdio で起動。サブコマンドなしのデフォルト動作 — 既存の `mcp.json` / Claude Code / Cursor 設定はそのまま動きます。

```bash
twikit-mcp           # デフォルト — MCP サーバー
twikit-mcp serve     # 明示的
```

### `list`

登録されたツール名を一行ずつソートして出力。

```bash
$ twikit-mcp list
add_list_member
block_user
…
vote
```

### `call <tool> [key=value …]`

ツールを 1 回呼び出し、JSON 出力をプリント。

```bash
$ twikit-mcp call get_user_info screen_name=elonmusk
{"id":"44196397","screen_name":"elonmusk", …}

$ twikit-mcp call search_tweets query=AI count=5 product=Top
[…]

$ twikit-mcp call get_tweet tweet_id=20 | jq .text
"just setting up my twttr"
```

## 型変換

CLI 引数は文字列で渡されるので、ツールのアノテーションに合わせて変換:

| アノテーション | 変換 |
|---|---|
| `str` | そのまま |
| `int` / `float` | `int(value)` / `float(value)` |
| `bool` | 緩い一致:`true / 1 / yes / on`(大文字小文字不問)→ `True`;それ以外 → `False` |
| `Optional[X]` / `X \| None` | `X` にアンラップ;**空文字列 → `None`** を明示的にエスケープ |
| その他 | 文字列のままパススルー |

KV 分割は**最初の `=` のみ** — URL / base64 / JWT に含まれる追加の `=` は保持されます。

## 終了コード

| Code | 意味 |
|---|---|
| `0` | 成功 |
| `1` | argparse / 使用法エラー |
| `2` | `ToolError`(引数バリデーション失敗 or twikit が型付き例外を投げた) |
| その他 | キャッチされなかった例外 — バグなので issue を立ててください |

## Tips

```bash
# jq にパイプ
twikit-mcp call get_user_info screen_name=elonmusk | jq .followers_count

# cron で定期スナップショット
0 10 * * 1   /usr/local/bin/twikit-mcp call get_trends category=trending count=20 \
             > "$HOME/trends/$(date +%F).json"

# 未知の引数エラーで有効な args を発見
$ twikit-mcp call get_user_info bogus=x
Unknown arg `bogus` for tool `get_user_info`. Valid args: ['screen_name', 'user_id']
```

---

## すべてのツール(マシン CLI)

--8<-- "docs/_cli_tools.ja.md"
