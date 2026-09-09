"""fetch/parse 結果を統合し M4_companies.json / M5_company_relations.json（フル版）を生成する。

入力（data_raw/）:
  jpx_listed.json, edinet_codes.json, wikidata_mapping.json, wikidata_relations.json,
  wikidata_personnel.json, edinet_relations.json(.gz), ir_crawl/data/ir_relations.json,
  sources.json（各入力の取得日）
出力（data_processed/masters/）:
  M4_companies.json, M5_company_relations.json, quarantine.json（要確認・除外した行）

旧 5_build_masters.py（persona_project）からの主な変更（Issue #1）:
  - 関係会社の分類ごとに関係タイプと方向を明示的に分岐する。親会社行は 相手→提出会社 の
    parent_subsidiary、「その他の関係会社」行は 相手→提出会社 の affiliate（提出会社は相手の関連会社）。
    分類不明の行は子会社に推定せず、株式保有（ownership）として status=needs_review に隔離する。
  - 企業名として不適切な行（数値・記号・「その他N社」等）は関係を作らず quarantine.json に記録する。
  - evidence に書類ID・基準日（period_end / 大株主の基準日）・提出日・取得日を保持する。
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import re
import sys
import unicodedata
from typing import Any

from config import (BASE_DIR, DATA_RAW, EDINET_DOC_VIEW_URL, MASTERS_DIR, RELATION_TYPES, VERSION)

GENERATED_AT = dt.date.today().isoformat()

# Wikidata プロパティ → (relation_type, source側, target側)
WD_PROPERTY_MAP = {
    "P355": ("parent_subsidiary", "subject", "object"),   # 子会社: subject が親
    "P749": ("parent_subsidiary", "object", "subject"),   # 親組織: object が親
    "P1830": ("ownership", "subject", "object"),          # 所有物: subject が保有側
    "P127": ("ownership", "object", "subject"),           # 所有者: object が保有側
    "P463": ("corporate_group", "subject", "object"),     # グループ所属
}

# 関係会社の分類 → (relation_type, 相手が source か)
#   owned=True の行（親会社・その他の関係会社）は相手→提出会社。
CLASSIFICATION_MAP = {
    "連結子会社": ("parent_subsidiary", False),
    "非連結子会社": ("parent_subsidiary", False),
    "子会社": ("parent_subsidiary", False),
    "持分法適用非連結子会社": ("parent_subsidiary", False),
    "持分法非適用非連結子会社": ("parent_subsidiary", False),
    "持分法適用関連会社": ("affiliate", False),
    "持分法非適用関連会社": ("affiliate", False),
    "関連会社": ("affiliate", False),
    "親会社": ("parent_subsidiary", True),
    # 財務諸表等規則8条: その他の関係会社 = 提出会社を関連会社とする会社 → 相手→提出会社の affiliate
    "その他の関係会社": ("affiliate", True),
}

_LEGAL_RE = re.compile(
    r"株式会社|（株）|\(株\)|㈱|合同会社|有限会社|（有）|\(有\)|㈲|ホールディングス|Holdings|HD|, ?Inc\.?|Co\., ?Ltd\.?|Corporation|Corp\.?|Ltd\.?|Limited|LLC",
    re.I,
)
_NOMINEE_RE = re.compile(r"信託口|カストディ|マスタートラスト|資産管理サービス信託|常任代理人|証券決済|CLEARING|NOMINEE|Nominee|Custody|CUSTODY")


def normalize_name(name: str) -> str:
    n = unicodedata.normalize("NFKC", name or "")
    n = _LEGAL_RE.sub("", n)
    n = re.sub(r"[\s　・･\-－—–]+", "", n)
    return n.lower()


def is_nominee_holder(name: str | None) -> bool:
    return bool(name and _NOMINEE_RE.search(unicodedata.normalize("NFKC", name)))


def load(name: str, required: bool = True) -> Any:
    path = DATA_RAW / name
    gz = DATA_RAW / (name + ".gz")
    if not path.exists() and gz.exists():
        with gzip.open(gz, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    if not path.exists():
        if not required:
            return None
        print(f"ERROR: {path} がありません。先に fetch/parse スクリプトを実行してください。", file=sys.stderr)
        sys.exit(2)
    return json.loads(path.read_text(encoding="utf-8"))


def source_dates() -> dict:
    return load("sources.json", required=False) or {}


# ---------------------------------------------------------------------------
# M4
# ---------------------------------------------------------------------------

def build_m4(jpx: list[dict], edinet: dict[str, dict], wd_mapping: list[dict]) -> dict:
    qid_by_cn = {m["corporate_number"]: m["qid"] for m in wd_mapping if m.get("corporate_number")}
    qid_by_ticker: dict[str, str] = {}
    qid_by_name: dict[str, str] = {}
    for m in wd_mapping:
        for t in m.get("tickers", []):
            qid_by_ticker.setdefault(str(t)[:4], m["qid"])
        label = m.get("label")
        if label and not (label.startswith("Q") and label[1:].isdigit()):
            qid_by_name.setdefault(normalize_name(label), m["qid"])

    qid_assign: dict[str, str] = {}
    used_qids: set[str] = set()

    def _ticker_and_name(code: str, rec: dict, cn: str | None) -> str | None:
        q = qid_by_ticker.get(code)
        if q and rec["name"] and qid_by_name.get(normalize_name(rec["name"])) == q:
            return q
        return None

    for resolver in (
        lambda code, rec, cn: cn and qid_by_cn.get(cn),
        _ticker_and_name,
        lambda code, rec, cn: qid_by_ticker.get(code),
        lambda code, rec, cn: rec["name"] and qid_by_name.get(normalize_name(rec["name"])),
    ):
        for rec in jpx:
            code = rec["securities_code"]
            if code in qid_assign:
                continue
            cn = edinet.get(code, {}).get("corporate_number")
            qid = resolver(code, rec, cn)
            if qid and qid not in used_qids:
                qid_assign[code] = qid
                used_qids.add(qid)

    companies: dict[str, dict] = {}
    for rec in jpx:
        code = rec["securities_code"]
        ed = edinet.get(code, {})
        companies[code] = {
            "name": rec["name"],
            "name_en": ed.get("name_en"),
            "securities_code": code,
            "corporate_number": ed.get("corporate_number"),
            "edinet_code": ed.get("edinet_code"),
            "market_segment": rec["market_segment"],
            "industry_33": rec["industry_33"],
            "industry_17": rec["industry_17"],
            "scale_category": rec["scale_category"],
            "address": ed.get("address"),
            "wikidata_qid": qid_assign.get(code),
        }
    print(f"M4: {len(companies)} 社（EDINET突合 {sum(1 for c in companies.values() if c['edinet_code'])} / "
          f"Wikidata QID付与 {len(qid_assign)}）")
    return {
        "master_id": "M4_companies",
        "version": VERSION,
        "generated_at": GENERATED_AT,
        "source": {
            "jpx": "JPX 東証上場銘柄一覧 (data_j.xls)",
            "edinet": "EDINET コードリスト（金融庁）",
            "wikidata": "Wikidata SPARQL (P414/P249/P3225)",
        },
        "companies": companies,
    }


# ---------------------------------------------------------------------------
# 関係ビルダー
# ---------------------------------------------------------------------------

class RelationBuilder:
    """エッジの名寄せ・重複マージ・隔離を担うビルダー。"""

    def __init__(self, companies: dict[str, dict]):
        self.companies = companies
        self.by_cn = {c["corporate_number"]: code for code, c in companies.items() if c.get("corporate_number")}
        self.by_qid = {c["wikidata_qid"]: code for code, c in companies.items() if c.get("wikidata_qid")}
        self.by_name = {normalize_name(c["name"]): code for code, c in companies.items() if c.get("name")}
        self.entities: dict[str, dict] = {}
        self._entity_index: dict[str, str] = {}
        self.relations: dict[tuple, dict] = {}
        self.quarantine: list[dict] = []

    # -- 名寄せ
    def resolve_listed(self, *, qid: str | None = None, cn: str | None = None,
                       name: str | None = None) -> str | None:
        if qid and qid in self.by_qid:
            return self.by_qid[qid]
        if cn and cn in self.by_cn:
            return self.by_cn[cn]
        if name and normalize_name(name) in self.by_name:
            return self.by_name[normalize_name(name)]
        return None

    def resolve_node(self, *, qid: str | None = None, cn: str | None = None,
                     name: str | None = None) -> dict | None:
        code = self.resolve_listed(qid=qid, cn=cn, name=name)
        if code:
            return {"type": "listed", "key": code}
        if not name and not qid:
            return None
        for k in (qid, cn, name and normalize_name(name)):
            if k and k in self._entity_index:
                ent_key = self._entity_index[k]
                break
        else:
            ent_key = f"ENT{len(self.entities) + 1:06d}"
            self.entities[ent_key] = {
                "name": name or qid,
                "corporate_number": cn,
                "wikidata_qid": qid,
                "listed": False,
            }
            for k in (qid, cn, name and normalize_name(name)):
                if k:
                    self._entity_index[k] = ent_key
        return {"type": "entity", "key": ent_key}

    # -- 追加
    def add(self, source: dict, target: dict, relation_type: str, attributes: dict,
            evidence: dict, *, status: str = "confirmed", reasons: list[str] | None = None) -> dict | None:
        if source == target:
            return None
        meta = RELATION_TYPES[relation_type]
        s, t = source, target
        if not meta["directed"] and (s["type"], s["key"]) > (t["type"], t["key"]):
            s, t = t, s
        key = (s["type"], s["key"], t["type"], t["key"], relation_type)
        rel = self.relations.get(key)
        if rel is None:
            rel = self.relations[key] = {
                "source": s,
                "target": t,
                "relation_type": relation_type,
                "category": meta["category"],
                "directed": meta["directed"],
                "status": status,
                "review_reasons": list(reasons or []),
                "attributes": {},
                "evidence": [],
            }
        else:
            # 確定根拠が 1 つでもあれば confirmed。要確認理由は集約する
            if status == "confirmed":
                rel["status"] = "confirmed"
            for r in reasons or []:
                if r not in rel["review_reasons"]:
                    rel["review_reasons"].append(r)
        if not any(_same_evidence(e, evidence) for e in rel["evidence"]):
            rel["evidence"].append(evidence)
        merge_attributes(rel["attributes"], attributes, evidence)
        return rel

    def reject(self, row: dict, reason: str, stage: str) -> None:
        self.quarantine.append({"stage": stage, "reason": reason, "row": row})

    def finalize(self) -> tuple[dict, list[dict]]:
        rels = []
        for rel in self.relations.values():
            if rel["status"] == "confirmed":
                rel["review_reasons"] = []
        ordered = sorted(self.relations.values(), key=lambda r: (
            r["source"]["type"], r["source"]["key"], r["target"]["type"], r["target"]["key"], r["relation_type"]))
        for i, rel in enumerate(ordered, start=1):
            rels.append({"relation_id": f"R{i:07d}", **rel})
        used = {r["key"] for rel in rels for r in (rel["source"], rel["target"]) if r["type"] == "entity"}
        entities = {k: v for k, v in self.entities.items() if k in used}
        return entities, rels


def _same_evidence(a: dict, b: dict) -> bool:
    keys = ("source", "property", "doc_id", "url", "as_of")
    return all(a.get(k) == b.get(k) for k in keys)


def merge_attributes(attrs: dict, new: dict, evidence: dict) -> None:
    """属性の統合。旧実装は「最初に見つかった値を残す」だったが、基準日の新しい値を現在値にし、
    それ以外は history に保持する（Issue #2 で拡張）。"""
    for k, v in new.items():
        if v is None:
            continue
        if isinstance(v, dict) and "value" in v:
            cur = attrs.get(k)
            if cur is None or _newer(v, cur):
                if cur is not None:
                    v.setdefault("history", []).extend([_strip_history(cur)] + cur.get("history", []))
                attrs[k] = v
            else:
                cur.setdefault("history", []).append(_strip_history(v))
        elif attrs.get(k) is None:
            attrs[k] = v


