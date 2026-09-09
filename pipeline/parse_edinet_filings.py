"""キャッシュ済みの有報ブロック（data_raw/edinet_blocks/*.json.gz）を解析し、
構造化した関係行を data_raw/edinet_relations.json（と .json.gz）に出力する。

解析ロジックは edinet_tables.py（回帰テスト: tests/test_edinet_tables.py）。
ネットワークアクセスは行わない。旧 4_fetch_edinet_filings.py の「取得と解析の同時実行」を分離した。

出力行の共通項目:
  filer_sec_code, doc_id, period_end, submit_date, kind(affiliated/shareholder/customer), filer_name
種別ごとの項目は edinet_tables の各 extract_* を参照。

使い方: python parse_edinet_filings.py [--limit N]
"""
from __future__ import annotations

import argparse
import collections
import gzip
import json
import sys

import edinet_tables as et
from config import DATA_RAW, EDINET_CACHE

OUT_PATH = DATA_RAW / "edinet_relations.json"
OUT_GZ = DATA_RAW / "edinet_relations.json.gz"


def parse_doc(payload: dict) -> list[dict]:
    doc = payload.get("doc", {})
    dei = payload.get("dei", {})
    sec = (doc.get("sec_code") or dei.get("security_code") or "")[:4] or None
    base = {
        "filer_sec_code": sec,
        "filer_name": doc.get("filer_name") or dei.get("filer_name"),
        "doc_id": doc.get("doc_id"),
        "period_end": doc.get("period_end") or dei.get("period_end"),
        "submit_date": (doc.get("submit_datetime") or "")[:10] or None,
    }
    out: list[dict] = []
    blocks = payload.get("blocks", {})
    for kind, raw in blocks.items():
        tables = et.parse_block(raw)
        if kind == "affiliated":
            rows = et.extract_affiliated(tables, et.block_text(raw))
        elif kind == "shareholder":
            rows = et.extract_shareholders(tables, et.block_text(raw))
        elif kind == "customer":
            rows = et.extract_customers(tables)
        else:
            continue
        for row in rows:
            out.append({**base, "kind": kind, **row})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    files = sorted(EDINET_CACHE.glob("*.json.gz"))
    if args.limit:
        files = files[: args.limit]
    if not files:
        print(f"ERROR: {EDINET_CACHE} にキャッシュがありません。fetch_edinet_filings.py fetch を先に実行してください。",
              file=sys.stderr)
        return 2
    records: list[dict] = []
    stats = collections.Counter()
    for i, f in enumerate(files, start=1):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            payload = json.load(fh)
        rows = parse_doc(payload)
        records.extend(rows)
        stats["docs"] += 1
        for r in rows:
            stats[r["kind"]] += 1
            if r["kind"] == "affiliated":
                stats["affiliated:" + (r["classification"] or "不明")] += 1
                if r.get("owned_by_counterparty"):
                    stats["affiliated:被所有"] += 1
            if r.get("name_problem"):
                stats["name_problem:" + r["name_problem"]] += 1
        if i % 500 == 0:
            print(f"... {i}/{len(files)} 書類 / {len(records)} 行", flush=True)
    DATA_RAW.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=0), encoding="utf-8")
    with gzip.open(OUT_GZ, "wt", encoding="utf-8") as fh:
        json.dump(records, fh, ensure_ascii=False)
    print(f"OK: {stats['docs']}書類から {len(records)}行 -> {OUT_PATH}")
    for k in sorted(stats):
        if k != "docs":
            print(f"   {k}: {stats[k]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
