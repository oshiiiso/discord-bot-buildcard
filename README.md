# Discord Bot - BuildCard

原神の UID から、プロフィール公開中の聖遺物スコア入りビルドカードを出す Bot（Python + discord.py）

個人・身内利用向けに開発した Bot です。ソースは公開しています。**不特定多数向けの配布・運用は想定していません**が、ソースの使い方は基本的に自由です。自分のサーバーで動かしたい場合は、[Issues](https://github.com/oshiiiso/discord-bot-buildcard/issues) か連絡をもらえればセットアップを補助します。

- リポジトリ: https://github.com/oshiiiso/discord-bot-buildcard
- 不具合・要望: [Issues](https://github.com/oshiiiso/discord-bot-buildcard/issues)
- 使い方: [docs/USER.md](docs/USER.md)
- 仕様: [docs/SPEC.md](docs/SPEC.md)

Discord 上の Bot 名は `BuildCard-Bot`。原神専用。

## 機能概要

- ピン留めとカード下のボタンから UID を入れてカードを出す
- プロフィールのキャラクター紹介に出しているキャラだけ選ぶ（所持全件ではない）
- 選択は UID を入れた本人だけ。カード画像はチャンネル公開
- 聖遺物スコアはサブステのみ（会心・攻撃%など）
- `/addchar` `/addset` でパッチ後のキャラ・セット表を足せる

## ディレクトリ構成

```
main.py                 # エントリーポイント
bot.py                  # Bot 本体
config.py               # 環境変数の読み込み
messages.py             # ユーザー向け文言
logging_config.py       # ログ設定
cogs/build.py           # スラッシュコマンド・カード投稿
games/genshin/          # スコア・定番判定・キャラ表
services/               # Enka 取得・カード描画・確認
ui/                     # 開始ボタン・UID 選択
data/genshin/           # キャラ・セット表（extras.json は追加分）
tools/                  # 表の再生成・立ち絵確認
docs/USER.md            # セットアップ・運用ガイド
docs/SPEC.md            # 仕様
storage/                # 実行時キャッシュ（.gitignore）
logs/                   # ログ（.gitignore）
tests/                  # 回帰テスト
```

## 開発環境セットアップ

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # トークン・チャンネル ID を編集
python main.py
```

詳細な手順・権限設定・コマンド一覧は [docs/USER.md](docs/USER.md) を参照。

### 環境変数（`.env`）

| 変数 | 説明 | デフォルト |
|---|---|---|
| `DISCORD_TOKEN` | Bot トークン | —（必須） |
| `GUILD_ID` | 動作させるサーバー ID | 未設定時はグローバル同期 |
| `CHANNEL_ID` | カード用テキストチャンネル ID（旧名 `GENSHIN_CHANNEL_ID` も可） | —（必須） |
| `LOG_LEVEL` | DEBUG / INFO / WARNING / ERROR | `INFO` |
| `LOG_RETENTION_DAYS` | ログ保持日数 | `30` |
| `ENKA_ASSET_RETENTION_DAYS` | 立ち絵などの画像キャッシュ保持日数（`0` で消さない） | `30` |

`.env` は Git に含めません。

### データ

Discord の `/addchar` `/addset` は `data/genshin/extras.json` に書く。再起動不要。`characters.json` / `artifact_sets.json` は触らない。

キャラ番号（`/addchar` の `number`）は Enka の `avatarId`。既存は `characters.json` の `enka_keys`。新規は UID API のレスポンスか `tools/enka_index.tsv`。

セット ID（`/addset` の `set_id`）は `artifact_sets.json` の `id`（例: `gladiator`）。定番判定の照合用。カード上のセット名は Enka の翻訳から出るので、未登録でも名前と点数は出る。

キャラ表の再生成（任意）:

```powershell
python tools/generate_genshin_data.py
```

`tools/enka_index.tsv` が必要。`extras.json` はそのまま残る。

立ち絵の CDN 実在確認:

```powershell
python tools/check_characters.py --online
```

Discord 上の確認は `/reload` → `/check`（`manage_messages`）。

## ブランチ運用

| ブランチ | 用途 |
|---------|------|
| **develop** | 日常の開発 |
| **main** | 確定版（develop からマージ。タグ `v*` で版を管理） |

### 普段の開発

```powershell
git checkout develop
# 作業 → commit → push
git push origin develop
```

### 確定版を出す（例: v0.1.0）

```powershell
git checkout main
git merge develop -m "release: v0.1.0"
git tag v0.1.0
git push origin main --tags
git checkout develop
```

## 注意事項

- Enka.Network の紹介枠 API に依存しています。障害・仕様変更・利用条件のリスクは自己責任でください。
- 本 Bot は個人サーバー向けです。公開サービスとしての提供は想定していません。
- このリポジトリのライセンス（MIT）が及ぶのは **ソースコードだけ** です。原神の立ち絵・名称や Enka から取得するデータは、それぞれの権利者のものです。

## ライセンス

MIT License — Copyright (c) 2026 oshiiiso

詳細は [LICENSE](LICENSE) を参照。
