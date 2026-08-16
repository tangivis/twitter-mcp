# XChat(加密私信)

XChat 是 X 的端到端加密私信系统。普通的 DM API 拿不到加密消息体——`get_dm_history`
会在 `warnings` 字段里如实说明,而不是假装这个会话是空的。

X 自己的网页客户端会在本地把会话解密,并把明文存进一个 SQLite 数据库。`twikit-mcp`
读的就是这个文件。**解密是浏览器做的,我们只是打开结果。**

## 这个功能到底是什么

- **纯本地。** 不发任何网络请求。不走 X API,不走付费 API,不做浏览器自动化。
- **只读。** 数据库以 SQLite 的 `mode=ro` + `immutable=1` 打开,不加锁,也不会在你的浏览器
  profile 旁边写出 `-wal`/`-shm` 附属文件。所有语句都是 `SELECT`。
- **不碰任何凭据。** 不需要 PIN、不需要 OAuth token、不需要加密密钥。这几个工具**不会**读你的
  `cookies.json`。
- **在这里读消息不会在 X 上标记已读。** 因为根本没有任何数据发给 X。
- **永远不读加密密钥。** 密钥表只被用于诊断计数,其余一概不碰。

## 前提条件

在 Chromium 系浏览器里打开 XChat、解锁、等它同步完。支持 Chrome、Chromium、Edge、Brave、Aside。
不支持 Safari —— WebKit 不使用 Chromium 的存储布局。

## 配置

在你 MCP 客户端的 `env` 块里设置,和 `TWITTER_COOKIES` 放一起:

| 变量 | 含义 |
|---|---|
| `XCHAT_BROWSER` | `auto`,或 `chrome` / `chromium` / `edge` / `brave` / `aside` 之一 |
| `XCHAT_BROWSER_PROFILE` | profile 目录名,例如 `Default` 或 `Profile 2` |
| `XCHAT_DATABASE_PATH` | 直接给 SQLite 文件的路径 —— 完全跳过自动发现 |

一个都不设时,XChat 工具会返回 `not_configured`,并把在你机器上找到的候选列出来供你选。
不管设不设,server 的其余部分都不受影响。

```json
{
  "mcpServers": {
    "twitter": {
      "command": "twikit-mcp",
      "env": {
        "TWITTER_COOKIES": "/home/YOU/.config/twitter-mcp/cookies.json",
        "XCHAT_BROWSER": "chrome"
      }
    }
  }
}
```

如果自动发现找到多个数据库,它**不会猜**,而是让你指定一个——读错 profile 会悄无声息地
返回另一个账号的会话。

macOS 上,MCP 宿主需要**完全磁盘访问权限**才能读浏览器 profile。在系统设置 → 隐私与安全性
里授权,重启宿主,再试;被拒时工具会明确告诉你这一点。

## 工具

| 工具 | 作用 |
|---|---|
| `xchat_status` | 本地存储能不能读、在哪、有多少会话——未配置时还会附上发现结果 |
| `xchat_list_conversations` | 按最新活动排序的会话列表,带最后一条消息预览 |
| `xchat_get_history` | 某个会话的消息,按时间正序 |

只带附件的消息会渲染成 `[image attachment]` 这样的占位符,而不是空文本——免得 agent 把
一张图误当成"对方没说话"。

## 限制

- **只能读到你浏览器已同步的部分。** 这读的是本地缓存,不是 X 的服务器。浏览器没拉过的会话就没有。
- **拿不到附件内容**,只有类型占位符。
- **依赖 X 的内部数据库 schema**,X 随时可以改。真改了的话,工具会以清晰的"缺少必需的 XChat 表"
  报错,而不是返回错误数据。这和 vendored twikit 的解析属于同一类脆弱性,见
  [issue #118](https://github.com/tangivis/twitter-mcp/issues/118)。

## 隐私

这几个工具会把私信内容送进你 agent 的上下文。这正是它的用途,但值得你有意识地对待:
这些会话会跟着你 MCP 客户端的上下文一起走。工具的 docstring 已做标注,行为良好的 agent
会把它们当敏感内容处理。
