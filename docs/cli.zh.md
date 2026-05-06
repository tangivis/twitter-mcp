# CLI 模式

`twikit-mcp` 是双模式二进制 — 同一个安装,两种调用方式。

| 模式 | 命令 | 何时用 |
|---|---|---|
| **MCP server**(默认) | `twikit-mcp` 或 `twikit-mcp serve` | AI agent 里调用(Claude Code、Cursor、Cline 等),LLM 通过 stdio 发 JSON-RPC |
| **CLI** | `twikit-mcp list` / `twikit-mcp call <tool> …` | shell 脚本、自动化、调试 |

两种模式**共享同一个** cookies 文件(`~/.config/twitter-mcp/cookies.json`)和同样的 57 个工具。

## 子命令

### `serve`(默认)

跑 MCP server,通过 stdio 通信。不带子命令时默认走这个 — 现有所有 `mcp.json` / Claude Code / Cursor 配置都不用改。

```bash
twikit-mcp           # 默认 — MCP server
twikit-mcp serve     # 显式
```

### `list`

打印所有注册过的工具名,排序后每行一个。

```bash
$ twikit-mcp list
add_list_member
block_user
…
vote
```

### `call <tool> [key=value …]`

调一个工具,打印 JSON 输出。

```bash
$ twikit-mcp call get_user_info screen_name=elonmusk
{"id":"44196397","screen_name":"elonmusk", …}

$ twikit-mcp call search_tweets query=AI count=5 product=Top
[…]

$ twikit-mcp call get_tweet tweet_id=20 | jq .text
"just setting up my twttr"
```

## 类型转换

CLI 传进来都是字符串,根据工具签名的标注 cast:

| 标注 | 转换 |
|---|---|
| `str` | 直通 |
| `int` / `float` | `int(value)` / `float(value)` |
| `bool` | 宽松匹配:`true / 1 / yes / on`(不区分大小写)→ `True`;其他 → `False` |
| `Optional[X]` / `X \| None` | 拆开取 `X`;**空字符串 → `None`**(显式 escape hatch) |
| 其他 | 当字符串直通 |

KV 切分**只切第一个 `=`** — URL / base64 / JWT 里的额外 `=` 完整保留。

## 退出码

| 码 | 含义 |
|---|---|
| `0` | 成功 |
| `1` | argparse / 用法错误 |
| `2` | `ToolError`(参数校验失败或 twikit 抛了类型化异常) |
| 其他 | 未捕获异常 — bug,请提 issue |

## Tips

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
