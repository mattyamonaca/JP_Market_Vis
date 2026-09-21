"""Ingest relationships individually checked against independent primary releases.

Inputs contain facts and source metadata only, never copied release prose.
The announcing corporation must be the actual party (not automatically its
listed parent). Re-publications of EDINET filings are not independent sources.
"""
from datetime import date
import re
from urllib.parse import urlsplit

from config import RELATION_TYPES


def add_official_relations(builder, records):
    for row in records:
        typ = row["relation_type"]
        if typ not in RELATION_TYPES:
            raise ValueError(f"Unknown relationship type: {typ}")
        refs = []
        for side in ("source", "target"):
            value = row[side]
            if value.get("code"):
                code = value["code"]
                if code not in builder.companies:
                    raise ValueError(f"Unknown listed code: {code}")
                refs.append({"type": "listed", "key": code})
            else:
                refs.append(builder.resolve_node(name=value["name"]))
        if not all(refs) or refs[0] == refs[1]:
            raise ValueError(f"Invalid endpoints: {row['id']}")
        document = row["document"]
        url = urlsplit(document["url"])
        if url.scheme != "https" or not url.netloc:
            raise ValueError("A primary HTTPS document URL is required")
        if document.get("origin") not in ("independent_primary_release", "independent_primary_website"):
            raise ValueError("EDINET mirrors and secondary articles are not independent primary releases")
        checked = row["review"]["on"]
        published = document.get("published")
        as_of = row.get("as_of", published)
        date.fromisoformat(checked)
        if (not as_of and document["origin"] == "independent_primary_release") or (as_of and date.fromisoformat(as_of) > date.fromisoformat(checked)):
            raise ValueError("Cannot review a future release")
        if row["review"]["status"] != "source_checked":
            raise ValueError("Candidate records must not be ingested as checked facts")
        evidence = {
            "source": "official_release" if document["origin"] == "independent_primary_release" else "issuer_website",
            "source_tier": "primary", "confidence": "high",
            "url": document["url"], "published": published, "as_of": as_of,
            "retrieved": checked, "verification": "verified", "support_status": "confirmed",
            "record_id": row["id"], "reviewer": row["review"]["by"],
            "origin": document["origin"],
        }
        if document.get("sha256"):
            evidence["source_check"] = {"status": "reviewed_document", "sha256": document["sha256"], "checked_at": checked}
        if "table_index" in document:
            evidence["table_ref"] = f"HTML table {document['table_index'] + 1}, row {document['row_index'] + 1}"
        elif document.get("page"):
            evidence["table_ref"] = f"PDF page {int(document['page'])}"
        attributes = {}
        if typ == "product_adoption":
            product = row.get("product", "").strip()
            if not product or len(product) > 160 or "\n" in product:
                raise ValueError("A reviewed product name is required for an adoption case")
            evidence["product"] = product
            if row.get("information_period"):
                period = row["information_period"]
                if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period) or period > checked[:7]:
                    raise ValueError("Invalid adoption case information period")
                evidence["information_period"] = period
        if typ == "interlocking_director":
            person = row["person"]
            roles = row["roles"]
            if not person or any(ref["key"] not in roles for ref in refs):
                raise ValueError("Both current offices must be identified for an interlocking director")
            attributes["persons"] = [{"name": person, "roles": roles}]
            evidence.update(person=person, role_at_filer=roles[refs[0]["key"]],
                            role_at_counterparty=roles[refs[1]["key"]], filer_sec_code=refs[0]["key"])
        if row.get("deal_status"):
            if row["deal_status"] not in ("agreed", "executed"):
                raise ValueError("Unknown deal status")
            attributes["deal_status"] = evidence["deal_status"] = row["deal_status"]
        relation = builder.add(*refs, typ, attributes, evidence)
        if typ == "interlocking_director" and relation:
            persons = relation["attributes"].setdefault("persons", [])
            if not any(re.sub(r"\s+", "", p["name"]) == re.sub(r"\s+", "", person) for p in persons):
                persons.append({"name": person, "roles": roles})