def _strip_history(v: dict) -> dict:
    return {kk: vv for kk, vv in v.items() if kk != "history"}


def _newer(a: dict, b: dict) -> bool:
    return (a.get("as_of") or "") > (b.get("as_of") or "")


# ---------------------------------------------------------------------------
# 各ソースの投入
# ---------------------------------------------------------------------------

def add_wikidata_relations(builder: RelationBuilder, wd_relations: list[dict], retrieved: str | None) -> None:
    n = n_dropped = n_non_org = 0
    for row in wd_relations:
        prop = row["property"]
        if prop not in WD_PROPERTY_MAP:
            continue
        relation_type, src_role, _ = WD_PROPERTY_MAP[prop]
        if not row.get("object_is_org", True):
            n_non_org += 1
            continue
        subject_code = builder.resolve_listed(qid=row["subject_qid"])
        if subject_code is None:
            n_dropped += 1
            continue
        subject = {"type": "listed", "key": subject_code}
        obj = builder.resolve_node(qid=row["object_qid"], cn=row.get("object_corporate_number"),
                                   name=row.get("object_label"))
        if obj is None:
            continue
        if relation_type == "ownership" and row.get("object_is_joint_venture") and src_role == "subject":
            relation_type = "joint_venture"
        source, target = (subject, obj) if src_role == "subject" else (obj, subject)
        builder.add(source, target, relation_type, {}, {
            "source": "wikidata", "source_tier": "secondary", "property": prop,
            "url": f"https://www.wikidata.org/wiki/{row['subject_qid']}",
            "as_of": None, "retrieved": retrieved, "confidence": "medium",
        })
        n += 1
    print(f"Wikidata 由来エッジ投入: {n} 行（廃止銘柄等の除外 {n_dropped} / 非組織の除外 {n_non_org}）")


