# 测试和 CI/CD

## 测试策略

这个项目的特殊之处在于：**写工具（发推/点赞/follow 等）有副作用,只能本地手动测;读工具一部分通过 `live-smoke.yml` 用 burner cookie 真打 X 验证(每周 cron + 每次 main push)。**

因此测试分三层：

| 测试类型 | 在 CI 中 | 覆盖内容 |
|---------|---------|---------|
| 导入和注册 | 可以 | server 能启动、57 个工具都注册成功 |
| 工具 Schema | 可以 | 参数名、必填/可选、类型都正确 |
| MCP 协议 | 可以 | initialize 握手响应正确 |
| URL 解析 | 可以 | 推文 URL → ID 的提取逻辑 |
| 环境变量 | 可以 | TWITTER_COOKIES 能正确覆盖默认路径 |
| Lint/格式 | 可以 | 代码风格一致 |
| **读工具(8 个 idempotent reads)** | **可以(live-smoke)** | **burner cookie 真打 X,失败自动 post 到 issue #37 触发 @claude 修** |
| **发推/点赞/follow 等写工具** | **不行** | **会污染 burner 账号,只能本地手动测** |

---

## 本地运行测试

```bash
cd ~/mcp-servers/twitter-mcp

# 安装开发依赖
uv sync --group dev

# 运行所有测试
uv run pytest -v

# 单独运行 lint 和格式检查
uv run ruff check .
uv run ruff format --check .

# 自动修复格式问题
uv run ruff format .
uv run ruff check --fix .
```

---

## Pre-commit hook（推荐一次性安装）

