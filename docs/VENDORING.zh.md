# Vendoring twikit — 开发文档

## 背景

### 问题

PyPI 不允许 `git+` URL 作为依赖：
```toml
# 这个能在本地用，但 PyPI 拒绝
twikit @ git+https://github.com/d60/twikit.git@refs/pull/412/head
```

PyPI 上的 twikit 2.3.3 有两个已知 bug：
1. `transaction.py` 中 `ON_DEMAND_FILE_REGEX` 匹配失败 → `"Couldn't get KEY_BYTE indices"` 报错
2. `gql.py` 中搜索请求用 GET 而不是 POST → 搜索功能失败

这两个 bug 在 PR#412 中已修复，但尚未合并到 twikit 主分支。

### 解决方案：Vendoring

将 twikit 整个包复制到本项目中（`twitter_mcp/_vendor/twikit/`），并应用 PR#412 的修复。

这样：
- `pyproject.toml` 中不再依赖 `twikit`
- 所有代码自包含，可正常发布到 PyPI
- 不需要等待上游合并 PR

### 退出策略

当 twikit 发布包含 PR#412 修复的新版本（>2.3.3）后：
1. 删除 `twitter_mcp/_vendor/twikit/`
2. 在 `pyproject.toml` 中改回 `"twikit>=2.3.4"`
3. 修改 `server.py` 中的 import 回 `from twikit import Client`

---

## 本地 patch 清单

除了从 PR#412 引入的两个修复外，vendored 代码还包含我们自己发现并修复的 bug。

| 版本 | 文件 | 修复内容 |
|------|------|---------|
| 0.1.3 | `_vendor/twikit/user.py` | `User.__init__` 容忍 `legacy.entities.description.urls` 和 `legacy.withheld_in_countries` 缺失 |
| 0.1.4 | `_vendor/twikit/user.py` | `User.__init__` 全面防御化，所有 `legacy.*` 字段改 `.get()` 带默认值 |
| 0.1.5 | `_vendor/twikit/tweet.py` | `Tweet` 属性全面防御化：`text`/`created_at`/`lang`/`favorite_count`/`retweet_count`/`reply_count`/`favorited`/`is_quote_status` 以及 `entities.*` 子树（hashtags/urls/media）都走 `.get()`。构造时 `_data["legacy"]` 也改为可选。|
| 0.1.9 | `_vendor/twikit/client/gql.py` | `GQLClient.tweet_result_by_rest_id` 把 `fieldToggles.withArticlePlainText` 从 `False` 翻成 `True`。这是 issue #10 修复 `get_article` 的关键一步：上游默认抑制 article 正文，翻成 `True` 后 `.article.article_results.result.plain_text` 才会真的填充。改动在源文件里加了 `# twitter-mcp patch (issue #10)` 注释,下次 vendor 刷新时不要漏掉。|
| 0.1.21 | `_vendor/twikit/client/client.py` | `Client.get_lists` 防御化 items[1] 遍历。issue #37 暴露:burner 0 lists 时 X 在 items[1] 塞了 promo 卡片或没有 `itemContent.list` 的 cell,上游用 `list["item"]["itemContent"]["list"]` 直挂 KeyError。改成 `.get()` 链 + 跳过没 list payload 的 entry。打了 `# twitter-mcp patch (issue #37)` 标记 + `tests/test_vendor.py::test_get_lists_skips_non_list_entries` 双重 guard,下次 vendor 刷新别漏。|

### 为什么要防御化 `User.__init__`

**问题：** X 的 GraphQL 响应并不保证 `legacy.*` 下的所有字段都存在。实际观察到的缺失场景：

- 账号没 pinned tweet → `pinned_tweet_ids_str` 不返回（触发 `@ClaudeDevs` 的 bug）
- 账号没受地区限制 → `withheld_in_countries` 不返回（触发 `@elonmusk` 的 bug）
- 账号 profile description 为空 → `entities.description.urls` 不返回
- 新建/冻结/不活跃账号 → counts、flags 等字段可能大面积缺失

