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

`web/`配下のHTML・CSS・Vanilla JavaScriptで構成された、iPhone向けの静的ダッシュボードです。現在の空室数、611・612・615、全空室、Type別集計、直近24時間の推移、過去7日・30日の空室表示傾向を表示します。

ブラウザはGitHub Pages上の同一オリジンから次の公開データを取得します。

- `data/latest.json`
- `data/history.csv`
- `config/rooms.json`

画面はヘッダー直下の「いま」「傾向」タブで分かれています。初期表示の「いま」では現在情報だけに集中でき、「傾向」を選んだときだけ履歴分析を表示します。

初回表示では`rooms.json`と`latest.json`だけを取得し、`history.csv`は「傾向」を初めて開いたときにlazy loadします。読み込み済みなら画面を往復しても再取得しません。その後は5分ごとに`latest.json`を確認し、新しい`observed_at`を検知した場合のみ、履歴を読み込み済みであれば`history.csv`も再取得します。

`NOT AVAILABLE`は「利用中」ではなく、「現在、公式空室ページに空室表示がない状態」です。

### 設備表示と空室フィルター（Phase 4.1）

現在空いている部屋とFeatured Rooms（611・612・615）には、部屋番号単位で公式確認できた比較設備をchipで表示します。「現在空いている部屋」の「設備で絞り込む」から単一の設備を選ぶと、現在availableでその設備を持つ部屋だけを表示します。「すべて」で解除できます。フィルターはFeatured Rooms、Type別状況、履歴グラフには影響しません。

設備キーと画面表示は次のとおりです。

| キー | 表示 | 公式ページ上の区分 |
| --- | --- | --- |
| `sauna` | サウナ | サウナ |
| `karaoke` | カラオケ | 通信カラオケ |
| `bath_tv` | 浴室TV | 22インチ浴室TV |
| `massage_chair` | マッサージ | マッサージチェア |
| `collagen_machine` | コラーゲン | コラーゲン（美肌）マシン |
| `rainbow_blower_bath` | 虹色ブロアー | 虹色ブロアーバス |
| `blower_bath` | ブロアーバス | ブロアーバス |

`rainbow_blower_bath`と`blower_bath`は公式ページ上で別の限定設備として客室一覧が示されているため、推測で統合せず別キーにしています。Wi-Fi、電子レンジ、一般的なTVなどの全室設備は、部屋選びの比較材料にならないためマスタ・chip・フィルターへ含めていません。

### 空室表示分析（Phase 4.2）

履歴エリアでは、日付が変わっても表示価値が失われないよう、JST基準のrolling windowで次を表示します。

- 直近24時間の空室数推移
- 過去7日／30日の分析サマリー
- 曜日×時間帯の平均空室数ヒートマップ（18–24時詳細／全日）
- 設備別の空室あり率
- 全50室の空室表示率ランキング

直近24時間グラフは、ブラウザの現在時刻から厳密に24時間前以降のraw観測を、実際の時刻間隔どおりに描画します。JSTの0時でリセットしません。

7日／30日分析では、現在進行中のJST hour bucketを除外し、その直前の完了済み168時間／720時間を対象にします。期待bucket数はそれぞれ常に168／720です。hour bucketのキーは`JST日付 YYYY-MM-DD + hour 00〜23`です。

「時間帯別の空室傾向」は曜日を縦軸、時間を横軸にします。初期の「18–24時」表示では18〜22時を1時間単位、22〜24時を15分単位で詳しく表示します。「全日」では00〜23時を1時間単位で表示します。どちらも表の内部だけを横スクロールでき、全日表示をモバイルで開いた場合は18時付近を初期位置にします。

22〜24時の15分表示では、`JST日付 + 15分slot`を表示用の基本単位とします。同じdate-slotに複数観測があれば先に`available_count`を平均し、その後、同じ曜日・同じslotに属するdate-slot平均を等しい重みで平均します。この15分slotは時間帯表だけに使用し、分析サマリー、設備別・部屋別の指標は従来どおり1時間bucket正規化です。

