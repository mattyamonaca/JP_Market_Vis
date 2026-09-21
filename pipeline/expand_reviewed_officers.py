"""Derive shared-officer pairs from already reviewed offices in one document.

A single reviewed profile may state that one person currently serves at A, B
and C. All three pairs share that person. Never join names across documents:
names alone do not establish identity, and dates or roles can differ.
"""
import hashlib
import itertools
import re
from collections import defaultdict


def expand_reviewed_officers(records):
    groups = defaultdict(list)
    existing = set()
    for row in records:
        if row.get("relation_type") != "interlocking_director":
            continue
        if row.get("derived_from") or row.get("review", {}).get("status") != "source_checked":
            continue
        if not all(row.get(side, {}).get("code") for side in ("source", "target")):
            continue
        doc = row["document"]
        if doc.get("origin") != "independent_primary_website" or not doc.get("sha256"):
            continue
        name = re.sub(r"\s+", "", row["person"])
        key = (doc["url"], doc["sha256"], name, row.get("as_of"), row["review"]["on"])
        groups[key].append(row)
        existing.add((doc["url"], name, tuple(sorted((row["source"]["code"], row["target"]["code"])))))
    additions = []
    for (url, digest, person, as_of, checked), rows in groups.items():
        roles = defaultdict(set)
        supports = defaultdict(list)
        for row in rows:
            for side in ("source", "target"):
                code = row[side]["code"]
                role = row["roles"].get(code, "")
                if re.search(r"取締役|監査役|執行役", role):
                    roles[code].add(role)
                    supports[code].append(row["id"])
        # Conflicting role labels need individual review, not an arbitrary pick.
        codes = sorted(c for c, values in roles.items() if len(values) == 1)
        for a, b in itertools.combinations(codes, 2):
            key = (url, person, (a, b))
            if key in existing:
                continue
            rid = hashlib.sha256(f"{a}|{b}|interlocking_director|{person}|{url}".encode()).hexdigest()[:20]
            if any(r["id"] == rid for r in records):
                continue
            existing.add(key)
            additions.append({
                "id": rid, "source": {"code": a}, "target": {"code": b},
                "relation_type": "interlocking_director", "person": person,
                "roles": {a: next(iter(roles[a])), b: next(iter(roles[b]))}, "as_of": as_of,
                "document": dict(rows[0]["document"]),
                "topic": "同一の公式役員紹介で確認した現任の兼職",
                "derived_from": sorted(set(supports[a] + supports[b])),
                "review": {"status": "source_checked", "by": "reviewed_same_document_offices", "on": checked},
            })
    return additions


if __name__ == "__main__":
    import argparse
    import json
    from pathlib import Path
    argparse.ArgumentParser(description=__doc__).parse_args()
    path = Path(__file__).parent / "data_raw/official_relations.json"
    records = json.loads(path.read_text())
    additions = expand_reviewed_officers(records)
    if additions:
        path.write_text(json.dumps(records + additions, ensure_ascii=False, indent=1) + "\n")
    print(f"Added {len(additions)} same-person pairs from reviewed profiles")