上游 twikit 在 `__init__` 里用 `legacy["key"]` 严格索引，任一字段缺失就抛 `KeyError`，连锁导致所有依赖 `User` 对象的工具（`get_user_tweets`、`client.user()` 等）全部不可用。

**解决方式：** `__init__` 里所有 `legacy[...]` 改为 `.get(..., 默认值)`，默认值按类型：

| 类型 | 默认 |
|------|------|
| 计数类（`*_count`） | `0` |
| 布尔标志 | `False` |
| 列表类（`*_ids`、`withheld_in_countries`） | `[]` |
| 字符串类（`name`、`location`、`description`） | `""` |
| 可选 URL（`profile_banner_url`、`url`） | `None`（保留原行为） |
| `translator_type` | `"none"` |

外层 `data["rest_id"]` 保留严格访问 —— `rest_id` 是 X API 的核心标识，缺失才是真异常。

**回归测试：** `tests/test_user_parsing.py` 和 `tests/test_tweet_parsing.py` 对每个可缺失字段做单独的参数化测试，外加「整个 `legacy` 为空 dict」的兜底用例，合计 51 个模型解析测试。

### 0.1.5：同时补齐 server.py 的测试覆盖

发现 `User` / `Tweet` 这类字段稳定性问题后，补了一整层 mock-based 行为测试：

- `tests/test_tools.py` — 57 个 MCP 工具的行为测试（args 传参、JSON 输出形状、text 截断、URL 解析）
- `tests/test_cookies.py` — `_get_client` 的错误路径（文件缺失、JSON 损坏、缺 `ct0`/`auth_token` 键）

现在 `twitter_mcp/server.py` 达到 **100% 覆盖**，CI 启用 `--cov-fail-under=95` 作为底线。

### 0.1.9：为什么要翻 `withArticlePlainText`

**问题:** issue #10 揭示 `get_article` 在 0.1.8 完全不工作 — 调的是 X 的**编辑器** op `ArticleEntityResultByRestId`,对你没创作过的 article 永远返回 `result: {}`。Reader 实际是双跳流程:`ArticleRedirectScreenQuery` 把 article rest_id 解析成 tweet rest_id,然后 `TweetResultByRestId` 取那条 tweet 的 article 正文。

而双跳流程的第二跳要拿到正文,必须把 `fieldToggles.withArticlePlainText` 设成 `True`。上游 twikit 默认是 `False`,所以正文 (`tweet.article.article_results.result.plain_text`) 被抑制,只剩 metadata。

**改动:** 唯一的改动是 `_vendor/twikit/client/gql.py::tweet_result_by_rest_id` 里的一行 — `'withArticlePlainText': False` → `True`。改动旁边带 `# twitter-mcp patch (issue #10)` 注释,下次同步上游时不要漏掉。

**回归测试:** `tests/test_articles.py::test_vendor_tweet_result_passes_article_plain_text_true` 通过 `inspect.getsource()` 读源码,断言 `False` 形式不存在、`True` 形式存在 — 即便有人在重做 vendor 的时候不小心覆盖回去也会被 CI 立刻揪出来。

---

## PR#412 修复内容

PR#412 包含 5 个 commit，改了 2 个文件（忽略 .gitignore）：

### 修复 1: `twikit/x_client_transaction/transaction.py`

**问题：** Twitter 修改了前端 JS 的打包格式，旧的正则表达式无法匹配 `ondemand.s` 文件的 hash。

**改动：**

```python
# 旧代码（PyPI 2.3.3，已失效）
ON_DEMAND_FILE_REGEX = re.compile(
    r"""['|\"]{1}ondemand\.s['|\"]{1}:\s*['|\"]{1}([\w]*)['|\"]{1}""",
    flags=(re.VERBOSE | re.MULTILINE))

# 新代码（PR#412）
ON_DEMAND_FILE_REGEX = re.compile(
    r""",(\d+):["']ondemand\.s["']""",
    flags=(re.VERBOSE | re.MULTILINE))
ON_DEMAND_HASH_PATTERN = r',{}:\"([0-9a-f]+)\"'
```

