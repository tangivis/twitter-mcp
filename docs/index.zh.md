# twikit-mcp

**Twitter/X MCP server + CLI — 不需要 API key。**

[![PyPI](https://img.shields.io/pypi/v/twikit-mcp)](https://pypi.org/project/twikit-mcp/)
[![CI](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/tangivis/twitter-mcp/blob/main/LICENSE)

[MCP](https://modelcontextprotocol.io/) server,让 Claude(或任何 MCP 兼容的 AI agent)用浏览器 cookies 操作 Twitter/X。同一个 `twikit-mcp` 二进制还能当 CLI 用,适合 shell 脚本和调试。

## 0.1.44 新增

- **进入官方 MCP registry** — 新增 `server.json`,把本 server 以 `io.github.tangivis/twitter-mcp` 声明给 [`registry.modelcontextprotocol.io`](https://registry.modelcontextprotocol.io):PyPI 包、stdio 传输,以及每个环境变量的可操作说明。配套哨兵测试保证它和 `pyproject.toml` 版本同步,并**双向**核对声明的变量与代码实际读取的变量 —— 既不能宣传一个不存在的开关,也不能漏掉一个用户需要设的。(closes #122)
- **补全 DeepSeek Harness 卡片** — 写上了 `reconnect` 那组键,以及活跃实例间 `serverName` 重名会让后加载的插件直接 fail 这件事。

## 0.1.43 新增

- **README 的客户端列表不再过期** — Pi(0.1.34 就写了文档)和 DeepSeek Harness(0.1.40)一直没进三语的那句 "Works with" 简介,因为没有任何东西把这句话和安装页连起来。现在都补上了,并加了哨兵测试:安装页上的每张客户端卡片都必须出现在每种语言的 README 简介里,下一个客户端不会再悄悄漏掉。纯文档 + 测试。

## 0.1.42 新增

- **`get_retweeters` 不再因为一个被封账号整个崩掉** — 转推者里只要有一个被封禁/注销,X 对那条 entry 返回 `__typename: UserUnavailable`,里面没有 `rest_id`。而 twikit 的 `User.__init__` 是硬取这个 key 的,于是**一个死账号就让整次调用挂 `KeyError: 'rest_id'`**。现在跳过解析不了的 entry,其余正常返回。`get_favoriters` 走同一段代码,一并修好。这个 bug 是 2026-08-17 的 live-smoke 打真实 X 时抓到的。(issue #37)
- 同一函数里紧邻的一处也一起加固了:cursor 提取原本假设 timeline 最后两条一定是 cursor,X 限流返回不含 cursor 时会 `KeyError`。现在取不到就是 `None`。

升级:`uv tool upgrade twikit-mcp`(或 `pip install --upgrade twikit-mcp`)。

## 0.1.41 新增

- **本地读取 XChat(加密私信)** — 新增三个工具,总数到 62:`xchat_status`、`xchat_list_conversations`、`xchat_get_history`。X 的网页客户端本来就会把会话解密并把明文存进本地 SQLite,这几个工具读的就是它。**零新依赖、零网络、零凭据、零写入路径** —— 数据库以 `mode=ro&immutable=1` 打开,所有语句都是 SELECT,永不读取加密密钥,在这里读也不会在 X 上标记已读。用 `XCHAT_BROWSER`(chrome/chromium/edge/brave/aside)、`XCHAT_BROWSER_PROFILE` 或 `XCHAT_DATABASE_PATH` 配置;一个都不设时工具保持休眠,server 其余部分不受影响。详见 [XChat 页面](xchat.md)。(closes #118)
- 感谢 [@DJNgoma](https://github.com/DJNgoma) —— SQLite 读取和浏览器 profile 发现的实现源自他在 PR #107 的工作。

升级:`uv tool upgrade twikit-mcp`(或 `pip install --upgrade twikit-mcp`)。

## 0.1.40 新增

- **DeepSeek Harness(dsh)安装指南** — [安装页](install.md)加了 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)。和 Pi 不同,dsh 自带官方 MCP 客户端(`@deepseek-ai/dsh-mcp-client`),不用装社区扩展 —— 但它的配置是 `cordis.yml` 里的插件条目,不是常见的 `mcpServers` 映射,而且**没有工具白名单**,59 个工具会全部注册。卡片把这两点都写清楚了,另外还有 `failOnStartupError` 和 `toolCallTimeoutMs` 两个值得知道的键。纯文档改动 —— 不动代码,`twikit-mcp` 是标准 stdio MCP server,不需要任何特殊处理。

## 0.1.39 新增

- **迁移到 MCP Python SDK v2** — server 现在基于 `MCPServer`(`mcp.server.mcpserver`),不再是已被删除的 `FastMCP`,依赖从 `mcp[cli]>=1.27,<2` 改成 `>=2,<3`。**协议层面对你没有任何变化**:完整的 `tools/list` 响应 —— 协商的协议版本、capabilities、59 个工具的全部输入/输出 schema —— 与 0.1.38 逐字节完全相同(58,843 字节,在真实 stdio 握手下跨两个 SDK 对比验证)。升级会拉取 SDK 2.x;如果你自己钉了 `mcp<2`,请留在 0.1.38。(closes #109)
- **`serverInfo.version` 现在报告真实的包版本** — SDK v1 会把这个字段填成它自己的版本,v2 不设置就是空。现在客户端在 initialize 响应里能看到 `twikit-mcp` 的真实版本号。

升级:`uv tool upgrade twikit-mcp`(或 `pip install --upgrade twikit-mcp`)。

## 0.1.38 新增

- **为 MCP 2026-07-28 规范铺路** — MCP Python SDK 2.0.0 已经正式发布,它把本 server 依赖的类改名了(`FastMCP` → `MCPServer`)。你的安装不受影响:从 0.1.35 起依赖就钉在 SDK 1.x。这个版本把所有对 SDK 私有工具注册表的读取收敛到一个内部访问器,把将来的 v2 迁移从 ~70 处改动变成一行改动。纯内部重构 —— 行为不变,生成的文档和 CLI 输出字节一致。(issue #109 phase 2)

升级:`uv tool upgrade twikit-mcp`(或 `pip install --upgrade twikit-mcp`)。

## 0.1.37 新增

- **`get_dm_history` 不再因 message request 崩溃** — 接受陌生人的 message request 后,X 会在会话时间线里塞一个 `trust_conversation` 系统条目,旧版直接 `KeyError: 'message'`。现在跳过非消息条目并通过新的 `timeline_events` 字段透出,同时用 `warnings` 字段提示端到端加密(X Chat)会话的历史可能不完整 —— legacy DM API 拿不到加密消息体,agent 不应据此断言"对方没回复"。干净会话的 JSON 形状与之前完全一致。(closes #104)
- **首次 DM 后读历史不再误报 "User not found"** — 刚发出第一条 DM 就读会话,X 侧可能瞬时 404;现在最多重试 3 次(短退避),持续失败时如实报告是会话不可用而不是用户不存在。(closes #102)
- 感谢 [@DJNgoma](https://github.com/DJNgoma) 的真机排查和两个补丁(PR #103、#105)。

升级:`uv tool upgrade twikit-mcp`(或 `pip install --upgrade twikit-mcp`)。

## 0.1.36 新增

- **所有工具接受整数 ID** — X 返回的推文/用户/列表 ID 是 JSON **数字**(`"id": 2087887408440164663`,旁边才是 `"id_str"`)。客户端把数字 `id` 原样传回来(`{"tweet_id": id}` 没加 `str()`)时,以前在工具代码运行之前就被验证层拒绝(`Input should be a valid string`)。现在全部雪花 ID 参数(59 个工具里的 37 处:`tweet_id`、`user_id`、`list_id`、`media_ids`……)接受 int 或 string,无损转成字符串。浮点数仍然拒绝:这些 ID 超过 2^53,float 已经精度损坏,静默接受会拿错推文。(closes #111)

升级:`uv tool upgrade twikit-mcp`(或 `pip install --upgrade twikit-mcp`)。

## 0.1.35 新增

- **把 MCP SDK 钉在 v2 以下** — `mcp[cli]` 之前没有上界,等 2.0.0 脱离预发布那天,新用户 `uv tool install twikit-mcp` 就会拉到 SDK v2。v2(实现 [2026-07-28 规范](https://blog.modelcontextprotocol.io/posts/2026-07-28/))把 `FastMCP` 改名成 `MCPServer`、`mcp.server.fastmcp.*` 挪到 `mcp.server.mcpserver.*`,本 server 会直接在 import 处炸。现在钉成 `>=1.27,<2`,并加了哨兵测试守着。已装好的用户行为不变。迁移在 issue #109 跟踪。

## 0.1.34 新增

- **Pi 安装指南** — [安装页](install.md)加了 [Pi](https://github.com/earendil-works/pi)。Pi 没有内置 MCP,所以这张卡片走的是先装社区 MCP 扩展(`pi-mcp-adapter`)、再用它的 `directTools` 白名单,免得本 server 的 59 个工具挤爆 coding session 的上下文。纯文档改动 —— 不动代码,`twikit-mcp` 是标准 stdio MCP server,不需要任何特殊处理。

## 0.1.33 新增

- **去掉 200 字符截断** — `get_timeline` / `search_tweets` / `get_user_tweets` / `get_bookmarks` / `get_list_tweets` / `get_scheduled_tweets` / `get_community_tweets` / `get_communities_timeline` / `search_community_tweet` 不再把推文 text 截到 200 字符。`get_tweet` 和 `get_tweet_replies` 也切到 `Tweet.full_text`,X note tweet(长帖,4000 字)能完整返回。响应大小由用户的 `count` 参数控制。(closes #97)
- **`get_article_preview` 引用推文报错优化** — 输入是 quote tweet 时,错误信息变成"这是引用推文,不是文章。用 get_tweet 读引用内容",不再扔通用的 "does not embed an article"。

## 0.1.32 新增

- **读推文回复** — 新增 `get_tweet_replies(tweet_id, cursor=None)` 工具,拿一条推下面的评论 / 讨论。走 X 的 TweetDetail GraphQL 端点(vendored twikit),一次返回一页,带 `next_cursor` 翻下一页。回复条目用和 `get_user_tweets` / `get_timeline` 同款紧凑形状。(closes #94)

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
