"""取得済み wikidata_relations.json に組織判定フラグ (object_is_org) を付与する。

3_fetch_wikidata.py の再実行なしで組織判定だけをやり直す用途。
WDQS のレート制限 (429) / 不安定 (5xx) に耐えるため:
  - 429: Retry-After を尊重（最低 60 秒待機）
  - 5xx/切断: 30 秒待機、失敗が続くバッチは二分割
  - バッチごとに data_processed/org_check_state.json へチェックポイント保存（再実行で再開）

使い方:
  python -u 3b_apply_org_flags.py
"""
from __future__ import annotations

import json
import sys
import time

import requests

from config import DATA_PROCESSED, DATA_RAW, WIKIDATA_SPARQL_URL, WIKIDATA_USER_AGENT

BATCH_SIZE = 100
STATE_PATH = DATA_PROCESSED / "org_check_state.json"
RELATIONS_PATH = DATA_RAW / "wikidata_relations.json"
MAX_ATTEMPTS = 6


def run_query(query: str) -> list[dict]:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = requests.post(
                WIKIDATA_SPARQL_URL,
                data={"query": query, "format": "json"},
                headers={"User-Agent": WIKIDATA_USER_AGENT,
                         "Accept": "application/sparql-results+json"},
                timeout=180,
            )
            if resp.status_code == 429:
                wait = max(int(resp.headers.get("Retry-After", "60")), 60)
                print(f"  429 rate-limited: {wait}s 待機 (attempt {attempt}/{MAX_ATTEMPTS})")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()["results"]["bindings"]
        except requests.RequestException as e:
            if attempt == MAX_ATTEMPTS:
                raise
            print(f"  {type(e).__name__}: 30s 待機 (attempt {attempt}/{MAX_ATTEMPTS})")
            time.sleep(30)
    raise RuntimeError("unreachable")


def check_batch(batch: list[str]) -> set[str]:
    values = " ".join(f"wd:{q}" for q in batch)
    query = f"SELECT ?o WHERE {{ VALUES ?o {{ {values} }} ?o wdt:P31/wdt:P279* wd:Q43229 . }}"
    try:
        rows = run_query(query)
        return {b["o"]["value"].rsplit("/", 1)[-1] for b in rows}
    except Exception as e:
        if len(batch) <= 20:
            raise
        mid = len(batch) // 2
        print(f"  batch({len(batch)}) failed ({type(e).__name__}), splitting", file=sys.stderr)
        time.sleep(15)
        return check_batch(batch[:mid]) | check_batch(batch[mid:])


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"checked": [], "org": []}


def save_state(state: dict) -> None:
    DATA_PROCESSED.mkdir(exist_ok=True)
    STATE_PATH.write_text(json.dumps(state), encoding="utf-8")


def main() -> int:
    relations = json.loads(RELATIONS_PATH.read_text(encoding="utf-8"))
    target = sorted({
        r["object_qid"] for r in relations
        if r["object_qid"] and r["property"] != "P463"
    })

    state = load_state()
    checked = set(state["checked"])
    org = set(state["org"])
    remaining = [q for q in target if q not in checked]
    print(f"対象 {len(target)} QID / 判定済 {len(checked)} / 残り {len(remaining)}")

    for i in range(0, len(remaining), BATCH_SIZE):
        batch = remaining[i:i + BATCH_SIZE]
        org |= check_batch(batch)
        checked.update(batch)
        save_state({"checked": sorted(checked), "org": sorted(org)})
        print(f"  ... {len(checked)}/{len(target)} (org: {len(org)})")
        time.sleep(3)

    for r in relations:
        r["object_is_org"] = (r["property"] == "P463") or (r["object_qid"] in org)
    n_non_org = sum(1 for r in relations if not r["object_is_org"])
    RELATIONS_PATH.write_text(json.dumps(relations, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK: object_is_org を付与（非組織 {n_non_org} 行）-> {RELATIONS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