`get_indices()` 方法的查找逻辑也相应调整：先匹配 index，再用 index 找 hash，最后拼接 URL。

### 修复 2: `twikit/client/gql.py`

**问题：** Twitter 搜索 API 端点不再接受 GET 请求。

**改动：**

```python
# 旧代码
return await self.gql_get(Endpoint.SEARCH_TIMELINE, variables, FEATURES)

# 新代码
return await self.gql_post(Endpoint.SEARCH_TIMELINE, variables, FEATURES)
```

---

## 实施计划

### 目录结构

```
twitter_mcp/
├── __init__.py
├── server.py                    ← MCP server（修改 import 路径）
└── _vendor/                     ← vendored 第三方库
    └── twikit/                  ← 完整的 twikit 包（含 PR#412 修复）
        ├── __init__.py
        ├── client/
        │   ├── client.py
        │   ├── gql.py           ← 修复 2: gql_get → gql_post
        │   └── v11.py
        ├── x_client_transaction/
        │   ├── transaction.py   ← 修复 1: 正则 + 查找逻辑
        │   └── ...
        └── ...（其余文件原样复制）
```

### 需要修改的文件

| 文件 | 改动 |
|------|------|
| `twitter_mcp/_vendor/twikit/x_client_transaction/transaction.py` | 应用 PR#412 的正则和 get_indices 修复 |
| `twitter_mcp/_vendor/twikit/client/gql.py` | `gql_get` → `gql_post`（第 159 行） |
| `twitter_mcp/server.py` | import 路径从 `from twikit import Client` 改为 `from twitter_mcp._vendor.twikit import Client` |
| `pyproject.toml` | 移除 `twikit` 依赖，添加 twikit 的子依赖（httpx, beautifulsoup4 等） |

### twikit 的依赖（需要加到 pyproject.toml）

从 twikit 的 pyproject.toml 中提取：

```toml
dependencies = [
    "mcp[cli]",
    # twikit 原依赖（vendored 后需要自己声明）
    "httpx[socks]",
    "beautifulsoup4",
    "lxml",
    "filetype",
    "pyotp",
    "pyjwt",
    "m3u8",
    "webvtt-py",
    "pyjsparser",
    "js2py-3-13",
    "cryptography",
]
```

---

## TDD 计划

### 第一阶段：验证 vendor 目录结构（不改任何代码）

```
tests/test_vendor.py
├── test_vendor_twikit_importable        — _vendor.twikit 能 import
├── test_vendor_client_importable        — _vendor.twikit.Client 能 import
├── test_vendor_transaction_importable   — _vendor.twikit.x_client_transaction 能 import
└── test_vendor_gql_importable           — _vendor.twikit.client.gql 能 import
```

### 第二阶段：验证 PR#412 修复已应用

```
tests/test_vendor_patches.py
├── test_on_demand_regex_new_format      — ON_DEMAND_FILE_REGEX 匹配新格式
├── test_on_demand_regex_not_old_format  — 旧正则已被替换
├── test_on_demand_hash_pattern_exists   — ON_DEMAND_HASH_PATTERN 变量存在
├── test_search_uses_gql_post            — search_timeline 用 gql_post 不是 gql_get
└── test_get_indices_error_messages      — get_indices 失败时有清晰的错误信息
```

### 第三阶段：验证 server.py 使用 vendor 版本

```
tests/test_server.py（更新现有测试）
├── test_import_server                   — server 仍能 import
├── test_tools_registered                — 57 个工具仍在
└── test_client_uses_vendor              — _get_client 使用的是 _vendor.twikit.Client
```

### 第四阶段：验证 pyproject.toml 无 git 依赖

```
tests/test_packaging.py
├── test_no_git_dependencies             — pyproject.toml 中没有 git+ URL
├── test_package_builds                  — uv build 成功
└── test_twikit_not_in_dependencies      — "twikit" 不在 dependencies 列表中
```

