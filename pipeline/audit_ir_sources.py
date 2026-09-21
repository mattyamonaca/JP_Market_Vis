"""Check whether stored IR excerpts can actually be found at their cited URLs.

This is a provenance check, not semantic approval of a relationship. All page
contents and excerpts stay in an ignored output directory. Requires requests,
beautifulsoup4, pypdf[crypto], fonttools and truststore; run with --help. Interrupted runs
resume from cache.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import io
import json
from pathlib import Path
import re
import threading
import time
import unicodedata
from urllib.parse import urldefrag, urlsplit

import requests
import truststore
from bs4 import BeautifulSoup
from pypdf import PdfReader


def normalize(value):
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", value)).casefold()


def excerpt_status(quote, text):
    q, body = normalize(quote), normalize(text)
    if len(q) < 12:
        return "excerpt_too_short"
    return "excerpt_found" if q in body else "excerpt_not_found"


def main():
    # Use the OS CA store as well as Python's trust configuration. Verification
    # stays enabled; this handles issuer sites with platform-provided roots.
    truststore.inject_into_ssl()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, default=Path(__file__).parent / "ir_crawl/data/ir_relations.json")
    ap.add_argument("--out", type=Path, default=Path("outputs/ir-source-audit"))
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--checks-out", type=Path, help="Export only hash-keyed check metadata, with no source prose")
    args = ap.parse_args()
    rows = json.loads(args.input.read_text())
    cache = args.out / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    urls = sorted({urldefrag(r["source_url"])[0] for r in rows})
    if args.limit:
        urls = urls[:args.limit]
    locks = {urlsplit(u).netloc: threading.Lock() for u in urls}

    def fetch(url):
        key = hashlib.sha256(url.encode()).hexdigest()
        meta_path, text_path = cache / (key + ".json"), cache / (key + ".txt")
        if meta_path.exists():
            return url, json.loads(meta_path.read_text())
        meta = {"url": url, "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        with locks[urlsplit(url).netloc]:
            try:
                with requests.get(url, timeout=(8, 20), stream=True,
                                  headers={"User-Agent": "JP-Market-Vis-source-audit/1.0"}) as response:
                    meta.update(http_status=response.status_code, final_url=response.url)
                    response.raise_for_status()
                    chunks, size = [], 0
                    for chunk in response.iter_content(65536):
                        size += len(chunk)
                        if size > 80_000_000:
                            raise ValueError("document_exceeds_80MB")
                        chunks.append(chunk)
                    data = b"".join(chunks)
                    meta["sha256"] = hashlib.sha256(data).hexdigest()
                    meta["content_type"] = response.headers.get("Content-Type", "")
                    if data.startswith(b"%PDF"):
                        doc = PdfReader(io.BytesIO(data))
                        text = "\n".join(p.extract_text() or "" for p in doc.pages)
                        meta["pages"] = len(doc.pages)
                    else:
                        soup = BeautifulSoup(data, "html.parser")
                        meta["title"] = soup.title.get_text(" ", strip=True) if soup.title else None
                        for tag in soup(["script", "style", "noscript"]):
                            tag.decompose()
                        text = soup.get_text(" ", strip=True)
                    text_path.write_text(text)
                    meta.update(result="fetched", text_length=len(text))
            except Exception as exc:
                meta.update(result="fetch_failed", error=f"{type(exc).__name__}: {exc}"[:300])
            time.sleep(0.3)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
        return url, meta

    results = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(fetch, u) for u in urls]
        for i, future in enumerate(as_completed(futures), 1):
            url, meta = future.result()
            results[url] = meta
            if i % 50 == 0 or i == len(urls):
                print(f"Fetched {i}/{len(urls)}", flush=True)
    audit = []
    for i, row in enumerate(rows):
        url = urldefrag(row["source_url"])[0]
        meta = results.get(url)
        if meta is None:
            continue
        key = hashlib.sha256(url.encode()).hexdigest()
        status = meta["result"]
        if status == "fetched":
            status = excerpt_status(row.get("evidence_quote", ""), (cache / (key + ".txt")).read_text())
        audit.append({"row_index": i, "row_sha256": hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                      "filer_sec_code": row["filer_sec_code"], "counterparty_name": row["counterparty_name"],
                      "relation_type": row["relation_type"], "url": url, "status": status, "document": meta})
    from collections import Counter
    report = {"summary": dict(Counter(r["status"] for r in audit)), "url_count": len(results),
              "limitations": "Excerpt presence does not verify parties, direction, relationship type, current validity, or publisher authenticity.",
              "rows": audit}
    (args.out / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    if args.checks_out:
        checks = {r["row_sha256"]: {"status": r["status"], **{k: r["document"][k]
                   for k in ("checked_at", "sha256", "http_status", "final_url") if k in r["document"]}} for r in audit}
        args.checks_out.write_text(json.dumps(checks, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
