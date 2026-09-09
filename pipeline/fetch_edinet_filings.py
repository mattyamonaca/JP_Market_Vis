"""EDINET API v2 から有価証券報告書を取得し、関係抽出に使う生テキストブロックをキャッシュする。

旧 `4_fetch_edinet_filings.py` は取得と同時に表を解析して行だけを保存していたため、
解析ロジックを直しても再取得なしに再解析できなかった。本スクリプトは
書類ごとの生 HTML ブロックを `data_raw/edinet_blocks/<docID>.json.gz` に保存し、
解析は `parse_edinet_filings.py` が担当する（再解析はオフラインで可能）。

使い方:
  python fetch_edinet_filings.py list  [--from 2025-06-14 --to 2026-06-13]
      → 期間内の有価証券報告書（docTypeCode=120、証券コードあり）の一覧を
        data_raw/edinet_docs.json に保存（書類ID → メタデータ）
  python fetch_edinet_filings.py fetch [--limit N] [--doc S100XXXX ...]
      → edinet_docs.json の各書類を取得し、生ブロックをキャッシュ（取得済みはスキップ）

EDINET_API_KEY は環境変数または ~/.persona/.env から読む。
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import io
import json
import re
import sys
import time
import zipfile

import requests

from config import DATA_RAW, EDINET_API_BASE, EDINET_CACHE, edinet_api_key

DOCS_PATH = DATA_RAW / "edinet_docs.json"
REQUEST_WAIT_SEC = 0.35

# XBRL 要素のローカル名 → 抽出種別
BLOCK_KIND = {
    "OverviewOfAffiliatedEntitiesTextBlock": "affiliated",
    "MajorShareholdersTextBlock": "shareholder",
    "InformationForEachOfMainCustomersTextBlock": "customer",
}
DEI_ELEMENTS = {
    "EDINETCodeDEI": "edinet_code",
    "SecurityCodeDEI": "security_code",
    "FilerNameInJapaneseDEI": "filer_name",
    "CurrentPeriodEndDateDEI": "period_end",
    "CurrentFiscalYearStartDateDEI": "period_start",
    "DocumentTypeDEI": "document_type",
}


def doc_metadata(doc: dict) -> dict:
    return {
        "doc_id": doc["docID"],
        "sec_code": str(doc.get("secCode") or "")[:4] or None,
        "edinet_code": doc.get("edinetCode"),
        "filer_name": doc.get("filerName"),
        "doc_type_code": doc.get("docTypeCode"),
        "doc_description": doc.get("docDescription"),
        "period_start": doc.get("periodStart"),
        "period_end": doc.get("periodEnd"),
        "submit_datetime": doc.get("submitDateTime"),
        "ordinance_code": doc.get("ordinanceCode"),
        "form_code": doc.get("formCode"),
    }


def list_filings(session: requests.Session, key: str, date: dt.date) -> list[dict]:
    resp = session.get(
        f"{EDINET_API_BASE}/documents.json",
        params={"date": date.isoformat(), "type": 2, "Subscription-Key": key},
        timeout=60,
    )
    resp.raise_for_status()
    docs = resp.json().get("results", []) or []
    return [d for d in docs if d.get("docTypeCode") == "120" and d.get("secCode")]


def fetch_blocks(session: requests.Session, key: str, doc_id: str) -> dict:
    resp = session.get(
        f"{EDINET_API_BASE}/documents/{doc_id}",
        params={"type": 1, "Subscription-Key": key},
        timeout=180,
    )
    resp.raise_for_status()
    blocks: dict[str, str] = {}
    dei: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = [n for n in zf.namelist() if "PublicDoc" in n and n.endswith(".xbrl")]
        for name in names:
            text = zf.read(name).decode("utf-8", errors="replace")
            for local, kind in BLOCK_KIND.items():
                if kind in blocks:
                    continue
                m = re.search(rf"<([\w-]+:{local})\b[^>]*>(.*?)</\1>", text, re.S)
                if m:
                    blocks[kind] = m.group(2)
            for local, field in DEI_ELEMENTS.items():
                if field in dei:
                    continue
                m = re.search(rf"<jpdei_cor:{local}\b[^>]*>(.*?)</jpdei_cor:{local}>", text, re.S)
                if m:
                    dei[field] = m.group(1).strip()
    return {"blocks": blocks, "dei": dei}


def cmd_list(args: argparse.Namespace, key: str) -> int:
    session = requests.Session()
    docs = json.loads(DOCS_PATH.read_text(encoding="utf-8")) if DOCS_PATH.exists() else {}
    start = dt.date.fromisoformat(args.date_from)
    end = dt.date.fromisoformat(args.date_to)
    day = start
    n_new = 0
    while day <= end:
        try:
            filings = list_filings(session, key, day)
        except requests.RequestException as e:
            print(f"WARN: {day} 一覧取得失敗: {e}", file=sys.stderr)
            time.sleep(5)
            continue
        for doc in filings:
            meta = doc_metadata(doc)
            meta["list_date"] = day.isoformat()
            if meta["doc_id"] not in docs:
                n_new += 1
            docs[meta["doc_id"]] = meta
        if filings:
            print(f"... {day}: {len(filings)}件")
        day += dt.timedelta(days=1)
        time.sleep(REQUEST_WAIT_SEC)
    DATA_RAW.mkdir(exist_ok=True)
    DOCS_PATH.write_text(json.dumps(docs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK: 有報 {len(docs)} 件（新規 {n_new}）-> {DOCS_PATH}")
    return 0


def cmd_fetch(args: argparse.Namespace, key: str) -> int:
    docs = json.loads(DOCS_PATH.read_text(encoding="utf-8")) if DOCS_PATH.exists() else {}
    targets = args.doc or sorted(docs)
    EDINET_CACHE.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    n_done = n_skip = n_fail = 0
    for i, doc_id in enumerate(targets):
        out = EDINET_CACHE / f"{doc_id}.json.gz"
        if out.exists() and not args.force:
            n_skip += 1
            continue
        if args.limit and n_done >= args.limit:
            break
        try:
            got = fetch_blocks(session, key, doc_id)
        except (requests.RequestException, zipfile.BadZipFile) as e:
            print(f"WARN: {doc_id} 取得失敗: {e}", file=sys.stderr)
            n_fail += 1
            time.sleep(3)
            continue
        payload = {
            "doc": docs.get(doc_id, {"doc_id": doc_id}),
            "dei": got["dei"],
            "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "blocks": got["blocks"],
        }
        with gzip.open(out, "wt", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        n_done += 1
        if n_done % 50 == 0:
            print(f"... {n_done} 取得 / {n_skip} 既存 / {n_fail} 失敗 ({i + 1}/{len(targets)})", flush=True)
        time.sleep(REQUEST_WAIT_SEC)
    print(f"OK: 取得 {n_done} / 既存 {n_skip} / 失敗 {n_fail} -> {EDINET_CACHE}")
    return 0 if n_fail == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_list = sub.add_parser("list")
    today = dt.date.today()
    p_list.add_argument("--from", dest="date_from", default=(today - dt.timedelta(days=365)).isoformat())
    p_list.add_argument("--to", dest="date_to", default=today.isoformat())
    p_fetch = sub.add_parser("fetch")
    p_fetch.add_argument("--limit", type=int, default=0)
    p_fetch.add_argument("--force", action="store_true")
    p_fetch.add_argument("--doc", nargs="*")
    args = parser.parse_args()

    key = edinet_api_key()
    if not key:
        print("EDINET_API_KEY 未設定。https://api.edinet-fsa.go.jp/ で取得し環境変数か ~/.persona/.env に設定してください。",
              file=sys.stderr)
        return 2
    return cmd_list(args, key) if args.cmd == "list" else cmd_fetch(args, key)


if __name__ == "__main__":
    sys.exit(main())
