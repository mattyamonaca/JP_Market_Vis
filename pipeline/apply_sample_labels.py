"""sample_labels.json（名称の部分一致で書いた人手判定）を sample.json に適用し、集計を付ける。"""
import collections, json, sys, unicodedata
from pathlib import Path
d = Path(sys.argv[1])
s = json.loads((d / "sample.json").read_text(encoding="utf-8"))
labels = json.loads((d / "sample_labels.json").read_text(encoding="utf-8"))
n = lambda x: unicodedata.normalize("NFKC", x)
for it in s["items"]:
    it["verdict"] = it["note"] = None
    for lb in labels:
        if lb["source_contains"] in n(it["source"]) and lb["target_contains"] in n(it["target"]):
            it["verdict"], it["note"] = lb["verdict"], lb["note"]
            break
un = [it["relation_id"] + " " + it["source"] + " -> " + it["target"] for it in s["items"] if not it["verdict"]]
c = collections.Counter(it["verdict"] for it in s["items"])
bys = collections.defaultdict(collections.Counter)
for it in s["items"]:
    bys[it["stratum"].split("/")[0]][it["verdict"]] += 1
s["summary"] = {
    "total": len(s["items"]), "by_verdict": dict(c), "by_source": {k: dict(v) for k, v in bys.items()},
    "method": "出所×カテゴリで層化した無作為抽出（seed 20260909、各層最大6件、確定関係のみ）。EDINET は取得済み原本表の該当行、IR は根拠文と公表URL、Wikidata は項目を参照して人手で判定。correct_stale は抽出は正しいが時点が古い／不明。",
    "caveat": "層ごとの件数が小さく、全体の正解率の点推定は参考値。監査中に見つけた誤りの型（第三者の出来事、合併の方向、自社子会社の主体、第三者割当の引受側）は検証器に反映済みで、該当関係は再生成後に要確認へ移っている。",
}
(d / "sample.json").write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(s["summary"]["by_verdict"], ensure_ascii=False), json.dumps(s["summary"]["by_source"], ensure_ascii=False))
print("unlabeled:", un)
