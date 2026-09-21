"""Count distinct confirmed graph relationships by evidence origin.

Overlap is reported separately. URL count and number of excerpts are not
contribution; unconfirmed evidence does not support a confirmed relation.
"""
import argparse
from collections import Counter
import json
from pathlib import Path


def contribution(relations, listed_only=True):
    buckets, sources, types = Counter(), Counter(), Counter()
    for rel in relations:
        if rel.get("status") != "confirmed":
            continue
        if listed_only and any(rel[s]["type"] != "listed" for s in ("source", "target")):
            continue
        origins = {"edinet" if e.get("origin") == "edinet_republication" else e["source"] for e in rel["evidence"]
                   if e.get("support_status", "confirmed") == "confirmed"}
        edinet, other = "edinet" in origins, bool(origins - {"edinet"})
        buckets["both" if edinet and other else "edinet_only" if edinet else "other_only" if other else "unsupported"] += 1
        sources.update(origins)
        types.update([rel["relation_type"]])
    e = buckets["edinet_only"] + buckets["both"]
    n = buckets["other_only"] + buckets["both"]
    return {"buckets": dict(buckets), "edinet_supported": e, "other_supported": n,
            "other_to_edinet_ratio": n / e if e else None, "sources": dict(sources), "types": dict(types)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    relations = json.loads(args.path.read_text())["relations"]
    result = {"listed_graph": contribution(relations), "all_relations": contribution(relations, False)}
    content = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.write_text(content)
    print(content)
