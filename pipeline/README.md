# pipeline — 企業関係データの生成

`public/M4_companies.json`（上場企業マスター）と `public/M5_company_relations.json`（関係エッジ）を
生成するスクリプト群。元は別プロジェクト `persona_project/persona_api/scripts/build_company_relations/`
にあったが、git 管理外で修正を追跡できなかったため本リポジトリへ移管した（Issue #1）。

## 構成

| ファイル | 役割 |
| --- | --- |
| `config.py` | パス・URL・関係タイプ定義 |
| `prepare_independent_companies.py` | 独立ソースの企業スナップショットを検証 |
| `fetch_edinet_codes.py` | EDINET コードリスト → `data_raw/edinet_codes.json` |
| `fetch_wikidata.py` / `apply_org_flags.py` | Wikidata の QID 対応・資本/グループ関係 → `data_raw/wikidata_*.json` |
| `fetch_edinet_filings.py` | EDINET API v2 から有価証券報告書を取得し、関係会社・大株主・主要顧客・役員の状況・経営上の重要な契約等・事業の内容の**生 HTML ブロック**を `data_raw/edinet_blocks/<docID>.json.gz` にキャッシュ（要 `EDINET_API_KEY`。種別を追加した場合は不足分だけ再取得して既存キャッシュに追加） |
| `edinet_tables.py` | 有報の表の解析ロジック（結合セル展開・分類見出しの継承・所有／被所有・比率） |
| `edinet_officers.py` | 「役員の状況」の解析（役員一覧の略歴から現任の他社役職＝役員兼任を抽出。回帰テスト `tests/test_edinet_officers.py`） |
| `edinet_contracts.py` | 「経営上の重要な契約等」の解析（相手方と契約の種類から提携を抽出。回帰テスト `tests/test_edinet_contracts.py`） |
| `fetch_group_members.py` | 企業グループ広報団体（三菱広報委員会・三井広報委員会・住友グループ広報委員会・みどり会）の公式サイトから会員会社一覧 → `data_raw/group_members.json` |
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
再取得は各独立ソースの取得処理を個別に実行する（`data_raw/sources.json` の取得日を更新すること）。

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

## 名寄せと別名（Issue #4）

- `aliases.py` の `match_key` で照合する: NFKC → 旧字体・異体字の置換（`aliases.json` の `kanji_variants`）→
  法人格の除去（株式会社・㈱・Inc.・Co., Ltd.・S.A.・有限公司・欧文名＋「社」等）→ 空白・記号除去 → 小文字化。
  「ホールディングス」「グループ」は法人の同一性に関わるので除かない（旧実装は除いていた）。
- 上場企業は 証券コード／法人番号／QID → 公式名（JPX 名・EDINET 提出者名・英文名）→ 別名 の順で解決する。
  EDINET 提出者名は JPX 名と互換（片方がもう片方を含む）な場合だけ索引に加える（「サッポロホールディングス」に
  「サッポロビール株式会社」を紐づけない）。
- `aliases.json` の `listed` は確認済みの通称・略称・旧商号。法人格のない別名（「ソニー」）は法人格のない原文名にだけ
  一致させ、「ソニー株式会社」（事業会社）を親会社に統合しない。`entities` は非上場法人の表記ゆれ（Ceva 等）。
- 統合の記録は `data_processed/masters/entity_merges.json`（上場企業へ解決した原文名と方法、entity に統合された
  原文名と理由）。
- 検索: M4 の `aliases` と `name_kana`（EDINET コードリストのヨミ）を `src/data/search.js` が索引にし、
  「東邦ガス」「とよた」「７２０３」で意図した企業に一致する。

## IR 抽出の根拠判定（Issue #6）

- `ir_validate.py` が LLM 抽出行の根拠文（evidence_quote）を検査し、「相手が根拠文に出ている」「関係タイプの
  手がかり語がある」「方向のあるタイプでは主体が分かる」場合だけ `confirmed` にする。共同登場だけ、製品が他社技術を
  ベースにしているだけ（`tech_basis_only`）、商標・PDF 注記・受賞・イベント（`noise_context`）、提出会社が当事者でない
  記述（`third_party_statement`）は `needs_review` にし、理由を `evidence.extraction.reasons` と
  `review_reasons` に残す。関係が現実にないという断定ではなく「この根拠では確定できない」という判定。
