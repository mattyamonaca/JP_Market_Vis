"""Wikidata SPARQL から東証上場企業の QID マッピングと資本・グループ・人的関係を取得する。

出力:
  data_raw/wikidata_mapping.json   — 東証上場エンティティ一覧（QID/ティッカー/法人番号/名称）
  data_raw/wikidata_relations.json — 関係トリプル（P355/P749/P127/P1830/P463）
  data_raw/wikidata_personnel.json — 役員データ（CEO/会長/取締役等 → 役員兼任の導出に使用）

使い方:
  python -u 3_fetch_wikidata.py                  # 全件取得
  python -u 3_fetch_wikidata.py --personnel-only # 役員データのみ取得

使用プロパティ:
  P414+P249: 上場取引所・ティッカー（東証=Q217475 で限定）
  P3225: 日本の法人番号
  P355 子会社 / P749 親組織 / P127 所有者 / P1830 所有物
  P463 会員（対象を企業集団 Q197952・コングロマリット Q778575 に限定 → グループ所属）
  P31=Q489097: 合弁会社判定
  P31/P279*=Q43229: 相手先の組織判定（製品・規格等の非組織ノイズ除去。
    例: ソニーの P1830 には Super Audio CD 等の規格が含まれるため）
"""
from __future__ import annotations

import json
import sys
import time

import requests

from config import DATA_RAW, WD_TSE_QID, WIKIDATA_SPARQL_URL, WIKIDATA_USER_AGENT

MAPPING_QUERY = f"""
SELECT ?co ?coLabel ?ticker ?cn WHERE {{
  ?co p:P414 ?st . ?st ps:P414 wd:{WD_TSE_QID} .
  OPTIONAL {{ ?st pq:P249 ?ticker . }}
  OPTIONAL {{ ?co wdt:P3225 ?cn . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "ja,en". }}
}}
"""

RELATIONS_QUERY = f"""
SELECT ?co ?p ?o ?oLabel ?oCn ?oJv WHERE {{
  VALUES ?p {{ wdt:P355 wdt:P749 wdt:P127 wdt:P1830 }}
  ?co p:P414/ps:P414 wd:{WD_TSE_QID} .
  ?co ?p ?o .
  FILTER(isIRI(?o))
  OPTIONAL {{ ?o wdt:P3225 ?oCn . }}
  BIND(EXISTS {{ ?o wdt:P31 wd:Q489097 }} AS ?oJv)
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "ja,en". }}
}}
"""

# 役員データ: 同一人物が複数の上場企業の役員を務める場合に
# interlocking_director（役員兼任）エッジを導出する
PERSONNEL_QUERY = f"""
SELECT ?co ?prop ?person ?personLabel WHERE {{
  VALUES ?prop {{ wdt:P169 wdt:P488 wdt:P3320 wdt:P1037 wdt:P5052 }}
  ?co p:P414/ps:P414 wd:{WD_TSE_QID} .
  ?co ?prop ?person .
  ?person wdt:P31 wd:Q5 .
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "ja,en". }}
}}
"""

# グループ所属: P361(部分)は株価指数等のノイズが多いため、
# P463(会員) かつ相手が企業集団/コングロマリットの場合のみ採用
GROUP_QUERY = f"""
SELECT ?co ?o ?oLabel ?oCn WHERE {{
  VALUES ?cls {{ wd:Q197952 wd:Q778575 }}
  ?co p:P414/ps:P414 wd:{WD_TSE_QID} .
  ?co wdt:P463 ?o .
  ?o wdt:P31 ?cls .
  OPTIONAL {{ ?o wdt:P3225 ?oCn . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "ja,en". }}
}}
"""


def run_query(query: str, retries: int = 3) -> list[dict]:
    for attempt in range(1, retries + 1):
        try:
            # 長大な VALUES 句でも切り詰められないよう POST を使用
            resp = requests.post(
                WIKIDATA_SPARQL_URL,
                data={"query": query, "format": "json"},
                headers={"User-Agent": WIKIDATA_USER_AGENT,
                         "Accept": "application/sparql-results+json"},
                timeout=180,
            )
            resp.raise_for_status()
            return resp.json()["results"]["bindings"]
        except (requests.RequestException, KeyError, ValueError) as e:
            if attempt == retries:
                raise
            wait = 10 * attempt
            print(f"retry {attempt}/{retries} after {wait}s: {e}", file=sys.stderr)
            time.sleep(wait)
    return []


def _qid(binding: dict, var: str) -> str | None:
    v = binding.get(var, {}).get("value")
    return v.rsplit("/", 1)[-1] if v else None


def _val(binding: dict, var: str) -> str | None:
    return binding.get(var, {}).get("value") or None


def fetch_mapping() -> list[dict]:
    print("Querying Wikidata: TSE-listed entity mapping ...")
    rows = run_query(MAPPING_QUERY)
    seen: dict[str, dict] = {}
    for b in rows:
        qid = _qid(b, "co")
        if not qid:
            continue
        rec = seen.setdefault(qid, {"qid": qid, "label": _val(b, "coLabel"),
                                    "tickers": [], "corporate_number": None})
        ticker = _val(b, "ticker")
        if ticker and ticker not in rec["tickers"]:
            rec["tickers"].append(ticker)
        if not rec["corporate_number"]:
            rec["corporate_number"] = _val(b, "cn")
    return list(seen.values())


