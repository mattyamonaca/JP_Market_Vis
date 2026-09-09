# 公開データの再生成と監査（Issue #3）— 2026-09-09

対象: `pipeline/` で再生成した `public/M4_companies.json` / `public/M5_company_relations.json` / `public/evidence/`。
入力は 2025-06-14〜2026-06-13 提出の有価証券報告書 3,939 件（EDINET API v2 から 2026-09-09 に再取得）、
Wikidata・IR 抽出は 2026-06-13 のスナップショット。旧公開データは `main` の 2026-06-13 生成版（81,445 関係）。

再実行: `python3 pipeline/audit.py --old <旧M5> --old-m4 <旧M4> --out reviews/2026-09-09-regeneration`、
`python3 pipeline/apply_sample_labels.py reviews/2026-09-09-regeneration`、`python3 pipeline/make_regen_report.py reviews/2026-09-09-regeneration`

## 件数

| 項目 | 旧 | 新 |
| --- | --- | --- |
| 関係（全体） | 81,445 | 83,482 |
| うち確定（confirmed） | — | 81,828 |
| うち要確認（needs_review） | — | 1,653 |
| うち過去（historical） | — | 1 |
| 非上場エンティティ | 59,780 | 57,940 |
| 数値・記号だけの企業ノード | 456 | **0** |
| 数値ノードに接続する関係 | 568 | **0** |
| 相互に親会社となる確定ペア | 99（上場同士 94） | **1（上場同士 0）** |
| 比率付き親子関係のうち 50% 以下 | 5,047 / 38,476 | 942 / 35,257 |

参照整合性: ID 重複 0、参照切れ 0、evidence なし 0。

残る相互親会社ペアは「ルノー・日産・三菱アライアンス <-> 日産自動車」（Wikidata 由来、非上場。原本で確認するまで反転・削除しない）。

50% 以下の親子関係は削除していない。内訳は原本の分類がすべて子会社系で、実質支配による連結の可能性があるため:

| 原本の分類 | 出所 | 件数 |
| --- | --- | --- |
| 連結子会社 | edinet | 852 |
| 親会社 | edinet | 46 |
| 子会社 | edinet | 17 |
| 連結子会社 | edinet, wikidata | 10 |
| 持分法適用非連結子会社 | edinet | 10 |
| 親会社 | edinet, wikidata | 5 |
| 子会社 | edinet, wikidata | 2 |

## 確認済みケースの現状

| ケース | 期待 | 再生成後 | 判定 |
| --- | --- | --- | --- |
| 京成→OLC 関連会社（その他の関係会社） | confirmed | R0076589（confirmed・20.14%） | OK |
| OLC→京成 親子（旧 R0044475 の逆転） | absent | なし | OK |
| 京成→OLC 親子（Wikidata P749） | needs_review | R0076591（needs_review） | OK |
| SBG→ZOZO 親子 | confirmed | R0083380（confirmed・51.9%） | OK |
| ZOZO→SBG 親子（旧 R0003946 の逆転） | absent | なし | OK |
| ソニー→M3 関連会社 | confirmed | R0061503（confirmed・33.9%） | OK |
| M3→ソニー 親子（逆転） | absent | なし | OK |
| イオン→イオン北海道 親子 | confirmed | R0073330（confirmed・67.2%） | OK |
| 三菱商事→ライフ 関連会社 | confirmed | R0071721（confirmed・25.56%） | OK |
| 三菱商事→ライフ 親子（旧 100%） | absent | なし | OK |
| ライフ→三菱商事 親子（逆転） | absent | なし | OK |
| 日本車輌→JR東海 技術提携（根拠不足） | needs_review | R0064219（needs_review） | OK |
| アイシン→東邦瓦斯 共同研究（名寄せ） | confirmed | R0065414（confirmed） | OK |

`pipeline/corrections.json` の訂正 18 件のうち 13 件を適用、5 件は「旧データの誤りが再生成で生成されなかった場合の削除」で対象なし（想定どおり）。
適用前後の状態は `pipeline/data_processed/masters/corrections_applied.json`（git 管理外。再生成で再現）に記録される。
ソニーFG は旧関係（100% 子会社）を `historical`（2025-10-01 まで）にし、持分 16.40% の関連会社を追加した。