- 根拠文が別の無向タイプ（共同研究・提携・合弁）を明示している場合は、提出会社が当事者として出ていることを条件に
  そのタイプへ読み替える（`extraction.retyped_from`）。方向のあるタイプへの読み替えはせず `suggested_type` に留める。
- 「Xによる…公開買付け」は X が主体。X が当社（子会社）なら提出会社→相手、相手なら相手→提出会社。
- 固定評価セット `fixtures/ir_eval.json`（実データから人手ラベル 29 件。アイシン／デンソー共同実証・三井物産／Ceva・
  丸紅／TiAuto などの正例、日本車輌／JR東海・商標注記・列挙のみ・第三者記述などの負例）で
  `python ir_validate.py --eval`、全件の判定分布は `--stats`。
- `ir_crawl/crawl.mjs` のプロンプトも同じ方針（両社名と関係語を含む一文のみ、direction / status / event_date）に更新。
  既存の 3,642 行は再クロールせず、検証器で判定している。

## 出所・時点・検証状態の保持と公開（Issue #5）

- evidence: `source`（edinet / wikidata / ir_disclosure / official_release）、`source_tier`（primary / secondary /
  llm_extraction。出所の種別で抽出の正しさとは別）、`as_of`（基準日。有報は期末、大株主は「…現在」の日付、IR は公表日）、
  `published`（提出日・公表日）、`retrieved`（取得日）、`url`（EDINET 閲覧画面 / Wikidata / リリース）、`doc_id`、
  `classification` と `classification_source`、`direction_source`、`raw_name`、`extraction`（判定コードのみ）。
  `facts` に人物・役職・契約会社・契約年月・団体・合意／実行状態・言及年を格納する。未取得項目は省略し、
  UI で必要に応じ「不明」「未確認」と表示する。`quote`・`relationship_note`・`note`・`extraction.cue` と
  比率の `raw` はローカルのフル版にのみ保持し、公開版では除外する。関係全体の分類や比率を個々の出典の事実として転記しない。
- 関係: `status`（confirmed / needs_review / historical）、`review_reasons`、`verification`（corrections.json で
  原本照合したものだけ verified）。
- `make_viz_data.py` は本体 `public/M5_company_relations.json`（evidence は出所・種別・基準日の要約）と
  `public/data/<版ID>/evidence/<shard>.json`（関係 1,000 件ごとの構造化項目・出典と比率の履歴）に分ける。詳細パネルが必要なシャードだけ取得する。
- 大株主の状況の注記に写された大量保有報告書の表は `property: large_holding_report`（比率 kind
  `share_large_holding`）として大株主本表と区別する。

## 人的・グループ・提携の拡充（有報の役員の状況・重要な契約等、グループ会員一覧）

資本関係に比べて手薄だった 3 カテゴリを、IR（有価証券報告書）と民間公表データ（グループ広報団体の会員一覧）で埋める。

- **人的（役員兼任）**: 有報「役員の状況」の役員一覧を `edinet_officers.py` が読む。略歴欄は「年月＋経歴」の入れ子の表
  （または `<br>` 区切り）なので入れ子を保って復元し、現任の印（現任／現在に至る／現職／現在）があり退任の記述がない行から
  「会社名＋役職」を分ける（「同社」は直前の会社、「当社」は提出会社、「Ａ（現Ｂ）」は現在名を先に照合）。注記の
  「…は、○○株式会社の社外取締役を兼務」も読む。相手が上場企業に解決できた行だけを `interlocking_director`（無向）として
  投入し、人物と両社での役職は `attributes.persons` に集約、根拠行は evidence の `quote`（時点は提出日）。
  非上場の兼職先（財団・大学・子会社）はエンティティを作らない。
- **提携**: 有報「経営上の重要な契約等」を `edinet_contracts.py` が読む。相手方・契約内容の列がある表は列から、
  年月＋概要の表や本文は文単位で「会社名＋契約の種類語」から拾い、`資本業務提携→capital_alliance`、
  `業務提携・協業→business_alliance`、`技術援助・ライセンス→technology_license`（導入＝相手→当社、供与＝当社→相手、
  方向不明は needs_review）、`共同開発→joint_research`。「Ａと合弁契約」は相手が共同出資のパートナーなので
  `business_alliance`＋注記「合弁契約」（合弁会社自体は関係会社の状況から投入済み）。株式譲渡・吸収分割・借入などは対象外。
  相手方であることが文中で明示されない（`party_cue` なし）ものは needs_review（理由 `contract:unclear_party`）。
  相手が上場企業でない場合は法人格付きの名前だけエンティティにする。
