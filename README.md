# LINE家計管理Bot

LINEにレシート写真を送るだけで、支出を自動記録・折半計算・月次レポートを送信する2人用家計管理ボット。

---

## 機能

- **レシートOCR** — レシート画像をGPT-4o Visionで読み取り、店名・金額・商品一覧を自動抽出
- **店舗情報補完** — Google Maps Places APIで店舗カテゴリを取得
- **カテゴリ自動判定** — 「食費」「日用品」「外食」などをGPT-4o-miniで自動分類
- **支出記録** — Google Sheetsに支出・商品明細を自動保存
- **折半計算** — 月の支出合計から2人の負担差額を計算
- **月次レポート** — 月末にLINEへ自動送信

---

## 使い方

### レシートを登録する

1. LINEのグループトークまたはBotとのトークで **レシート写真を送信**
2. Botが読み取り結果を返信
   ```
   📸 レシートを読み取りました

   🏪 セブンイレブン新宿店
   📅 2024/06/10
   💰 合計: 1,230円
   📂 カテゴリ: コンビニ
   🙋 支払い: 志水

   ✅ この内容で登録しますか？
   ```
3. **「はい」** を返信 → スプレッドシートに記録される
4. 内容が違う場合は **「いいえ」** または **「修正」** を返信

### 手動で登録する（レシートなし）

リッチメニューの「手入力」ボタンを押すか、テキストで以下の形式を送信：
```
手入力
```
対話形式で店名・金額・カテゴリ・支払い者を入力できます。

### 月次レポートを見る

月末に自動送信されます。手動で確認したい場合はリッチメニューの「月次レポート」を押してください。

---

## セットアップ

### 必要なもの

