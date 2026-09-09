"""企業の公式サイト URL を Wikidata P856 から収集する（IR クロールの入口）。

入力: M5 のハブ上位企業（関係数の多い順）から SAMPLE_N 社、または --all で QID 付き全社
出力: ir_crawl/data/sample_urls.json
  [{"code":"7203","name":"トヨタ自動車","url":"https://global.toyota"}]

P856 は複数・誤ロケール（例: ソニー→インド版）を返すため、
.co.jp > 日本語(.com/ja) > .com > その他 の優先度で 1 件に絞る。
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent.parent
MASTERS = BASE.parent.parent / "lambda" / "layers" / "core" / "python" / "persona_core" / "tables" / "masters"
OUT = Path(__file__).parent / "data" / "sample_urls.json"
SAMPLE_N = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 30


def url_score(url: str) -> int:
    u = url.lower()
    if ".co.jp" in u:
        return 0
    if "/ja" in u or ".jp" in u:
        return 1
    if u.endswith(".com/") or u.endswith(".com"):
        return 2
    return 3


def pick_url(urls: list[str]) -> str | None:
    if not urls:
        return None
    return sorted(urls, key=url_score)[0]


def main() -> int:
    m4 = json.loads((MASTERS / "M4_companies.json").read_text(encoding="utf-8"))["companies"]
    m5 = json.loads((MASTERS / "M5_company_relations.json").read_text(encoding="utf-8"))

    # 関係数の多い順（ハブ優先）に並べる。--all なら全 QID 付き上場企業、
    # それ以外は上位 SAMPLE_N 社。
    deg: dict[str, int] = defaultdict(int)
    for rel in m5["relations"]:
        for node in (rel["source"], rel["target"]):
            if node["type"] == "listed":
                deg[node["key"]] += 1
    all_listed = "--all" in sys.argv
    # --all は全上場企業、通常はエッジを持つ企業を優先
    pool = list(m4.keys()) if all_listed else sorted(deg, key=lambda c: -deg[c])
    pool.sort(key=lambda c: -deg.get(c, 0))

    targets, qids = [], {}
    n_no_qid = 0
    for code in pool:
        c = m4.get(code)
        if not c:
            continue
        if not c.get("wikidata_qid"):
            n_no_qid += 1
            continue
        targets.append(code)
        qids[code] = c["wikidata_qid"]
        if not all_listed and len(targets) >= SAMPLE_N:
            break
    if all_listed:
        print(f"対象 {len(targets)} 社（QID付き）/ QID無しで除外 {n_no_qid} 社")

    # P856 をバッチ取得
    url_by_qid: dict[str, list[str]] = defaultdict(list)
    qid_list = list(qids.values())
    for i in range(0, len(qid_list), 150):
        batch = qid_list[i:i + 150]
        values = " ".join(f"wd:{q}" for q in batch)
        query = f"SELECT ?co ?site WHERE {{ VALUES ?co {{ {values} }} ?co wdt:P856 ?site }}"
        r = requests.post("https://query.wikidata.org/sparql",
                          data={"query": query, "format": "json"},
                          headers={"User-Agent": "persona-project-ir/1.0",
                                   "Accept": "application/sparql-results+json"}, timeout=120)
        r.raise_for_status()
        for b in r.json()["results"]["bindings"]:
            q = b["co"]["value"].rsplit("/", 1)[-1]
            url_by_qid[q].append(b["site"]["value"])

    out = []
    for code in targets:
        url = pick_url(url_by_qid.get(qids[code], []))
        if url:
            out.append({"code": code, "name": m4[code]["name"], "url": url})

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK: {len(out)}/{len(targets)} 社に URL 付与 -> {OUT}")
    for r in out[:10]:
        print(f"   {r['code']} {r['name']} -> {r['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
