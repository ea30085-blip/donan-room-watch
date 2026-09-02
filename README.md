# DONAN Room Watch

ホテル アイリーンドナン町田の公開空室ページから情報を取得し、将来的に空室履歴の蓄積・傾向分析・iPhone向けダッシュボードを構築する個人用プロジェクトです。

## 実装済みスコープ

Phase 1では、対象ページを通常のHTTP GETで1回取得し、次の情報を検証付きで解析します。

- 取得日時（日本時間、ISO 8601）
- 空室総数
- 準備中室数
- 現在空室の部屋番号と Type

Phase 2では、公式客室情報から作成した50室の客室マスタと照合したうえで、最新状態と1観測1行の履歴を保存します。

- 空室ページに掲載されている客室: `available`
- 掲載されていない客室: `not_available`

`not_available`は「利用中」を意味しません。「公式ページ上でavailableとして掲載されていない状態」です。準備中の具体的な部屋番号は公式HTMLから確定できないため、部屋別ステータスには`preparing`を使用せず、集計値`preparing_count`だけを保存します。

GitHub Actions、定期実行、データベース、Web UI、PWA、通知、AI分析、将来予測はまだ実装していません。

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