def add_personnel_relations(builder: RelationBuilder, personnel: list[dict], retrieved: str | None) -> None:
    by_person: dict[str, dict] = {}
    for rec in personnel:
        code = builder.resolve_listed(qid=rec.get("company_qid"))
        if code is None:
            continue
        p = by_person.setdefault(rec["person_qid"], {"name": rec.get("person_label"), "codes": set()})
        p["codes"].add(code)
    n = 0
    for person_qid, p in by_person.items():
        codes = sorted(p["codes"])
        for i in range(len(codes)):
            for j in range(i + 1, len(codes)):
                builder.add({"type": "listed", "key": codes[i]}, {"type": "listed", "key": codes[j]},
                            "interlocking_director", {"person": p["name"]}, {
                                "source": "wikidata", "source_tier": "secondary", "property": "P169/P488",
                                "person": p["name"], "person_qid": person_qid,
                                "url": f"https://www.wikidata.org/wiki/{person_qid}",
                                "as_of": None, "retrieved": retrieved, "confidence": "medium"})
                n += 1
    print(f"役員兼任エッジ投入: {n} 行")


def edinet_evidence(row: dict, retrieved: str | None, extra: dict) -> dict:
    ev = {
        "source": "edinet",
        "source_tier": "primary",
        "property": row.get("kind"),
        "doc_id": row.get("doc_id"),
        "url": EDINET_DOC_VIEW_URL.format(doc_id=row.get("doc_id")) if row.get("doc_id") else None,
        "as_of": row.get("as_of") or row.get("period_end"),
        "published": row.get("submit_date"),
        "retrieved": retrieved,
        "confidence": "high",
        "filer_sec_code": row.get("filer_sec_code"),
        "raw_name": row.get("raw_name"),
        "table_ref": f"table{row.get('table_index')}/row{row.get('row_index')}",
    }
    ev.update({k: v for k, v in extra.items() if v is not None})
    return ev