- **グループ**: `fetch_group_members.py` が三菱広報委員会・三井広報委員会・住友グループ広報委員会・みどり会の会員会社一覧
  （各団体の公式サイト）を取得し、`build_masters.py` が上場会員 → グループ（エンティティ、`kind: "group"`）の
  `corporate_group` を投入する（evidence の `source` は `group_site`、`source_tier` は `primary`）。会員が上場持株会社の
  子会社（三菱UFJ銀行など）の場合は、有報で確定した親子関係をたどって上場親会社を会員として扱い `attributes.member_via`
  に記録する。芙蓉懇談会・三金会は公式の会員一覧が公開されていないため対象外。Wikidata（P463）由来のグループも
  同じエンティティに統合される。全体マップでは会員が 2 社以上のグループをハブ（点線の二重円）として描く。
- 再取得と再生成: `python fetch_edinet_filings.py fetch`（新しい種別だけ取得。全書類で約 4 時間）→
  `python fetch_group_members.py` → `parse_edinet_filings.py` → `build_masters.py` → `make_viz_data.py`。

## 公開前の追加検査

- 法人格だけ・文章が混入したエンティティは、入力済みキャッシュも含め統合の最終段階で隔離します。
- `ir_crawl/data/ir_relations.json` と `poc_results.json` はローカル原本です。Gitへ追加しないでください。
  再生成には前者が必要です。欠損したままIR関係を落として生成することはできません。
- `compare_company_sources.py` はJPX Excelと独立ソースの照合専用です。照合用Excelと差分結果は
  `data_raw/jpx_comparison/` に置き、本番名簿の補完や絞り込みには使用しません。読み取りにはopenpyxlが必要です。
- 名簿・関係・詳細から算出した版IDを本体に埋め、詳細を `data/<版ID>/evidence/` に保存します。
  既存版は上書きせず、クライアントは版が異なる応答を表示しません。固定URL時代の詳細は削除し、
  古い画面には取得エラーと再読み込み案内を出します。古い版の削除時も他の版への転送は禁止です。
- `npm run build` は実際のバンドル対象の著作権・許諾文を `THIRD_PARTY_NOTICES.txt` に同梱します。
  許諾文が欠ける依存が見つかればビルドは失敗します。バージョン指定の補足は `build/licenses/` を参照してください。

### 独立ソース企業マスター（2026-09-21）

通常の生成は `data_raw/independent_companies.json` のレビュー済みスナップショットを利用します。`prepare_independent_companies.py` で検証し、`build_masters.py` に入力します。`fetch_jpx.py` は本番パイプラインから外しました。JPXは比較専用であり、不足値をJPXから埋めません。スナップショットの更新時は出典URL・資料日・不一致/未確認フラグを維持し、上場廃止や新規上場の発効日も確認してください。`run.sh` は独立スナップショットを自動更新しません。

名称・33業種・未確認の市場区分を含むため、UIは注意文とJPX公式への確認リンクを表示します。17業種・規模区分は空欄です。地方市場やPRO市場も収録対象となります。

## IR根拠の検証とEDINET以外の情報源

[2026-09-21の信頼性監査・追加結果](IR_RELIABILITY_REVIEW_2026-09-21.md)に、確認基準、未達の件数目標、情報源ごとの制約を記載しています。

- `audit_ir_sources.py`: IR抽出の本文照合。本文一致と関係の意味の確認は別です。追加依存は `requirements-audit.txt`。
- `discover_issuer_sources.py`: 公式サイト候補の調査。候補を自動承認しません。
- `data_raw/ir_source_checks.json`: 元の抽出行のハッシュに結び付いた検証メタデータ。原文引用を含みません。検証がないIR抽出は要確認になります。
- `data_raw/official_relations.json`: 当事者・関係・時点を資料と個別照合した事実。AI照合であることを明記します。
- `source_contribution.py`: 確認済み上場企業間の関係を情報源ごとに重複排除して集計。企業サイト上の有報転載はEDINET由来です。

取得した全文・PDF・引用抜粋・未確認候補は `outputs/` などの無視対象に保存し、公開ファイルやGit履歴に追加しないでください。
