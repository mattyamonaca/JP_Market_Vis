"""Content-addressed provenance checks, without storing source prose in Git."""
import hashlib
import json


def row_key(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def check_for(row, checks):
    check = checks.get(row_key(row))
    if not check:
        return {"status": "not_checked"}
    return {key: check[key] for key in ("status", "checked_at", "sha256", "http_status", "final_url") if key in check}
