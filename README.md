# DONAN Room Watch

ホテル アイリーンドナン町田の公開空室ページから情報を取得し、将来的に空室履歴の蓄積・傾向分析・iPhone向けダッシュボードを構築する個人用プロジェクトです。

## 実装済みスコープ

Phase 1では、対象ページを通常のHTTP GETで1回取得し、次の情報を検証付きで解析します。

- 取得日時（日本時間、ISO 8601）
- 空室総数
- 準備中室数
- 現在空室の部屋番号と Type

Phase 2では、公式客室情報から作成した50室の客室マスタと照合したうえで、最新状態と1観測1行の履歴を保存します。Phase 3では、GitHub Actionsからこの処理を定期実行し、データ変更を`main`へ自動commit・pushします。

- 空室ページに掲載されている客室: `available`
- 掲載されていない客室: `not_available`

`not_available`は「利用中」を意味しません。「公式ページ上でavailableとして掲載されていない状態」です。準備中の具体的な部屋番号は公式HTMLから確定できないため、部屋別ステータスには`preparing`を使用せず、集計値`preparing_count`だけを保存します。

データベース、PWA、通知、AI分析、将来予測はまだ実装していません。

## セットアップ（Windows PowerShell）

Python 3.10 以降を用意し、リポジトリ直下で以下を実行します。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

PowerShell の実行ポリシーで仮想環境を有効化できない場合は、`.venv\Scripts\python.exe` を `python` の代わりに使えます。

## 実行方法

```powershell
python src\scraper.py
```

1回のコマンドで次を順番に実行します。

1. 空室ページを1回だけ取得
2. Phase 1のHTML解析・整合性検証
3. 客室マスタとのroom・Type照合
4. `data/latest.json`の更新
5. `data/history.csv`への追記
6. 観測結果と履歴追記有無をJSONで表示

HTTPエラー、タイムアウト、ページ構造変更、件数不一致、未知の客室、Type不一致などを検出した場合は、`latest.json`と`history.csv`を更新せず、標準エラーへ理由を表示して終了コード1で終了します。

## GitHub Actionsによる自動収集

`.github/workflows/collect.yml`はGitHub-hostedの`ubuntu-latest`とPython 3.13を使用し、以下を順番に実行します。

1. `main`をcheckout
2. `requirements.txt`から依存関係をインストール
3. pytestを実行
4. スクレイパーを1回実行
5. `data/latest.json`と`data/history.csv`の差分を確認
6. 差分がある場合だけ`github-actions[bot]`としてcommit・push

テストまたは取得・検証が失敗すると、その後の収集・commitは実行されません。自動commitのメッセージは`chore(data): collect room availability`です。認証にはリポジトリ組み込みの`GITHUB_TOKEN`を使い、追加のPersonal Access Tokenは不要です。

### 実行スケジュール

全スケジュールは`timezone: "Asia/Tokyo"`を指定し、日本時間の07分を基準に毎日実行します。

| 日本時間 | 間隔 | 実行分 |
| --- | --- | --- |
| 10:00〜17:59 | 30分 | 07分、37分 |
| 18:00〜翌01:59 | 15分 | 07分、22分、37分、52分 |
| 02:00〜09:59 | 60分 | 07分 |

GitHub Actionsのscheduleは厳密なリアルタイム実行を保証しません。GitHub側の混雑によって開始が遅れ、負荷が非常に高い場合は実行が落とされる可能性もあります。毎時00分付近の混雑を避けるため、すべて07分以降へずらしています。

### 手動実行と確認方法

初回確認はGitHubへpushした後、リポジトリの`Actions`タブから`Collect room availability`を選び、`Run workflow`で`main`を指定して実行します。

実行ログの`Collect availability`ステップでは、`observed_at`、`available_count`、`preparing_count`、`available_rooms`、`history_appended`を確認できます。続く`Check data changes`または`Commit and push data`ステップで、commitが省略されたか`main`へpushされたかを確認できます。赤い失敗表示の場合は、失敗したpytest・取得・検証・rebaseなどのステップを開いて原因を確認してください。

同じ収集workflowは同時実行されず、実行中の処理をキャンセルせずに待機します。push前に`git pull --rebase origin main`を行い、競合を安全に解消できない場合はforce pushせず失敗します。

## Webダッシュボード（Phase 4）

`web/`配下のHTML・CSS・Vanilla JavaScriptで構成された、iPhone向けの静的ダッシュボードです。現在の空室数、611・612・615、全空室、Type別集計、本日の空室数推移、611・615の本日状態推移を表示します。

ブラウザはGitHub Pages上の同一オリジンから次の公開データを取得します。

- `data/latest.json`
- `data/history.csv`
- `config/rooms.json`

