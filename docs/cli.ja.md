# CLI モード

`twikit-mcp` はデュアルモードのバイナリです — 同じインストールで、2 つの利用方法。

| モード | コマンド | 使う場面 |
|---|---|---|
| **MCP サーバー**(デフォルト) | `twikit-mcp` または `twikit-mcp serve` | AI エージェント(Claude Code、Cursor、Cline など)から呼び出し、LLM が stdio 経由で JSON-RPC を送る |
| **CLI** | `twikit-mcp list` / `twikit-mcp call <tool> …` | シェルスクリプト、自動化、デバッグ |

両モードとも**同じ cookies ファイル**(`~/.config/twitter-mcp/cookies.json`)と同じ 57 ツールを共有します。

## サブコマンド

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
