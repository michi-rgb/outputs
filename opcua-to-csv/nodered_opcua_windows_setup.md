# Node-RED OPC-UA セットアップ手順書（Windows版）

OPC-UAサーバーからデータを受信し、CSVファイルに自動保存するNode-REDフローのWindows向けセットアップ手順です。

| 項目 | 内容 |
|---|---|
| 対応OS | Windows 10 / Windows 11 |
| 必要ソフト | Node.js (v18以上), Node-RED |
| Node-REDパッケージ | node-red-contrib-opcua |
| プロトコル | OPC-UA (OPC Unified Architecture)  TCP/4840 |
| CSV保存先 | `C:\Users\ユーザー名\opcua_data\` |

---

## 1. 事前準備：Node.js のインストール

Node-RED を動かすには Node.js が必要です。未インストールの場合は以下の手順でインストールしてください。

1. ブラウザで https://nodejs.org を開く
2. **「LTS (Long Term Support)」版**の Windows Installer (.msi) をダウンロード
3. ダウンロードした `.msi` ファイルを実行し、ウィザードに従いインストール
4. インストール完了後、コマンドプロンプト（cmd）を**新規に開いて**バージョン確認：

```
node -v
npm -v
```

> **注意:** インストール後は必ずコマンドプロンプトを開き直してください。古いウィンドウでは PATH が更新されておらず、コマンドが認識されません。

---

## 2. Node-RED のインストール

**コマンドプロンプトを管理者として実行**し、以下のコマンドを実行します。

> 管理者として実行: スタートメニュー →「cmd」と入力 → 右クリック →「管理者として実行」

```
npm install -g node-red
```

インストール完了後、バージョン確認：

```
node-red --version
```

---

## 3. OPC-UA パッケージのインストール

### 方法A：コマンドラインから（推奨）

Node-RED のホームディレクトリで実行します：

```
cd %USERPROFILE%\.node-red
npm install node-red-contrib-opcua
```

### 方法B：Node-RED 画面から

1. Node-RED（http://localhost:1880）を起動する（次章参照）
2. 右上メニュー（≡）→「パレットの管理」をクリック
3. 「ノードを追加」タブで `node-red-contrib-opcua` を検索
4. 「ノードを追加」ボタンをクリック

---

## 4. Node-RED の起動

コマンドプロンプトまたは PowerShell で以下を実行します：

```
node-red
```

起動後、ブラウザで http://localhost:1880 を開くとエディタ画面が表示されます。

### Windows 起動時に自動起動させる場合（任意）

pm2 (Process Manager 2) を使うと、Windows 起動時に Node-RED を自動起動できます。

```
npm install -g pm2
npm install -g pm2-windows-startup
pm2 start node-red
pm2-startup install
pm2 save
```

---

## 5. flows.json のインポート

1. ブラウザで http://localhost:1880 を開く
2. 右上のメニュー（≡）→「読み込み」をクリック
3. 「クリップボード」タブで「ファイルを選択」→ `flows.json` を選択
4. 「読み込み」ボタンをクリック
5. 右上の「デプロイ」ボタン（赤）をクリック

---

## 6. OPC-UA エンドポイントの変更

デフォルトのエンドポイントは `opc.tcp://localhost:4840` です。

変更するには：
1. フロー内の `OPC-UA Server` ノード（config ノード）をダブルクリック
2. `Endpoint` の URL を変更（例: `opc.tcp://192.168.1.100:4840`）
3. 「完了」→「デプロイ」をクリック

---

## 7. 監視ノードID（NodeID）の変更

デフォルトでは以下のノードIDを監視しています：

| ノードID | 名前 | 単位 | 基準値 |
|---|---|---|---|
| `ns=1;i=1001` | Temperature（温度） | ℃ | 25.0 |
| `ns=1;i=1002` | Pressure（圧力） | kPa | 101.3 |
| `ns=1;i=1003` | FlowRate（流量） | L/min | 50.0 |

