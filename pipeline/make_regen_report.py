"""audit.json / sample.json / quarantine.json から再生成レポート（REPORT.md）を作る。
  python pipeline/make_regen_report.py reviews/2026-09-09-regeneration
"""
import json, sys
from pathlib import Path

d = Path(sys.argv[1])
a = json.loads((d / "audit.json").read_text(encoding="utf-8"))
s = json.loads((d / "sample.json").read_text(encoding="utf-8"))
q = json.loads((Path(__file__).parent / "data_processed" / "masters" / "quarantine.json").read_text(encoding="utf-8"))
diff, c, le, sv = a["diff_vs_old"], a["counts"], a["parent_ratio_le_50"], s["summary"]
rows_bt = "\n".join(f"| {t} | {v['old']:,} | {v['new_confirmed']:,} |" for t, v in diff["by_type"].items())
rows_un = "\n".join(f"| {u['type']} | {', '.join(u['sources'])} | {u['count']:,} |" for u in diff["unmatched_by_type_and_source"][:8])
known = "\n".join(
    f"| {k['case']} | {k['expected']} | "
    + (", ".join(f"{f['id']}（{f['status']}" + (f"・{round(f['ratio'] * 100, 2)}%" if f['ratio'] is not None else "") + "）" for f in k["found"]) or "なし")
    + f" | {'OK' if k['ok'] else 'NG'} |" for k in a["known_cases"])
le_rows = "\n".join(f"| {x['classification']} | {', '.join(x['sources'])} | {x['count']} |" for x in le["by_classification_and_source"])
sample_rows = "\n".join(f"| {it['relation_id']} | {it['stratum']} | {it['source']} → {it['target']} | {it['relation_type']} | {it['verdict']} | {it['note']} |" for it in s["items"])
import collections
qr = collections.Counter(r["reason"] for r in q["rows"])
q_line = "、".join(f"{k} {v:,}" for k, v in qr.most_common())
md = f"""# 公開データの再生成と監査（Issue #3）— 2026-09-09

対象: `pipeline/` で再生成した `public/M4_companies.json` / `public/M5_company_relations.json` / `public/evidence/`。
入力は 2025-06-14〜2026-06-13 提出の有価証券報告書 3,939 件（EDINET API v2 から 2026-09-09 に再取得）、
Wikidata・IR 抽出は 2026-06-13 のスナップショット。旧公開データは `main` の 2026-06-13 生成版（81,445 関係）。

再実行: `python3 pipeline/audit.py --old <旧M5> --old-m4 <旧M4> --out reviews/2026-09-09-regeneration`、
`python3 pipeline/apply_sample_labels.py reviews/2026-09-09-regeneration`、`python3 pipeline/make_regen_report.py reviews/2026-09-09-regeneration`

## 件数

| 項目 | 旧 | 新 |
| --- | --- | --- |
| 関係（全体） | 81,445 | {c['relations']:,} |
| うち確定（confirmed） | — | {c['by_status']['confirmed']:,} |
| うち要確認（needs_review） | — | {c['by_status']['needs_review']:,} |
| うち過去（historical） | — | {c['by_status'].get('historical', 0):,} |
| 非上場エンティティ | 59,780 | {c['entities']:,} |
| 数値・記号だけの企業ノード | 456 | **{a['numeric_entities']['count']}** |
| 数値ノードに接続する関係 | 568 | **{a['numeric_entities']['relations_touching']}** |
| 相互に親会社となる確定ペア | 99（上場同士 94） | **{a['mutual_parent_pairs']['count']}（上場同士 {a['mutual_parent_pairs']['listed_both']}）** |
| 比率付き親子関係のうち 50% 以下 | 5,047 / 38,476 | {le['count']} / {le['of_with_ratio']:,} |

参照整合性: ID 重複 {len(a['integrity']['duplicate_ids'])}、参照切れ {a['integrity']['broken_refs']}、evidence なし {a['integrity']['without_evidence']}。

残る相互親会社ペアは「{a['mutual_parent_pairs']['pairs'][0]['pair'] if a['mutual_parent_pairs']['pairs'] else 'なし'}」（Wikidata 由来、非上場。原本で確認するまで反転・削除しない）。

50% 以下の親子関係は削除していない。内訳は原本の分類がすべて子会社系で、実質支配による連結の可能性があるため:

| 原本の分類 | 出所 | 件数 |
| --- | --- | --- |
{le_rows}

## 確認済みケースの現状

| ケース | 期待 | 再生成後 | 判定 |
| --- | --- | --- | --- |
{known}

`pipeline/corrections.json` の訂正 18 件のうち 13 件を適用、5 件は「旧データの誤りが再生成で生成されなかった場合の削除」で対象なし（想定どおり）。
適用前後の状態は `pipeline/data_processed/masters/corrections_applied.json`（git 管理外。再生成で再現）に記録される。
ソニーFG は旧関係（100% 子会社）を `historical`（2025-10-01 まで）にし、持分 16.40% の関連会社を追加した。

## 隔離（quarantine）

{q['count']:,} 行を関係にせず `quarantine.json` に記録: {q_line}。

## 旧データとの対応

旧 relation_id → 新 relation_id の対応表: `relation_id_map.json`（{diff['old_ids_mapped']:,} 件対応、{diff['old_ids_unmatched']:,} 件対応なし）。
対応なしの主な内訳:

| 旧タイプ | 出所 | 件数 |
| --- | --- | --- |
{rows_un}

旧 parent_subsidiary の対応なしは、旧パーサーが分類不明を子会社にしていたもので、新データでは
関連会社（affiliate 160 → 4,5xx）・株式保有・要確認・方向反転へ移った分と、複数期の重複がまとまった分を含む。

| タイプ | 旧 | 新（確定） |
| --- | --- | --- |
{rows_bt}

IR 由来の提携・合弁・M&A は根拠判定（#6）で要確認へ回った分が減っている（確定から外れただけで削除はしていない）。

## 層化無作為サンプルの監査

{sv['method']}

結果（{sv['total']} 件）: {json.dumps(sv['by_verdict'], ensure_ascii=False)}

出所別: {json.dumps(sv['by_source'], ensure_ascii=False)}

{sv['caveat']}

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
{sample_rows}

## 公開データのサイズ

| ファイル | 展開後 | gzip |
| --- | --- | --- |
| M4_companies.json | 1.8 MB | 0.3 MB |
| M5_company_relations.json | 38.2 MB | 2.0 MB |
| evidence/（84 シャード、必要時のみ取得） | 48.3 MB | — |
"""
(d / "REPORT.md").write_text(md, encoding="utf-8")
print("written", d / "REPORT.md")
