# OPC-UA → CSV 変換アプリ (Node-RED)

OPC-UAサーバーからデータを受信し、CSVファイルに自動保存するNode-REDフローです。

---

## 構成ファイル

| ファイル | 説明 |
|---|---|
| `flows.json` | Node-REDにインポートするフロー定義 |
| `mock-server.js` | テスト用OPC-UAモックサーバー |
| `package.json` | モックサーバーの依存関係 |

---

## セットアップ手順

### 1. Node-REDのインストール（未インストールの場合）

```bash
npm install -g --unsafe-perm node-red
```

### 2. OPC-UAパッケージのインストール

Node-REDのホームディレクトリ（通常 `~/.node-red`）で実行：

```bash
cd ~/.node-red
npm install node-red-contrib-opcua
```

またはNode-RED画面右上メニュー →「パレットの管理」→「ノードを追加」から `node-red-contrib-opcua` を検索してインストール。

### 3. flows.json のインポート

1. Node-RED（http://localhost:1880）を起動
2. 右上のメニュー（≡）→「読み込み」をクリック
3. `flows.json` のファイルを選択
4. 「読み込み」ボタンをクリック
5. 右上の「デプロイ」ボタンをクリック

---

## OPC-UAエンドポイントの変更

デフォルトのエンドポイントは `opc.tcp://localhost:4840` です。

変更するには：
1. フロー内の `OPC-UA Server` ノード（config ノード）をダブルクリック
2. `Endpoint` の URL を変更
3. 「完了」→「デプロイ」

---

## 監視ノードIDの変更

デフォルトでは `ns=1;i=1001`〜`ns=1;i=1003` を監視しています。

変更するには：
1. `Temperature (ns=1;i=1001)` などの `OpcUa-Item` ノードをダブルクリック
2. `Item` にノードIDを入力（例: `ns=2;s=MyVariable`）
3. 「完了」→「デプロイ」

ノードを追加したい場合は、`OpcUa-Item` ノードをコピーして `データ整形` ノードに接続。

---

## テスト用モックサーバーの使い方

実際のOPC-UAサーバーがない場合は、付属のモックサーバーを使用してください。

### インストール

```bash
cd opcua-to-csv
npm install
```

### 起動

```bash
node mock-server.js
```

起動すると以下のノードが1秒ごとにランダム値で更新されます：

| ノードID | 名前 | 単位 | 基準値 |
|---|---|---|---|
| ns=1;i=1001 | Temperature | ℃ | 25.0 |
| ns=1;i=1002 | Pressure | kPa | 101.3 |
| ns=1;i=1003 | FlowRate | L/min | 50.0 |

---

## CSV出力

### 保存先

```
~/opcua_data/opcua_YYYY-MM-DD.csv
```

- Windows: `C:\Users\ユーザー名\opcua_data\`
- Mac/Linux: `/home/ユーザー名/opcua_data/`

### CSVフォーマット

```csv
timestamp,nodeId,value,dataType,status
2025-01-15T10:30:00.000Z,ns=1;i=1001,25.3,Double,Good
2025-01-15T10:30:01.000Z,ns=1;i=1002,101.5,Double,Good
```

### フラッシュタイミング

データは以下のタイミングでCSVに書き込まれます：
- **100件** データが溜まったとき
- **30秒** 経過したとき（どちらか先に達した方）
- 「手動フラッシュ」injectノードを手動で実行したとき

件数・時間の変更は `バッファ` functionノード内の `BUFFER_SIZE` / `FLUSH_INTERVAL_MS` を修正してください。

---

## フロー構成

```
[inject: 起動時に自動開始]
        ↓
[OpcUa-Item: ns=1;i=1001] ─┐
[OpcUa-Item: ns=1;i=1002] ─┼→ [function: データ整形] → [function: バッファ] → [function: CSV書き込み] → [debug]
[OpcUa-Item: ns=1;i=1003] ─┘
                                      ↑
[inject: 手動フラッシュ] ────────────┘
[inject: 30秒タイマー] ──────────────┘

[catch: エラーキャッチ] → [debug: エラーログ]
```

---

## トラブルシューティング

### 接続できない
- OPC-UAサーバー（またはモックサーバー）が起動しているか確認
- ファイアウォールでポート4840が開いているか確認
- エンドポイントURLが正しいか確認

### CSVが作成されない
- Node-REDのデバッグパネル（右側のバグアイコン）でエラーを確認
- `~/opcua_data/` フォルダへの書き込み権限があるか確認
- 手動フラッシュ用のinjectノードを実行してみる

### パッケージが見つからない
```bash
cd ~/.node-red
npm install node-red-contrib-opcua
# Node-REDを再起動
```
