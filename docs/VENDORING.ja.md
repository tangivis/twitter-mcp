# twikit のベンダリング

> ⚠️ このパッチログは現在 **中国語のみ** です。**上部の言語切り替えで「中文」を選択** してください。または [GitHub](https://github.com/tangivis/twitter-mcp/blob/main/docs/VENDORING.zh.md) で閲覧してください。

## なぜ存在するか(日本語サマリ)

PyPI は依存に `git+` URL を許可しませんが、PyPI 上の `twikit` 2.3.3 には PR#412 で修正済みの既知バグが 2 つあります(執筆時点でマージ未完)。加えて、X のレスポンス形状が変動するため防御的パースが必要です。

`pip install twikit-mcp` がすぐ動くよう、`twikit` パッケージ全体を `twitter_mcp/_vendor/twikit/` にベンダリングし、PR#412 の修正と独自の追加パッチを適用しています。

## パッチログ(日本語サマリ)

| バージョン | ファイル | 修正内容 |
|---|---|---|
| 0.1.3 | `_vendor/twikit/user.py` | `User.__init__` が `legacy.entities.description.urls` と `legacy.withheld_in_countries` の欠落を許容 |
| 0.1.4 | `_vendor/twikit/user.py` | `User.__init__` を全面的に防御化 — すべての `legacy.*` フィールドが `.get()` + 型別デフォルト |
| 0.1.5 | `_vendor/twikit/tweet.py` | `Tweet` プロパティと `entities.*` サブツリーを全面防御化 |
| 0.1.9 | `_vendor/twikit/client/gql.py` | `tweet_result_by_rest_id` の `fieldToggles.withArticlePlainText` を `False` → `True`(issue #10 — 修正前は記事本文が空) |
| 0.1.21 | `_vendor/twikit/client/client.py` | `get_lists` がブラケットアクセスではなく `.get()` チェーンを使用(issue #37 — リスト 0 個のバーナーアカウントで `KeyError: 'list'`) |

## 撤退戦略

`twikit` が PR#412 マージ済みで > 2.3.3 をリリースしたら:

1. `twitter_mcp/_vendor/twikit/` を削除
2. `pyproject.toml` の `dependencies` に `"twikit>=X.Y.Z"` を追加
3. `server.py` のインポートを `from twikit import Client` に戻す

それまでは各パッチに `# twitter-mcp patch (issue #N)` マーカーを付け、中国語版のパッチテーブル(上部の言語切り替えから)で追跡しています。

## 翻訳コントリビュート歓迎

`docs/VENDORING.ja.md` を充実させる PR をお待ちしています。中国語ページは事実情報(コミットハッシュ、ファイルパス、問題/解決ペア)中心なので、直訳でも十分機能します。