## 隔離（quarantine）

5,717 行を関係にせず `quarantine.json` に記録: nominee_holder 4,494、name:others_count 1,175、name:empty 33、name:label 7、name:numeric_only 6、name:too_short 2。

## 旧データとの対応

旧 relation_id → 新 relation_id の対応表: `relation_id_map.json`（62,724 件対応、18,721 件対応なし）。
対応なしの主な内訳:

| 旧タイプ | 出所 | 件数 |
| --- | --- | --- |
| parent_subsidiary | edinet | 17,988 |
| ownership | edinet | 437 |
| major_customer | edinet | 108 |
| affiliate | edinet | 56 |
| business_alliance | ir_disclosure | 41 |
| joint_venture | ir_disclosure | 34 |
| ownership | ir_disclosure | 21 |
| joint_research | ir_disclosure | 12 |

旧 parent_subsidiary の対応なしは、旧パーサーが分類不明を子会社にしていたもので、新データでは
関連会社（affiliate 160 → 4,5xx）・株式保有・要確認・方向反転へ移った分と、複数期の重複がまとまった分を含む。

| タイプ | 旧 | 新（確定） |
| --- | --- | --- |
| affiliate | 160 | 4,525 |
| business_alliance | 1,091 | 332 |
| capital_alliance | 96 | 37 |
| corporate_group | 64 | 65 |
| joint_research | 156 | 96 |
| joint_venture | 145 | 39 |
| major_customer | 2,342 | 2,191 |
| merger_acquisition | 53 | 22 |
| ownership | 32,625 | 37,915 |
| parent_subsidiary | 44,675 | 36,604 |
| technology_license | 38 | 2 |

IR 由来の提携・合弁・M&A は根拠判定（#6）で要確認へ回った分が減っている（確定から外れただけで削除はしていない）。

## 層化無作為サンプルの監査

出所×カテゴリで層化した無作為抽出（seed 20260909、各層最大6件、確定関係のみ）。EDINET は取得済み原本表の該当行、IR は根拠文と公表URL、Wikidata は項目を参照して人手で判定。correct_stale は抽出は正しいが時点が古い／不明。

結果（49 件）: {"correct": 46, "correct_stale": 3}

出所別: {"edinet": {"correct": 11, "correct_stale": 1}, "ir_disclosure": {"correct": 24}, "official_release": {"correct": 1}, "wikidata": {"correct": 10, "correct_stale": 2}}

層ごとの件数が小さく、全体の正解率の点推定は参考値。監査中に見つけた誤りの型（第三者の出来事、合併の方向、自社子会社の主体、第三者割当の引受側）は検証器に反映済みで、該当関係は再生成後に要確認へ移っている。

監査の過程（修正前のサンプルを含む。修正のたびにサンプルの一部が入れ替わるため、判定は名称の組で `sample_labels.json` に記録）で見つかった誤りの型と対処:

- 第三者の出来事を提出会社の関係として抽出（記事の転載、子会社同士の合併、他社による買収）→ `third_party_statement`
- 対等な合併・経営統合で存続側が分からない → `direction_unclear`
- 「子会社であるX社による…取得」で相手が自社子会社 → `counterparty_is_own_subsidiary`
- 第三者割当増資を引き受けた側なのに相手→提出会社になっていた → 引受側を提出会社として方向を修正
- 「X社への譲渡」の取得側、「Xによる…株式の取得」の長い社名 → 助詞による主体判定へ統一（#15 レビュー対応）
- 根拠文だけでは判定できない型（山形證券／岡三証券グループ: 岡三の子会社が主体、エンバイオ／MEL 社: 出資先の投資先）は
  修正前のサンプルで誤りとして記録し、今回の確定データからは外れている（要確認または再抽出で相手が変わった）

いずれも検証器（`pipeline/ir_validate.py`）に反映し、固定評価セット 38 件は全件一致。

サンプルの各件:

