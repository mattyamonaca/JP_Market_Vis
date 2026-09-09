"""JPX 東証上場銘柄一覧 (data_j.xls) を取得し JSON 化する。

出力: data_raw/jpx_listed.json
  [{"securities_code": "7203", "name": "トヨタ自動車", "market_segment": "prime",
    "industry_33": "輸送用機器", "industry_17": "自動車・輸送機", "scale_category": "TOPIX Core30"}, ...]

内国株式（プライム/スタンダード/グロース）のみ抽出。ETF・REIT・外国株は除外。
"""
from __future__ import annotations

import json
import sys

import requests
import xlrd

from config import DATA_RAW, JPX_LIST_URL, MARKET_SEGMENT_MAP


def fetch_jpx_workbook() -> xlrd.book.Book:
    print(f"Fetching {JPX_LIST_URL}")
    resp = requests.get(JPX_LIST_URL, timeout=60)
    resp.raise_for_status()
    return xlrd.open_workbook(file_contents=resp.content)


def parse(book: xlrd.book.Book) -> list[dict]:
    sheet = book.sheet_by_index(0)
    header = [str(c.value).strip() for c in sheet.row(0)]
    col = {name: i for i, name in enumerate(header)}

    required = ["コード", "銘柄名", "市場・商品区分", "33業種区分", "17業種区分", "規模区分"]
    missing = [c for c in required if c not in col]
    if missing:
        raise RuntimeError(f"JPX一覧のヘッダーが想定と異なります。missing={missing} header={header}")

    records = []
    for r in range(1, sheet.nrows):
        row = sheet.row(r)
        segment_raw = str(row[col["市場・商品区分"]].value).strip()
        segment = MARKET_SEGMENT_MAP.get(segment_raw)
        if segment is None:
            continue  # ETF/ETN/REIT/外国株/出資証券等は対象外

        code_val = row[col["コード"]].value
        code = str(int(code_val)) if isinstance(code_val, float) else str(code_val).strip()

        def cell(name: str) -> str | None:
            v = str(row[col[name]].value).strip()
            return v if v and v != "-" else None

        records.append({
            "securities_code": code,
            "name": cell("銘柄名"),
            "market_segment": segment,
            "industry_33": cell("33業種区分"),
            "industry_17": cell("17業種区分"),
            "scale_category": cell("規模区分"),
        })
    return records


def main() -> int:
    DATA_RAW.mkdir(exist_ok=True)
    book = fetch_jpx_workbook()
    records = parse(book)
    if len(records) < 3000:
        print(f"WARNING: 内国株式が {len(records)} 件しか取れていません（通常約3,900件）", file=sys.stderr)

    out = DATA_RAW / "jpx_listed.json"
    out.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    seg_counts: dict[str, int] = {}
    for rec in records:
        seg_counts[rec["market_segment"]] = seg_counts.get(rec["market_segment"], 0) + 1
    print(f"OK: {len(records)} 銘柄 -> {out} (segments: {seg_counts})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
