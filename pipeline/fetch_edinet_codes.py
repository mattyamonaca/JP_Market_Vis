"""EDINET コードリスト (Edinetcode.zip) を取得し、上場企業分を JSON 化する。

出力: data_raw/edinet_codes.json
  {"<証券コード4桁>": {"edinet_code": "E02144", "corporate_number": "1180301018771",
                       "name": "トヨタ自動車株式会社", "name_en": "TOYOTA MOTOR CORPORATION",
                       "address": "...", "industry_edinet": "輸送用機器"}}

CSV は cp932・1行目がダウンロード情報行・2行目がヘッダー。
証券コードは5桁（末尾0）で格納されているため先頭4桁に正規化する。
"""
from __future__ import annotations

import csv
import io
import json
import sys
import zipfile

import requests

from config import DATA_RAW, EDINET_CODELIST_URL


def fetch_csv_text() -> str:
    print(f"Fetching {EDINET_CODELIST_URL}")
    resp = requests.get(EDINET_CODELIST_URL, timeout=120)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        return zf.read(name).decode("cp932", errors="replace")


def parse(csv_text: str) -> dict[str, dict]:
    lines = csv_text.splitlines()
    # 1行目はダウンロード実行日等のメタ行のためスキップ
    reader = csv.DictReader(lines[1:])
    if reader.fieldnames is None or "ＥＤＩＮＥＴコード" not in reader.fieldnames:
        raise RuntimeError(f"EDINETコードリストのヘッダーが想定と異なります: {reader.fieldnames}")

    result: dict[str, dict] = {}
    for row in reader:
        sec5 = (row.get("証券コード") or "").strip()
        if not sec5:
            continue  # 非上場ファンド・非上場企業
        sec4 = sec5[:4]
        cn = (row.get("提出者法人番号") or "").strip() or None
        result[sec4] = {
            "edinet_code": (row.get("ＥＤＩＮＥＴコード") or "").strip() or None,
            "corporate_number": cn,
            "name": (row.get("提出者名") or "").strip() or None,
            "name_en": (row.get("提出者名（英字）") or "").strip() or None,
            "address": (row.get("所在地") or "").strip() or None,
            "industry_edinet": (row.get("提出者業種") or "").strip() or None,
        }
    return result


def main() -> int:
    DATA_RAW.mkdir(exist_ok=True)
    mapping = parse(fetch_csv_text())
    if len(mapping) < 3000:
        print(f"WARNING: 証券コード付きが {len(mapping)} 件のみ（通常4,000件前後）", file=sys.stderr)

    out = DATA_RAW / "edinet_codes.json"
    out.write_text(json.dumps(mapping, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK: {len(mapping)} 社 -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
