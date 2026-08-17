# インストール + MCP クライアントへの登録

3 ステップ。ステップ 3 でクライアントを選びます。

## 1. バイナリをインストール

```bash
uv tool install twikit-mcp
```

なぜ `uv tool install`:`twikit-mcp` を独立環境(依存衝突なし)で `PATH` 上に配置、以降の起動は瞬時、アップグレードは `uv tool upgrade twikit-mcp` の一行で完結。

`uv` がない場合:[1 行でインストール](https://docs.astral.sh/uv/getting-started/installation/)(macOS / Linux は curl 一発)。`pipx` / `pip` でも OK — 詳細は [README "Choose your install"](https://github.com/tangivis/twitter-mcp#choose-your-install) を参照。

## 2. X の cookies を配置

ブラウザで [x.com](https://x.com) にログイン → DevTools(F12)→ **Application** → **Cookies** → `https://x.com`。`ct0` と `auth_token` をコピー。

```bash
mkdir -p ~/.config/twitter-mcp
cat > ~/.config/twitter-mcp/cookies.json <<'EOF'
{"ct0": "...", "auth_token": "..."}
EOF
chmod 600 ~/.config/twitter-mcp/cookies.json
```

## 3. クライアントへの登録

JSON の形(`mcpServers` ブロック)はどのクライアントでも同じ、**設定ファイルの場所**だけが違います。`/home/YOU` は自分のホームに置き換えてください。

### Claude Code

CLI 一発、JSON を編集不要:

```bash
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- twikit-mcp
```

### Claude Desktop

| OS | 設定ファイル |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

ファイルがなければ作成、以下を追加:

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

Claude Desktop を再起動。

### Cursor

`~/.cursor/mcp.json`(グローバル)または `.cursor/mcp.json`(プロジェクト単位)を編集:

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

Cursor は自動リロードするので再起動不要。

### Windsurf

`~/.codeium/windsurf/mcp_config.json` を編集:

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

Windsurf を再起動。

### Cline(VS Code 拡張)

Cline パネル → ⚙️ → **MCP Servers** → **Edit MCP Settings** を開く。保存すると自動リロード。

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

`~/.config/opencode/config.json` を編集:

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

Pi には MCP が組み込まれていません — まずコミュニティ製の MCP 拡張を入れます。[`pi-mcp-adapter`](https://github.com/nicobailon/pi-mcp-adapter) がこの server には最適です:設定の形は上記と同じ `mcpServers`、接続は遅延、そして `directTools` の許可リストで `twikit-mcp` の 62 ツールがコーディングセッションのコンテキストを圧迫するのを防げます。

```bash
pi install npm:pi-mcp-adapter
```

次に `~/.config/mcp/mcp.json`(グローバル)または `.mcp.json`(プロジェクト単位)を編集:

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

`directTools` の 7 つはネイティブツールとして登録され、残り 55 は 1 つのプロキシツールの背後で必要時に発見されます。`command` は**絶対パス**で書いてください — Pi のサブプロセス環境の `PATH` に `~/.local/bin` が入っているとは限りません。

Pi の MCP 拡張はいずれもコミュニティ製で公式ではなく、あなたのフルシステム権限で動きます。cookie のパスを預ける前にソースを確認してください。

### DeepSeek Harness(dsh)

[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) は公式の MCP クライアント(`@deepseek-ai/dsh-mcp-client`)を同梱しているため、コミュニティ拡張は不要です。設定は `mcpServers` マップではなく、`cordis.yml` のプラグインエントリとして書きます:

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

`serverName` がツール名の名前空間になり、モデルからは `mcp__twitter__get_tweet` や `mcp__twitter__search_tweets` として見えます。

Pi と違い、**dsh にはツールの許可リストがありません** — 62 ツールすべてが登録され、一部だけを公開する公式な方法はないため、コンテキストの余裕を見込んでおいてください。

知っておくと便利なオプション:`failOnStartupError: true` は cookie パスの誤りを黙って握りつぶさず起動時に失敗させます。`toolCallTimeoutMs`(既定 `60000`)は重い読み取りに大きな `count` を渡す場合に引き上げる価値があります。`reconnect` グループ(`enabled`、`initialDelayMs`、`maxDelayMs`、`maxAttempts`)は再接続の挙動を制御します —— dsh は倍々のバックオフで再試行し、`maxAttempts` 回連続で失敗するとその server のツールを登録解除、接続が安定すると回数をリセットします。

複数インスタンスを動かす場合、`serverName` は必ず別々にしてください:稼働中のインスタンス間で重複すると、後から読み込まれたプラグインが load 時に失敗します。

dsh は developer preview であり設定の形が変わる可能性があります。上記のキーが合わなくなっていたら[プラグインの README](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.md) を確認してください。

### その他の MCP クライアント

`twikit-mcp` は標準的な **stdio** MCP サーバーです。クライアントの設定ファイルがどんな形でも、JSON の形は同じ:

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

クライアントによっては `mcpServers` ではなく `mcp.servers` を使ったり、別のトップレベル key の中にネストすることもあります — クライアントのドキュメントを確認してください。`command` と `env` フィールドはどこでも共通です。

## 動作確認

クライアントで質問してみる:

> AI 関連のツイートを検索して

エージェントが `search_tweets` を呼び結果を返せば OK。権限エラーが出たら `cookies.json` のパスが間違っているはず — 上の JSON の `TWITTER_COOKIES` を再確認。

## アップグレード

```bash
uv tool upgrade twikit-mcp
```

完了 — 次回クライアント起動時に新しいバイナリが使われます。