为了避免"本地忘了 format → push → CI 红"这种来回,仓库自带了一份 [`pre-commit`](https://pre-commit.com) 配置,会在每次 `git commit` 之前自动跑 `ruff format` 和 `ruff check --fix`。

**clone 后执行一次:**

```bash
uv sync --group dev
uv run pre-commit install
```

之后每次 `git commit` 都会自动:

1. 对 staged 的 Python 文件跑 `ruff format` — 如果有改动,**aborted 这次 commit**,需要 `git add` 重新 commit。
2. 对 staged 文件跑 `ruff check --fix`(包括 import 排序) — 如果还有 lint error,abort。
3. 全过才放行。

**手动对全仓跑一次**(等价于 CI 的检查):

```bash
uv run pre-commit run --all-files
```

**升级 hook 版本**(`.pre-commit-config.yaml` 里的 `rev` 应与 `uv.lock` 里的 ruff 对齐):

```bash
uv run pre-commit autoupdate
```

> ⚠️ Pre-commit 是"兜底",不是终极防线 — 新人忘了 `pre-commit install` 时它不会生效。**`.github/workflows/ci.yml` 里的 `ruff format --check` 仍然是最终守门员。**

---

## 15 个测试用例

```
tests/test_server.py
├── 导入测试
│   ├── test_import_server           — server 模块可导入
│   └── test_import_client_helper    — _get_client 函数存在
├── 工具注册测试
│   ├── test_tools_registered        — 57 个工具名全部正确
│   └── test_tool_count              — 工具数量恰好 57 个
├── 工具 Schema 测试
│   ├── test_send_tweet_has_text_param        — text 是必填参数
│   ├── test_send_tweet_has_optional_reply_to — reply_to 是可选参数
│   ├── test_search_tweets_has_query_param    — query 是必填参数
│   ├── test_search_tweets_has_product_param  — product 参数存在
│   ├── test_get_user_tweets_has_screen_name  — screen_name 必填
│   ├── test_get_tweet_has_tweet_id           — tweet_id 参数存在
│   └── test_all_tools_have_descriptions      — 所有工具都有描述
├── URL 解析测试
│   └── test_get_tweet_url_parsing   — 各种 URL 格式正确提取 ID
├── MCP 协议测试
│   └── test_mcp_initialize_handshake — JSON-RPC initialize 握手
└── 配置测试
    ├── test_cookies_path_env_override — 环境变量覆盖默认路径
    └── test_server_name               — server 名称是 "twitter"
```

---

## GitHub Actions CI

每次 push 到 `main` 或创建 PR 时自动运行。

配置文件：[`.github/workflows/ci.yml`](.github/workflows/ci.yml)

### 三个 Job

```
push/PR → GitHub Actions 触发
  │
  ├── lint job
  │   ├── ruff format --check    → 格式正确？
  │   └── ruff check             → 没有 lint 错误？
  │
  ├── test job (3 个 OS 并行)
  │   ├── ubuntu-latest   ─┐
  │   ├── macos-latest    ─┤─── uv sync → pytest -v
  │   └── windows-latest  ─┘
  │
  └── protocol job
      └── 发送 MCP initialize 请求 → 验证响应正确
```

### CI 不做什么

- **不调用 Twitter API** — 没有 cookies，也不应该在 CI 里操作真实账号
- **不发推/搜索/点赞** — 这些是"集成测试"，只能本地手动验证
- **不需要任何 secrets** — 所有测试都不依赖认证信息

### 查看 CI 状态

push 后在 GitHub repo 的 [Actions 页面](https://github.com/tangivis/twitter-mcp/actions) 查看运行结果。

README 顶部的 badge 也会显示最新状态：

[![CI](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml)

---

## 自动发布到 PyPI

配置文件：[`.github/workflows/publish.yml`](.github/workflows/publish.yml)

### 发布流程

```
打 git tag (v*) → GitHub Actions 触发
  │
  ├── test job
  │   ├── ruff lint + format
  │   └── pytest
  │
  └── publish job（test 通过后）
      ├── uv build          → 构建 .whl 和 .tar.gz
      └── pypi-publish      → 上传到 PyPI
```

### 如何发布新版本

```bash
# 1. 更新 pyproject.toml 里的 version
#    version = "0.2.0"

# 2. 提交
git add -A && git commit -m "release: v0.2.0"

# 3. 打 tag（必须以 v 开头）
git tag v0.2.0

# 4. 推送代码和 tag
git push && git push --tags

# 5. GitHub Actions 自动: 跑测试 → 构建 → 发布到 PyPI
```

### 首次发布：配置 Trusted Publisher

PyPI 推荐使用 [Trusted Publisher](https://docs.pypi.org/trusted-publishers/) 替代 API token，通过 GitHub Actions 的 OIDC 认证自动发布，不需要存储任何 secret。

**一次性设置步骤：**

1. 登录 [pypi.org](https://pypi.org)，进入账号设置
2. 点击 **Publishing** → **Add a new pending publisher**
3. 填写：
   - **PyPI Project Name:** `twikit-mcp`
   - **Owner:** `tangivis`
   - **Repository name:** `twitter-mcp`
   - **Workflow name:** `publish.yml`
   - **Environment name:** 留空
4. 点击 **Add**

设置完成后，打 `v*` tag 就会自动发布。

### 为什么用 Trusted Publisher 而不是 API Token？

| 方式 | 安全性 | 配置 |
|------|--------|------|
| API Token | 需要在 GitHub Secrets 里存 token，泄露风险 | 需要手动创建和轮换 |
| **Trusted Publisher** | 无 token，OIDC 短期凭证，自动过期 | PyPI 上一次性配置 |

本项目使用 Trusted Publisher（`pypa/gh-action-pypi-publish` + `id-token: write` 权限）。

---

## 添加新工具时的测试

如果你在 `server.py` 里加了新工具，对应也要：

1. 更新 `test_tools_registered` 里的 `expected` 集合
2. 更新 `test_tool_count` 里的数字
3. 为新工具的参数写 schema 测试
4. 如果有纯逻辑（如 URL 解析），单独测试那部分逻辑

例如添加了 `follow_user` 工具后：

```python
# tests/test_server.py

def test_follow_user_has_screen_name():
    """follow_user requires 'screen_name'."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["follow_user"]
    schema = tool.parameters
    assert "screen_name" in schema["properties"]
    assert "screen_name" in schema.get("required", [])
```

同时更新已有测试：

```python
def test_tool_count():
    """Exactly 8 tools are registered."""  # 7 → 8
    from twitter_mcp.server import mcp
    tools = mcp._tool_manager._tools
    assert len(tools) == 8

def test_tools_registered():
    """All 8 tools are registered."""
    from twitter_mcp.server import mcp
    tools = mcp._tool_manager._tools
    expected = {
        "send_tweet", "get_tweet", "get_timeline",
        "search_tweets", "like_tweet", "retweet",
        "get_user_tweets", "follow_user",  # 新增
    }
    assert set(tools.keys()) == expected
```
