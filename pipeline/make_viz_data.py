"""フル版 M4/M5（data_processed/masters）から公開アプリ用の public/M4_companies.json /
public/M5_company_relations.json を生成する。

旧 make_viz_data.py は evidence を先頭 2 件・引用 80 文字に切り詰め、date/retrieved を落としていた。
本版は判断材料になる項目（基準日・提出日・取得日・原本URL・書類ID・抽出根拠・検証状態）を保持し、
表示に使わない内部項目（table_ref 等）だけを落とす（Issue #5）。
比率は互換のため数値 `ownership_ratio` / `sales_ratio` も残し、意味付きの構造は `ownership` / `sales` に入れる。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from config import MASTERS_DIR, PUBLIC_DIR

EVIDENCE_KEYS = (
    "source", "source_tier", "confidence", "property", "doc_id", "url", "as_of", "published", "retrieved",
    "classification", "classification_source", "direction_source", "relationship_note", "quote", "raw_name",
    "person", "verification", "note",
)


def trim_evidence(ev: dict) -> dict:
    out = {}
    for k in EVIDENCE_KEYS:
        v = ev.get(k)
        if v not in (None, "", []):
            out[k] = v
    return out


def slim_ratio(attr: dict | None) -> dict | None:
    if not attr:
        return None
    out = {k: attr[k] for k in ("value", "kind", "scope", "indirect", "raw", "as_of", "doc_id", "status", "note")
           if attr.get(k) is not None}
    hist = [{k: h[k] for k in ("value", "kind", "scope", "indirect", "raw", "as_of", "doc_id", "status", "note")
             if h.get(k) is not None} for h in attr.get("history", [])]
    if hist:
        out["history"] = hist
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(PUBLIC_DIR), help="出力先（既定: public/）。検証用に別ディレクトリへ出せる")
    args = ap.parse_args()
    out_dir = Path(args.out)
    m4 = json.loads((MASTERS_DIR / "M4_companies.json").read_text(encoding="utf-8"))
    m5 = json.loads((MASTERS_DIR / "M5_company_relations.json").read_text(encoding="utf-8"))

    slim_rels = []
    for r in m5["relations"]:
        raw_attrs = r.get("attributes") or {}
        attrs: dict = {}
        own = raw_attrs.get("ownership_ratio")
        if isinstance(own, dict):
            if own.get("value") is not None:
                attrs["ownership_ratio"] = own["value"]
            attrs["ownership"] = slim_ratio(own)
        elif own is not None:
            attrs["ownership_ratio"] = own
        sales = raw_attrs.get("sales_ratio")
        if isinstance(sales, dict):
            attrs["sales_ratio"] = sales.get("value")
            attrs["sales"] = slim_ratio(sales)
        elif sales is not None:
            attrs["sales_ratio"] = sales
        if raw_attrs.get("sales_amount"):
            attrs["sales_amount"] = raw_attrs["sales_amount"]
        for k in ("person",):
            if raw_attrs.get(k) is not None:
                attrs[k] = raw_attrs[k]
        rel = {
            "relation_id": r["relation_id"],
            "source": r["source"],
            "target": r["target"],
            "relation_type": r["relation_type"],
            "category": r["category"],
            "directed": r["directed"],
            "status": r.get("status", "confirmed"),
            "attributes": attrs,
            "evidence": [trim_evidence(e) for e in r["evidence"]],
        }
        if r.get("review_reasons"):
            rel["review_reasons"] = r["review_reasons"]
        if r.get("verification"):
            rel["verification"] = r["verification"]
        slim_rels.append(rel)

    m5_slim = {
        "master_id": m5["master_id"],
        "version": m5["version"],
        "generated_at": m5.get("generated_at"),
        "status_values": m5.get("status_values"),
        "relation_types": m5["relation_types"],
        "entities": m5["entities"],
        "relations": slim_rels,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "M4_companies.json").write_text(
        json.dumps(m4, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out_dir / "M5_company_relations.json").write_text(
        json.dumps(m5_slim, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    def mb(name: str) -> str:
        return f"{(out_dir / name).stat().st_size / 1e6:.1f}MB"

    print(f"M4 -> {out_dir / 'M4_companies.json'} ({mb('M4_companies.json')})")
    print(f"M5 -> {out_dir / 'M5_company_relations.json'} ({mb('M5_company_relations.json')}) / {len(slim_rels)} エッジ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
