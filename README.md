<div align="center">

# twikit-mcp

**Twitter/X MCP Server — No API Key Required**

[![CI](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/twikit-mcp)](https://pypi.org/project/twikit-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/twikit-mcp)](https://pypi.org/project/twikit-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An [MCP](https://modelcontextprotocol.io/) server that lets Claude (or any MCP-compatible AI agent) interact with Twitter/X using browser cookies.
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

#### 1. Create cookies.json

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

> **What are these?** `ct0` is the CSRF token (~160 hex chars), `auth_token` is your session token (40 hex chars). They are found in your browser cookies after logging in to x.com. Cookies expire — `auth_token` typically lasts several months, `ct0` may be shorter. Re-extract from your browser when expired.

#### 2. Install & register

Choose **one** of the following methods:

**Option A: uvx** — zero-install, fetches each call (slow first run, fast after; cache shared with other uv tools). Best for quick try-out.

```bash
# Claude Code
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- uvx twikit-mcp

# Or run directly
uvx twikit-mcp
```

**Option B: `uv tool install`** *(recommended for daily use)* — pinned isolated venv, instant startup, simple upgrade path.

```bash
# Install once. Drops a `twikit-mcp` binary on PATH (~/.local/bin).
uv tool install twikit-mcp

# List your installed uv tools (sanity check)
uv tool list

# Upgrade when a new version ships
uv tool upgrade twikit-mcp
# Or upgrade ALL uv-tool-managed binaries at once:
uv tool upgrade --all

# Uninstall (clean removal of the venv + binary)
uv tool uninstall twikit-mcp
```

Then register with Claude Code (uses the binary on PATH — no `uvx` prefix):

```bash
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- twikit-mcp
```

The cookies file is **the same** as for every other option: `~/.config/twitter-mcp/cookies.json` (or wherever `TWITTER_COOKIES` env var points). `uv tool install` doesn't change where config lives — only where the *binary* lives.

> uvx vs `uv tool install` quick rule: use **uvx** if you'll call it once or twice (e.g. one-off script). Use **`uv tool install`** if it's part of your dev workflow (e.g. wired into Claude Code daily) — startup is instant after the one-time install.

**Option C: pip**

```bash
pip install twikit-mcp

# Claude Code
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- twikit-mcp

# Or run directly
TWITTER_COOKIES=~/.config/twitter-mcp/cookies.json twikit-mcp
```

**Option D: pipx** (isolated install — same idea as `uv tool install`, but with pipx)

```bash
pipx install twikit-mcp

# Claude Code
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- twikit-mcp
```

#### Using with other MCP clients

This is a standard MCP server (stdio transport). It works with **any** MCP-compatible client — not just Claude Code.

Add to your MCP client config (e.g. `mcp.json`, `settings.json`):

```json
{
  "mcpServers": {
    "twitter": {
      "command": "twikit-mcp",
      "env": {
        "TWITTER_COOKIES": "/home/YOU/.config/twitter-mcp/cookies.json"
      }
    }
  }
}
```

> Works with: Claude Code, Claude Desktop, Cursor, Windsurf, opencode, Cline, etc.

That's it. Start talking:

```
> Search tweets about AI
> What did @elonmusk post recently?
> Send a tweet saying: Hello from Claude!
```

#### CLI mode (no MCP client needed)

The same `twikit-mcp` binary doubles as a one-shot CLI. Two modes:

**Human-friendly subcommands** — pretty-print tweets, profiles, timeline directly:

```bash
twikit-mcp tweet 20                     # show tweet 20 (Jack's first one)
twikit-mcp tweet https://x.com/u/status/123    # URL works too
twikit-mcp user elonmusk                # pretty profile
twikit-mcp tl 10                        # last 10 tweets from your home timeline
twikit-mcp search "AI" 5                # 5 top results for "AI"
twikit-mcp trends 20                    # top 20 trending topics
```

Output is plain text — readable in any terminal, native unicode (no `\uXXXX` escapes).

**Machine-friendly subcommands** — raw JSON, `key=value` args, every one of the 57 MCP tools:

```bash
twikit-mcp list                         # all 57 tool names
twikit-mcp call get_user_info screen_name=elonmusk
twikit-mcp call search_tweets query=AI count=5 product=Top
twikit-mcp call get_user_info screen_name=elonmusk | jq .followers_count
```

**MCP server mode** — the default when no subcommand is given:

```bash
twikit-mcp                              # stdio JSON-RPC for MCP clients
twikit-mcp serve                        # explicit, same behavior
```

All three modes share the same `~/.config/twitter-mcp/cookies.json` — no separate config.

### Available Tools

| Tool | Description |
|------|-------------|
| `send_tweet` | Post a tweet or reply |
| `get_tweet` | Fetch a tweet by ID or URL |
| `get_timeline` | Get home timeline |
| `search_tweets` | Search tweets (Latest/Top) |
| `like_tweet` | Like a tweet |
| `retweet` | Retweet a tweet |
| `get_user_info` | Get a user's profile metadata by `screen_name` OR `user_id` |
| `get_user_tweets` | Get tweets from a specific user |
| `get_user_followers` | List a user's followers (paginated via `cursor`, max 100/call) |
| `get_user_following` | List who a user follows (paginated via `cursor`, max 100/call) |
| `follow_user` | Follow a user by screen name |
| `unfollow_user` | Unfollow a user by screen name |
| `delete_tweet` | Delete a tweet by ID |
| `unfavorite_tweet` | Unlike a tweet by ID |
| `delete_retweet` | Un-retweet a tweet by ID |
| `bookmark_tweet` | Bookmark a tweet (optional `folder_id`) |
| `delete_bookmark` | Remove a tweet from bookmarks |
| `get_bookmarks` | List bookmarked tweets (paginated via `cursor`, max 100/call) |
| `get_favoriters` | List users who liked a tweet (paginated via `cursor`, max 100/call) |
| `get_retweeters` | List users who retweeted a tweet (paginated via `cursor`, max 100/call) |
| `search_user` | Search for users by query (paginated via `cursor`, max 100/call) |
| `get_trends` | Get trending topics by category (`trending`/`for-you`/`news`/`sports`/`entertainment`) |
| `get_article_preview` | Get title / preview / cover of an X Article embedded in a tweet (no auth) |
| `get_article` | Fetch an X Article's body — `format="preview" \| "plain" \| "full"` (default `"plain"`) |
| `block_user` | Block a user by screen name (rate-limited — avoid bulk) |
| `unblock_user` | Unblock a user by screen name |
| `mute_user` | Mute a user by screen name (rate-limited — avoid bulk) |
| `unmute_user` | Unmute a user by screen name |
| `get_notifications` | Fetch notifications — `type="All"\|"Verified"\|"Mentions"` (paginated via `cursor`, max 100/call) |
| `send_dm` | ⚠️ Send a PRIVATE DM to a user — do not bulk-call |
| `send_dm_to_group` | ⚠️ Send a PRIVATE DM to a group conversation — do not bulk-call |
| `get_dm_history` | ⚠️ Get DM conversation history with a user (private — paginate via `max_id`) |
| `delete_dm` | ⚠️ Delete a DM by message ID (private) |
| `get_list` | Get a Twitter List by ID |
| `get_lists` | Get authenticated user's Lists (paginated via `cursor`, max 100/call) |
| `get_list_tweets` | Get tweets from a List (paginated via `cursor`, max 100/call) |
| `get_list_members` | Get members of a List (paginated via `cursor`, max 100/call) |
| `get_list_subscribers` | Get subscribers of a List (paginated via `cursor`, max 100/call) |
| `create_list` | Create a new Twitter List (`name` required; optional `description`, `is_private`) |
| `edit_list` | Edit a List's metadata — at least one of `name`/`description`/`is_private` required |
| `add_list_member` | Add a user to a List by `screen_name` OR `user_id` |
| `remove_list_member` | Remove a user from a List by `screen_name` OR `user_id` |
| `create_scheduled_tweet` | Schedule a tweet at a future Unix timestamp (`scheduled_at` required; at least `text` or `media_ids` required) |
| `get_scheduled_tweets` | Get all scheduled tweets for the authenticated user |
| `delete_scheduled_tweet` | Delete a scheduled tweet by its `scheduled_tweet_id` |
| `create_poll` | Create an X poll card (2-4 `choices`, `duration_minutes` > 0); returns `card_uri` for use with `send_tweet` |
| `vote` | Vote on a poll — requires `selected_choice`, `card_uri`, `tweet_id`, `card_name` |
| `get_community` | Get a Twitter Community by ID |
| `search_community` | Search for Communities by query (paginated via `cursor`) |
| `get_community_tweets` | Get tweets from a Community — `tweet_type` one of `Top`/`Latest`/`Media` (paginated, max 100/call) |
| `get_communities_timeline` | Get the joined-communities feed (paginated via `cursor`, max 100/call) |
| `get_community_members` | Get members of a Community (paginated via `cursor`, max 100/call) |
| `get_community_moderators` | Get moderators of a Community (paginated via `cursor`, max 100/call) |
| `search_community_tweet` | Search tweets within a Community by query (paginated via `cursor`, max 100/call) |
| `join_community` | Join a Community by ID |
| `leave_community` | Leave a Community by ID |
| `request_to_join_community` | Request to join a Community — optional `answer` for moderated communities |

> **X Articles note**: long-form posts at `https://x.com/i/article/<id>` live in a different ID namespace than tweets. `get_tweet` refuses them with a clear error pointing to `get_article`. `get_article_preview` works without auth via the public syndication endpoint. `get_article` runs a two-hop reader flow internally: `ArticleRedirectScreenQuery` resolves the article rest_id to the underlying tweet rest_id, then `TweetResultByRestId` fetches the tweet's article body. The `format` arg controls how much of the response makes it through to the LLM:
>
> - `"preview"` (~1 KB) — `rest_id`, `title`, `preview_text`, `cover_image`. Card-display use case.
> - `"plain"` (~20 KB, **default**) — adds `plain_text`, flat `media` URL list, `lifecycle_state`. The 80% LLM-reading-an-article case; fits inside Claude Code's `MAX_MCP_OUTPUT_TOKENS`.
> - `"full"` (~150 KB+) — raw GraphQL payload including the heavy `content_state` block tree. Only ask for this if you actually need rich-content rendering / archiving / structure analysis.
>
> Both queryIds are hardcoded like the 80+ other twikit endpoints; if X rotates them, refresh from the public `bundle.Articles.*.js` / `bundle.TwitterArticles.*.js` chunks on `abs.twimg.com` (no auth needed for discovery).

### Check version

```bash
twikit-mcp --version
# or: twikit-mcp -v
# or: python -m twitter_mcp.server --version
```

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

# uvx
claude mcp add twitter -s user ^
  -e "TWITTER_COOKIES=%APPDATA%\twitter-mcp\cookies.json" ^
  -- uvx twikit-mcp

# Or with pip
pip install twikit-mcp
claude mcp add twitter -s user ^
  -e "TWITTER_COOKIES=%APPDATA%\twitter-mcp\cookies.json" ^
  -- twikit-mcp
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

#### 1. 创建 cookies.json

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

> **这两个值是什么？** `ct0` 是 CSRF token（约160位十六进制），`auth_token` 是会话 token（40位十六进制），都在浏览器 Cookies 中。Cookies 会过期——`auth_token` 通常有效数月，`ct0` 可能更短。过期后从浏览器重新提取即可。

#### 2. 安装 & 注册

选择以下 **任一** 方式：

**方式 A: uvx** — 零安装,每次调用拉一份。第一次慢,之后用 cache,跟其他 uv 工具共享。适合临时试用。

```bash
# Claude Code
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- uvx twikit-mcp

# 或直接运行
uvx twikit-mcp
```

**方式 B: `uv tool install`** *(日常使用推荐)* — 隔离 venv,启动瞬间,升级简单。

```bash
# 一次性安装,在 PATH 上注册一个 `twikit-mcp` 二进制(默认路径 ~/.local/bin)
uv tool install twikit-mcp

# 列出当前 uv 管理的工具(确认装上了)
uv tool list

# 有新版本时升级
uv tool upgrade twikit-mcp
# 或一键升级所有 uv 装的工具:
uv tool upgrade --all

# 卸载(连 venv 一起清掉)
uv tool uninstall twikit-mcp
```

然后用 PATH 上的二进制注册到 Claude Code(不要再加 `uvx` 前缀):

```bash
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- twikit-mcp
```

cookies 文件**位置不变** — 仍然是 `~/.config/twitter-mcp/cookies.json`(或者 `TWITTER_COOKIES` 环境变量指的地方)。`uv tool install` 只改变**二进制**的安装位置,不改 config 路径。

> uvx vs `uv tool install` 的简单选择: 一次性 / 偶尔用 → **uvx**;天天接到 Claude Code 里用 → **`uv tool install`**(启动快很多)。

**方式 C: pip**

```bash
pip install twikit-mcp

# Claude Code
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- twikit-mcp

# 或直接运行
TWITTER_COOKIES=~/.config/twitter-mcp/cookies.json twikit-mcp
```

**方式 D: pipx**(隔离安装,跟 `uv tool install` 思路一样,但换工具)

```bash
pipx install twikit-mcp

# Claude Code
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- twikit-mcp
```

#### 在其他 MCP 客户端中使用

这是标准的 MCP server（stdio 传输），**不限于 Claude Code**，任何支持 MCP 的客户端都能用。

在你的 MCP 客户端配置中添加（如 `mcp.json`、`settings.json`）：

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

搞定。直接说人话：

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
| `get_user_info` | 查看用户资料（`screen_name` 或 `user_id` 二选一,id/简介/粉丝/头像等） | "查一下 @xxx 的资料" |
| `get_user_tweets` | 看某人的推 | "看看 @xxx 最近发了什么" |
| `get_user_followers` | 拉某人的粉丝列表(`cursor` 分页,单次最多 100) | "看看 @xxx 的粉丝" |
| `get_user_following` | 拉某人关注的人(`cursor` 分页,单次最多 100) | "@xxx 都关注谁?" |
| `follow_user` | 关注用户 | "关注 @xxx" |
| `unfollow_user` | 取消关注 | "取关 @xxx" |
| `delete_tweet` | 删除推文 | "删除这条推文" |
| `unfavorite_tweet` | 取消点赞 | "取消对这条推的点赞" |
| `delete_retweet` | 取消转推 | "取消转推这条" |
| `bookmark_tweet` | 收藏推文（可选 `folder_id`） | "收藏这条推文" |
| `delete_bookmark` | 取消收藏推文 | "取消收藏这条推文" |
| `get_bookmarks` | 获取收藏列表（`cursor` 分页，单次最多 100） | "看看我的收藏" |
| `get_favoriters` | 获取点赞某推文的用户（`cursor` 分页，单次最多 100） | "谁点赞了这条推？" |
| `get_retweeters` | 获取转推某推文的用户（`cursor` 分页，单次最多 100） | "谁转推了这条？" |
| `search_user` | 搜索用户（`cursor` 分页，单次最多 100） | "搜一下叫 xxx 的用户" |
| `get_trends` | 获取热门话题（分类：`trending`/`for-you`/`news`/`sports`/`entertainment`） | "现在有哪些热门话题？" |
| `get_article_preview` | 拿 X Article 的标题/摘要/封面(无需登录) | "这篇文章在讲什么 [链接]" |
| `get_article` | 拿 X Article 的正文,`format="preview" \| "plain" \| "full"`(默认 `"plain"`) | "把这篇文章读给我听 [链接]" |
| `block_user` | 屏蔽用户（受频率限制，避免批量操作） | "屏蔽 @xxx" |
| `unblock_user` | 取消屏蔽用户 | "取消屏蔽 @xxx" |
| `mute_user` | 静音用户（受频率限制，避免批量操作） | "静音 @xxx" |
| `unmute_user` | 取消静音用户 | "取消静音 @xxx" |
| `get_notifications` | 获取通知（`type="All"\|"Verified"\|"Mentions"`，`cursor` 分页，单次最多 100） | "看看我的通知" |
| `send_dm` | ⚠️ 发送私信给用户，勿批量调用 | "私信 @xxx：..." |
| `send_dm_to_group` | ⚠️ 发送私信到群组，勿批量调用 | "发消息到群组..." |
| `get_dm_history` | ⚠️ 获取与某用户的私信记录（私密，通过 `max_id` 分页） | "看看和 @xxx 的私信记录" |
| `delete_dm` | ⚠️ 删除某条私信（私密） | "删除这条私信" |
| `get_list` | 通过 ID 获取 Twitter 列表 | "查看列表 xxx" |
| `get_lists` | 获取当前用户的所有列表（`cursor` 分页，单次最多 100） | "我有哪些列表？" |
| `get_list_tweets` | 获取列表中的推文（`cursor` 分页，单次最多 100） | "查看列表推文" |
| `get_list_members` | 获取列表成员（`cursor` 分页，单次最多 100） | "列表成员有哪些？" |
| `get_list_subscribers` | 获取列表订阅者（`cursor` 分页，单次最多 100） | "谁订阅了这个列表？" |
| `create_list` | 创建新列表（`name` 必填，可选 `description`、`is_private`） | "新建列表 xxx" |
| `edit_list` | 编辑列表信息（`name`/`description`/`is_private` 至少提供一个） | "重命名列表" |
| `add_list_member` | 将用户加入列表（`screen_name` 或 `user_id` 二选一） | "把 @xxx 加入列表" |
| `remove_list_member` | 将用户从列表移除（`screen_name` 或 `user_id` 二选一） | "从列表移除 @xxx" |
| `create_scheduled_tweet` | 定时发推（`scheduled_at` 为未来 Unix 时间戳，`text` 或 `media_ids` 至少提供一个） | "明天发推" |
| `get_scheduled_tweets` | 获取当前用户的所有定时推文 | "有哪些定时推？" |
| `delete_scheduled_tweet` | 删除定时推文（需提供 `scheduled_tweet_id`） | "取消定时推" |
| `create_poll` | 创建投票（2-4 个选项，`duration_minutes` > 0），返回 `card_uri` | "发起投票" |
| `vote` | 对投票投票（需提供 `selected_choice`、`card_uri`、`tweet_id`、`card_name`） | "给这个选项投票" |
| `get_community` | 通过 ID 获取 Twitter 社区 | "查看社区 xxx" |
| `search_community` | 搜索社区（`cursor` 分页） | "搜索 Python 社区" |
| `get_community_tweets` | 获取社区推文（`tweet_type` 为 `Top`/`Latest`/`Media`，分页，单次最多 100） | "看看社区最新推文" |
| `get_communities_timeline` | 获取已加入社区的时间线（`cursor` 分页，单次最多 100） | "看看社区动态" |
| `get_community_members` | 获取社区成员（`cursor` 分页，单次最多 100） | "社区有哪些成员？" |
| `get_community_moderators` | 获取社区版主（`cursor` 分页，单次最多 100） | "社区版主是谁？" |
| `search_community_tweet` | 在社区内搜索推文（`cursor` 分页，单次最多 100） | "在社区里搜 xxx" |
| `join_community` | 加入社区 | "加入这个社区" |
| `leave_community` | 退出社区 | "退出这个社区" |
| `request_to_join_community` | 申请加入社区（受限社区可选 `answer`） | "申请加入这个社区" |

> **X Articles 说明**:`https://x.com/i/article/<id>` 这种长文与普通推文是两个 ID 命名空间。`get_tweet` 遇到 article URL 会直接拒绝并提示用 `get_article`。`get_article_preview` 走公共 syndication 端点,不需要登录。`get_article` 内部是两跳 reader 流程,通过 `format` 参数控制返回大小:
>
> - `"preview"` (~1 KB) — `rest_id` / `title` / `preview_text` / `cover_image`,卡片场景
> - `"plain"` (~20 KB,**默认**) — 上面 + `plain_text` + 扁平化 `media` URL 列表 + `lifecycle_state`,LLM 读全文的 80% 场景,刚好放得下 Claude Code 的 `MAX_MCP_OUTPUT_TOKENS`
> - `"full"` (~150 KB+) — 原始 GraphQL 响应,含庞大的 `content_state` 富文本块树,只在做富文本渲染/归档/结构分析时才需要
>
> 两个 queryId 都跟其他 80+ 端点一样硬编码 — 如果 X 改了 hash,从公开的 `bundle.Articles.*.js` / `bundle.TwitterArticles.*.js` chunk 里 grep 出新值即可,无需登录态。

### 查看版本

```bash
twikit-mcp --version
# 或:twikit-mcp -v
# 或:python -m twitter_mcp.server --version
```

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

# uvx
claude mcp add twitter -s user ^
  -e "TWITTER_COOKIES=%APPDATA%\twitter-mcp\cookies.json" ^
  -- uvx twikit-mcp

# 或使用 pip
pip install twikit-mcp
claude mcp add twitter -s user ^
  -e "TWITTER_COOKIES=%APPDATA%\twitter-mcp\cookies.json" ^
  -- twikit-mcp
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

#### 1. cookies.json の作成

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

> **これは何？** `ct0` は CSRF トークン（約160桁の16進数）、`auth_token` はセッショントークン（40桁の16進数）で、ブラウザの Cookie から取得します。Cookie は有効期限があります — `auth_token` は通常数ヶ月、`ct0` はより短い場合があります。期限切れの際はブラウザから再取得してください。

#### 2. インストール & 登録

以下の **いずれか** の方法を選んでください：

**方法 A: uvx** — ゼロインストール、毎回フェッチ。初回のみ遅い、以降はキャッシュで高速。お試し向け。

```bash
# Claude Code
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- uvx twikit-mcp

# または直接実行
uvx twikit-mcp
```

**方法 B: `uv tool install`**（日常利用に推奨）— 専用 venv で隔離インストール、起動が瞬時、アップグレードも簡単。

```bash
# 一度だけインストール。PATH (~/.local/bin) に `twikit-mcp` バイナリを配置
uv tool install twikit-mcp

# uv tool 管理下のツール一覧（確認用）
uv tool list

# 新バージョンが出たらアップグレード
uv tool upgrade twikit-mcp
# uv で入れた全ツールを一括アップグレード:
uv tool upgrade --all

# アンインストール（venv ごと削除）
uv tool uninstall twikit-mcp
```

PATH 上のバイナリで Claude Code に登録（`uvx` プレフィックス不要）:

```bash
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- twikit-mcp
```

cookies ファイルの場所は**他のオプションと同じ** — `~/.config/twitter-mcp/cookies.json` (もしくは `TWITTER_COOKIES` 環境変数)。`uv tool install` が変えるのは**バイナリの場所**だけで、設定ファイルの場所は変わりません。

> uvx と `uv tool install` の使い分け: 一回だけ / たまに → **uvx**;Claude Code に組み込んで毎日使う → **`uv tool install`**(起動が圧倒的に速い)。

**方法 C: pip**

```bash
pip install twikit-mcp

# Claude Code
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- twikit-mcp

# または直接実行
TWITTER_COOKIES=~/.config/twitter-mcp/cookies.json twikit-mcp
```

**方法 D: pipx**（隔離インストール — `uv tool install` と同じ思想、ツール違い）

```bash
pipx install twikit-mcp

# Claude Code
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- twikit-mcp
```

#### 他の MCP クライアントでの使用

これは標準的な MCP サーバー（stdio トランスポート）です。**Claude Code 専用ではなく**、MCP 対応のすべてのクライアントで使用できます。

MCP クライアントの設定ファイル（`mcp.json`、`settings.json` など）に追加：

```json
{
  "mcpServers": {
    "twitter": {
      "command": "twikit-mcp",
      "env": {
        "TWITTER_COOKIES": "/home/ユーザー名/.config/twitter-mcp/cookies.json"
      }
    }
  }
}
```

> 対応クライアント：Claude Code、Claude Desktop、Cursor、Windsurf、opencode、Cline など。

以上です。自然言語で話しかけてください：

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
| `get_user_info` | ユーザープロフィール取得(`screen_name` か `user_id` のどちらか、id/bio/フォロワー数/アイコンなど) | 「@xxx のプロフィールを見せて」 |
| `get_user_tweets` | ユーザーのツイート取得 | 「@xxx の最近の投稿を見せて」 |
| `get_user_followers` | フォロワー一覧取得(`cursor` でページング、1 回最大 100) | 「@xxx のフォロワーを見せて」 |
| `get_user_following` | フォロー中の一覧取得(`cursor` でページング、1 回最大 100) | 「@xxx は誰をフォローしてる?」 |
| `follow_user` | ユーザーをフォロー | 「@xxx をフォロー」 |
| `unfollow_user` | フォロー解除 | 「@xxx をフォロー解除」 |
| `delete_tweet` | ツイート削除 | 「このツイートを削除して」 |
| `unfavorite_tweet` | いいね取り消し | 「このツイートのいいねを取り消して」 |
| `delete_retweet` | リツイート取り消し | 「このリツイートを取り消して」 |
| `bookmark_tweet` | ブックマーク追加（`folder_id` オプション） | 「このツイートをブックマークして」 |
| `delete_bookmark` | ブックマーク削除 | 「このブックマークを削除して」 |
| `get_bookmarks` | ブックマーク一覧取得（`cursor` でページング、1 回最大 100） | 「ブックマークを見せて」 |
| `get_favoriters` | ツイートにいいねしたユーザー一覧（`cursor` でページング、1 回最大 100） | 「このツイートにいいねした人は?」 |
| `get_retweeters` | ツイートをリツイートしたユーザー一覧（`cursor` でページング、1 回最大 100） | 「誰がリツイートした?」 |
| `search_user` | ユーザー検索（`cursor` でページング、1 回最大 100） | 「〜というユーザーを検索して」 |
| `get_trends` | トレンド取得（カテゴリ：`trending`/`for-you`/`news`/`sports`/`entertainment`） | 「今のトレンドを見せて」 |
| `get_article_preview` | X Article のタイトル/プレビュー/カバー画像取得(認証不要) | 「この記事の概要を教えて [URL]」 |
| `get_article` | X Article の本文取得、`format="preview" \| "plain" \| "full"`(デフォルト `"plain"`) | 「この記事を読んで [URL]」 |
| `block_user` | ユーザーをブロック（レート制限あり — 一括使用禁止） | 「@xxx をブロック」 |
| `unblock_user` | ユーザーのブロックを解除 | 「@xxx のブロックを解除」 |
| `mute_user` | ユーザーをミュート（レート制限あり — 一括使用禁止） | 「@xxx をミュート」 |
| `unmute_user` | ユーザーのミュートを解除 | 「@xxx のミュートを解除」 |
| `get_notifications` | 通知取得（`type="All"\|"Verified"\|"Mentions"`、`cursor` でページング、1 回最大 100） | 「通知を見せて」 |
| `send_dm` | ⚠️ ユーザーにダイレクトメッセージを送信 — 一括送信禁止 | 「@xxx にDMして：...」 |
| `send_dm_to_group` | ⚠️ グループにダイレクトメッセージを送信 — 一括送信禁止 | 「グループにメッセージ送信...」 |
| `get_dm_history` | ⚠️ ユーザーとの DM 履歴取得（プライベート、`max_id` でページング） | 「@xxx との DM 履歴を見せて」 |
| `delete_dm` | ⚠️ DM を削除（プライベート） | 「この DM を削除して」 |
| `get_list` | ID でリストを取得 | 「リスト xxx を見せて」 |
| `get_lists` | 自分のリスト一覧取得（`cursor` でページング、1 回最大 100） | 「自分のリストは？」 |
| `get_list_tweets` | リストのツイート取得（`cursor` でページング、1 回最大 100） | 「リストのツイートを見せて」 |
| `get_list_members` | リストのメンバー取得（`cursor` でページング、1 回最大 100） | 「リストのメンバーは？」 |
| `get_list_subscribers` | リストの購読者取得（`cursor` でページング、1 回最大 100） | 「誰がリストを購読している？」 |
| `create_list` | リストを作成（`name` 必須、`description`・`is_private` は任意） | 「リスト xxx を作成して」 |
| `edit_list` | リスト情報を編集（`name`/`description`/`is_private` のいずれか必須） | 「リスト名を変更して」 |
| `add_list_member` | リストにユーザーを追加（`screen_name` か `user_id` どちらか一方） | 「@xxx をリストに追加して」 |
| `remove_list_member` | リストからユーザーを削除（`screen_name` か `user_id` どちらか一方） | 「@xxx をリストから削除して」 |
| `create_scheduled_tweet` | 予約投稿（`scheduled_at` は未来の Unix タイムスタンプ、`text` または `media_ids` のどちらかが必須） | 「明日ツイートして」 |
| `get_scheduled_tweets` | 予約中のツイート一覧を取得 | 「予約ツイートは？」 |
| `delete_scheduled_tweet` | 予約ツイートを削除（`scheduled_tweet_id` 必須） | 「予約を取り消して」 |
| `create_poll` | 投票を作成（選択肢 2-4 個、`duration_minutes` > 0）、`card_uri` を返す | 「投票を作って」 |
| `vote` | 投票する（`selected_choice`・`card_uri`・`tweet_id`・`card_name` すべて必須） | 「この選択肢に投票して」 |
| `get_community` | ID でコミュニティを取得 | 「コミュニティ xxx を見せて」 |
| `search_community` | クエリでコミュニティを検索（`cursor` でページング） | 「Python コミュニティを探して」 |
| `get_community_tweets` | コミュニティのツイートを取得（`tweet_type` は `Top`/`Latest`/`Media`、最大 100 件） | 「コミュニティの最新投稿を見せて」 |
| `get_communities_timeline` | 参加済みコミュニティのタイムラインを取得（`cursor` でページング、最大 100 件） | 「コミュニティのフィードを見せて」 |
| `get_community_members` | コミュニティのメンバー一覧を取得（`cursor` でページング、最大 100 件） | 「コミュニティのメンバーは？」 |
| `get_community_moderators` | コミュニティのモデレーター一覧を取得（`cursor` でページング、最大 100 件） | 「モデレーターは誰？」 |
| `search_community_tweet` | コミュニティ内のツイートを検索（`cursor` でページング、最大 100 件） | 「このコミュニティで xxx を検索して」 |
| `join_community` | コミュニティに参加 | 「このコミュニティに参加して」 |
| `leave_community` | コミュニティを退出 | 「このコミュニティを退出して」 |
| `request_to_join_community` | コミュニティへの参加申請（審査制コミュニティは `answer` も任意） | 「このコミュニティへの参加を申請して」 |

> **X Articles について**:`https://x.com/i/article/<id>` の長文記事はツイートとは別の ID 名前空間に属します。`get_tweet` は article URL を渡されると拒否し、`get_article` を案内します。`get_article_preview` は公開 syndication エンドポイント経由で認証不要。`get_article` は内部で 2 ホップ reader フローを走り、`format` 引数で出力サイズを制御:
>
> - `"preview"` (~1 KB) — `rest_id` / `title` / `preview_text` / `cover_image`、カード表示用途
> - `"plain"` (~20 KB、**デフォルト**) — 上記 + `plain_text` + フラットな `media` URL リスト + `lifecycle_state`、LLM が記事を読む 80% のケース、Claude Code の `MAX_MCP_OUTPUT_TOKENS` に収まる
> - `"full"` (~150 KB+) — 重い `content_state` ブロックツリーを含む生 GraphQL レスポンス、リッチコンテンツのレンダリング・アーカイブ・構造解析が必要な場合のみ
>
> どちらの queryId も他の 80+ エンドポイント同様ハードコードされており、X がハッシュをローテートした場合は公開されている `bundle.Articles.*.js` / `bundle.TwitterArticles.*.js` チャンクから新しいハッシュを取得できます(認証不要)。

### バージョン確認

```bash
twikit-mcp --version
# または: twikit-mcp -v
# または: python -m twitter_mcp.server --version
```

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

# uvx
claude mcp add twitter -s user ^
  -e "TWITTER_COOKIES=%APPDATA%\twitter-mcp\cookies.json" ^
  -- uvx twikit-mcp

# または pip
pip install twikit-mcp
claude mcp add twitter -s user ^
  -e "TWITTER_COOKIES=%APPDATA%\twitter-mcp\cookies.json" ^
  -- twikit-mcp
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