変更するには：
1. `Temperature (ns=1;i=1001)` などの `OpcUa-Item` ノードをダブルクリック
2. `Item` フィールドにノードIDを入力（例: `ns=2;s=MyVariable`）
3. 「完了」→「デプロイ」をクリック

---

## 8. テスト用モックサーバー

実際のOPC-UAサーバーがない場合は、付属のモックサーバーを使用できます。

### インストール

コマンドプロンプトで `opcua-to-csv` フォルダに移動してから実行：

```
cd C:\path\to\opcua-to-csv
npm install
```

### 起動

```
node mock-server.js
```

起動後、上記3つのノードIDが1秒ごとにランダム値で更新されます。`Ctrl+C` で停止します。

---

## 9. CSV出力

### 保存先

```
C:\Users\ユーザー名\opcua_data\opcua_YYYY-MM-DD.csv
```

フォルダは初回実行時に自動作成されます。

### CSVフォーマット

```csv
timestamp,nodeId,value,dataType,status
2025-01-15T10:30:00.000Z,ns=1;i=1001,25.3,Double,Good
2025-01-15T10:30:01.000Z,ns=1;i=1002,101.5,Double,Good
```

### 書き込みタイミング

- **100件**データが溜まったとき
- **30秒**経過したとき（どちらか先）
- 「手動フラッシュ」inject ノードを手動実行したとき

件数・時間の変更は「バッファ」function ノード内の `BUFFER_SIZE` / `FLUSH_INTERVAL_MS` を修正してください。

---

## 10. Windows ファイアウォール設定

外部のOPC-UAサーバーに接続する場合や、他のPCからNode-REDにアクセスする場合は設定が必要です。

### ポート 4840（OPC-UA）を開く

1. スタートメニュー →「Windows Defender ファイアウォール」→「詳細設定」
2. 「受信の規則」→ 右側「新しい規則」
3. 「ポート」を選択 → 次へ
4. 「TCP」「特定のローカルポート: **4840**」→ 次へ
5. 「接続を許可する」→ 次へ
6. 「ドメイン」「プライベート」「パブリック」すべてチェック → 次へ
7. 名前:「OPC-UA 4840」→「完了」

### ポート 1880（Node-RED）を外部公開する場合

同様の手順でポート 1880 を開きます（ローカルのみ使用する場合は不要）。

---

## 11. トラブルシューティング

### `node-red` コマンドが認識されない

- コマンドプロンプトを管理者として実行しているか確認
- `npm install -g node-red` を再実行
- 環境変数 PATH に npm のグローバルパスが含まれているか確認：

```
npm config get prefix
```

表示されたパスの `bin` フォルダが PATH に入っているか確認してください。

### OPC-UAサーバーに接続できない

- モックサーバー（または実サーバー）が起動しているか確認
- Windowsファイアウォールでポート 4840 が開いているか確認（前章参照）
- エンドポイントURLが正しいか確認
  - 同一PC: `opc.tcp://localhost:4840`
  - 別PC: `opc.tcp://[IPアドレス]:4840`

### CSVが作成されない

- Node-REDのデバッグパネル（右側のバグアイコン）でエラーを確認
- `C:\Users\ユーザー名\opcua_data\` フォルダへの書き込み権限があるか確認
- 手動フラッシュ用のinjectノードを実行してみる

### node-red-contrib-opcua が見つからない

```
cd %USERPROFILE%\.node-red
npm install node-red-contrib-opcua
```

インストール後、Node-RED を再起動（`Ctrl+C` で停止 → `node-red` で再起動）。

---

## 12. フロー構成

```
[inject: 起動時に自動開始]
        ↓
[OpcUa-Item: ns=1;i=1001] ─┐
[OpcUa-Item: ns=1;i=1002] ─┼→ [function: データ整形] → [function: バッファ] → [function: CSV書き込み] → [debug]
[OpcUa-Item: ns=1;i=1003] ─┘         ↑
[inject: 手動フラッシュ] ────────────┘
[inject: 30秒タイマー] ──────────────┘

[catch: エラーキャッチ] → [debug: エラーログ]
```
