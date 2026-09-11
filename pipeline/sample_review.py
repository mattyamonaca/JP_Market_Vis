"""層化無作為サンプル（audit.py の sample.json）を人手で監査するための補助（Issue #3）。

各サンプル関係について、抽出元の原文（EDINET はキャッシュした表の該当行と前後、IR は根拠文と URL、
Wikidata は QID）を並べて表示する。監査者は verdict（correct / wrong_direction / wrong_type /
wrong_ratio / not_a_company / unverifiable）と note を sample.json に記入する。

  python sample_review.py <sample.json> [--public DIR] [--only R0000123]
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import edinet_tables as et  # noqa: E402
from config import EDINET_CACHE, PUBLIC_DIR  # noqa: E402


def load_shard(pub: Path, relation_id: str, size: int) -> dict:
    shard = f"{int(relation_id[1:]) // size:04d}"
    return json.loads((pub / "evidence" / f"{shard}.json").read_text(encoding="utf-8")).get(relation_id, {})


def show_edinet_row(ev: dict) -> None:
    doc = ev.get("doc_id")
    p = EDINET_CACHE / f"{doc}.json.gz"
    if not doc or not p.exists():
        print("    （キャッシュなし）")
        return
    payload = json.load(gzip.open(p, "rt", encoding="utf-8"))
    kind = {"affiliated": "affiliated", "shareholder": "shareholder", "large_holding_report": "shareholder",
            "customer": "customer"}.get(ev.get("property"), "affiliated")
    raw = payload["blocks"].get(kind, "")
    tables = et.parse_block(raw)
    target = (ev.get("raw_name") or "").replace("\n", " ")
    for ti, t in enumerate(tables):
        for r, row in enumerate(t.rows):
            cell = row[0].text.replace("\n", " ") if row else ""
            if target and target[:12] in cell:
                ctx = t.context.strip().replace("\n", " ")[-80:]
                print(f"    表{ti} 直前の本文: …{ctx}")
                print(f"    見出し: {[c.text.replace(chr(10), '/')[:14] for c in t.rows[0]][:7]}")
                for rr in range(max(0, r - 1), min(len(t.rows), r + 2)):
                    mark = ">>" if rr == r else "  "
                    print(f"    {mark} {[c.text.replace(chr(10), '/')[:18] for c in t.rows[rr]][:7]}")
                return
    print(f"    （該当行が見つからない: {target!r}）")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sample")
    ap.add_argument("--public", default=str(PUBLIC_DIR))
    ap.add_argument("--only")
    args = ap.parse_args()
    pub = Path(args.public)
    m5 = json.loads((pub / "M5_company_relations.json").read_text(encoding="utf-8"))
    size = (m5.get("evidence_shards") or {}).get("size", 1000)
    sample = json.loads(Path(args.sample).read_text(encoding="utf-8"))
    for item in sample["items"]:
        rid = item["relation_id"]
        if args.only and rid != args.only:
            continue
        print(f"=== {rid} [{item['stratum']}] {item['source']} -> {item['target']} ({item['relation_type']}) ratio={item['ratio']}")
        detail = load_shard(pub, rid, size)
        for ev in detail.get("evidence", []):
            print(f"  - {ev.get('source')} {ev.get('property') or ''} doc={ev.get('doc_id') or ''} as_of={ev.get('as_of')} cls={ev.get('classification') or ''}"
                  f" dir={ev.get('direction_source') or ''} url={ev.get('url') or ''}")
            if ev.get("quote"):
                print(f"    根拠文: {ev['quote'][:200]}")
            if ev.get("source") == "edinet":
                show_edinet_row(ev)
        print(f"  verdict={item.get('verdict')} note={item.get('note')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
