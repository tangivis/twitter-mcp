# Technical design

> ⚠️ This deep-dive is currently authored in 中文 only. Switch the **language toggle in the top bar to 中文** to read it, or browse the source on [GitHub](https://github.com/tangivis/twitter-mcp/blob/main/docs/TECHNICAL.zh.md).
>
> An English translation is welcome — open a PR adding `docs/TECHNICAL.en.md` content. The page is internals-focused (MCP protocol, FastMCP, tool registration mechanics, cookie auth flow) so a literal translation works fine.

## TL;DR pointers (English)

If you're an English-only reader who lands here looking for high-level info, here's the elevator pitch:

- **What is MCP?** A JSON-RPC 2.0 protocol over stdio that lets an LLM client (Claude Code, Cursor, …) discover and call "tools" exposed by a server process. Think of it as a typed function-call interface for LLMs.
- **What does this server do?** Wraps every public method on the vendored [twikit](https://github.com/d60/twikit) Twitter/X client as an `@mcp.tool()`-decorated async function. 57 tools total. The LLM picks one based on user intent + the tool's docstring.
- **Why vendored twikit?** Two upstream PR-#412 fixes that aren't released to PyPI yet, plus our own defensive `.get()` patches. See [Vendoring twikit](VENDORING.md).
- **Auth model?** Browser cookies (`ct0` + `auth_token`) lifted from a logged-in X session. No developer-account approval, no $200/mo API tier.

For the granular details (FastMCP internals, tool output budget shaping, server lifecycle in Claude Code, etc.) — please toggle to the 中文 version above.
