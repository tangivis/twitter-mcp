# 安装 + 注册到你的 MCP 客户端

三步。第 3 步选你的客户端。

## 1. 安装二进制

```bash
uv tool install twikit-mcp
```

为什么用 `uv tool install`:把 `twikit-mcp` 装在独立隔离环境里(无依赖冲突),后续启动是即时的,升级只要一句 `uv tool upgrade twikit-mcp`。

没有 `uv`:[一行装好](https://docs.astral.sh/uv/getting-started/installation/)(macOS / Linux 一条 curl)。也可以用 `pipx` / `pip` — 详见 [README "Choose your install"](https://github.com/tangivis/twitter-mcp#choose-your-install)。

## 2. 把 X cookies 放好

浏览器登 [x.com](https://x.com) → DevTools(F12)→ **Application** → **Cookies** → `https://x.com`,复制 `ct0` 和 `auth_token` 两个值。

```bash
mkdir -p ~/.config/twitter-mcp
cat > ~/.config/twitter-mcp/cookies.json <<'EOF'
{"ct0": "...", "auth_token": "..."}
EOF
chmod 600 ~/.config/twitter-mcp/cookies.json
```

## 3. 注册到你的客户端

每个客户端配置的 JSON 形状(`mcpServers` 块)都一样,只是**配置文件位置**不同。下面把 `/home/YOU` 替换成你自己的家目录。

### Claude Code

CLI 命令一行搞定,不用编辑 JSON:

```bash
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- twikit-mcp
```

### Claude Desktop

| 系统 | 配置文件 |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

文件不存在就创建,加进去:

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

重启 Claude Desktop。

### Cursor

编辑 `~/.cursor/mcp.json`(全局)或 `.cursor/mcp.json`(项目级):

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

Cursor 自动加载,不用重启。

### Windsurf

编辑 `~/.codeium/windsurf/mcp_config.json`:

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

重启 Windsurf。

### Cline(VS Code 扩展)

打开 Cline 面板 → ⚙️ → **MCP Servers** → **Edit MCP Settings**。保存后 Cline 自动加载。

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

### opencode

编辑 `~/.config/opencode/config.json`:

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

### Pi

Pi 没有内置 MCP —— 得先装社区 MCP 扩展。[`pi-mcp-adapter`](https://github.com/nicobailon/pi-mcp-adapter) 最适合本 server:配置形状和上面一样是 `mcpServers`、默认 lazy 连接、还有 `directTools` 白名单,免得 `twikit-mcp` 的 62 个工具挤爆 coding session 的上下文。

```bash
pi install npm:pi-mcp-adapter
```

然后编辑 `~/.config/mcp/mcp.json`(全局)或 `.mcp.json`(项目级):

```json
{
  "mcpServers": {
    "twitter": {
      "command": "/home/YOU/.local/bin/twikit-mcp",
      "env": {
        "TWITTER_COOKIES": "/home/YOU/.config/twitter-mcp/cookies.json"
      },
      "lifecycle": "lazy",
      "directTools": [
        "get_tweet",
        "get_tweet_replies",
        "search_tweets",
        "get_user_info",
        "get_user_tweets",
        "get_timeline",
        "get_trends"
      ]
    }
  }
}
```

`directTools` 里这 7 个注册成原生工具,其余 55 个留在一个代理工具后面按需发现。`command` 请写**绝对路径** —— Pi 拉子进程时 `PATH` 里不一定有 `~/.local/bin`。

Pi 的 MCP 扩展都是社区个人维护、非官方,且以你的完整系统权限运行。装之前先看一眼源码,毕竟它要拿你的 cookie 路径。

### DeepSeek Harness(dsh)

[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 自带官方 MCP 客户端(`@deepseek-ai/dsh-mcp-client`),不需要装社区扩展。配置写在 `cordis.yml` 里,是一条插件条目,不是 `mcpServers` 映射:

```yaml
- id: mcp-twitter
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: twitter
    transport: stdio
    command: twikit-mcp
    env:
      TWITTER_COOKIES: /home/YOU/.config/twitter-mcp/cookies.json
```

`serverName` 给工具做命名空间,模型那边看到的是 `mcp__twitter__get_tweet`、`mcp__twitter__search_tweets` 这种名字。

和 Pi 不同,**dsh 没有工具白名单** —— 62 个工具会全部注册,没有官方支持的办法只暴露一部分,上下文预算要自己留够。

两个值得知道的可选键:`failOnStartupError: true` 让 cookie 路径写错时在激活阶段直接报错,而不是静悄悄一个工具都不注册;`toolCallTimeoutMs`(默认 `60000`)在你给重读接口传大 `count` 时值得调高。

dsh 目前是 developer preview,配置形状可能会变;上面这些键要是对不上了,查[插件自己的 README](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.md)。

### 其他任何 MCP 客户端

`twikit-mcp` 是标准 **stdio** MCP server。不管你的客户端配置文件长什么样,JSON 形状都一样:

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

有些客户端用 `mcp.servers` 不是 `mcpServers`,或者包在另一个顶层 key 下面 — 看客户端文档。`command` 和 `env` 字段都通用。

## 验证

在你的客户端里问一句:

> 搜一下 AI 相关的推文

agent 应该调 `search_tweets` 把结果返回。如果报权限错,八成是 `cookies.json` 路径写错了 — 检查上面 JSON 里的 `TWITTER_COOKIES`。

## 升级

```bash
uv tool upgrade twikit-mcp
```

完事 — 客户端下次启动就用新二进制。
