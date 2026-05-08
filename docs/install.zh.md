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
