# DONAN Room Watch

ホテル アイリーンドナン町田の公開空室ページから情報を取得し、将来的に空室履歴の蓄積・傾向分析・iPhone向けダッシュボードを構築する個人用プロジェクトです。

## Phase 1 のスコープ

現在の Phase 1 では、対象ページを通常の HTTP GET で1回取得し、次の情報を検証付きで JSON 出力します。

- 取得日時（日本時間、ISO 8601）
- 空室総数
- 準備中室数
- 現在空室の部屋番号と Type

GitHub Actions、定期実行、履歴保存、データベース、ダッシュボード、通知、予測分析はまだ実装していません。

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

成功時は標準出力へ JSON を出力します。1回の実行で対象サイトへのリクエストは1回だけです。HTTPエラー、タイムアウト、ページ構造変更、件数不一致などを検出した場合は、誤った JSON を出力せず、標準エラーへ理由を表示して終了コード1で終了します。

## テスト方法

```powershell
python -m pytest
```

テストは `tests/fixtures/` の最小HTMLを使うため、対象サイトへアクセスしません。空室あり、空室0件、重複部屋番号、HTML構造異常などを検証します。

## 対象ページ

<https://www.hotenavi.com/donan-m/empty>

対象ページでは旧レイアウト用と現行レイアウト用のリンクが同時に含まれ、同じ部屋番号が複数回現れます。スクレーパーは部屋番号を重複排除し、ソートして出力します。
