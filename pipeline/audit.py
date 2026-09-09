"""公開データの監査（Issue #3）。

  python audit.py [--public DIR] [--old OLD_M5.json --old-m4 OLD_M4.json] [--out DIR] [--sample N --seed S]

チェック項目:
  - 数値・記号だけの企業（entity）名と、それに接続する関係（確定データで 0 件であること）
  - 参照整合性・ID 重複・evidence の有無
  - 相互に親会社となる候補ペア（一括反転・削除はせず、根拠の出所と理由を列挙する）
  - 比率付き親子関係のうち 50% 以下のもの（削除はしない。分類・出所の内訳を出す）
  - 既知の訂正ケース（OLC/京成、ZOZO/SBG、M3/ソニー、イオン北海道、ライフ/三菱商事、ソニーFG）の現状
  - 旧公開データとの対応（旧 relation_id → 新 relation_id）と差分の集計
  - 層化無作為サンプル（出所 × カテゴリ）の抽出。人手監査用に原本参照情報を付ける
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from aliases import match_key  # noqa: E402
from config import PUBLIC_DIR  # noqa: E402

NUMERIC_RE = re.compile(r"^[\s0-9０-９.,．、()（）%％△▲\-−―－ー・/\[\]［］]*$")

KNOWN_CASES = [
    # (説明, source, target, relation_type, 期待 status または None=存在しないこと)
    ("京成→OLC 関連会社（その他の関係会社）", "listed:9009", "listed:4661", "affiliate", "confirmed"),
    ("OLC→京成 親子（旧 R0044475 の逆転）", "listed:4661", "listed:9009", "parent_subsidiary", None),
    ("京成→OLC 親子（Wikidata P749）", "listed:9009", "listed:4661", "parent_subsidiary", "needs_review"),
    ("SBG→ZOZO 親子", "listed:9984", "listed:3092", "parent_subsidiary", "confirmed"),
    ("ZOZO→SBG 親子（旧 R0003946 の逆転）", "listed:3092", "listed:9984", "parent_subsidiary", None),
    ("ソニー→M3 関連会社", "listed:6758", "listed:2413", "affiliate", "confirmed"),
    ("M3→ソニー 親子（逆転）", "listed:2413", "listed:6758", "parent_subsidiary", None),
    ("イオン→イオン北海道 親子", "listed:8267", "listed:7512", "parent_subsidiary", "confirmed"),
    ("三菱商事→ライフ 関連会社", "listed:8058", "listed:8194", "affiliate", "confirmed"),
    ("三菱商事→ライフ 親子（旧 100%）", "listed:8058", "listed:8194", "parent_subsidiary", None),
    ("ライフ→三菱商事 親子（逆転）", "listed:8194", "listed:8058", "parent_subsidiary", None),
    ("日本車輌→JR東海 技術提携（根拠不足）", "listed:7102", "listed:9022", "technology_license", "needs_review"),
    ("アイシン→東邦瓦斯 共同研究（名寄せ）", "listed:7259", "listed:9533", "joint_research", "confirmed"),
]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def node_label(m4: dict, m5: dict, ref: dict) -> str:
    if ref["type"] == "listed":
        return m4["companies"].get(ref["key"], {}).get("name", ref["key"])
    return m5["entities"].get(ref["key"], {}).get("name", ref["key"])


def key_of(ref: dict, m4: dict, m5: dict) -> str:
    """旧新の対応に使う安定キー: 上場は listed:code、entity は正規化名。"""
    if ref["type"] == "listed":
        return f"listed:{ref['key']}"
    return "entity:" + match_key(m5["entities"].get(ref["key"], {}).get("name", ref["key"]))


def audit(m4: dict, m5: dict, old_m4: dict | None, old_m5: dict | None, sample_n: int, seed: int) -> dict:
    rels = m5["relations"]
    ents = m5["entities"]
    companies = m4["companies"]
    report: dict = {"generated_at": m5.get("generated_at"), "counts": {}}

    # --- 基本
    status_counts = collections.Counter(r.get("status", "confirmed") for r in rels)
    report["counts"] = {"relations": len(rels), "entities": len(ents), "companies": len(companies),
                        "by_status": dict(status_counts)}

    # --- 数値ノード
    numeric = {k: v["name"] for k, v in ents.items() if NUMERIC_RE.match(unicodedata.normalize("NFKC", v.get("name") or ""))}
    touching = [r["relation_id"] for r in rels if any(x["type"] == "entity" and x["key"] in numeric for x in (r["source"], r["target"]))]
    report["numeric_entities"] = {"count": len(numeric), "examples": dict(list(numeric.items())[:10]),
                                  "relations_touching": len(touching)}

    # --- 参照整合性
    ids = collections.Counter(r["relation_id"] for r in rels)
    broken = [r["relation_id"] for r in rels if any(
        (x["type"] == "listed" and x["key"] not in companies) or (x["type"] == "entity" and x["key"] not in ents)
        for x in (r["source"], r["target"]))]
    no_ev = [r["relation_id"] for r in rels if not r.get("evidence")]
    report["integrity"] = {"duplicate_ids": [k for k, c in ids.items() if c > 1], "broken_refs": len(broken),
                           "without_evidence": len(no_ev)}

    # --- 相互親会社ペア
    parents = {}
    for r in rels:
        if r["relation_type"] == "parent_subsidiary" and r.get("status", "confirmed") == "confirmed":
            parents[(r["source"]["type"], r["source"]["key"], r["target"]["type"], r["target"]["key"])] = r
    mutual = []
    seen = set()
    for (st, sk, tt, tk), r in parents.items():
        rev = parents.get((tt, tk, st, sk))
        if rev and (tt, tk, st, sk) not in seen:
            seen.add((st, sk, tt, tk))
            mutual.append({
                "a": r["relation_id"], "b": rev["relation_id"],
                "pair": f"{node_label(m4, m5, r['source'])} <-> {node_label(m4, m5, r['target'])}",
                "listed_both": st == "listed" and tt == "listed",
                "a_sources": sorted({e["source"] for e in r["evidence"]}),
                "b_sources": sorted({e["source"] for e in rev["evidence"]}),
                "a_as_of": max((e.get("as_of") or "" for e in r["evidence"]), default=None) or None,
                "b_as_of": max((e.get("as_of") or "" for e in rev["evidence"]), default=None) or None,
                "note": "両方向が別々の出所・時点に由来する可能性。原本で確認するまで反転・削除しない",
            })
    report["mutual_parent_pairs"] = {"count": len(mutual), "listed_both": sum(1 for m in mutual if m["listed_both"]),
                                     "pairs": mutual}

    # --- 50% 以下の親子関係
    low = []
    by_kind = collections.Counter()
    for r in rels:
        if r["relation_type"] != "parent_subsidiary" or r.get("status", "confirmed") != "confirmed":
            continue
        v = r.get("attributes", {}).get("ownership_ratio")
        if v is not None and v <= 0.5:
            cls = next((e.get("classification") for e in r["evidence"] if e.get("classification")), None)
            srcs = tuple(sorted({e["source"] for e in r["evidence"]}))
            by_kind[(cls or "(分類なし)", srcs)] += 1
            low.append(r["relation_id"])
    with_ratio = sum(1 for r in rels if r["relation_type"] == "parent_subsidiary" and r.get("status", "confirmed") == "confirmed"
                     and r.get("attributes", {}).get("ownership_ratio") is not None)
    report["parent_ratio_le_50"] = {
        "count": len(low), "of_with_ratio": with_ratio,
        "by_classification_and_source": [{"classification": k[0], "sources": list(k[1]), "count": c} for k, c in by_kind.most_common()],
        "note": "有報が連結子会社と記載していれば実質支配の可能性があるため、50%以下という理由だけでは削除しない",
    }

    # --- 既知ケース
    idx = {}
    for r in rels:
        idx.setdefault((f"{r['source']['type']}:{r['source']['key']}", f"{r['target']['type']}:{r['target']['key']}", r["relation_type"]), []).append(r)
    known = []
    for desc, s, t, typ, expected in KNOWN_CASES:
        found = idx.get((s, t, typ), [])
        statuses = [f["status"] for f in found]
        ok = (not found) if expected is None else (bool(found) and all(st == expected for st in statuses))
        known.append({"case": desc, "expected": expected or "absent", "found": [
            {"id": f["relation_id"], "status": f["status"], "ratio": f.get("attributes", {}).get("ownership_ratio"),
             "verified": f.get("verification", {}).get("status") if f.get("verification") else None} for f in found], "ok": ok})
    report["known_cases"] = known

    # --- 旧データとの対応
    if old_m5 and old_m4:
        new_by_key = {}
        for r in rels:
            new_by_key.setdefault((key_of(r["source"], m4, m5), key_of(r["target"], m4, m5), r["relation_type"]), []).append(r["relation_id"])
        mapping = {}
        unmatched = collections.Counter()
        for r in old_m5["relations"]:
            k = (key_of(r["source"], old_m4, old_m5), key_of(r["target"], old_m4, old_m5), r["relation_type"])
            new_ids = new_by_key.get(k)
            if new_ids:
                mapping[r["relation_id"]] = new_ids[0]
            else:
                unmatched[(r["relation_type"], tuple(sorted({e["source"] for e in r["evidence"]})))] += 1
        old_types = collections.Counter(r["relation_type"] for r in old_m5["relations"])
        new_types = collections.Counter(r["relation_type"] for r in rels if r.get("status", "confirmed") == "confirmed")
        report["diff_vs_old"] = {
            "old_relations": len(old_m5["relations"]), "new_relations": len(rels),
            "new_confirmed": status_counts.get("confirmed", 0),
            "old_ids_mapped": len(mapping), "old_ids_unmatched": len(old_m5["relations"]) - len(mapping),
            "unmatched_by_type_and_source": [{"type": k[0], "sources": list(k[1]), "count": c} for k, c in unmatched.most_common(20)],
            "by_type": {t: {"old": old_types.get(t, 0), "new_confirmed": new_types.get(t, 0)} for t in sorted(set(old_types) | set(new_types))},
            "old_entities": len(old_m5["entities"]), "new_entities": len(ents),
        }
        report["_id_map"] = mapping

    # --- 層化無作為サンプル
    rng = random.Random(seed)
    strata: dict[tuple, list] = {}
    for r in rels:
        if r.get("status", "confirmed") != "confirmed":
            continue
        src = sorted({e["source"] for e in r["evidence"]})[0]
        strata.setdefault((src, r["category"]), []).append(r)
    sample = []
    per = max(1, sample_n // max(1, len(strata)))
    for (src, cat), items in sorted(strata.items()):
        for r in rng.sample(items, min(per, len(items))):
            sample.append({
                "relation_id": r["relation_id"], "stratum": f"{src}/{cat}",
                "source": node_label(m4, m5, r["source"]), "target": node_label(m4, m5, r["target"]),
                "relation_type": r["relation_type"], "ratio": r.get("attributes", {}).get("ownership_ratio"),
                "evidence": [{k: e.get(k) for k in ("source", "as_of")} for e in r["evidence"]],
                "verdict": None, "note": None,
            })
    report["stratified_sample"] = {"seed": seed, "strata": len(strata), "per_stratum": per, "items": sample}
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--public", default=str(PUBLIC_DIR))
    ap.add_argument("--old")
    ap.add_argument("--old-m4")
    ap.add_argument("--out", default=None)
    ap.add_argument("--sample", type=int, default=60)
    ap.add_argument("--seed", type=int, default=20260909)
    args = ap.parse_args()
    pub = Path(args.public)
    m4 = load(pub / "M4_companies.json")
    m5 = load(pub / "M5_company_relations.json")
    old_m5 = load(Path(args.old)) if args.old else None
    old_m4 = load(Path(args.old_m4)) if args.old_m4 else None
    report = audit(m4, m5, old_m4, old_m5, args.sample, args.seed)
    id_map = report.pop("_id_map", None)
    out = Path(args.out) if args.out else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
        (out / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        if id_map is not None:
            (out / "relation_id_map.json").write_text(json.dumps(id_map, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        (out / "sample.json").write_text(json.dumps(report["stratified_sample"], ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("stratified_sample", "mutual_parent_pairs")}, ensure_ascii=False, indent=1))
    print("mutual_parent_pairs:", report["mutual_parent_pairs"]["count"], "listed_both:", report["mutual_parent_pairs"]["listed_both"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
