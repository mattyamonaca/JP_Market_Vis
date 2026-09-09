# ir_crawl — 企業IRサイト LLMナビ型クロール（提携・出資の長尾データ）

EDINET・Wikidata に出てこない**業務提携・資本提携・合弁・技術提携・共同研究・小規模出資**を、
各社の公式IRサイト（ニュースリリース）から取得し、LLM で構造化して M5 に追加するパイプライン。
これらは取得が困難なぶん、競合が持てない独自データ（差別化資産）になる。

## 設計方針：個社ハードコードをしない

約3,900社のサイト構造はバラバラなため、サイトごとのスクレイパは書かない。
**ヘッドレス描画 → LLM/ヒューリスティックでIRリンクとリリースを発見 → LLM抽出**の汎用フローにし、
保守コストを「予測可能なトークンコスト」に変換する。

## パイプライン

1. `discover_urls.py` — Wikidata P856 から company→公式URL（.co.jp 優先で1件に正規化）
2. `crawl_poc.mjs`（Node + Playwright）— 描画 → IR/ニュース一覧を発見 → 提携系見出しを抽出 →
   各リリース本文を取得 → Kimi(`moonshot-v1-32k`) で構造化 → `data/poc_results.json`

### 重要な技術メモ

- **抽出 LLM は非思考モデル `moonshot-v1-32k` を使う。** `kimi-k2.5` は reasoning にトークンを
  使い切り `content` を返さない（finish=length・content空）。構造化抽出には不向き
- Node の ESM は NODE_PATH を見ない。`node_modules` を occupation_db_vis から symlink して解決
- 企業IRサイトは JS 動的描画が多く、静的 fetch では空。Playwright 必須

## 実行

```bash
cd scripts/build_company_relations
.venv/bin/python ir_crawl/discover_urls.py --n 30      # 対象URL収集（ハブ上位）
cd ir_crawl && ln -sfn ../../../../visualize/occupation_db_vis/node_modules node_modules
KIMI_API_KEY=$(grep ^KIMI_API_KEY= ~/.persona/.env|cut -d= -f2) node crawl_poc.mjs 6
```

## 測定結果（2026-06・ハブ上位6社）

| 指標 | 値 |
|---|---|
| IRページ到達 | 6/6（100%） |
| 関係抽出 | 32件（4/6社で抽出。三菱商事・丸紅は一覧のDOM構造が異なり0） |
| トークン | 約4,200 tok/社 |
| 所要 | 約19秒/社（直列） |
| 3,900社換算 | 約16Mトークン / 約21時間（直列・並列化で2〜3h） |

抽出品質は良好（三井物産→曽田香料/東レ ownership、伊藤忠→アイチコーポレーション capital_alliance、
住友商事→Graphyte JV、アイシン→デンソー/豊田通商 JV 等を相手企業名・日付・根拠つきで取得）。

## 本番実行結果（2026-06）

- 対象 1,813 社（Wikidata P856 で URL 解決できた社）を並列6でクロール
- 1,800/1,813 社・**3,632 関係**を抽出（約740万トークン）。残13社は末尾でハングし手動救出
  - ハング原因: Kimi `fetch` にタイムアウト未設定で応答待ちのまま停止 → **修正済み**（AbortController 60s）
  - 救出: `crawl_progress.json`（20社ごとチェックポイント）の relations を `ir_relations.json` へ書き出し
- 抽出種別: business_alliance 1,889 / ownership 685 / joint_venture 272 / joint_research 257 /
  major_customer 231 / capital_alliance 176 / merger_acquisition 76 / technology_license 46
- これらが M5 に confidence=low で統合され、可視化に「提携」カテゴリとして表示される

## 本格展開に向けた残課題

- **URL 被覆**: P856 は QID 付き企業のみ（M4 の約半数）。QID 無し企業向けに EDINET 提出者情報等の代替探索が必要
- **サイト構造の長尾**: 年度タブJS等で一覧が取れない社（三菱商事/丸紅型）向けに、アンカー
  キーワード一致でなく「描画後ページを LLM に渡してリリースリンクを発見させる」フォールバック
- **M5 マージ**: counterparty を M4/エンティティへ名寄せし、`source=ir_disclosure`・`confidence=low`・
  `source_url` 付きでエッジ化。EDINET 高信頼層と分離（viz の信頼度表示で区別可能）
- **robots.txt / 礼儀**: 全社クロール時は robots 準拠・レート制御・bot 明示
