# 技術設計

> ⚠️ この詳細解説は現在 **中国語のみ** です。**上部の言語切り替えで「中文」を選択** するか、[GitHub](https://github.com/tangivis/twitter-mcp/blob/main/docs/TECHNICAL.zh.md) で閲覧してください。
>
> 日本語訳の PR を歓迎します(`docs/TECHNICAL.ja.md` の内容追加)。内部実装にフォーカスした内容(MCP プロトコル、FastMCP、ツール登録機構、cookie 認証フロー)なので、直訳で問題ありません。

## TL;DR(日本語)

英語/日本語のみのリーダー向けに概要だけ:

- **MCP とは?** stdio 経由の JSON-RPC 2.0 プロトコル。LLM クライアント(Claude Code、Cursor 等)がサーバープロセスから「ツール」を発見・呼び出すための仕組み。LLM 向けの型付き関数呼び出しインターフェースと考えれば OK。
- **このサーバーは何を?** ベンダリングした [twikit](https://github.com/d60/twikit) の公開メソッドを `@mcp.tool()` デコレータ付き async 関数として 57 個ラップしています。LLM がユーザー意図 + ツール docstring から選択します。
- **なぜ twikit をベンダリング?** PyPI 未リリースの上流 PR-#412 修正と、プロジェクト独自の防御パッチを含めるため。詳細は [Vendoring twikit](VENDORING.md)。
- **認証?** ログイン済み X セッションから取得したブラウザ cookies(`ct0` + `auth_token`)。開発者アカウント申請も $200/月の API 階層も不要。

詳細(FastMCP 内部、ツール出力バジェット制御、Claude Code でのサーバーライフサイクル等)は中国語版へ。