収集頻度は時間帯によって異なるため、履歴行を直接平均しません。まず同じhour bucket内の観測を平均し、その後で各hour bucketを同じ重みとして期間平均を計算します。これにより、15分間隔の時間帯が60分間隔の時間帯より過剰に重くなることを防ぎます。

指標の定義は次のとおりです。

- **平均空室数**：各hour bucket内の`available_count`平均を求め、そのbucket平均を期間内で等価平均
- **観測カバレッジ**：観測が1件以上あるhour bucket数 ÷ 期待hour bucket数（168または720）
- **時間帯表（18〜22時）**：hour bucket平均をJST曜日と1時間列へ分類し、該当date-hour bucketを等価平均
- **時間帯表（22〜24時）**：15分date-slot平均をJST曜日と15分列へ分類し、該当date-slotを等価平均
- **時間帯表（全日）**：hour bucket平均をJST曜日と00〜23時の1時間列へ分類し、該当date-hour bucketを等価平均
- **設備別 空室あり率**：各観測で対象設備の客室が1室以上availableならtrueとし、hour内true率を求めた後、hour bucketを等価平均
- **部屋別 空室表示率**：各観測で対象roomがavailableならtrueとし、hour内true率を求めた後、hour bucketを等価平均

ヒートマップの色は期間内の相対値ではなく、`0–2未満`、`2–4未満`、`4–6未満`、`6–8未満`、`8室以上`の固定scaleです。各セルには平均値とサンプル数`n`を表示します。1時間セルの`n`は使用したdate-hour bucket数、15分セルの`n`は使用したdate-slot数で、raw観測件数ではありません。`n=1〜2`は少数サンプルとして淡く表示します。

観測がないhour bucketや15分slotは0室やnot_availableとして補完せず、未観測として統計から除外し、時間帯表では`-- / n=0`と表示します。30日分がまだ蓄積されていない場合も存在するデータだけで計算し、観測日数、観測hour数、coverageを併記します。

ここでいう空室表示率・空室あり率は、公式空室ページに`available`として掲載されていた割合です。`not_available`は利用中を保証せず、実際の客室利用率、稼働率、予約成功率を示すものではありません。

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

公式の[客室情報](https://www.hotenavi.com/donan-m/room)と[サービス・設備情報](https://www.hotenavi.com/donan-m/service)を2026-09-10に確認して作成した客室マスタです。全50室の`room`、`type`、部屋ごとの`facilities`を保持します。

`facilities`は全客室で必須の配列です。空の場合も`[]`を明示します。roomの3桁形式・重複・Typeの有無に加え、配列型、許可キー、設備キーの重複をPython保存処理とブラウザ表示処理の双方で検証します。未知の設備キーが含まれる場合は観測データを保存せず、ダッシュボードもエラーとして扱います。

```json
{
  "source_url": "https://www.hotenavi.com/donan-m/room",
  "facility_source_url": "https://www.hotenavi.com/donan-m/service",
  "verified_at": "2026-09-10",
  "rooms": [
    {"room": "101", "type": "A", "facilities": ["rainbow_blower_bath"]},
    {"room": "615", "type": "I", "facilities": ["sauna", "karaoke", "bath_tv", "massage_chair", "collagen_machine", "blower_bath"]}
  ]
}
```

設備情報は2026-09-10時点の公式掲載内容です。公式サイトで設備や対応客室が変更された場合は、`config/rooms.json`の対応客室と`verified_at`を再確認・更新する必要があります。設備は静的属性のため`data/history.csv`へ重複保存しません。

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

テストは`tests/fixtures/`とpytestの`tmp_path`を使うため、対象サイトへアクセスしません。Phase 1の解析テストに加え、客室マスタ、設備対応、設備フィルター、全室ステータス、履歴生成、空室0件、重複防止、異常時の非更新、ダッシュボード構造を検証します。

## 対象ページ

- 空室情報: <https://www.hotenavi.com/donan-m/empty>
- 客室情報: <https://www.hotenavi.com/donan-m/room>
- サービス・設備情報: <https://www.hotenavi.com/donan-m/service>

対象ページでは旧レイアウト用と現行レイアウト用のリンクが同時に含まれ、同じ部屋番号が複数回現れます。スクレーパーは部屋番号を重複排除し、ソートして出力します。