- LINE Developersアカウント
- Googleアカウント（Sheets API利用）
- OpenAI APIキー
- Google Maps APIキー
- [Railway](https://railway.app) アカウント（デプロイ先）

---

### 1. LINE公式アカウント作成

1. [LINE Developers](https://developers.line.biz/) にアクセスしてログイン
2. 「新規プロバイダー作成」→ 任意の名前を入力
3. 「Messaging APIチャネル」を作成
4. 「Messaging API設定」タブから以下を取得：
   - **Channel Secret** → `LINE_CHANNEL_SECRET`
   - **チャネルアクセストークン（長期）**（「発行」ボタンを押す）→ `LINE_CHANNEL_ACCESS_TOKEN`
5. QRコードからBotを友達追加 → グループLINEに招待
6. 「グループトークへの参加を許可する」をONにする
7. 「応答メッセージ」をOFFにする

---

### 2. Google Sheets 設定

#### サービスアカウントの作成

1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクトを作成
2. 「APIとサービス」→「ライブラリ」→「Google Sheets API」を有効化
3. 「APIとサービス」→「認証情報」→「サービスアカウント作成」
4. 作成したサービスアカウント →「キー」タブ →「鍵を追加」→「JSON」でダウンロード

#### スプレッドシートの作成・共有

1. [Google Sheets](https://sheets.google.com) で新規スプレッドシートを作成
2. URLからIDを取得: `https://docs.google.com/spreadsheets/d/【このID】/edit`
3. 「共有」→ サービスアカウントのメール（`xxx@project.iam.gserviceaccount.com`）を **編集者** として追加

#### JSONを環境変数用の1行文字列に変換

```bash
python -c "import json; print(json.dumps(json.load(open('service_account.json'))))"
```

出力をそのまま `GOOGLE_SERVICE_ACCOUNT_JSON` に使用します。

---

### 3. Google Maps APIキー取得

1. Google Cloud Console →「APIとサービス」→「ライブラリ」→ **Places API (New)** を有効化
2. 「認証情報」→「APIキーを作成」
3. 取得したキーを `GOOGLE_MAPS_API_KEY` に設定

> 月5ドル程度の無料枠があります。個人利用では超えることはほぼありません。

---

### 4. OpenAI APIキー取得

1. [OpenAI Platform](https://platform.openai.com/) →「API keys」→「Create new secret key」
2. 取得したキーを `OPENAI_API_KEY` に設定

---

### 5. Railway デプロイ

```bash
npm install -g @railway/cli
railway login
railway init
railway up
```

デプロイ後、Railway ダッシュボードの「Settings」→「Domains」でURLを確認します。

#### 環境変数の設定

Railway ダッシュボード → Variables タブで以下をすべて設定：

| 変数名 | 値 |
|--------|-----|
| `LINE_CHANNEL_SECRET` | LINEから取得 |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINEから取得 |
| `GOOGLE_SHEETS_SPREADSHEET_ID` | スプレッドシートID |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | JSONを1行にしたもの |
| `GOOGLE_MAPS_API_KEY` | Mapsから取得 |
| `OPENAI_API_KEY` | OpenAIから取得 |
| `SHIMIZU_USER_ID` | 次のステップで取得 |
| `CRON_SECRET` | 任意の文字列（例: `random_secret_12345`） |

---

### 6. LINE WebhookにURLを設定

1. LINE Developers → チャネルページ →「Messaging API設定」タブ
2. 「Webhook URL」に入力:
   ```
   https://your-app.up.railway.app/webhook
   ```
3. 「検証」ボタンで成功を確認 →「Webhookの利用」をON

---

### 7. 自分のLINEユーザーIDを設定

1. デプロイ後にLINEから任意のテキスト（例: 「テスト」）を送信
2. Railway ダッシュボード →「Deployments」→「Logs」を開く
3. ログに `user_id: Uxxxxxxxxx` の形式でIDが表示される
4. `SHIMIZU_USER_ID` に設定して再デプロイ

> このIDを使って「誰が支払ったか」を自動判定します。

---

### 8. 動作確認

1. グループLINEにレシート画像を送信
2. 数秒後に確認メッセージが返ってくることを確認
3. 「はい」を押して登録完了メッセージを確認
4. スプレッドシートの「支出記録」シートにデータが追加されていることを確認

---

## トラブルシューティング

| 症状 | 原因 | 対処 |
|------|------|------|
| Webhook検証失敗 | URLが間違っている | `/webhook` まで含めているか確認 |
| レシート読み取りエラー | OpenAI APIキー不正 | `OPENAI_API_KEY` を確認 |
| Sheets保存失敗 | サービスアカウント未共有 | シートをサービスアカウントのメールで共有 |
| 店舗情報が取得できない | Maps APIキー不正 | `GOOGLE_MAPS_API_KEY` と Places API の有効化を確認 |
| 支払い者が常に「彼女」になる | `SHIMIZU_USER_ID` 未設定 | ログからIDを取得して設定・再デプロイ |

---

## 技術構成

```
LINE Messaging API
    ↓ Webhook
FastAPI (Railway)
    ├── OCR: GPT-4o Vision  → レシート画像 → JSON
    ├── 店舗情報: Google Maps Places API (New)
    ├── カテゴリ判定: GPT-4o-mini
    └── 記録: Google Sheets API
```

### 主要ファイル

| ファイル | 役割 |
|----------|------|
| `app/main.py` | FastAPIエントリポイント、webhookルーティング |
| `app/line_handler.py` | メッセージ振り分け、確認フロー管理 |
| `app/ocr.py` | GPT-4o VisionによるレシートOCR |
| `app/maps.py` | Google Maps Places API で店舗情報取得 |
| `app/ai.py` | GPT-4o-mini によるカテゴリ自動判定 |
| `app/sheets.py` | Google Sheetsへの読み書き |
| `app/calculator.py` | 折半計算・月次レポート生成 |
| `app/models.py` | データモデル定義 |

### 使用モデル

- **gpt-4o** — レシートOCR（画像認識）
- **gpt-4o-mini** — カテゴリ自動判定（テキスト分類）

### スプレッドシートのシート構成

| シート名 | 内容 |
|----------|------|
| 支出記録 | 日付・店名・金額・カテゴリ・支払い者 |
| 商品明細 | レシートの個別商品リスト |
| 月次集計 | 月ごとの合計・折半額 |

---

## ローカル開発

```bash
# 依存関係インストール
pip install -r requirements.txt

# .envファイルを作成（.env.exampleをコピー）
cp .env.example .env
# .envを編集して各種キーを設定

# 起動
uvicorn app.main:app --reload
```