| ID | 層 | 関係 | タイプ | 判定 | 補足 |
| --- | --- | --- | --- | --- | --- |
| R0012527 | edinet/capital | ソウルドアウト(株) → リンカーズ | ownership | correct | 大株主の状況 1.03%（2025-07-31現在）と一致 |
| R0009172 | edinet/capital | みずほ銀行 → 澁澤倉庫 | ownership | correct_stale | 大株主の注記に写された2016-10-14の大量保有報告書（4.93%）。抽出は正しいが時点が古い。property=large_holding_report・基準日で区別 |
| R0022001 | edinet/capital | 国分グループ本社株式会社 → 久世 | affiliate | correct | その他の関係会社（被所有19.9%）→ 国分→久世 関連会社 |
| R0076182 | edinet/capital | ＡＶＡＮＴＩＡ → 株式会社 宇戸平工務店 | parent_subsidiary | correct | 連結子会社 100.0% |
| R0017138 | edinet/capital | 三好 稔美 → ファンペップ | ownership | correct | 大株主（個人）2.77% |
| R0066401 | edinet/capital | ＣＣＩグループ → 株式会社QR インベストメント | parent_subsidiary | correct | 連結子会社 100.00% |
| R0036387 | edinet/transaction | ＳＤＳホールディングス → 株式会社東セン貿 | major_customer | correct | 主要な顧客 103,268千円 |
| R0054473 | edinet/transaction | メタルアート → ダイハツ工業 | major_customer | correct | 主要な顧客 11,881百万円 |
| R0035884 | edinet/transaction | ホーブ → トーワ物産株式会社 | major_customer | correct | 主要な顧客 336,444千円 |
| R0050893 | edinet/transaction | ミラティブ → Google LLC | major_customer | correct | 主要な顧客 1,017,344千円 |
| R0069317 | edinet/transaction | 旭化学工業 → マキタ | major_customer | correct | 主要な顧客 954,497千円（上場のマキタへ名寄せ） |
| R0061816 | edinet/transaction | 名古屋電機工業 → 東日本高速道路株式会社 | major_customer | correct | 主要な顧客 2,109,068千円 |
| R0013254 | ir_disclosure/alliance | ネスレ日本株式会社 → キッコーマン | business_alliance | correct | 連携した海上輸送 |
| R0068226 | ir_disclosure/alliance | 日本精密 → クロスフォー | business_alliance | correct | 業務提携の発表 |
| R0005050 | ir_disclosure/alliance | Old City Association社 → マツモト | business_alliance | correct | 基本合意書（MOU）。deal_status=agreed |
| R0004085 | ir_disclosure/alliance | MINIEYE TECHNOLOGY CO.,LTD. → イクヨ | business_alliance | correct | 業務提携の検討に関する基本合意書。agreed 段階 |
| R0008188 | ir_disclosure/alliance | VI-grade社 → ＳＯＬＩＺＥ　Ｈｏｌｄｉｎｇｓ | business_alliance | correct | 協業開始の記述あり |
| R0010111 | ir_disclosure/alliance | 株式会社イヤサカ → シイエム・シイ | business_alliance | correct | 業務提携基本契約書（2021-06-22） |
| R0080124 | ir_disclosure/capital | テレビ東京ホールディングス → Minto | ownership | correct | 戦略的出資 |
| R0053681 | ir_disclosure/capital | マイポックス → thomas 株式会社 | ownership | correct | 出資 |
| R0042267 | ir_disclosure/capital | Ｊ．フロント　リテイリング → TableCheck | ownership | correct | CVC の出資（引用付与の問題あり） |
| R0015866 | ir_disclosure/capital | 株式会社レノ → 養命酒製造 | ownership | correct | レノによる公開買付け（相手が主体） |
| R0057168 | ir_disclosure/capital | リケンＮＰＲ → Hastings Holding Corp. | ownership | correct | 子会社 RCA 経由の Hastings 株式取得（修正後は正しい相手が確定に残る） |
| R0053683 | ir_disclosure/capital | マイポックス → ミスミ化学株式会社 | ownership | correct | 株式取得（子会社化） |
| R0067543 | ir_disclosure/group | 島津製作所 → Plasmion GmbH | merger_acquisition | correct | 発行済株式の75%を取得し子会社化 |
| R0039126 | ir_disclosure/group | ｆｏｎｆｕｎ → インバウンドテクノロジー株式会社 | merger_acquisition | correct | 事業譲受（M&A実績ページ） |
| R0039130 | ir_disclosure/group | ｆｏｎｆｕｎ → 株式会社ゼロワン | merger_acquisition | correct | 事業譲受（M&A実績ページ） |
| R0053135 | ir_disclosure/group | 太平洋セメント → 米Vulcan社 | merger_acquisition | correct | 資産等の買収完了（会社ではなく事業用資産。タイプは merger_acquisition のまま） |
| R0070263 | ir_disclosure/group | 丸紅 → TiAuto Investments Pty Ltd | merger_acquisition | correct | 公式公表で確認済み（agreed） |
| R0049449 | ir_disclosure/group | 塩野義製薬 → 田辺ファーマ | merger_acquisition | correct | 田辺ファーマからのエダラボン事業の買収 |
| R0058724 | ir_disclosure/transaction | 高見沢サイバネティックス → 警察庁 | major_customer | correct | 納入。相手は官公庁 |
| R0046534 | ir_disclosure/transaction | レゾナック・ホールディングス → ローム | major_customer | correct | 長期供給契約（2021） |
| R0036518 | ir_disclosure/transaction | ハンモック → (株)京王百貨店 | major_customer | correct | 主要取引先の掲載 |
| R0036519 | ir_disclosure/transaction | ハンモック → 奥村組 | major_customer | correct | 主要取引先の掲載 |
| R0036116 | ir_disclosure/transaction | グリーンエナジー＆カンパニー → 日本郵便 | major_customer | correct | 受注および完工 |
| R0036517 | ir_disclosure/transaction | ハンモック → (株)不二家システムセンター | major_customer | correct | 主要取引先の掲載 |
| R0061515 | official_release/capital | ソニーグループ → ソニーフィナンシャルグループ | affiliate | correct | 原本確認済みの訂正（16.40%・2025-10-01） |
| R0061480 | wikidata/capital | ソニーグループ → ソニー・ミュージック・インディア | ownership | correct | Wikidata P1830 |
| R0055083 | wikidata/capital | ちゅうぎんフィナンシャルグループ → 中国銀行 | ownership | correct | Wikidata P1830。持株会社と銀行 |
| R0068021 | wikidata/capital | キヤノン → Canon Computer Systems | parent_subsidiary | correct_stale | Wikidata P355。現存しない可能性のある子会社で時点不明 |
| R0068336 | wikidata/capital | ブシロード → 新日本プロレス | parent_subsidiary | correct | Wikidata P355 |
| R0065544 | wikidata/capital | 本田技研工業 → ホンダマニュファクチャリングUK | parent_subsidiary | correct_stale | Wikidata P355。2021年に生産終了した拠点で時点不明 |
| R0063203 | wikidata/capital | 京セラ → Kyocera (United States) | parent_subsidiary | correct | Wikidata P355 |
| R0039198 | wikidata/group | 東北新社 → 東北新社グループ | corporate_group | correct | Wikidata P463 |
| R0043185 | wikidata/group | ユナイテッド・スーパーマーケット・ホールディングス → イオングループ | corporate_group | correct | Wikidata P463 |
| R0077321 | wikidata/group | 名古屋鉄道 → 名鉄グループ | corporate_group | correct | Wikidata P463 |
| R0077032 | wikidata/group | 西日本鉄道 → 西鉄グループ | corporate_group | correct | Wikidata P463 |
| R0044862 | wikidata/group | ＧＭＯペパボ → ＧＭＯインターネットグループ | corporate_group | correct | Wikidata P463 |
| R0079049 | wikidata/group | ＡＮＡホールディングス → ANAグループ | corporate_group | correct | Wikidata P463 |

## 公開データのサイズ

| ファイル | 展開後 | gzip |
| --- | --- | --- |
| M4_companies.json | 1.8 MB | 0.3 MB |
| M5_company_relations.json | 38.2 MB | 2.0 MB |
| evidence/（84 シャード、必要時のみ取得） | 48.3 MB | — |
