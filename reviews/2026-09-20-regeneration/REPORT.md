# 再生成レポート 2026-09-20（人的・グループ・提携の拡充）

このレポートは `pipeline/audit.py` の自動監査に、今回追加した出所（有報「役員の状況」「経営上の重要な契約等」、グループ広報団体の会員一覧）の
サンプル判定を付けたもの。以下の自動生成部分の前に、今回の拡充の要点と判定方法を記す。

## 今回の拡充

| カテゴリ | 確定関係（旧→新） | 全体マップ上（旧→新） | 主な出所 |
| --- | --- | --- | --- |
| 人的（役員兼任） | 0 → 5,460 | 0 → 5,460 | 有報「役員の状況」の略歴に現任と記載された他社役職（36,241 行のうち相手が上場企業のもの 8,005 行） |
| 提携 | 467 → 1,850 | 80 → 481 | 有報「経営上の重要な契約等」（2,564 行 → 投入 1,979 行、うち確定 1,572・要確認 407） |
| グループ | 87 → 232 | 1 → 210（ハブへの線） | 三菱広報委員会・三井広報委員会・住友グループ広報委員会・みどり会の会員会社一覧（183 社。子会社が会員の場合は上場親会社 55 社） |
| 資本・取引 | 変更なし | ほぼ変更なし | — |

## サンプル判定の方法と注意

- 出所 × カテゴリで層化した無作為抽出（seed 20260920、各層最大 7 件、確定関係のみ、90 件中 78 件が抽出対象の層に該当）。
- 今回新設した出所（edinet/personnel 7 件・edinet/alliance 7 件・group_site/group 7 件）はすべて判定した（30 件、修正前の抽出で誤りだった
  1 件＝借入先の表の誤分類は修正後の再生成で消えている）。既存出所のうち前回（2026-09-09）の判定名簿と名前が一致した項目にも判定を付け、
  残り（null）は今回の変更対象外で前回の再生成レポートで判定済みの層。
- **判定は、公開データに保持した根拠文（有報の略歴行・契約の記載・会員一覧の原文名）を読んで行ったもので、人手で原本 PDF と照合したものではない。**
  「原本で検証済み」の印は付けていない。
- 監査中に見つけて修正した誤りの型: 借入先（シンジケートローン）の表を直前の資本業務提携の文脈から誤分類（ぴあ→静岡銀行ほか 8 行。表の文脈から
  種別を補うのは除外語を含まない場合に限定）、法人格だけの断片「.Ltd.」、原文名の「他」「親会社である」の付着、改行で分かれた社名。
- 残る既知の課題: 原文名の先頭に副詞が残る例（「新たに弥生株式会社」。表示名のみの問題で、相手が上場企業のものは名寄せで解決済み）。
  技術提携の方向は「導入／供与」の語がない場合 needs_review（407 件の大半）。相手が上場企業でなく法人格もない名前（大学・研究所等）は投入していない。

---

# 公開データの再生成と監査（Issue #3）— 2026-09-09（最終再生成 2026-09-20）

対象: `pipeline/` で再生成した `public/M4_companies.json` / `public/M5_company_relations.json` / `public/evidence/`（生成日 2026-09-20）。
入力は 2025-06-14〜2026-06-13 提出の有価証券報告書 3,939 件（EDINET API v2 から 2026-09-09 に再取得したキャッシュを再解析）、
Wikidata・IR 抽出は 2026-06-13 のスナップショット。旧公開データは `main` の 2026-06-13 生成版（81,445 関係）。

再実行: `python3 pipeline/audit.py --old <旧M5> --old-m4 <旧M4> --out reviews/2026-09-09-regeneration`、
`python3 pipeline/apply_sample_labels.py reviews/2026-09-09-regeneration`、`python3 pipeline/make_regen_report.py reviews/2026-09-09-regeneration`

## 件数

| 項目 | 旧 | 新 |
| --- | --- | --- |
| 関係（全体） | 81,445 | 90,787 |
| うち確定（confirmed） | — | 88,813 |
| うち要確認（needs_review） | — | 1,973 |
| うち過去（historical） | — | 1 |
| 非上場エンティティ | 59,780 | 58,653 |
| 数値・記号だけの企業ノード | 456 | **0** |
| 数値ノードに接続する関係 | 568 | **0** |
| 法人格だけの企業ノード（「株式会社」「Inc.」等） | — | **0** |
| 企業名として不適切な企業ノード（name_problem 全種）／接続する関係 | — | **0 ／ 0** |
| 相互に親会社となる確定ペア | 99（上場同士 94） | **1（上場同士 0）** |
| 比率付き親子関係のうち 50% 以下 | 5,047 / 38,476 | 942 / 35,257 |