def ratio_attribute(row: dict, kind: str) -> dict | None:
    """比率を意味付きの構造にする（Issue #2）。
    kind: 'voting'（議決権所有割合）/ 'share'（発行済株式に対する所有株式数の割合）"""
    if row.get("ratio_total") is None and row.get("ratio_indirect") is None:
        return None
    return {
        "value": row.get("ratio_total"),
        "kind": kind,
        "scope": "total" if row.get("ratio_total") is not None else "indirect_only",
        "indirect": row.get("ratio_indirect"),
        "raw": row.get("ratio_raw"),
        "as_of": row.get("as_of") or row.get("period_end"),
        "doc_id": row.get("doc_id"),
    }


def add_edinet_relations(builder: RelationBuilder, edinet_rows: list[dict], retrieved: str | None) -> None:
    n = 0
    by_type: dict[str, int] = {}
    n_junk = n_nominee = n_unclassified = 0
    for row in edinet_rows:
        filer_code = row.get("filer_sec_code")
        if filer_code not in builder.companies:
            continue
        cp_name = row.get("counterparty_name")
        kind = row.get("kind")
        if row.get("name_problem"):
            builder.reject(row, f"name:{row['name_problem']}", "edinet")
            n_junk += 1
            continue
        if kind == "shareholder" and is_nominee_holder(cp_name):
            builder.reject(row, "nominee_holder", "edinet")
            n_nominee += 1
            continue
        filer_node = {"type": "listed", "key": filer_code}
        counterparty = builder.resolve_node(name=cp_name)
        if counterparty is None:
            continue

        if kind == "affiliated":
            cls = row.get("classification")
            owned = bool(row.get("owned_by_counterparty"))
            reasons: list[str] = []
            status = "confirmed"
            if cls in CLASSIFICATION_MAP:
                rel_type, cls_owned = CLASSIFICATION_MAP[cls]
                if cls_owned != owned:
                    # 分類と所有方向が矛盾（例: 子会社なのに被所有）→ 表記どおりの方向で株式保有として要確認
                    rel_type = "ownership"
                    status = "needs_review"
                    reasons.append("direction_conflict")
                    n_unclassified += 1
            else:
                # 分類不明: 子会社と推定せず、表に書かれた事実（議決権の所有）だけを株式保有として記録
                rel_type = "ownership"
                status = "needs_review"
                reasons.append("unclassified")
                n_unclassified += 1
            if row.get("direction_conflict") and "direction_conflict" not in reasons:
                reasons.append("direction_conflict")
                status = "needs_review"
            source, target = (counterparty, filer_node) if owned else (filer_node, counterparty)
            ev = edinet_evidence(row, retrieved, {
                "classification": cls,
                "classification_source": row.get("classification_source"),
                "direction_source": row.get("direction_source"),
                "relationship_note": row.get("relationship_note"),
            })
            builder.add(source, target, rel_type, {"ownership_ratio": ratio_attribute(row, "voting")},
                        ev, status=status, reasons=reasons)
        elif kind == "shareholder":
            rel_type = "ownership"
            ev = edinet_evidence(row, retrieved, {})
            builder.add(counterparty, filer_node, rel_type, {"ownership_ratio": ratio_attribute(row, "share")}, ev)
        elif kind == "customer":
            rel_type = "major_customer"
            ev = edinet_evidence(row, retrieved, {})
            attrs = {}
            if row.get("ratio_total") is not None:
                attrs["sales_ratio"] = {"value": row["ratio_total"], "kind": "sales_share",
                                        "as_of": row.get("period_end"), "doc_id": row.get("doc_id")}
            if row.get("sales_amount") is not None:
                attrs["sales_amount"] = {"value": row["sales_amount"], "unit": row.get("sales_unit"),
                                         "as_of": row.get("period_end"), "doc_id": row.get("doc_id")}
            builder.add(filer_node, counterparty, rel_type, attrs, ev)
        else:
            continue
        n += 1
        by_type[rel_type] = by_type.get(rel_type, 0) + 1
    print(f"EDINET 由来エッジ投入: {n} 行（{by_type}） 除外: 名称不適 {n_junk} / 名義株主 {n_nominee} / "
          f"分類不明・矛盾→要確認 {n_unclassified}")


