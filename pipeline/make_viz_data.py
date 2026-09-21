"""フル版 M4/M5（data_processed/masters）から公開アプリ用データを public/ に生成する。

旧 make_viz_data.py は evidence を先頭 2 件・引用 80 文字に切り詰め、date/retrieved を落としていた（Issue #5）。
本版は原文を再配信せず、構造化された抽出情報と出典を 2 層に分ける:

  public/M5_company_relations.json
      関係の本体。evidence は要約（出所・出所種別・基準日・検証状態）だけを持つ。
  public/evidence/<shard>.json
      関係IDごとの出典・抽出項目（原本URL・書類ID・資料内の位置・分類・役職・契約年月等）と
      比率の履歴。詳細パネルを開いたときに該当シャードだけを取得する（1 シャード = 1,000 関係）。

比率は互換のため数値 `ownership_ratio` / `sales_ratio` を残し、意味付きの構造は `ownership` / `sales` に入れる。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

from config import MASTERS_DIR, PUBLIC_DIR

SHARD_SIZE = 1000

EVIDENCE_KEYS = (
    "source", "source_tier", "confidence", "property", "doc_id", "url", "as_of", "published", "retrieved",
    "classification", "classification_source", "direction_source", "raw_name", "table_ref",
    "verification", "filer_sec_code",
)
FACT_KEYS = ("person", "role_at_filer", "role_at_counterparty", "contracting_party", "contract_date",
             "organization", "deal_status", "event_year")
RATIO_KEYS = ("value", "kind", "scope", "direct", "indirect", "as_of", "doc_id", "status", "verified",
              "has_older_values", "conflict_same_period", "conflicting_values")


def full_evidence(ev: dict) -> dict:
    # 許可した項目だけを出力する。自由文や将来追加されるフィールドは自動公開しない。
    out = {k: ev[k] for k in EVIDENCE_KEYS if ev.get(k) not in (None, "", [], {})}
    facts = {k: ev[k] for k in FACT_KEYS if ev.get(k) not in (None, "", [], {})}
    if facts:
        out["facts"] = facts
    # cue は原文断片。判定コードは維持するが、原文断片は配信しない。
    extraction = {k: ev["extraction"][k] for k in ("reasons", "llm_type", "retyped_from", "suggested_type")
                  if ev.get("extraction", {}).get(k) not in (None, "", [], {})}
    if extraction:
        out["extraction"] = extraction
    return out


def public_verification(value: dict) -> dict:
    out = {k: value[k] for k in ("status", "on", "as_of", "by") if value.get(k) is not None}
    source = value.get("source") or {}
    out["source"] = {k: source[k] for k in ("url", "published") if source.get(k)}
    return out


def summary_evidence(ev: dict) -> dict:
    out = {"source": ev.get("source"), "tier": ev.get("source_tier")}
    if ev.get("as_of"):
        out["as_of"] = ev["as_of"]
    if ev.get("verification"):
        out["verification"] = ev["verification"]
    return out


def slim_ratio(attr: dict | None, with_history: bool) -> dict | None:
    if not attr:
        return None
    out = {k: attr[k] for k in RATIO_KEYS if attr.get(k) is not None}
    if with_history and attr.get("history"):
        out["history"] = [{k: h[k] for k in RATIO_KEYS if h.get(k) is not None} for h in attr["history"]]
    return out


def shard_of(relation_id: str) -> str:
    n = int(relation_id[1:])
    return f"{n // SHARD_SIZE:04d}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(PUBLIC_DIR), help="出力先（既定: public/）。検証用に別ディレクトリへ出せる")
    args = ap.parse_args()
    out_dir = Path(args.out)
    m4 = json.loads((MASTERS_DIR / "M4_companies.json").read_text(encoding="utf-8"))
    m5 = json.loads((MASTERS_DIR / "M5_company_relations.json").read_text(encoding="utf-8"))

    slim_rels = []
    shards: dict[str, dict] = {}
    for r in m5["relations"]:
        raw_attrs = r.get("attributes") or {}
        attrs: dict = {}
        detail: dict = {"evidence": [full_evidence(e) for e in r["evidence"]]}
        own = raw_attrs.get("ownership_ratio")
        if isinstance(own, dict):
            # 本体には表示に使う最小限（現在値・意味・基準日）だけを置き、内訳と履歴はシャードへ
            if own.get("value") is not None:
                attrs["ownership_ratio"] = own["value"]
            attrs["ownership"] = {k: own[k] for k in ("kind", "scope", "as_of", "verified", "has_older_values",
                                                       "conflict_same_period", "conflicting_values") if own.get(k) is not None}
            detail["ownership"] = slim_ratio(own, with_history=True)
        elif own is not None:
            attrs["ownership_ratio"] = own
        sales = raw_attrs.get("sales_ratio")
        if isinstance(sales, dict):
            if sales.get("value") is not None:
                attrs["sales_ratio"] = sales["value"]
            attrs["sales"] = slim_ratio(sales, with_history=False)
        elif sales is not None:
            attrs["sales_ratio"] = sales
        if raw_attrs.get("sales_amount"):
            attrs["sales_amount"] = slim_ratio(raw_attrs["sales_amount"], with_history=False) \
                if isinstance(raw_attrs["sales_amount"], dict) else raw_attrs["sales_amount"]
            if isinstance(raw_attrs["sales_amount"], dict) and raw_attrs["sales_amount"].get("unit"):
                attrs["sales_amount"]["unit"] = raw_attrs["sales_amount"]["unit"]
        for k in ("person", "persons", "deal_status", "event_year", "contract_date", "member_via"):
            if raw_attrs.get(k) is not None:
                attrs[k] = raw_attrs[k]
        # この2値は統合処理の固定ラベル。自由記述の契約説明は通さない。
        if raw_attrs.get("contract_note") in ("合弁契約", "相互ライセンス"):
            attrs["contract_kind"] = raw_attrs["contract_note"]
        rel = {
            "relation_id": r["relation_id"],
            "source": r["source"],
            "target": r["target"],
            "relation_type": r["relation_type"],
            "category": r["category"],
            "directed": r["directed"],
            "status": r.get("status", "confirmed"),
            "attributes": attrs,
            "evidence": [summary_evidence(e) for e in r["evidence"]],
        }
        for k in ("review_reasons", "valid_until", "superseded_by"):
            if r.get(k):
                rel[k] = r[k]
        if r.get("verification"):
            rel["verification"] = {kk: r["verification"].get(kk) for kk in ("status", "on", "as_of")}
            detail["verification"] = public_verification(r["verification"])
        slim_rels.append(rel)
        shards.setdefault(shard_of(r["relation_id"]), {})[r["relation_id"]] = detail

    m5_slim = {
        "master_id": m5["master_id"],
        "version": m5["version"],
        "evidence_format": "structured-facts-v1",
        "generated_at": m5.get("generated_at"),
        "status_values": m5.get("status_values"),
        "evidence_shards": {"path": "evidence/{shard}.json", "size": SHARD_SIZE},
        "relation_types": m5["relation_types"],
        "entities": m5["entities"],
        "relations": slim_rels,
    }
    # 本体・名簿・詳細のどれが変わっても別の配信先にする。
    digest = hashlib.sha256()
    for payload in (m4, m5_slim, shards):
        digest.update(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
    revision = digest.hexdigest()[:24]
    m4["dataset_id"] = m5_slim["dataset_id"] = revision
    m5_slim["evidence_shards"]["path"] = f"data/{revision}/evidence/{{shard}}.json"
    for payload in shards.values():
        for detail in payload.values():
            detail["dataset_id"] = revision
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "M4_companies.json").write_text(
        json.dumps(m4, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out_dir / "M5_company_relations.json").write_text(
        json.dumps(m5_slim, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    # 旧クライアントが固定URLを要求した場合は404にし、別関係の出典を返さない。
    legacy_dir = out_dir / "evidence"
    if legacy_dir.exists():
        shutil.rmtree(legacy_dir)
    ev_dir = out_dir / "data" / revision / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)
    total_ev = 0
    for shard, payload in shards.items():
        p = ev_dir / f"{shard}.json"
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if p.exists() and p.read_text(encoding="utf-8") != text:
            raise RuntimeError(f"Immutable dataset changed: {p}")
        p.write_text(text, encoding="utf-8")
        total_ev += p.stat().st_size

    def mb(p: Path) -> str:
        return f"{p.stat().st_size / 1e6:.1f}MB"

    print(f"M4 -> {out_dir / 'M4_companies.json'} ({mb(out_dir / 'M4_companies.json')})")
    print(f"M5 -> {out_dir / 'M5_company_relations.json'} ({mb(out_dir / 'M5_company_relations.json')}) / {len(slim_rels)} エッジ")
    print(f"evidence -> {ev_dir} ({len(shards)} シャード / 合計 {total_ev / 1e6:.1f}MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
