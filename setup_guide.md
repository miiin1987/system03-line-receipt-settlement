# セットアップガイド

## 全体の流れ

1. LINE公式アカウント作成・チャネル設定
2. Google Sheets スプレッドシート作成
3. Google Maps API キー取得
4. OpenAI API キー取得
5. Railwayにデプロイ
6. LINE WebhookにURLを設定

---

## 1. LINE公式アカウント作成

### 1-1. LINE Developersにアクセス

https://developers.line.biz/ にアクセスし、LINEアカウントでログイン。

### 1-2. プロバイダー作成

「新規プロバイダー作成」→ 任意の名前（例: 家計管理Bot）

### 1-3. チャネル作成

「Messaging APIチャネル」を選択し、以下を入力：
- チャネル名: 家計管理Bot（任意）
- チャネル説明: 任意
- 大業種・小業種: 任意

### 1-4. 認証情報の取得

チャネルページの「Messaging API設定」タブから：
- **Channel Secret** → `.env` の `LINE_CHANNEL_SECRET` に貼る
- **チャネルアクセストークン（長期）** → 「発行」ボタンを押して `.env` の `LINE_CHANNEL_ACCESS_TOKEN` に貼る

### 1-5. グループLINEに招待

- 「Messaging API設定」タブの QRコード からBotを友達追加
- 志水さんと彼女さんのグループLINEにBotを招待
- 「グループトークへの参加を許可する」をONにする

---

## 2. Google Sheets スプレッドシート作成

### 2-1. サービスアカウントのJSONを取得

既に Google Sheets API の認証済み環境がある場合、サービスアカウントのJSONファイルを用意してください。

なければ：
1. https://console.cloud.google.com/ にアクセス
2. プロジェクトを選択 or 新規作成
3. 「APIとサービス」→「認証情報」→「サービスアカウント作成」
4. 作成したサービスアカウントをクリック →「キー」タブ → 「鍵を追加」→「JSON」でダウンロード
5. Google Sheets API を有効化：「APIとサービス」→「ライブラリ」→「Google Sheets API」→「有効にする」

### 2-2. スプレッドシートを作成・共有

1. https://sheets.google.com で新規スプレッドシートを作成
2. スプレッドシートのURLから ID を取得
   - 例: `https://docs.google.com/spreadsheets/d/【ここがID】/edit`
3. 画面右上「共有」→ サービスアカウントのメールアドレス（例: xxx@project.iam.gserviceaccount.com）を「編集者」として追加

### 2-3. 環境変数に設定

```
GOOGLE_SHEETS_SPREADSHEET_ID=取得したスプレッドシートID
```

JSONファイルを1行文字列に変換：
```bash
python -c "import json; print(json.dumps(json.load(open('service_account.json'))))"
```
出力をそのまま `GOOGLE_SERVICE_ACCOUNT_JSON=` に貼る。

---

## 3. Google Maps API キー取得

1. https://console.cloud.google.com/ → 「APIとサービス」→「ライブラリ」
2. 以下を検索して有効化：
   - **Places API (New)**
3. 「APIとサービス」→「認証情報」→「APIキーを作成」
4. 取得したキーを `.env` の `GOOGLE_MAPS_API_KEY` に貼る

> 注意: Places API (New) は呼び出しごとに課金されます。月5ドル程度の無料枠があります。

---

## 4. OpenAI API キー取得

1. https://platform.openai.com/ にアクセス
2. 「API keys」→「Create new secret key」
3. 取得したキーを `.env` の `OPENAI_API_KEY` に貼る

> 使用モデル: `gpt-4o`（OCR）、`gpt-4o-mini`（カテゴリ判定）

---

## 5. Railway デプロイ

### 5-1. Railway CLI インストール

```bash
npm install -g @railway/cli
railway login
```

### 5-2. プロジェクト作成・デプロイ

```bash
cd システム③家計管理
railway init
railway up
```

### 5-3. 環境変数をRailwayに設定

Railway ダッシュボード → Variables タブで以下をすべて設定：

| 変数名 | 値 |
|--------|-----|
| LINE_CHANNEL_SECRET | LINEから取得 |
| LINE_CHANNEL_ACCESS_TOKEN | LINEから取得 |
| GOOGLE_SHEETS_SPREADSHEET_ID | シートID |
| GOOGLE_SERVICE_ACCOUNT_JSON | JSONを1行にしたもの |
| GOOGLE_MAPS_API_KEY | Mapsから取得 |
| OPENAI_API_KEY | OpenAIから取得 |
| SHIMIZU_USER_ID | 次のステップで取得 |
| CRON_SECRET | 任意の文字列（例: random_secret_12345） |

### 5-4. デプロイURLを確認

Railway ダッシュボード → 「Settings」→「Domains」でURLを確認。
例: `https://your-app.up.railway.app`

---

## 6. LINE WebhookにURLを設定

1. LINE Developers → チャネルページ → 「Messaging API設定」タブ
2. 「Webhook URL」に Railway の URL を入力：
   ```
   https://your-app.up.railway.app/webhook
   ```
3. 「検証」ボタンで成功を確認
4. 「Webhookの利用」をONにする
5. 「応答メッセージ」をOFFにする

---

## 7. 志水さんのLINEユーザーIDを取得

1. Railway デプロイ後、LINEから任意のテキスト（例: 「テスト」）を送信
2. Railway ダッシュボードの「Deployments」→「Logs」を開く
3. ログに `user_id: Uxxxxxxxxx` の形式で表示されるIDをコピー
4. `SHIMIZU_USER_ID` に設定して再デプロイ

---

## 8. 動作確認

1. グループLINEにレシート画像を送信
2. 数秒後に確認メッセージが返ってくることを確認
3. 「はい」を押して登録完了メッセージを確認
4. Googleスプレッドシートを開いて「支出記録」シートにデータが追加されていることを確認

---

## よくある問題

| 症状 | 原因 | 対処 |
|------|------|------|
| Webhook検証失敗 | URLが間違っている | `/webhook` まで含めているか確認 |
| レシート読み取りエラー | OpenAI APIキー | `.env` の OPENAI_API_KEY を確認 |
| Sheets保存失敗 | サービスアカウント未共有 | シートをサービスアカウントのメールで共有 |
| 店舗情報が取得できない | Maps APIキー | GOOGLE_MAPS_API_KEY を確認・Places API有効化 |
| 支払い者が「彼女」になる | SHIMIZU_USER_ID未設定 | ログからIDを取得して設定 |