参照整合性: ID 重複 0、参照切れ 0、evidence なし 0。

### 名称の監査

企業名として不適切な entity 名（`edinet_tables.name_problem`）: なし。
法人格を除いた本体が 1 文字以下の名称: 17 件（㈱ｇ、株式会社Ｍ、Z株式会社、株式会社創、(株)孝、(有)彩、有限会社志、株式会社晴、株式会社杏、有限会社欅）。

数字を社名に含む法人（#20 レビューで「株式会社」に破損していた 3 社）。脚注番号の除去は法人格・閉じ括弧の直後に限り、
数字を除くと法人格しか残らない場合は名称の一部として保持する（`clean_name`。回帰テスト `test_clean_name_keeps_digits_that_belong_to_the_name`）:

| 名称 | 書類 | 文脈 | entity | 判定 |
| --- | --- | --- | --- | --- |
| 株式会社88 | S100W2DE | フェイスネットワーク(3489) の大株主 | ENT000125 | OK |
| 株式会社58 | S100XS2Y | エスネットワークス(5867) の大株主 | ENT000105 | OK |
| 株式会社28 | S100XHR6 | GLOE(9565) の連結子会社 | ENT000049 | OK |

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
| 京成→OLC 関連会社（その他の関係会社） | confirmed | R0083763（confirmed・20.14%） | OK |
| OLC→京成 親子（旧 R0044475 の逆転） | absent | なし | OK |
| 京成→OLC 親子（Wikidata P749） | needs_review | R0083765（needs_review） | OK |
| SBG→ZOZO 親子 | confirmed | R0090684（confirmed・51.9%） | OK |
| ZOZO→SBG 親子（旧 R0003946 の逆転） | absent | なし | OK |
| ソニー→M3 関連会社 | confirmed | R0067811（confirmed・33.9%） | OK |
| M3→ソニー 親子（逆転） | absent | なし | OK |
| イオン→イオン北海道 親子 | confirmed | R0080368（confirmed・67.2%） | OK |
| 三菱商事→ライフ 関連会社 | confirmed | R0078689（confirmed・25.56%） | OK |
| 三菱商事→ライフ 親子（旧 100%） | absent | なし | OK |
| ライフ→三菱商事 親子（逆転） | absent | なし | OK |
| 日本車輌→JR東海 技術提携（根拠不足） | needs_review | R0070709（needs_review） | OK |
| アイシン→東邦瓦斯 共同研究（名寄せ） | confirmed | R0072002（confirmed） | OK |

`pipeline/corrections.json` の訂正 18 件のうち 13 件を適用、5 件は「旧データの誤りが再生成で生成されなかった場合の削除」で対象なし（想定どおり）。
適用前後の状態は `pipeline/data_processed/masters/corrections_applied.json`（git 管理外。再生成で再現）に記録される。
ソニーFG は旧関係（100% 子会社）を `historical`（2025-10-01 まで）にし、持分 16.40% の関連会社を追加した。

## 隔離（quarantine）

5,723 行を関係にせず `quarantine.json` に記録: nominee_holder 4,494、name:others_count 1,175、name:empty 33、name:label 7、name:legal_form_only 6、name:numeric_only 6、name:too_short 2。

## 旧データとの対応

旧 relation_id → 新 relation_id の対応表: `relation_id_map.json`（83,479 件対応、0 件対応なし）。
対応なしの主な内訳:

| 旧タイプ | 出所 | 件数 |
| --- | --- | --- |


旧 parent_subsidiary の対応なしは、旧パーサーが分類不明を子会社にしていたもので、新データでは
関連会社（affiliate 160 → 4,5xx）・株式保有・要確認・方向反転へ移った分と、複数期の重複がまとまった分を含む。