IR_DIRECTION = {
    "ownership": "out", "major_customer": "out", "merger_acquisition": "out", "technology_license": "out",
    "business_alliance": "out", "capital_alliance": "out", "joint_venture": "out", "joint_research": "out",
}


def add_ir_relations(builder: RelationBuilder, ir_rows: list[dict], retrieved: str | None) -> None:
    n = 0
    by_type: dict[str, int] = {}
    for row in ir_rows:
        filer_code = row.get("filer_sec_code")
        rel_type = row.get("relation_type")
        if filer_code not in builder.companies or rel_type not in RELATION_TYPES:
            continue
        import edinet_tables as et
        problem = et.name_problem(row.get("counterparty_name"))
        if problem:
            builder.reject(row, f"name:{problem}", "ir")
            continue
        counterparty = builder.resolve_node(name=row.get("counterparty_name"))
        if counterparty is None:
            continue
        filer_node = {"type": "listed", "key": filer_code}
        direction = IR_DIRECTION.get(rel_type, "out")
        source, target = (filer_node, counterparty) if direction == "out" else (counterparty, filer_node)
        evidence = {
            "source": "ir_disclosure", "source_tier": "llm_extraction", "url": row.get("source_url"),
            "quote": row.get("evidence_quote") or None, "as_of": row.get("date"), "published": row.get("date"),
            "retrieved": retrieved, "confidence": "low", "filer_sec_code": filer_code,
        }
        builder.add(source, target, rel_type, {}, evidence)
        n += 1
        by_type[rel_type] = by_type.get(rel_type, 0) + 1
    print(f"IR 由来エッジ投入: {n} 行（{by_type}）")


