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

from aliases import AliasIndex, base_name, compatible_official_names, load_aliases, match_key
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

_NOMINEE_RE = re.compile(r"信託口|カストディ|マスタートラスト|資産管理サービス信託|常任代理人|証券決済|CLEARING|NOMINEE|Nominee|Custody|CUSTODY")


def normalize_name(name: str) -> str:
    """名寄せ用キー（aliases.match_key）。旧字体・法人格・空白を畳み込む。ホールディングス等は残す。"""
    return match_key(name)


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

    alias_dict = load_aliases()
    companies: dict[str, dict] = {}
    for rec in jpx:
        code = rec["securities_code"]
        ed = edinet.get(code, {})
        aliases = list((alias_dict["listed"].get(code) or {}).get("aliases", []))
        name_edinet = ed.get("name")
        if name_edinet and base_name(name_edinet) != base_name(rec["name"]) and compatible_official_names(rec["name"], name_edinet):
            aliases.append(base_name(name_edinet))
        companies[code] = {
            "name": rec["name"],
            "name_edinet": name_edinet if compatible_official_names(rec["name"], name_edinet) else None,
            "name_kana": ed.get("name_kana") if compatible_official_names(rec["name"], name_edinet) else None,
            "aliases": aliases,
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

    def __init__(self, companies: dict[str, dict], aliases: dict | None = None):
        self.companies = companies
        self.by_cn = {c["corporate_number"]: code for code, c in companies.items() if c.get("corporate_number")}
        self.by_qid = {c["wikidata_qid"]: code for code, c in companies.items() if c.get("wikidata_qid")}
        self.alias_index = AliasIndex(companies, aliases)
        self.entities: dict[str, dict] = {}
        self._entity_index: dict[str, str] = {}
        self.relations: dict[tuple, dict] = {}
        self.quarantine: list[dict] = []
        # 名寄せの記録: 上場企業へ解決した名称と方法 / entity に統合された原文名
        self.listed_resolutions: dict[str, dict[str, str]] = {}
        self.entity_merges: dict[str, dict[str, str]] = {}

    # -- 名寄せ
    def resolve_listed(self, *, qid: str | None = None, cn: str | None = None,
                       name: str | None = None) -> str | None:
        if qid and qid in self.by_qid:
            return self.by_qid[qid]
        if cn and cn in self.by_cn:
            return self.by_cn[cn]
        if name:
            code, how = self.alias_index.resolve_listed(name)
            if code:
                self.listed_resolutions.setdefault(code, {})[name] = how
                return code
        return None

    def resolve_node(self, *, qid: str | None = None, cn: str | None = None,
                     name: str | None = None) -> dict | None:
        code = self.resolve_listed(qid=qid, cn=cn, name=name)
        if code:
            return {"type": "listed", "key": code}
        if not name and not qid:
            return None
        canon, reason = self.alias_index.canonical_entity_name(name) if name else (name, None)
        name_key = normalize_name(canon) if canon else None
        for k, how in ((qid, "same_wikidata_qid"), (cn, "same_corporate_number"), (name_key, "normalized_name")):
            if k and k in self._entity_index:
                ent_key = self._entity_index[k]
                if reason is None:
                    reason = how
                break
        else:
            ent_key = f"ENT{len(self.entities) + 1:06d}"
            self.entities[ent_key] = {
                "name": canon or qid,
                "corporate_number": cn,
                "wikidata_qid": qid,
                "listed": False,
            }
            for k in (qid, cn, name_key):
                if k:
                    self._entity_index[k] = ent_key
        if name and name != self.entities[ent_key]["name"]:
            self.entity_merges.setdefault(ent_key, {})[name] = reason or "normalized_name"
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
        """ID を投入順に依存しない形で確定する（再取得順序が変わっても同じ出力になる）。"""
        # 参照されている entity だけを、正規化名→法人番号→QID の順で並べ直して ID を振り直す
        used = {r["key"] for rel in self.relations.values() for r in (rel["source"], rel["target"])
                if r["type"] == "entity"}
        ordered_ents = sorted(
            (k for k in self.entities if k in used),
            key=lambda k: (normalize_name(self.entities[k]["name"] or ""), self.entities[k].get("corporate_number") or "",
                           self.entities[k].get("wikidata_qid") or "", self.entities[k]["name"] or ""))
        remap = {old: f"ENT{i:06d}" for i, old in enumerate(ordered_ents, start=1)}
        entities = {remap[k]: self.entities[k] for k in ordered_ents}
        self.merge_report = {
            "listed": {code: names for code, names in sorted(self.listed_resolutions.items())},
            "entities": {remap[k]: {"name": self.entities[k]["name"], "merged_names": names}
                         for k, names in self.entity_merges.items() if k in remap},
        }

        def node(ref: dict) -> dict:
            return {"type": "entity", "key": remap[ref["key"]]} if ref["type"] == "entity" else ref

        rels = []
        for rel in self.relations.values():
            rel["source"] = node(rel["source"])
            rel["target"] = node(rel["target"])
            if rel["status"] == "confirmed":
                rel["review_reasons"] = []
            finalize_attributes(rel["attributes"])
            rel["evidence"].sort(key=evidence_sort_key)
        ordered = sorted(self.relations.values(), key=lambda r: (
            r["source"]["type"], r["source"]["key"], r["target"]["type"], r["target"]["key"], r["relation_type"]))
        for i, rel in enumerate(ordered, start=1):
            rels.append({"relation_id": f"R{i:07d}", **rel})
        return entities, rels


def _same_evidence(a: dict, b: dict) -> bool:
    keys = ("source", "property", "doc_id", "url", "as_of")
    return all(a.get(k) == b.get(k) for k in keys)


TIER_ORDER = {"primary": 0, "secondary": 1, "llm_extraction": 2}
KIND_ORDER = {"voting": 0, "share": 1, "share_large_holding": 2, "sales_share": 0}


def merge_attributes(attrs: dict, new: dict, evidence: dict) -> None:
    """属性の統合（Issue #2）。旧実装は「最初に見つかった値を残す」だったが、意味付きの値
    （{"value", "kind", "as_of", ...}）はすべて候補として保持し、finalize_attributes で
    投入順に依存しない規則で現在値を選ぶ。"""
    for k, v in new.items():
        if v is None:
            continue
        if isinstance(v, dict) and "value" in v:
            cands = attrs.setdefault(k, {"candidates": []})
            if isinstance(cands, dict) and "candidates" in cands:
                if not any(_same_candidate(c, v) for c in cands["candidates"]):
                    cands["candidates"].append(dict(v))
        elif attrs.get(k) is None:
            attrs[k] = v


def _same_candidate(a: dict, b: dict) -> bool:
    return all(a.get(k) == b.get(k) for k in ("value", "kind", "indirect", "as_of", "doc_id", "raw"))


def candidate_sort_key(c: dict) -> tuple:
    """現在値の選択順: 基準日の新しい順 → 合計が読めているもの → 議決権 > 株式数 → 書類IDの新しい順。
    同じ意味（kind）・同じ時点の値だけが実質的に比較される。"""
    return (
        -(_date_int(c.get("as_of"))),
        0 if c.get("value") is not None else 1,
        0 if c.get("verified") else 1,
        KIND_ORDER.get(c.get("kind"), 9),
        c.get("status") != "executed",
        "" if c.get("doc_id") is None else "~" + c.get("doc_id"),
        # 以下は決定性のためだけの順序（同順位の競合は finalize_attributes で未確定にする）
        c.get("raw") or "",
        c.get("value") if c.get("value") is not None else -1,
    )


def _same_rank(a: dict, b: dict) -> bool:
    """同じ意味・同じ時点・同じ書類・同じ検証状態の候補か（この場合は値の優劣を決められない）。"""
    return candidate_sort_key(a)[:6] == candidate_sort_key(b)[:6]


def _date_int(d: str | None) -> int:
    if not d:
        return 0
    try:
        return int(d.replace("-", "")[:8])
    except ValueError:
        return 0


def finalize_attributes(attrs: dict) -> None:
    for k, v in list(attrs.items()):
        if isinstance(v, dict) and "candidates" in v:
            cands = sorted(v["candidates"], key=candidate_sort_key)
            if not cands:
                del attrs[k]
                continue
            current = dict(cands[0])
            hist = [dict(c) for c in cands[1:]]
            # 同順位（同じ意味・時点・書類）で値が食い違う候補があれば、投入順で片方を選ばず現在値を未確定にする
            tied = [c for c in cands[1:] if _same_rank(c, cands[0]) and c.get("value") is not None
                    and current.get("value") is not None and abs(c["value"] - current["value"]) > 0.001]
            if tied:
                hist = [dict(c) for c in cands]
                current = {k: v for k, v in cands[0].items() if k not in ("value", "direct", "indirect", "raw")}
                current["value"] = None
                current["scope"] = "unresolved"
                current["conflicting_values"] = sorted({c["value"] for c in [cands[0], *tied]})
            # 現在値と意味（kind）が異なる候補や基準日が異なる候補があることを明示
            if hist:
                current["history"] = hist
                if any((h.get("as_of") != current.get("as_of")) for h in hist):
                    current["has_older_values"] = True
                # 同じ意味・同じ時点で値が食い違う候補（丸め差 0.1pt 以内は同一とみなす）
                if any(h.get("value") is not None and current.get("value") is not None
                       and h.get("as_of") == current.get("as_of") and h.get("kind") == current.get("kind")
                       and abs(h["value"] - current["value"]) > 0.001
                       for h in hist):
                    current["conflict_same_period"] = True
            attrs[k] = current


def evidence_sort_key(e: dict) -> tuple:
    return (-(_date_int(e.get("as_of"))), TIER_ORDER.get(e.get("source_tier"), 9), e.get("doc_id") or "", e.get("url") or "")


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
    total = row.get("ratio_total")
    indirect = row.get("ratio_indirect")
    if total is None and indirect is None:
        return None
    attr = {
        # value は「合計（直接＋間接）」。括弧内の間接だけしか読めなかった場合は合計不明として value=None
        "value": total,
        "kind": kind,
        "scope": "total" if total is not None else "indirect_only",
        "indirect": indirect,
        "raw": row.get("ratio_raw"),
        "as_of": row.get("as_of") or row.get("period_end"),
        "doc_id": row.get("doc_id"),
    }
    if total is not None and indirect is not None and indirect <= total:
        attr["direct"] = round(total - indirect, 4)
    return attr


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
            large = row.get("report_kind") == "large_holding_report"
            ev = edinet_evidence(row, retrieved, {
                "property": "large_holding_report" if large else "shareholder",
                "note": "大株主の状況の注記に記載された大量保有報告書の写し（株券等保有割合）" if large else None,
            })
            builder.add(counterparty, filer_node, rel_type,
                        {"ownership_ratio": ratio_attribute(row, "share_large_holding" if large else "share")}, ev)
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


_AGREED_RE = re.compile(r"agreed to|agreement to|will (acquire|establish|form)|plans? to|intends? to|予定|合意|"
                        r"締結(し|いた)|決議|方針|基本合意|MOU|覚書", re.I)
_COMPLETED_RE = re.compile(r"completed|has acquired|acquired (in|on)|established (in|on)|完了|取得(し|いた)しました|"
                           r"買収(し|いた)しました|設立(し|いた)しました|子会社化(し|いた)しました|開始(し|いた)しました", re.I)
_YEAR_RE = re.compile(r"(?<!\d)(19[89]\d|20[0-3]\d)(?=年|\b)")


def valid_date(d: str | None) -> str | None:
    if not d or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
        return None
    try:
        dt.date.fromisoformat(d)
    except ValueError:
        return None
    if d > GENERATED_AT:
        return None  # 未来日は抽出誤り
    return d


def deal_status(quote: str | None) -> str | None:
    """公表文から 合意（agreed）／実行済み（executed）を推定。判定できなければ None。"""
    if not quote:
        return None
    if _COMPLETED_RE.search(quote):
        return "executed"
    if _AGREED_RE.search(quote):
        return "agreed"
    return None


def historical_year(quote: str | None, published: str | None) -> int | None:
    """公表文が 2 年以上前の年に言及していれば、その年（沿革の言及）を返す。"""
    if not quote:
        return None
    years = [int(y) for y in _YEAR_RE.findall(quote)]
    if not years:
        return None
    ref = int(published[:4]) if published else int(GENERATED_AT[:4])
    old = [y for y in years if ref - y >= 2]
    return min(old) if old else None


IR_DIRECTION = {
    "ownership": "out", "major_customer": "out", "merger_acquisition": "out", "technology_license": "out",
    "business_alliance": "out", "capital_alliance": "out", "joint_venture": "out", "joint_research": "out",
}


def add_ir_relations(builder: RelationBuilder, ir_rows: list[dict], retrieved: str | None) -> None:
    """IR 抽出行の投入（Issue #6）。根拠文の検証（ir_validate）に通った行だけ confirmed にし、
    根拠が不足する行は needs_review として理由を残す。"""
    import edinet_tables as et
    from ir_validate import validate

    n = 0
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    n_retyped = 0
    for row in ir_rows:
        filer_code = row.get("filer_sec_code")
        rel_type = row.get("relation_type")
        if filer_code not in builder.companies or rel_type not in RELATION_TYPES:
            continue
        problem = et.name_problem(row.get("counterparty_name"))
        if problem:
            builder.reject(row, f"name:{problem}", "ir")
            continue
        counterparty = builder.resolve_node(name=row.get("counterparty_name"))
        if counterparty is None:
            continue
        filer = builder.companies[filer_code]
        filer_names = [filer.get("name"), filer.get("name_edinet"), *(filer.get("aliases") or [])]
        verdict = validate(row, [x for x in filer_names if x])
        rel_type = verdict.get("resolved_type") or rel_type
        filer_node = {"type": "listed", "key": filer_code}
        # 方向: 根拠文の手がかり（in = 相手が主体）> LLM の direction > 既定（提出会社が主体）
        direction = verdict.get("direction") or row.get("direction") or IR_DIRECTION.get(rel_type, "out")
        source, target = (filer_node, counterparty) if direction != "in" else (counterparty, filer_node)
        published = valid_date(row.get("date"))
        quote = row.get("evidence_quote") or None
        deal = row.get("status") if row.get("status") in ("agreed", "executed") else deal_status(quote)
        event_year = historical_year(quote, published)
        evidence = {
            "source": "ir_disclosure", "source_tier": "llm_extraction", "url": row.get("source_url"),
            "quote": quote, "as_of": published, "published": published,
            "retrieved": retrieved, "confidence": "low", "filer_sec_code": filer_code,
            "extraction": {
                "cue": verdict.get("cue"), "reasons": verdict.get("reasons") or [],
                "llm_type": row.get("relation_type"),
            },
        }
        if verdict.get("retyped_from"):
            evidence["extraction"]["retyped_from"] = verdict["retyped_from"]
            n_retyped += 1
        if verdict.get("suggested_type"):
            evidence["extraction"]["suggested_type"] = verdict["suggested_type"]
        if deal:
            evidence["deal_status"] = deal
        if event_year:
            evidence["event_year"] = event_year
            evidence["note"] = f"公表文は{event_year}年の出来事に言及（公表日と時点が異なる）"
        attrs = {}
        if deal:
            attrs["deal_status"] = deal
        if event_year:
            attrs["event_year"] = event_year
        status = verdict["status"]
        reasons = [f"ir:{r}" for r in verdict.get("reasons") or []]
        builder.add(source, target, rel_type, attrs, evidence, status=status, reasons=reasons)
        n += 1
        by_type[rel_type] = by_type.get(rel_type, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
    print(f"IR 由来エッジ投入: {n} 行（{by_type}） 判定 {by_status} / 根拠に基づく読み替え {n_retyped}")


# ---------------------------------------------------------------------------
# 確認済み訂正（corrections.json）
# ---------------------------------------------------------------------------

CORRECTIONS_PATH = BASE_DIR / "corrections.json"


def _match_ref(builder: RelationBuilder, spec: str) -> dict | None:
    """'listed:7203' / 'name:○○' を node 参照に解決する。"""
    kind, _, val = spec.partition(":")
    if kind == "listed":
        return {"type": "listed", "key": val} if val in builder.companies else None
    if kind == "entity":
        return {"type": "entity", "key": val} if val in builder.entities else None
    if kind == "name":
        code = builder.resolve_listed(name=val)
        if code:
            return {"type": "listed", "key": code}
        ent = builder._entity_index.get(normalize_name(val))
        return {"type": "entity", "key": ent} if ent else None
    return None


def _find_relation(builder: RelationBuilder, match: dict) -> tuple[tuple | None, dict | None]:
    s = _match_ref(builder, match["source"])
    t = _match_ref(builder, match["target"])
    if s is None or t is None:
        return None, None
    key = (s["type"], s["key"], t["type"], t["key"], match["relation_type"])
    return key, builder.relations.get(key)


def apply_corrections(builder: RelationBuilder, corrections: dict) -> list[dict]:
    """原本で確認した訂正を適用する。適用結果（前後の状態）を返し、レポート用に保存する。

    action:
      set_status   : status / review_reasons を変更（要確認への隔離、確認済みへの昇格）
      retype       : relation_type と方向（swap）を変更。元の evidence は保持し、検証 evidence を追加
      set_ratio    : 比率の現在値を検証済み値にし、抽出値は history に残す
      supersede    : 旧関係を status=historical（valid_until=as_of）にし、新関係を追加
      remove       : 関係を削除し quarantine に記録
    いずれも relation.verification に {status, on, by, source, note} を残す。
    """
    log: list[dict] = []
    for c in corrections.get("relations", []):
        key, rel = _find_relation(builder, c["match"])
        entry = {"id": c.get("id"), "action": c["action"], "match": c["match"], "applied": False}
        if rel is None:
            entry["note"] = "対象の関係が見つからない（再生成で消えたか名寄せ失敗）"
            log.append(entry)
            continue
        verification = {
            "status": "verified", "on": c.get("verified_on"), "by": c.get("verified_by", "manual"),
            "source": c.get("source"), "as_of": c.get("as_of"), "note": c.get("reason"),
        }
        ver_evidence = {
            "source": "official_release", "source_tier": "primary", "confidence": "high",
            "url": (c.get("source") or {}).get("url"), "as_of": c.get("as_of"),
            "published": (c.get("source") or {}).get("published"), "retrieved": c.get("verified_on"),
            "note": c.get("reason"), "verification": "verified",
        }
        before = {"relation_type": rel["relation_type"], "status": rel["status"],
                  "source": rel["source"], "target": rel["target"],
                  "ownership_ratio": _strip_hist(rel["attributes"].get("ownership_ratio"))}
        action = c["action"]
        if action == "set_status":
            rel["status"] = c["status"]
            for r in c.get("review_reasons", []):
                if r not in rel["review_reasons"]:
                    rel["review_reasons"].append(r)
            rel["verification"] = verification
            rel["evidence"].append(ver_evidence)
        elif action == "retype":
            new_type = c.get("relation_type", rel["relation_type"])
            s, t = rel["source"], rel["target"]
            if c.get("swap"):
                s, t = t, s
            meta = RELATION_TYPES[new_type]
            if not meta["directed"] and (s["type"], s["key"]) > (t["type"], t["key"]):
                s, t = t, s
            del builder.relations[key]
            new_key = (s["type"], s["key"], t["type"], t["key"], new_type)
            existing = builder.relations.get(new_key)
            if existing is not None:
                # 訂正先に既に関係がある（誤った親子関係と正しい関連会社関係が重複している典型）:
                # 双方の evidence・比率候補・要確認理由を保持して統合する
                for ev in rel["evidence"]:
                    if not any(_same_evidence(e, ev) for e in existing["evidence"]):
                        existing["evidence"].append(ev)
                for k2, v2 in rel["attributes"].items():
                    if isinstance(v2, dict) and "candidates" in v2:
                        for cand in v2["candidates"]:
                            merge_attributes(existing["attributes"], {k2: cand}, ver_evidence)
                    elif existing["attributes"].get(k2) is None:
                        existing["attributes"][k2] = v2
                for r2 in rel.get("review_reasons", []):
                    if r2 not in existing["review_reasons"]:
                        existing["review_reasons"].append(r2)
                existing["status"] = c.get("status", "confirmed")
                existing["verification"] = verification
                existing["evidence"].append(ver_evidence)
                rel = existing
            else:
                rel.update({"relation_type": new_type, "category": meta["category"], "directed": meta["directed"],
                            "source": s, "target": t, "status": c.get("status", "confirmed"), "verification": verification})
                rel["evidence"].append(ver_evidence)
                builder.relations[new_key] = rel
        elif action == "set_ratio":
            new_ratio = dict(c["ownership_ratio"])
            new_ratio.setdefault("as_of", c.get("as_of"))
            new_ratio.setdefault("status", "executed")
            new_ratio["verified"] = True
            merge_attributes(rel["attributes"], {"ownership_ratio": new_ratio}, ver_evidence)
            rel["verification"] = verification
            rel["evidence"].append(ver_evidence)
        elif action == "supersede":
            rel["status"] = "historical"
            rel["valid_until"] = c.get("as_of")
            rel["verification"] = verification
            rel["evidence"].append(ver_evidence)
            new = c.get("new")
            if new:
                s, t = rel["source"], rel["target"]
                if new.get("swap"):
                    s, t = t, s
                attrs = {}
                if new.get("ownership_ratio"):
                    attrs["ownership_ratio"] = {**new["ownership_ratio"], "as_of": new["ownership_ratio"].get("as_of", c.get("as_of")),
                                                "status": new["ownership_ratio"].get("status", "executed"), "verified": True}
                created = builder.add(s, t, new["relation_type"], attrs, dict(ver_evidence), status="confirmed")
                if created is not None:
                    created["verification"] = verification
                    rel["superseded_by"] = (s["type"], s["key"], t["type"], t["key"], new["relation_type"])
        elif action == "remove":
            del builder.relations[key]
            builder.reject({"relation": before, "correction": c.get("id")}, f"correction:{c.get('reason')}", "corrections")
        else:
            entry["note"] = f"未知の action: {action}"
            log.append(entry)
            continue
        entry.update({"applied": True, "before": before, "after": {
            "relation_type": rel["relation_type"], "status": rel["status"], "source": rel["source"], "target": rel["target"],
            "ownership_ratio": _strip_hist(rel["attributes"].get("ownership_ratio"))}})
        log.append(entry)
    return log


def _strip_hist(v):
    if isinstance(v, dict):
        return {k: vv for k, vv in v.items() if k not in ("history", "candidates")} | (
            {"candidates": len(v["candidates"])} if "candidates" in v else {})
    return v


def resolve_superseded_refs(relations: list[dict]) -> None:
    """finalize 後に superseded_by のキーを relation_id に置き換える。"""
    by_key = {(r["source"]["type"], r["source"]["key"], r["target"]["type"], r["target"]["key"], r["relation_type"]): r["relation_id"]
              for r in relations}
    for r in relations:
        k = r.get("superseded_by")
        if isinstance(k, (list, tuple)):
            r["superseded_by"] = by_key.get(tuple(k))


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
    corrections = json.loads(CORRECTIONS_PATH.read_text(encoding="utf-8")) if CORRECTIONS_PATH.exists() else {}
    correction_log = apply_corrections(builder, corrections)
    print(f"訂正適用: {sum(1 for c in correction_log if c['applied'])}/{len(correction_log)} 件")
    for c in correction_log:
        if not c["applied"]:
            print(f"   WARN 未適用 {c.get('id')}: {c.get('note')}", file=sys.stderr)
    entities, relations = builder.finalize()
    resolve_superseded_refs(relations)

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
            "historical": "確認済みの後続開示により過去の状態となった関係（valid_until まで有効）",
        },
        "relation_types": RELATION_TYPES,
        "entities": entities,
        "relations": relations,
    }

    MASTERS_DIR.mkdir(parents=True, exist_ok=True)
    (MASTERS_DIR / "M4_companies.json").write_text(json.dumps(m4, ensure_ascii=False, indent=1), encoding="utf-8")
    (MASTERS_DIR / "M5_company_relations.json").write_text(json.dumps(m5, ensure_ascii=False, indent=1), encoding="utf-8")
    (MASTERS_DIR / "entity_merges.json").write_text(
        json.dumps({"generated_at": GENERATED_AT, **builder.merge_report}, ensure_ascii=False, indent=1), encoding="utf-8")
    (MASTERS_DIR / "corrections_applied.json").write_text(
        json.dumps({"generated_at": GENERATED_AT, "log": correction_log}, ensure_ascii=False, indent=1), encoding="utf-8")
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