| タイプ | 旧 | 新（確定） |
| --- | --- | --- |
| affiliate | 4,524 | 4,524 |
| business_alliance | 1,085 | 1,074 |
| capital_alliance | 95 | 287 |
| corporate_group | 65 | 210 |
| interlocking_director | 0 | 5,460 |
| joint_research | 186 | 173 |
| joint_venture | 114 | 39 |
| major_customer | 2,314 | 2,191 |
| merger_acquisition | 53 | 22 |
| ownership | 38,401 | 37,915 |
| parent_subsidiary | 36,604 | 36,602 |
| technology_license | 38 | 316 |

IR 由来の提携・合弁・M&A は根拠判定（#6）で要確認へ回った分が減っている（確定から外れただけで削除はしていない）。

## 層化無作為サンプルの監査

出所×カテゴリで層化した無作為抽出（seed 20260909、各層最大6件、確定関係のみ）。EDINET は取得済み原本表の該当行、IR は根拠文と公表URL、Wikidata は項目を参照して人手で判定。correct_stale は抽出は正しいが時点が古い／不明。

結果（78 件）: {"correct": 30, "null": 48}

出所別: {"edinet": {"correct": 14, "null": 14}, "group_site": {"correct": 7}, "ir_disclosure": {"null": 22, "correct": 6}, "official_release": {"correct": 1}, "wikidata": {"null": 12, "correct": 2}}

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
| R0059231 | edinet/alliance | 日本製鉄 → ＪＦＥホールディングス | business_alliance | correct | 日伯ニオブの合弁協定。相手は共同出資のパートナー |
| R0067832 | edinet/alliance | ソニーグループ → ＫＡＤＯＫＡＷＡ | capital_alliance | correct | 資本業務提携（第三者割当増資による新株式の発行）の表どおり |
| R0018117 | edinet/alliance | 三菱UFJニコス → ＡＳＪ | business_alliance | correct | 包括代理通信販売加盟店契約（業務提携）の表どおり |
| R0006496 | edinet/alliance | SP.LINKS株式会社 → Ｍマート | business_alliance | correct | 業務提携契約書の表どおり |
| R0044032 | edinet/alliance | Ｓｙｎｓｐｅｃｔｉｖｅ → 三井物産 | business_alliance | correct | 画像データ取得業務委託契約。相手方は三井物産を構成員とするコンソーシアム（構成員として抽出） |
| R0034290 | edinet/alliance | 遠智有限公司 → キューブ | business_alliance | correct | 合弁会社設立契約。相手は共同出資のパートナー |
| R0026330 | edinet/alliance | 新たに弥生株式会社 → エフアンドエム | capital_alliance | correct | 資本業務提携契約の記載どおり。原文名先頭の「新たに」（副詞）が残る（要修正、表示名のみの問題） |
| R0033794 | edinet/capital | 西村 正巳 → オービーシステム | ownership | None | None |
| R0067691 | edinet/capital | アンリツ → Anritsu Eletrônica Ltda. | parent_subsidiary | None | None |
| R0052114 | edinet/capital | アイカ工業 → アイカ・ラミネーツ・ ベトナム社 | parent_subsidiary | None | None |
| R0003124 | edinet/capital | JP MORGAN CHASE BANK 385632 → りそなホールディングス | ownership | None | None |
| R0018070 | edinet/capital | 三菱UFJアセットマネジメント株式会社 → 光村印刷 | ownership | None | None |
| R0042150 | edinet/capital | キリンホールディングス → Kirin Brewery of America, LLC | parent_subsidiary | None | None |
| R0078793 | edinet/capital | 三谷商事 → クリーンガス福井株式会社 | parent_subsidiary | None | None |
| R0058261 | edinet/personnel | ＡＧＣ → デンソー | interlocking_director | correct | 両社の有報の役員の状況（AGC社外取締役 馬場久美子・デンソー取締役会長 有馬浩二）どおり |
| R0053756 | edinet/personnel | 石原ケミカル → サカタインクス | interlocking_director | correct | 役員の状況の略歴（サカタインクス社外取締役・現任）どおり |
| R0041985 | edinet/personnel | Ａｉロボティクス → アジアクエスト | interlocking_director | correct | 両社の有報で同一人物（岡田雅史）の現任役職を確認 |
| R0039741 | edinet/personnel | ＬＩＦＵＬＬ → ＣａＳｙ | interlocking_director | correct | 両社の有報で同一人物（中尾隆一郎）の現任役職を確認 |
| R0044586 | edinet/personnel | ラサ商事 → 旭ダイヤモンド工業 | interlocking_director | correct | 役員の状況の略歴（ラサ商事社外取締役・現任）どおり |
| R0047485 | edinet/personnel | パルマ → 牧野フライス製作所 | interlocking_director | correct | 役員の状況の略歴（牧野フライス製作所監査役・現任）どおり |
| R0055775 | edinet/personnel | 早稲田アカデミー → 綜研化学 | interlocking_director | correct | 両社の有報で同一人物（布施木孝叔）の現任役職を確認 |
| R0052492 | edinet/transaction | サスメド → 株式会社コラボスクエア | major_customer | None | None |
| R0067474 | edinet/transaction | 大同信号 → 東日本旅客鉄道 | major_customer | None | None |
| R0085988 | edinet/transaction | 共栄タンカー → コスモ石油 | major_customer | None | None |
| R0078871 | edinet/transaction | カノークス → フタバ産業 | major_customer | None | None |
| R0054512 | edinet/transaction | アンジェス → (株)エス・ディ・コラボ | major_customer | None | None |
| R0062145 | edinet/transaction | 日本エマージェンシーアシスタンス → American Express International Inc | major_customer | None | None |
| R0089455 | edinet/transaction | ＫＹＣＯＭホールディングス → 日立製作所 | major_customer | None | None |
| R0082100 | group_site/group | 三菱ＨＣキャピタル → 三菱グループ | corporate_group | correct | 三菱広報委員会の会員会社一覧に掲載 |
| R0070329 | group_site/group | 名村造船所 → 三和グループ | corporate_group | correct | みどり会のメンバー会社一覧に掲載 |
| R0080613 | group_site/group | 三菱ＵＦＪフィナンシャル・グループ → 三和グループ | corporate_group | correct | みどり会の会員は子会社の三菱UFJ銀行（旧三和銀行）。上場親会社として表示、member_via に記録 |
| R0058181 | group_site/group | 三ツ星ベルト → 三和グループ | corporate_group | correct | みどり会のメンバー会社一覧に掲載 |
| R0085357 | group_site/group | 日本郵船 → 三菱グループ | corporate_group | correct | 三菱広報委員会の会員会社一覧に掲載 |
| R0077834 | group_site/group | 三井物産 → 三井グループ | corporate_group | correct | 三井広報委員会の会員会社一覧に掲載（Wikidata P463 とも一致） |
| R0057557 | group_site/group | コスモエネルギーホールディングス → 三和グループ | corporate_group | correct | みどり会のメンバー会社一覧に掲載 |
| R0001221 | ir_disclosure/alliance | Brakes India Private Limited → ＴＢＫ | business_alliance | None | None |
| R0004159 | ir_disclosure/alliance | 株式会社Ｌｕｕｐ → 東急 | capital_alliance | None | None |
| R0010398 | ir_disclosure/alliance | アヲハタ → キユーピー | joint_research | None | None |
| R0013487 | ir_disclosure/alliance | トタルエナジーズ社 → 川崎重工業 | business_alliance | None | None |
| R0020246 | ir_disclosure/alliance | 京都大学iPS細胞研究所 → 伊藤園 | joint_research | None | None |
| R0028863 | ir_disclosure/alliance | 東山口信用金庫 → ＮＥＸＹＺ．Ｇｒｏｕｐ | business_alliance | None | None |
| R0016608 | ir_disclosure/alliance | ワールドネット株式会社 → 伊藤忠エネクス | business_alliance | None | None |
| R0074200 | ir_disclosure/capital | 壱番屋 → 株式会社me | ownership | None | None |
| R0039792 | ir_disclosure/capital | 日本Ｍ＆Ａセンターホールディングス → 株式会社SBWorks | ownership | None | None |
| R0084173 | ir_disclosure/capital | ゼロ → Auto Carrier(Thailand) Co., Ltd. | ownership | None | None |
| R0051791 | ir_disclosure/capital | 三菱瓦斯化学 → 三菱商事 | ownership | None | None |
| R0050279 | ir_disclosure/capital | うるる → 株式会社ブレインフィード | ownership | None | None |
| R0044335 | ir_disclosure/capital | アルピコホールディングス → ㈱ハーベスト | ownership | None | None |
| R0044961 | ir_disclosure/capital | Ｊ．フロント　リテイリング → Sally | ownership | correct | CVC の出資。同じ根拠文が無関係なPDF 4件にも付いている（引用付与の問題） |
| R0040964 | ir_disclosure/group | ｆｏｎｆｕｎ → インバウンドテクノロジー株式会社 | merger_acquisition | correct | 事業譲受（M&A実績ページ） |
| R0040966 | ir_disclosure/group | ｆｏｎｆｕｎ → グルーコードコミュニケーションズ株式会社 | merger_acquisition | None | None |
| R0040961 | ir_disclosure/group | ｆｏｎｆｕｎ → 株式会社portera | merger_acquisition | None | None |
| R0082383 | ir_disclosure/group | ＳＯＭＰＯホールディングス → Aspen Insurance Holdings Limited | merger_acquisition | None | None |
| R0036729 | ir_disclosure/group | ニッスイ → Pesquera Yadran S.A. | merger_acquisition | None | None |
| R0074334 | ir_disclosure/group | 島津製作所 → Plasmion GmbH | merger_acquisition | correct | 発行済株式の75%を取得し子会社化 |
| R0040965 | ir_disclosure/group | ｆｏｎｆｕｎ → 株式会社イー・クラウドサービス | merger_acquisition | correct | 株式譲受（M&A実績ページ） |
| R0037170 | ir_disclosure/transaction | グリーンエナジー＆カンパニー → 日本郵便 | major_customer | correct | 受注および完工 |
| R0037171 | ir_disclosure/transaction | グリーンエナジー＆カンパニー → 綜電(株) | major_customer | None | None |
| R0050435 | ir_disclosure/transaction | レゾナック・ホールディングス → ローム | major_customer | correct | 長期供給契約（2021） |
| R0001835 | ir_disclosure/transaction | Farnell → ローム | major_customer | None | None |
| R0068011 | ir_disclosure/transaction | 池上通信機 → 東北放送株式会社 | major_customer | None | None |
| R0037696 | ir_disclosure/transaction | ハンモック → 味の素 | major_customer | None | None |
| R0037704 | ir_disclosure/transaction | ハンモック → アズワン | major_customer | None | None |
| R0067829 | official_release/capital | ソニーグループ → ソニーフィナンシャルグループ | affiliate | correct | 原本確認済みの訂正（16.40%・2025-10-01） |
| R0076638 | wikidata/capital | 任天堂 → 任天堂ネットワークサービス | parent_subsidiary | None | None |
| R0026599 | wikidata/capital | 日本トラスティ・サービス信託銀行 → ソフトバンクグループ | ownership | None | None |
| R0072227 | wikidata/capital | スズキ → パックスズキ | parent_subsidiary | None | None |
| R0077739 | wikidata/capital | 三井物産 → Mitsui & Co (Ireland) | parent_subsidiary | None | None |
| R0067768 | wikidata/capital | ソニーグループ → ソニーオプティアーク | ownership | None | None |
| R0072114 | wikidata/capital | 本田技研工業 → ソニー・ホンダモビリティ | parent_subsidiary | None | None |
| R0067306 | wikidata/capital | セイコーエプソン → Epson (United States) | parent_subsidiary | None | None |
| R0075163 | wikidata/group | ブシロード → ブシロードグループ | corporate_group | None | None |
| R0084216 | wikidata/group | 西日本鉄道 → 西鉄グループ | corporate_group | correct | Wikidata P463 |
| R0083691 | wikidata/group | 京王電鉄 → 京王グループ | corporate_group | None | None |
| R0064921 | wikidata/group | ブラザー工業 → ブラザーグループ | corporate_group | None | None |
| R0083524 | wikidata/group | 東武鉄道 → 芙蓉グループ | corporate_group | None | None |
| R0084514 | wikidata/group | 名古屋鉄道 → 名鉄グループ | corporate_group | correct | Wikidata P463 |
| R0086070 | wikidata/group | ＮＩＰＰＯＮ　ＥＸＰＲＥＳＳホールディングス → NXグループ | corporate_group | None | None |

## 公開データのサイズ

| ファイル | 展開後 | gzip |
| --- | --- | --- |
| M4_companies.json | 1.8 MB | 0.3 MB |
| M5_company_relations.json | 41.2 MB | 2.4 MB |
| evidence/（91 シャード、必要時のみ取得） | 54.2 MB | — |
