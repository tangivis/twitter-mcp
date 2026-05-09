# twikit-mcp

**Twitter/X MCP server + CLI — 不需要 API key。**

[![PyPI](https://img.shields.io/pypi/v/twikit-mcp)](https://pypi.org/project/twikit-mcp/)
[![CI](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/tangivis/twitter-mcp/blob/main/LICENSE)

[MCP](https://modelcontextprotocol.io/) server,让 Claude(或任何 MCP 兼容的 AI agent)用浏览器 cookies 操作 Twitter/X。同一个 `twikit-mcp` 二进制还能当 CLI 用,适合 shell 脚本和调试。

## 0.1.32 新增

- **读推文回复** — 新增 `get_tweet_replies(tweet_id, cursor=None)` 工具,拿一条推下面的评论 / 讨论。走 X 的 TweetDetail GraphQL 端点(vendored twikit),一次返回一页,带 `next_cursor` 翻下一页。回复条目用和 `get_user_tweets` / `get_timeline` 同款紧凑形状。(closes #94)

升级:`uv tool upgrade twikit-mcp`(或 `pip install --upgrade twikit-mcp`)。

## 0.1.31 新增

- **各客户端安装矩阵文档** — 新增[安装页](install.md),走过 Claude Code / Claude Desktop / Cursor / Windsurf / Cline / opencode 6 个客户端的注册步骤(每个 ≤ 12 行,只列配置文件路径 + JSON 片段)。统一安装命令(`uv tool install twikit-mcp`),JSON 形状跨客户端通用。(closes #92)

## 0.1.30 新增

- **API 文档页面本地化** — `/zh/api/` 和 `/ja/api/` 现在显示中文 / 日文 chrome(标题、引言、表头、节标题),不再 fallback 到英文。工具 docstring 保持原文(从 Python 源码读),与 `mkdocstrings` 同套权衡。(closes #90)

## 0.1.29 新增

- **Community + article-preview 稳定性** — `get_community` / `get_community_tweets` / `get_community_members` / `get_community_moderators` / `search_community_tweet` 不再因 `KeyError: 'rest_id'` 或 `IndexError` 崩。`get_article_preview` 在 syndication 端点 404(X 删了旧文章)时返回干净的 `ToolError`,不再泄露 `HTTPStatusError` 堆栈。`_vendor/twikit/community.py` + `client.py` 全面 `.get()` 防御化。**Issue #76 全部完成** — `T_DRIFT` 现在是空集了。(issue #76 parts 2 + 3)

## 0.1.28 新增

- **List 工具稳定性** — `get_list` / `get_list_tweets` / `get_list_members` / `get_list_subscribers` 在 burner 受 X 限流时不再崩(`KeyError: 'created_at'` / `IndexError` / `Invalid list id`)。`_vendor/twikit/list.py` + `client.py` 全面 `.get()` 防御化:字段缺失 → `None`/`""`/`0`,entries 为空 → 空 `Result`。live-smoke 的 `T_LIST` 也拆掉了 `T_DRIFT` 兜底,这一类 bug 真出现会立刻红 CI。(issue #76 part 1)

## 0.1.27 新增

- **下载推文视频(yt-dlp)** — 新增 `download_tweet_video` MCP 工具 + `twikit-mcp video <id>` 人用 CLI。默认保存到 `~/Downloads/twikit-mcp/`,通过你现有的 `cookies.json` 认证。需要 [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) 在 PATH 里(`uv tool install yt-dlp`);`ffmpeg` 只在你传 `bestvideo+bestaudio` 这类需要 mux 的 format 时才需要。(closes #84)

## 0.1.26 新增

- **`get_tweet` 暴露引用推文** — 响应里现在多了 `is_quote_status`、`quoted_id`、`quoted_author`、`quoted_text`。如果当前推是 quote retweet,直接能看到引用了谁说啥,不用 agent 再 call 一次。这些字段本来就在同一次 GraphQL 响应里,我们只是没抽出来给 agent。(closes #82)

## 0.1.25 新增

- **`get_tweet` 返回会话上下文** — 响应里现在多了 `in_reply_to`(回复时的父推 ID)和 `conversation_id`(整条 thread 的根推 ID)。Agent 拿到一条回复推文不再需要让用户手动贴父推链接,直接能溯源到根。(closes #77)

## 0.1.24 新增

- **Rich 渲染卡片** — 0.1.23 的终端卡片现在改由 [Rich](https://github.com/Textualize/rich) 输出,emoji 和中日韩字符**列宽正确**(`❤ 🔁` 行不再让右边框偏移),并且 tweet / 个人主页 / bio URL 都用 **OSC 8 可点超链接**包裹 — 在 iTerm2 / kitty / WezTerm / Windows Terminal / gnome-terminal ≥ 3.36 里 cmd-click 直接打开。Trends 改成了真正的 Table 排版。
- 纯文本(非 TTY)输出不变:`| jq` / `> file` / `NO_COLOR=1` 消费者继续字节稳定。

## 0.1.23 新增

- **ASCII Twitter 卡片 UI** — `twikit-mcp tweet` / `user` / `tl` / `search` / `trends` 在终端里现在会渲染成 box-drawing 卡片(粗体作者名、灰显时间戳、正文 / 计数 / URL 之间分隔线)。重定向到文件或管道,或设 `NO_COLOR=1`,自动回退到原来的字节稳定纯文本输出。样例见 [CLI 模式](cli.md)。

## 0.1.22 新增

- **人用 CLI 子命令** — 直接在 shell 里读推 / 看 profile / 刷 timeline / 搜索 / 看 trends:

  ```bash
  twikit-mcp tweet 20
  twikit-mcp user elonmusk
  twikit-mcp tl 10
  ```

  纯文本输出,原生中日韩文,合理的默认值。详见 [CLI 模式](cli.md)。
- **全链路 UTF-8 输出** — 不再有 `\uXXXX` 转义。中文 / 日本語 / 希腊文 / emoji 都以可读形式经过工具。
- **三语文档站** — 你正在看的就是,顶部切换语言。

## 你能拿到什么

- **57 个工具** — 推文、用户、列表、社群、定时推文+投票、私信、文章、搜索、趋势、通知。
- **浏览器 cookie 认证** — 从你的 X 会话拷 `ct0` + `auth_token`,搞定。
- **两种传输,一个二进制** — 默认是 MCP server(给 AI agent 用),`twikit-mcp call <tool>` 是 CLI(给 shell 用)。
- **vendored 版 [twikit](https://github.com/d60/twikit)** — 带项目自己打的防御补丁。

## 文档导航

- **[CLI 模式](cli.md)** — 子命令、类型转换、退出码、例子。
- **[MCP 工具 API](api.md)** — 自动生成的参考:每个工具的签名 + docstring + CLI 调用例子,跟代码同步。
- **[技术设计](TECHNICAL.md)** — 内部实现(中文)。
- **[Vendoring twikit](VENDORING.md)** — 每个补丁和对应的 issue(中文)。
- **[GitHub repo](https://github.com/tangivis/twitter-mcp)** — README 有三语完整安装 / 快速开始。

## 快速安装

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