---

## 风险和注意事项

### 许可证

twikit 使用 MIT 许可证，允许 vendoring。需要：
- 在 `_vendor/twikit/` 目录下保留原始 LICENSE 文件
- 在项目 README 中标注 "Built with twikit"（已有）

### 代码量

twikit 完整包约 14,900 行 Python 代码。全部 vendor 会让项目体积增大，但：
- 这是标准做法（pip 自身也 vendor 了 requests、certifi 等）
- 保持完整包比只复制部分文件更不容易出问题
- 将来切回 PyPI 依赖时只需删目录 + 改 import

### 更新维护

vendored 代码不会自动更新。如果 twikit 发布了新功能：
- 短期：手动同步需要的改动
- 长期：等 PR#412 合并后切回 PyPI 依赖（退出策略）

## 上游参考索引（2026-05 调研）

upstream `d60/twikit` 自 2025-04-22 之后**事实停更**（156 open issues / 13 open PR 无人 review），我们 vendor 的 2.3.3 ≈ upstream HEAD。anti-bot drift 的修法都散在 open PR 里。本表登记**值得在我们用户撞上时回头查的修复**，懒人手册：症状对得上 → 抄对应 patch → 在「本地 patch 清单」里加一行。

| 症状 / 失败模式 | 上游 PR / Issue | 影响我们的代码 | 备注 |
|---|---|---|---|
| `ClientTransaction` 初始化崩 — X 换了 webpack chunk 格式，`ondemand.s.js` 正则失配 | [#408](https://github.com/d60/twikit/issues/408) / [#409](https://github.com/d60/twikit/issues/409) / [#410](https://github.com/d60/twikit/pull/410) / [#411](https://github.com/d60/twikit/pull/411) / [#416](https://github.com/d60/twikit/pull/416) | `_vendor/twikit/x_client_transaction/` | 我们沿用同一段代码，X 下次推 chunk 我们也会炸 |
| `search_timeline` 返回 404 — 要改 GET → POST | [#412](https://github.com/d60/twikit/pull/412) / [#419](https://github.com/d60/twikit/pull/419) | `_vendor/twikit/client/gql.py` 的 search 路径，影响 `search_tweets` 工具 | 我们已经合过早期的 #412（见上一节），后续 #419 是延伸修复 |
| `User.__init__` / `Client.request` 偶发 `KeyError`（X 偷偷不发某些字段） | [#417](https://github.com/d60/twikit/issues/417) / [#418](https://github.com/d60/twikit/pull/418) | `_vendor/twikit/user.py` 等 model 类 | 同 0.1.4 的 `User.__init__` 防御化思路；`tests/test_fixture_shapes.py` 是配套护栏 |
| transaction-id key 提取 fallback（主正则 miss 时兜底） | [#407](https://github.com/d60/twikit/pull/407) | `_vendor/twikit/x_client_transaction/` | 配合上面 #410 系列 |
| 登录加 Castle (Arkose 类) token 检验 | [#393](https://github.com/d60/twikit/pull/393) | 不影响 — 我们 cookie-only，不走 `login()` 流程 | 知道一下，避免误诊 |

### 怎么用这张表

1. CI 红 / live-smoke 红 / 用户 issue 报错，先**对症状那一列**。
2. 命中 → 去对应 PR 的 diff（GitHub UI 上 `Files changed` tab）拿原始改动。
3. 在 `_vendor/twikit/` 对应文件应用 patch，**加 `# twitter-mcp patch (issue #N)` 标记**（同我们已有约定）。
4. 在「本地 patch 清单」加一行说明（来源 upstream PR 号 + 我们 issue 号）。
5. 加 mock 回归测试 → CI 通过 → PR 合并。

未命中 → 回上游 issue 列表搜关键词，没找到再开新 issue / 自己写 patch。这张表保持**当前实际撞上的工程问题**为主，不要把所有 PR 都搬过来。
