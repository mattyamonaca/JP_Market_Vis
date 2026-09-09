# pipeline — 企業関係データの生成

`public/M4_companies.json`（上場企業マスター）と `public/M5_company_relations.json`（関係エッジ）を
生成するスクリプト群。元は別プロジェクト `persona_project/persona_api/scripts/build_company_relations/`
にあったが、git 管理外で修正を追跡できなかったため本リポジトリへ移管した（Issue #1）。

## 構成

| ファイル | 役割 |
| --- | --- |
| `config.py` | パス・URL・関係タイプ定義 |
| `fetch_jpx.py` | JPX 上場銘柄一覧 → `data_raw/jpx_listed.json` |
| `fetch_edinet_codes.py` | EDINET コードリスト → `data_raw/edinet_codes.json` |
| `fetch_wikidata.py` / `apply_org_flags.py` | Wikidata の QID 対応・資本/グループ関係 → `data_raw/wikidata_*.json` |
| `fetch_edinet_filings.py` | EDINET API v2 から有価証券報告書を取得し、関係会社・大株主・主要顧客の**生 HTML ブロック**を `data_raw/edinet_blocks/<docID>.json.gz` にキャッシュ（要 `EDINET_API_KEY`） |
| `edinet_tables.py` | 有報の表の解析ロジック（結合セル展開・分類見出しの継承・所有／被所有・比率） |
| `parse_edinet_filings.py` | キャッシュを解析して `data_raw/edinet_relations.json(.gz)` を出力（オフライン） |
| `build_masters.py` | 各ソースを統合し `data_processed/masters/M4,M5` と `quarantine.json` を出力 |
| `make_viz_data.py` | 公開用に軽量化して `public/` へ出力 |
| `ir_crawl/` | 各社 IR サイトの LLM 抽出（長時間ジョブ。結果 `ir_crawl/data/ir_relations.json` を同梱） |
| `fixtures/`, `tests/` | 実書類から抜粋した回帰テスト |

## 実行

```sh
cd pipeline
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python fetch_edinet_filings.py list --from 2025-06-14 --to 2026-06-13   # 対象書類の一覧
python fetch_edinet_filings.py fetch                                    # 生ブロックをキャッシュ（数時間）
python parse_edinet_filings.py                                         # 解析（数分）
python build_masters.py                                                # 統合
python make_viz_data.py                                                # public/ へ出力
```

`EDINET_API_KEY` は環境変数または `~/.persona/.env` から読む。JPX・EDINETコード・Wikidata の
再取得は `fetch_jpx.py` 等を個別に実行する（`data_raw/sources.json` の取得日を更新すること）。

テスト: リポジトリ直下で `python3 -m unittest discover -s pipeline/tests`。

## 旧パイプラインからの主な変更（Issue #1）

- **取得と解析を分離**。生ブロックをキャッシュするので、解析ロジックの修正は再取得なしに反映できる。
- **結合セル（rowspan/colspan）を展開**。結合セルの下段にある間接所有割合 `(87.74)` を企業名として
  登録しない。企業名として不適切な行（数値・記号・「その他N社」・分類ラベル）は `quarantine.json` に記録し、
  関係を作らない。
- **分類の継承**。節見出し（「(3) その他の関係会社」）、表内のラベル行（「（連結子会社）」）、区分列、
  行頭の括弧、見出しセル、注記（「上記会社は連結子会社であります」）の順で分類を決める。
- **所有／被所有の区別**。列見出し（「被所有割合」）、所有／被所有の別列、セル内の「被所有」表記、
  分類（親会社・その他の関係会社）から方向を決める。
- **分類ごとの関係タイプ**
  - 連結子会社・非連結子会社・子会社 → 提出会社→相手 `parent_subsidiary`
  - 持分法適用関連会社・関連会社 → 提出会社→相手 `affiliate`
  - 親会社 → 相手→提出会社 `parent_subsidiary`
  - その他の関係会社（提出会社を関連会社とする会社。財務諸表等規則8条）→ 相手→提出会社 `affiliate`
  - 分類不明・分類と方向の矛盾 → 子会社に推定せず、表に書かれた事実のみ `ownership` として
    `status: "needs_review"` に隔離
- **比率の意味を保持**。合計（括弧外）と間接所有（括弧内・内数）、議決権／株式数の別、基準日、
  書類ID を `attributes.ownership_ratio` に構造化し、複数の書類で値が異なる場合は基準日の新しい値を
  現在値、それ以外を `history` に残す。
- **evidence に基準日・提出日・取得日・原本URL・抽出根拠（分類の出所・方向の出所・原文名）を保持**。

## データの範囲

`data_raw/edinet_docs.json` は 2025-06-14〜2026-06-13 提出の有価証券報告書（証券コードあり）3,939 件。
同一企業の 2 期分が含まれる場合、基準日の新しい方を現在値にし、古い方は history に残す。

## 比率・時点・訂正の扱い（Issue #2）

- `attributes.ownership_ratio` は `{value, kind, scope, direct, indirect, raw, as_of, doc_id, history}`。
  `value` は合計（直接＋間接）、`indirect` は括弧内の間接所有（内数）、`direct` はその差。
  `kind` は `voting`（議決権所有割合。関係会社の状況）／`share`（発行済株式に対する所有株式数の割合。大株主の状況）。
  括弧内しか読めない場合は `value: null, scope: "indirect_only"` とし、部分比率を合計として表示しない。
- 複数の書類で値が異なる場合、候補をすべて保持し、`基準日の新しい順 → 合計あり → 検証済み → 議決権 > 株式数 → 書類ID`
  の順で現在値を選ぶ。取得順には依存しない。それ以外は `history` に残し、`has_older_values` /
  `conflict_same_period` で状況を示す。
- IR 抽出は公表文から `deal_status`（`agreed` = 合意・予定、`executed` = 実行済み）と、2 年以上前の年への
  言及 `event_year`（沿革の記述）を推定する。日付が不正・未来のものは不明（null）にする。
- `corrections.json` に原本で確認した訂正を書くと `build_masters.py` が適用し、
  `data_processed/masters/corrections_applied.json` に前後の状態を記録する。
  `supersede` は旧関係を `status: "historical"`（`valid_until` 付き）にして新関係を追加するので、
  変更前後を区別できる。50% 以下という理由だけで親子関係を削除する処理はない。