def fetch_relations() -> list[dict]:
    print("Querying Wikidata: capital relations ...")
    rows = run_query(RELATIONS_QUERY)
    relations = []
    for b in rows:
        prop = _qid(b, "p")  # 例: P355
        relations.append({
            "subject_qid": _qid(b, "co"),
            "property": prop,
            "object_qid": _qid(b, "o"),
            "object_label": _val(b, "oLabel"),
            "object_corporate_number": _val(b, "oCn"),
            "object_is_joint_venture": _val(b, "oJv") == "true",
        })

    time.sleep(2)
    print("Querying Wikidata: corporate group membership ...")
    for b in run_query(GROUP_QUERY):
        relations.append({
            "subject_qid": _qid(b, "co"),
            "property": "P463",
            "object_qid": _qid(b, "o"),
            "object_label": _val(b, "oLabel"),
            "object_corporate_number": _val(b, "oCn"),
            "object_is_joint_venture": False,
        })
    return relations


ORG_CHECK_BATCH = 150  # P279* パスが重いため WDQS の60秒制限内に収まるサイズ


def _org_check_batch(batch: list[str]) -> set[str]:
    """1バッチの組織判定。WDQS が不安定な場合はバッチを二分割して再試行する。"""
    values = " ".join(f"wd:{q}" for q in batch)
    query = f"SELECT ?o WHERE {{ VALUES ?o {{ {values} }} ?o wdt:P31/wdt:P279* wd:Q43229 . }}"
    try:
        rows = run_query(query)
        return {_qid({"o": b["o"]}, "o") for b in rows}
    except Exception as e:
        if len(batch) <= 20:
            raise
        mid = len(batch) // 2
        print(f"  batch({len(batch)}) failed ({type(e).__name__}), splitting -> {mid}+{len(batch) - mid}",
              file=sys.stderr)
        time.sleep(10)
        return _org_check_batch(batch[:mid]) | _org_check_batch(batch[mid:])


def fetch_org_flags(relations: list[dict]) -> None:
    """相手先 QID が組織 (Q43229 配下) かをバッチ判定し、各行に object_is_org を付与する。

    P463 行はクエリ側で企業集団に限定済みのため常に True。
    """
    target_qids = sorted({
        r["object_qid"] for r in relations
        if r["object_qid"] and r["property"] != "P463"
    })
    print(f"Checking organization class for {len(target_qids)} object QIDs ...")
    org_qids: set[str] = set()
    for i in range(0, len(target_qids), ORG_CHECK_BATCH):
        batch = target_qids[i:i + ORG_CHECK_BATCH]
        org_qids.update(_org_check_batch(batch))
        print(f"  ... {min(i + ORG_CHECK_BATCH, len(target_qids))}/{len(target_qids)} "
              f"(org accumulated: {len(org_qids)})")
        time.sleep(1.5)

    for r in relations:
        r["object_is_org"] = (r["property"] == "P463") or (r["object_qid"] in org_qids)
    n_non_org = sum(1 for r in relations if not r["object_is_org"])
    print(f"org check done: 非組織 {n_non_org} 行をフラグ付け（build 時に除外）")


def fetch_personnel() -> list[dict]:
    """上場企業の役員（CEO/会長/取締役等）データを取得する。

    同一人物が複数の上場企業の役員を務めるケースから、build 側で
    interlocking_director（役員兼任）エッジを導出する。
    """
    print("Querying Wikidata: directors/officers ...")
    rows = run_query(PERSONNEL_QUERY)
    out = []
    for b in rows:
        out.append({
            "company_qid": _qid(b, "co"),
            "property": _qid(b, "prop"),
            "person_qid": _qid(b, "person"),
            "person_label": _val(b, "personLabel"),
        })
    return out


def write_personnel() -> None:
    personnel = fetch_personnel()
    out = DATA_RAW / "wikidata_personnel.json"
    out.write_text(json.dumps(personnel, ensure_ascii=False, indent=1), encoding="utf-8")
    n_persons = len({p["person_qid"] for p in personnel})
    print(f"OK: {len(personnel)} 役員レコード（{n_persons} 人）-> {out}")


def main() -> int:
    DATA_RAW.mkdir(exist_ok=True)

    if "--personnel-only" in sys.argv:
        write_personnel()
        return 0

    mapping = fetch_mapping()
    out1 = DATA_RAW / "wikidata_mapping.json"
    out1.write_text(json.dumps(mapping, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK: {len(mapping)} TSE-listed entities -> {out1}")

    time.sleep(2)  # WDQS レート制限への配慮

    relations = fetch_relations()
    time.sleep(2)
    fetch_org_flags(relations)
    out2 = DATA_RAW / "wikidata_relations.json"
    out2.write_text(json.dumps(relations, ensure_ascii=False, indent=1), encoding="utf-8")
    by_prop: dict[str, int] = {}
    for r in relations:
        by_prop[r["property"]] = by_prop.get(r["property"], 0) + 1
    print(f"OK: {len(relations)} relation triples -> {out2} (by property: {by_prop})")

    time.sleep(2)
    write_personnel()
    return 0


if __name__ == "__main__":
    sys.exit(main())