# ---------------------------------------------------------------------------

def main() -> int:
    dates = source_dates()
    d = lambda name: (dates.get(name) or {}).get("retrieved")  # noqa: E731
    jpx = load("jpx_listed.json")
    edinet_codes = load("edinet_codes.json")
    wd_mapping = load("wikidata_mapping.json")
    wd_relations = load("wikidata_relations.json")
    edinet_rows = load("edinet_relations.json")
    personnel = load("wikidata_personnel.json", required=False) or []
    ir_path = BASE_DIR / "ir_crawl" / "data" / "ir_relations.json"
    ir_rows = json.loads(ir_path.read_text(encoding="utf-8")) if ir_path.exists() else []

    m4 = build_m4(jpx, edinet_codes, wd_mapping)
    builder = RelationBuilder(m4["companies"])
    add_wikidata_relations(builder, wd_relations, d("wikidata_relations.json"))
    add_personnel_relations(builder, personnel, d("wikidata_personnel.json"))
    add_edinet_relations(builder, edinet_rows, d("edinet_blocks"))
    add_ir_relations(builder, ir_rows, d("ir_crawl/data/ir_relations.json"))
    entities, relations = builder.finalize()

    m5 = {
        "master_id": "M5_company_relations",
        "version": VERSION,
        "generated_at": GENERATED_AT,
        "source": {
            "wikidata": "Wikidata SPARQL (資本: P355/P749/P127/P1830; グループ: P463; 役員兼任: P169/P488 等)",
            "edinet": "EDINET API v2 有価証券報告書（関係会社の状況・大株主の状況・主要な顧客）",
            "ir_disclosure": "各社IRサイトのプレスリリースを LLM(moonshot-v1-32k) で構造化 (confidence=low)",
        },
        "status_values": {
            "confirmed": "出所の記載どおりに抽出できた関係（内容の真偽を保証するものではない）",
            "needs_review": "分類不明・方向の矛盾など、出所の記載から関係タイプを確定できない関係",
        },
        "relation_types": RELATION_TYPES,
        "entities": entities,
        "relations": relations,
    }

    MASTERS_DIR.mkdir(parents=True, exist_ok=True)
    (MASTERS_DIR / "M4_companies.json").write_text(json.dumps(m4, ensure_ascii=False, indent=1), encoding="utf-8")
    (MASTERS_DIR / "M5_company_relations.json").write_text(json.dumps(m5, ensure_ascii=False, indent=1), encoding="utf-8")
    (MASTERS_DIR / "quarantine.json").write_text(
        json.dumps({"generated_at": GENERATED_AT, "count": len(builder.quarantine), "rows": builder.quarantine},
                   ensure_ascii=False, indent=1), encoding="utf-8")

    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    listed_to_listed = 0
    for r in relations:
        by_type[r["relation_type"]] = by_type.get(r["relation_type"], 0) + 1
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        if r["source"]["type"] == "listed" and r["target"]["type"] == "listed":
            listed_to_listed += 1
    print(f"M5: {len(relations)} エッジ（上場-上場 {listed_to_listed} / 非上場エンティティ {len(entities)} / "
          f"status {by_status}）-> {MASTERS_DIR}")
    print(f"   タイプ別: {json.dumps(by_type, ensure_ascii=False)}")
    print(f"   隔離: {len(builder.quarantine)} 行 -> quarantine.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
