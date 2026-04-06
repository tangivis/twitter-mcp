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
├── test_tools_registered                — 7 个工具仍在
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
