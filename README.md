# JP Market Vis — 日本の上場企業マップ

日本の上場企業の資本・取引・提携・人的・グループ関係を探索する静的Webアプリ。

**公開URL:** https://mattyamonaca.github.io/JP_Market_Vis/

## できること

- **全体マップ**：上場企業同士の関係をネットワークで表示。企業名・通称・読み・証券コード検索、5カテゴリの絞り込み、最小関係数、ズーム・全体表示。右下の「回転」をONにすると左右ドラッグでノード群全体を平面内で回転できます（タッチ対応）。回転領域にフォーカスして左右矢印キーで15°ずつ回転、Escで移動モードに戻ります。
- **関係グラフ**：企業を中心とする1ホップの関係。上場企業を選択して移動、履歴で戻る、企業・関係の詳細とエビデンスを表示。
- **関係一覧**：カテゴリ・関係タイプ・企業名・コードで検索。300件ずつページ送りして全件を確認。
- **統計・データ**：関係タイプ、出所、信頼度、ハブ企業ランキング、データの対象と制約。

円の色は17業種、円の大きさは収録関係数です。株価・時価総額の表示ではなく、配置に地理的な意味はありません。カテゴリで絞った後の関係数で最小関係数を判定し、残った企業同士の線を表示します。

## 元になった実装

既存の `persona_project/visualize/company_relations_vis` を移植。
React 18 / Vite 6 / react-force-graph-2d / React Flow の構成とデータを継承し、全体マップを初期画面に変更、検索・表示調整・モバイル用レイアウト・ロード/エラー表示・一覧ページ送りを追加しました。カテゴリ全解除時の個別グラフの不具合も修正しています。

元プロジェクトやAPIへの実行時依存はありません。HTML・JavaScript・CSS・JSONだけで動作し、外部APIキー・バックエンドは不要です。初回データの非圧縮サイズは約34MBです。

## データ

| 項目 | 内容 |
| --- | --- |
| 生成日 | 2026-06-13 |
| データバージョン | 2026.06 |
| 収録上場企業 | 3,734社 |
| 収録関係 | 81,445件 |
| 非上場等の関係先 | 59,780件 |
| 対象 | 東証プライム・スタンダード・グロースの内国株式 |

地方単独上場、ETF、REIT等を網羅するデータではありません。全体マップは両端が収録上場企業の関係だけを使用し、関係のない企業は表示しません（検索は全収録企業を対象）。個別グラフ・関係一覧には非上場の関係先も含みます。個別グラフは約90関係先に表示を制限し、省略数を表示します。

公開情報から作成された既存スナップショットをそのまま収録しています。最新データの再収集・正誤の全件確認は実施していません。自動抽出・名寄せ・LLMによるIR開示抽出を含み、誤り、欠落、古い関係が残る可能性があります。収録信頼度は内容の正しさを保証しません。関係がない表示は、現実に関係がないことを意味しません。

データ出所：

- [JPX 東証上場銘柄一覧](https://www.jpx.co.jp/markets/statistics-equities/misc/01.html)
- [金融庁 EDINET](https://disclosure2.edinet-fsa.go.jp/)：コードリスト・有価証券報告書
- [Wikidata](https://www.wikidata.org/)：資本関係・グループ所属等
- 企業IR開示：関係詳細に収録URLを表示

各関係の `evidence` に出所・書類ID・URL・抽出根拠等がある場合は保持し、詳細画面で確認できます。出所別・信頼度別統計はエビデンス件数です。ソースコードのライセンスはリポジトリの [LICENSE](LICENSE) を参照してください。収録データ・引用元には各提供元の利用条件が適用されます。

## 開発

Node.js 22、npmを使用します。

```sh
npm ci
npm run dev
```

開発URL：`http://localhost:5184/JP_Market_Vis/`（ポート使用中はViteの出力を確認）。

```sh
npm test
npm run build
npm run preview
```

`dist/` が公開成果物です。テストは全関係の参照整合性・ID重複・出所、検索正規化、カテゴリ全解除、グラフのフィルタと描画用データ分離を確認します。

## GitHub Pages

[ViteのGitHub Pagesガイド](https://vite.dev/guide/static-deploy.html#github-pages)に従い、`vite.config.js` に `base: '/JP_Market_Vis/'` を設定しています。データ取得にも `import.meta.env.BASE_URL` を使います。

[GitHub ActionsのPagesワークフロー](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)を `.github/workflows/pages.yml` に用意しています。リポジトリの **Settings → Pages → Source** を **GitHub Actions** に設定すると、`main` へのpushでテスト・ビルド後に `dist/` を公開します。PRではテストとビルドだけを実行します。手動実行はActionsの `Deploy to GitHub Pages` から行えます。

別名のリポジトリに移す場合はViteの `base` を変更してください。ハッシュやサーバー側のルーティングに依存しない単一ページです。

## データの更新

`public/M4_companies.json` と `public/M5_company_relations.json` を同じスナップショットの組で置き換え、`npm test` と `npm run build` を実行します。READMEの件数・生成日も更新してください。

データ生成パイプラインは [`pipeline/`](pipeline/README.md) にあります（元は別プロジェクト `persona_project` にあったものを移管）。EDINET の再取得には API キーが必要です。認証情報はこのリポジトリに含めていません。
