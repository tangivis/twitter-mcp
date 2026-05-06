# CLI mode

**[English](#english)** | **[中文](#zh)** | **[日本語](#ja)**

---

## English

`twikit-mcp` is a dual-mode binary: same install, two transports.

| Mode | Command | When |
|---|---|---|
| **MCP server** (default) | `twikit-mcp` or `twikit-mcp serve` | Inside an AI agent (Claude Code, Cursor, Cline, …). LLM sends JSON-RPC over stdio. |
| **CLI** | `twikit-mcp list` / `twikit-mcp call <tool> …` | Shell scripts, automation, debugging. |

Both share the same cookies file (`~/.config/twitter-mcp/cookies.json`) and the same 57 tools.

### Subcommands

#### `serve` (default)

Run the MCP server over stdio. Default when no subcommand given — every existing `mcp.json` / Claude Code / Cursor config keeps working unchanged.

```bash
twikit-mcp           # default — MCP server
twikit-mcp serve     # explicit
```

#### `list`

Print all registered tool names, sorted, one per line.

```bash
$ twikit-mcp list
add_list_member
block_user
…
vote
```

#### `call <tool> [key=value …]`

Invoke one tool, print its JSON output.

```bash
$ twikit-mcp call get_user_info screen_name=elonmusk
{"id":"44196397","screen_name":"elonmusk", …}

$ twikit-mcp call search_tweets query=AI count=5 product=Top
[…]

$ twikit-mcp call get_tweet tweet_id=20 | jq .text
"just setting up my twttr"
```

### Type coercion

CLI args are strings; we cast to the tool's annotated types:

| Annotation | Coercion |
|---|---|
| `str` | passthrough |
| `int` / `float` | `int(value)` / `float(value)` |
| `bool` | loose: `true / 1 / yes / on` (case-insensitive) → `True`; else `False` |
| `Optional[X]` / `X \| None` | unwrap to `X`; **empty string → `None`** explicitly |
| anything else | passthrough as raw string |

KV split is on the **first** `=` only — URLs / base64 / JWTs with extra `=` survive.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Argparse / usage error |
| `2` | `ToolError` (validation rejected the input or twikit raised typed exception) |
| Other | Uncaught exception — bug, please file an issue |

### Tips

```bash
# Pipe to jq
twikit-mcp call get_user_info screen_name=elonmusk | jq .followers_count

# Cron a snapshot
0 10 * * 1   /usr/local/bin/twikit-mcp call get_trends category=trending count=20 \
             > "$HOME/trends/$(date +%F).json"

# Discover args via 'unknown arg' error
$ twikit-mcp call get_user_info bogus=x
Unknown arg `bogus` for tool `get_user_info`. Valid args: ['screen_name', 'user_id']
```

---

## 中文 { #zh }

`twikit-mcp` 是双模式二进制 — 同一个安装,两种调用方式。

| 模式 | 命令 | 何时用 |
|---|---|---|
| **MCP server**(默认) | `twikit-mcp` 或 `twikit-mcp serve` | AI agent 里调用(Claude Code、Cursor、Cline 等),LLM 通过 stdio 发 JSON-RPC |
| **CLI** | `twikit-mcp list` / `twikit-mcp call <tool> …` | shell 脚本、自动化、调试 |

两种模式**共享同一个** cookies 文件(`~/.config/twitter-mcp/cookies.json`)和同样的 57 个工具。

### 子命令

#### `serve`(默认)

跑 MCP server,通过 stdio 通信。不带子命令时默认走这个 — 现有所有 `mcp.json` / Claude Code / Cursor 配置都不用改。

```bash
twikit-mcp           # 默认 — MCP server
twikit-mcp serve     # 显式
```

#### `list`

打印所有注册过的工具名,排序后每行一个。

```bash
$ twikit-mcp list
add_list_member
block_user
…
vote
```

#### `call <tool> [key=value …]`

调一个工具,打印 JSON 输出。

```bash
$ twikit-mcp call get_user_info screen_name=elonmusk
{"id":"44196397","screen_name":"elonmusk", …}

$ twikit-mcp call search_tweets query=AI count=5 product=Top
[…]

$ twikit-mcp call get_tweet tweet_id=20 | jq .text
"just setting up my twttr"
```

### 类型转换

CLI 传进来都是字符串,根据工具签名的标注 cast:

| 标注 | 转换 |
|---|---|
| `str` | 直通 |
| `int` / `float` | `int(value)` / `float(value)` |
| `bool` | 宽松匹配:`true / 1 / yes / on`(不区分大小写)→ `True`;其他 → `False` |
| `Optional[X]` / `X \| None` | 拆开取 `X`;**空字符串 → `None`**(显式 escape hatch) |
| 其他 | 当字符串直通 |

KV 切分**只切第一个 `=`** — URL / base64 / JWT 里的额外 `=` 完整保留。

### 退出码

| 码 | 含义 |
|---|---|
| `0` | 成功 |
| `1` | argparse / 用法错误 |
| `2` | `ToolError`(参数校验失败或 twikit 抛了类型化异常) |
| 其他 | 未捕获异常 — bug,请提 issue |

### Tips

```bash
# 管道接 jq
twikit-mcp call get_user_info screen_name=elonmusk | jq .followers_count

# cron 定期拍快照
0 10 * * 1   /usr/local/bin/twikit-mcp call get_trends category=trending count=20 \
             > "$HOME/trends/$(date +%F).json"

# 通过"未知参数"报错查看可用 args
$ twikit-mcp call get_user_info bogus=x
Unknown arg `bogus` for tool `get_user_info`. Valid args: ['screen_name', 'user_id']
```

---

## 日本語 { #ja }

`twikit-mcp` はデュアルモードのバイナリです — 同じインストールで、2 つの利用方法。

| モード | コマンド | 使う場面 |
|---|---|---|
| **MCP サーバー**(デフォルト) | `twikit-mcp` または `twikit-mcp serve` | AI エージェント(Claude Code、Cursor、Cline など)から呼び出し、LLM が stdio 経由で JSON-RPC を送る |
| **CLI** | `twikit-mcp list` / `twikit-mcp call <tool> …` | シェルスクリプト、自動化、デバッグ |

両モードとも**同じ cookies ファイル**(`~/.config/twitter-mcp/cookies.json`)と同じ 57 ツールを共有します。

### サブコマンド

#### `serve`(デフォルト)

MCP サーバーを stdio で起動。サブコマンドなしのデフォルト動作 — 既存の `mcp.json` / Claude Code / Cursor 設定はそのまま動きます。

```bash
twikit-mcp           # デフォルト — MCP サーバー
twikit-mcp serve     # 明示的
```

#### `list`

登録されたツール名を一行ずつソートして出力。

```bash
$ twikit-mcp list
add_list_member
block_user
…
vote
```

#### `call <tool> [key=value …]`

ツールを 1 回呼び出し、JSON 出力をプリント。

```bash
$ twikit-mcp call get_user_info screen_name=elonmusk
{"id":"44196397","screen_name":"elonmusk", …}

$ twikit-mcp call search_tweets query=AI count=5 product=Top
[…]

$ twikit-mcp call get_tweet tweet_id=20 | jq .text
"just setting up my twttr"
```

### 型変換

CLI 引数は文字列で渡されるので、ツールのアノテーションに合わせて変換:

| アノテーション | 変換 |
|---|---|
| `str` | そのまま |
| `int` / `float` | `int(value)` / `float(value)` |
| `bool` | 緩い一致:`true / 1 / yes / on`(大文字小文字不問)→ `True`;それ以外 → `False` |
| `Optional[X]` / `X \| None` | `X` にアンラップ;**空文字列 → `None`** を明示的にエスケープ |
| その他 | 文字列のままパススルー |

KV 分割は**最初の `=` のみ** — URL / base64 / JWT に含まれる追加の `=` は保持されます。

### 終了コード

| Code | 意味 |
|---|---|
| `0` | 成功 |
| `1` | argparse / 使用法エラー |
| `2` | `ToolError`(引数バリデーション失敗 or twikit が型付き例外を投げた) |
| その他 | キャッチされなかった例外 — バグなので issue を立ててください |

### Tips

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
