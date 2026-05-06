# twikit-mcp

**Twitter/X MCP server + CLI — 不需要 API key。**

[![PyPI](https://img.shields.io/pypi/v/twikit-mcp)](https://pypi.org/project/twikit-mcp/)
[![CI](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/tangivis/twitter-mcp/blob/main/LICENSE)

[MCP](https://modelcontextprotocol.io/) server,让 Claude(或任何 MCP 兼容的 AI agent)用浏览器 cookies 操作 Twitter/X。同一个 `twikit-mcp` 二进制还能当 CLI 用,适合 shell 脚本和调试。

## 0.1.24 新增

- **Rich 渲染卡片** — 0.1.23 的终端卡片现在改由 [Rich](https://github.com/Textualize/rich) 输出,emoji 和中日韩字符**列宽正确**(`❤ 🔁` 行不再让右边框偏移),并且 tweet / 个人主页 / bio URL 都用 **OSC 8 可点超链接**包裹 — 在 iTerm2 / kitty / WezTerm / Windows Terminal / gnome-terminal ≥ 3.36 里 cmd-click 直接打开。Trends 改成了真正的 Table 排版。
- 纯文本(非 TTY)输出不变:`| jq` / `> file` / `NO_COLOR=1` 消费者继续字节稳定。

升级:`uv tool upgrade twikit-mcp`(或 `pip install --upgrade twikit-mcp`)。

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