ページを開いたときに全データを取得し、その後は5分ごとに`latest.json`をキャッシュ無効化付きで確認します。新しい`observed_at`を検知した場合だけ、履歴を含む表示を更新します。

`NOT AVAILABLE`は「利用中」ではなく、「現在、公式空室ページに空室表示がない状態」です。

### GitHub Pages構成

`.github/workflows/pages.yml`が`web/`の中身をartifact直下へ配置し、`data/`と`config/`を同じartifactへコピーしてGitHub Pagesへデプロイします。以下の変更時に動作します。

- `web/**`
- `data/**`
- `config/**`
- `.github/workflows/pages.yml`

Phase 3の収集commitは`GITHUB_TOKEN`によるpushのため別workflowのpushイベントを発生させません。そのため、Pages workflowは`Collect room availability`の成功完了も検知し、最新の`main`から再デプロイします。

公開後の想定URLは次のとおりです。現時点ではGitHub上へのデプロイ成功をまだ確認していません。

<https://ea30085-blip.github.io/donan-room-watch/>

### ローカル確認（Windows PowerShell）

リポジトリ直下で公開用と同じ構成を作り、HTTPサーバを起動します。

```powershell
New-Item -ItemType Directory -Force .preview-site, .preview-site\data, .preview-site\config
Copy-Item -Force web\* .preview-site\
Copy-Item -Force data\latest.json, data\history.csv .preview-site\data\
Copy-Item -Force config\rooms.json .preview-site\config\
python -m http.server 8000 --directory .preview-site
```

その後、ブラウザで<http://127.0.0.1:8000/>を開きます。`file://`での直開きは使用しません。

### GitHub Pagesの有効化

Phase 4を`main`へpushした後、GitHubのリポジトリで`Settings` → `Pages` → `Build and deployment`を開き、`Source`に`GitHub Actions`を選択します。その後、`Actions`タブの`Deploy dashboard to GitHub Pages`を手動実行して初回デプロイを確認してください。

成功時はworkflowのdeploy結果に公開URLが表示されます。失敗時は`Assemble static site`、`Upload GitHub Pages artifact`、`Deploy to GitHub Pages`のどのステップで失敗したか確認してください。

### iPhone Safariで開く

公開URLをSafariで開きます。ホーム画面へ追加する場合は、Safari下部の共有ボタンから`ホーム画面に追加`を選択してください。Service Workerやオフライン対応はまだ実装していないため、表示にはネットワーク接続が必要です。

## データ構造

### `config/rooms.json`

公式の[客室情報](https://www.hotenavi.com/donan-m/room)を2026-09-02に確認して作成した客室マスタです。全50室の`room`と`type`を保持します。roomの3桁形式、重複、Typeの有無は実行時にも検証されます。

```json
{
  "source_url": "https://www.hotenavi.com/donan-m/room",
  "verified_at": "2026-09-02",
  "rooms": [
    {"room": "101", "type": "A"},
    {"room": "102", "type": "B"}
  ]
}
```

設備については公式の[サービス・設備情報](https://www.hotenavi.com/donan-m/service)も確認しましたが、Phase 2のマスタには確実に必要なroom・Typeだけを登録しています。

### `data/latest.json`

直近の観測を全50室分保持します。客室は部屋番号順です。一時ファイルを書き終えてから`os.replace`で置換します。

```json
{
  "observed_at": "2026-09-02T03:00:00+09:00",
  "available_count": 2,
  "preparing_count": 0,
  "total_rooms": 50,
  "available_rooms": ["212", "516"],
  "rooms": [
    {"room": "101", "type": "A", "status": "not_available"},
    {"room": "212", "type": "D", "status": "available"}
  ]
}
```

### `data/history.csv`

1回の観測を1行で保存します。`available_rooms`は部屋番号順の`|`区切りで、空室0件なら空文字です。同じ`observed_at`は重複追記しません。

```csv
observed_at,available_count,preparing_count,total_rooms,available_rooms
2026-09-02T03:00:00+09:00,4,0,50,212|402|501|516
```

## テスト方法

```powershell
python -m pytest
```

テストは`tests/fixtures/`とpytestの`tmp_path`を使うため、対象サイトへアクセスしません。Phase 1の解析テストに加え、客室マスタ、全室ステータス、履歴生成、空室0件、重複防止、異常時の非更新を検証します。

## 対象ページ

- 空室情報: <https://www.hotenavi.com/donan-m/empty>
- 客室情報: <https://www.hotenavi.com/donan-m/room>
- サービス・設備情報: <https://www.hotenavi.com/donan-m/service>

対象ページでは旧レイアウト用と現行レイアウト用のリンクが同時に含まれ、同じ部屋番号が複数回現れます。スクレーパーは部屋番号を重複排除し、ソートして出力します。
