"""統合処理（build_masters.py）のテスト（Issue #1 / #2）。

- 分類ごとの関係タイプと方向
- 比率の意味（合計／直接／間接、議決権／株式数）と基準日
- 取得順に依存しない現在値の選択と履歴の保持
- 50%以下という理由だけで親子関係を削除しないこと
- IR 抽出の合意／実行済み・沿革言及の判定
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import build_masters as bm  # noqa: E402

COMPANIES = {
    "4661": {"name": "オリエンタルランド", "corporate_number": "1", "wikidata_qid": None},
    "9009": {"name": "京成電鉄", "corporate_number": "2", "wikidata_qid": None},
    "7512": {"name": "イオン北海道", "corporate_number": "3", "wikidata_qid": None},
    "8267": {"name": "イオン", "corporate_number": "4", "wikidata_qid": None},
    "8002": {"name": "丸紅", "corporate_number": "5", "wikidata_qid": None},
}


def row(filer, name, cls, owned, total, indirect=None, doc="S1", period="2025-03-31", kind="affiliated", **extra):
    return {
        "filer_sec_code": filer, "doc_id": doc, "period_end": period, "submit_date": "2025-06-20", "kind": kind,
        "counterparty_name": name, "raw_name": name, "name_problem": None,
        "classification": cls, "classification_source": "section" if cls else None,
        "owned_by_counterparty": owned, "direction_source": "classification", "direction_conflict": False,
        "ratio_total": total, "ratio_indirect": indirect, "ratio_raw": f"{total} ({indirect})",
        "relationship_note": None, "table_index": 0, "row_index": 1, **extra,
    }


def build(rows, ir_rows=()):
    b = bm.RelationBuilder(COMPANIES)
    bm.add_edinet_relations(b, list(rows), "2026-09-09")
    if ir_rows:
        bm.add_ir_relations(b, list(ir_rows), "2026-06-13")
    return b.finalize()


def find(rels, s, t, typ):
    for r in rels:
        if r["source"]["key"] == s and r["target"]["key"] == t and r["relation_type"] == typ:
            return r
    return None


class ClassificationDirection(unittest.TestCase):
    def test_other_affiliated_company_becomes_affiliate_from_counterparty(self):
        ents, rels = build([row("4661", "京成電鉄", "その他の関係会社", True, 0.2014, 0.0007)])
        self.assertIsNone(find(rels, "4661", "9009", "parent_subsidiary"))
        rel = find(rels, "9009", "4661", "affiliate")
        self.assertIsNotNone(rel)
        self.assertEqual(rel["status"], "confirmed")
        self.assertAlmostEqual(rel["attributes"]["ownership_ratio"]["value"], 0.2014)
        self.assertAlmostEqual(rel["attributes"]["ownership_ratio"]["indirect"], 0.0007)
        self.assertAlmostEqual(rel["attributes"]["ownership_ratio"]["direct"], 0.2007)
        self.assertEqual(rel["attributes"]["ownership_ratio"]["kind"], "voting")
        self.assertEqual(rel["attributes"]["ownership_ratio"]["as_of"], "2025-03-31")

    def test_parent_row_reverses_direction(self):
        ents, rels = build([row("7512", "イオン", "親会社", True, 0.672, 0.016)])
        rel = find(rels, "8267", "7512", "parent_subsidiary")
        self.assertIsNotNone(rel)
        self.assertAlmostEqual(rel["attributes"]["ownership_ratio"]["direct"], 0.656)
        self.assertIsNone(find(rels, "7512", "8267", "parent_subsidiary"))

    def test_unclassified_is_not_promoted_to_subsidiary(self):
        ents, rels = build([row("4661", "某社", None, False, 1.0)])
        self.assertIsNone(find(rels, "4661", "ENT000001", "parent_subsidiary"))
        rel = find(rels, "4661", "ENT000001", "ownership")
        self.assertEqual(rel["status"], "needs_review")
        self.assertIn("unclassified", rel["review_reasons"])

    def test_subsidiary_below_fifty_percent_is_kept(self):
        ents, rels = build([row("4661", "某社", "連結子会社", False, 0.4)])
        rel = find(rels, "4661", "ENT000001", "parent_subsidiary")
        self.assertIsNotNone(rel)
        self.assertEqual(rel["status"], "confirmed")

    def test_bad_names_are_quarantined(self):
        b = bm.RelationBuilder(COMPANIES)
        bm.add_edinet_relations(b, [row("4661", "(87.74)", "連結子会社", False, None, name_problem="numeric_only")], None)
        self.assertEqual(len(b.relations), 0)
        self.assertEqual(b.quarantine[0]["reason"], "name:numeric_only")


class RatioSemantics(unittest.TestCase):
    def test_indirect_only_is_not_shown_as_total(self):
        ents, rels = build([row("4661", "某社", "連結子会社", False, None, 0.8774)])
        attr = find(rels, "4661", "ENT000001", "parent_subsidiary")["attributes"]["ownership_ratio"]
        self.assertIsNone(attr["value"])
        self.assertEqual(attr["scope"], "indirect_only")

    def test_newest_period_wins_regardless_of_order(self):
        old = row("4661", "某社", "連結子会社", False, 1.0, doc="S_OLD", period="2025-03-31")
        new = row("4661", "某社", "持分法適用関連会社", False, 0.164, doc="S_NEW", period="2026-03-31")
        for order in ((old, new), (new, old)):
            ents, rels = build(order)
            aff = find(rels, "4661", "ENT000001", "affiliate")
            par = find(rels, "4661", "ENT000001", "parent_subsidiary")
            self.assertEqual(aff["attributes"]["ownership_ratio"]["as_of"], "2026-03-31")
            self.assertEqual(par["attributes"]["ownership_ratio"]["as_of"], "2025-03-31")
            self.assertEqual([e["doc_id"] for e in aff["evidence"]], ["S_NEW"])

    def test_same_relation_two_periods_keeps_history_and_current_is_newest(self):
        r1 = row("4661", "某社", "連結子会社", False, 0.9, doc="S_A", period="2025-03-31")
        r2 = row("4661", "某社", "連結子会社", False, 0.95, doc="S_B", period="2026-03-31")
        results = []
        for order in ((r1, r2), (r2, r1)):
            ents, rels = build(order)
            attr = find(rels, "4661", "ENT000001", "parent_subsidiary")["attributes"]["ownership_ratio"]
            results.append((attr["value"], attr["as_of"], [(h["value"], h["as_of"]) for h in attr["history"]]))
            self.assertTrue(attr["has_older_values"])
            self.assertEqual([e["doc_id"] for e in find(rels, "4661", "ENT000001", "parent_subsidiary")["evidence"]],
                             ["S_B", "S_A"])
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0][0], 0.95)

    def test_voting_and_share_ratios_are_kept_apart(self):
        vote = row("4661", "某社", None, False, 0.3, doc="S_A")
        share = row("4661", "某社", None, False, 0.28, doc="S_A", kind="shareholder", as_of="2025-03-31")
        share["owned_by_counterparty"] = None
        ents, rels = build([vote, share])
        # 大株主行は 相手→提出会社、分類不明の所有行は 提出会社→相手
        own = find(rels, "ENT000001", "4661", "ownership")
        self.assertEqual(own["attributes"]["ownership_ratio"]["kind"], "share")
        rev = find(rels, "4661", "ENT000001", "ownership")
        self.assertEqual(rev["attributes"]["ownership_ratio"]["kind"], "voting")

    def test_entity_ids_do_not_depend_on_insertion_order(self):
        a = row("4661", "甲社", "連結子会社", False, 1.0)
        b = row("4661", "乙社", "連結子会社", False, 1.0)
        e1, _ = build([a, b])
        e2, _ = build([b, a])
        self.assertEqual(e1, e2)


class IrStatus(unittest.TestCase):
    def test_agreed_vs_executed_and_historical_year(self):
        agreed = {"filer_sec_code": "8002", "counterparty_name": "TiAuto Investments Pty Ltd",
                  "relation_type": "merger_acquisition", "date": "2026-06-10",
                  "evidence_quote": "Marubeni Corporation has agreed to acquire TiAuto Investments Pty Ltd",
                  "source_url": "https://example.com/a"}
        hist = {"filer_sec_code": "8002", "counterparty_name": "B-Quik Co., Ltd",
                "relation_type": "merger_acquisition", "date": None,
                "evidence_quote": "Marubeni entered the car maintenance business in Thailand in 2006 through the acquisition of B-Quik Co., Ltd",
                "source_url": "https://example.com/a"}
        ents, rels = build([], ir_rows=[agreed, hist])
        by_name = {ents[r["target"]["key"]]["name"]: r for r in rels}
        self.assertEqual(by_name["TiAuto Investments Pty Ltd"]["attributes"]["deal_status"], "agreed")
        self.assertNotIn("event_year", by_name["TiAuto Investments Pty Ltd"]["attributes"])
        self.assertEqual(by_name["B-Quik Co., Ltd"]["attributes"]["event_year"], 2006)
        self.assertIsNone(by_name["B-Quik Co., Ltd"]["evidence"][0]["as_of"])

    def test_invalid_dates_become_unknown(self):
        self.assertIsNone(bm.valid_date("2025-00-00"))
        self.assertIsNone(bm.valid_date("2031-12-31"))
        self.assertEqual(bm.valid_date("2026-03-24"), "2026-03-24")
        self.assertEqual(bm.deal_status("株式取得を完了しました"), "executed")
        self.assertEqual(bm.deal_status("資本業務提携契約を締結することを決議"), "agreed")
        self.assertIsNone(bm.deal_status("共同で検討"))


class Corrections(unittest.TestCase):
    def _builder(self):
        b = bm.RelationBuilder(COMPANIES)
        bm.add_edinet_relations(b, [row("4661", "ソニーフィナンシャルグループ", "連結子会社", False, 1.0,
                                        doc="S_OLD", period="2025-03-31")], "2026-09-09")
        return b

    def test_supersede_marks_old_as_historical_and_adds_new(self):
        b = self._builder()
        log = bm.apply_corrections(b, {"relations": [{
            "id": "sfg", "match": {"source": "listed:4661", "target": "name:ソニーフィナンシャルグループ",
                                   "relation_type": "parent_subsidiary"},
            "action": "supersede", "as_of": "2025-10-01",
            "new": {"relation_type": "affiliate",
                    "ownership_ratio": {"value": 0.164, "kind": "share", "scope": "total"}},
            "source": {"url": "https://example.com/spin", "published": "2025-10-01"},
            "reason": "スピンオフ実行", "verified_on": "2026-09-09"}]})
        self.assertTrue(log[0]["applied"])
        ents, rels = b.finalize()
        bm.resolve_superseded_refs(rels)
        old = find(rels, "4661", "ENT000001", "parent_subsidiary")
        new = find(rels, "4661", "ENT000001", "affiliate")
        self.assertEqual(old["status"], "historical")
        self.assertEqual(old["valid_until"], "2025-10-01")
        self.assertEqual(old["superseded_by"], new["relation_id"])
        self.assertEqual(new["status"], "confirmed")
        self.assertEqual(new["verification"]["status"], "verified")
        self.assertAlmostEqual(new["attributes"]["ownership_ratio"]["value"], 0.164)
        self.assertEqual(new["attributes"]["ownership_ratio"]["status"], "executed")
        self.assertEqual(new["evidence"][0]["source"], "official_release")

    def test_set_ratio_keeps_extracted_value_in_history(self):
        b = self._builder()
        bm.apply_corrections(b, {"relations": [{
            "id": "x", "match": {"source": "listed:4661", "target": "name:ソニーフィナンシャルグループ",
                                 "relation_type": "parent_subsidiary"},
            "action": "set_ratio", "as_of": "2025-03-31",
            "ownership_ratio": {"value": 0.99, "kind": "voting", "scope": "total"},
            "source": {"url": "https://example.com/x"}, "reason": "原本確認", "verified_on": "2026-09-09"}]})
        ents, rels = b.finalize()
        attr = find(rels, "4661", "ENT000001", "parent_subsidiary")["attributes"]["ownership_ratio"]
        self.assertAlmostEqual(attr["value"], 0.99)
        self.assertTrue(attr["verified"])
        self.assertEqual(attr["history"][0]["value"], 1.0)

    def test_missing_target_is_reported_not_silently_ignored(self):
        b = self._builder()
        log = bm.apply_corrections(b, {"relations": [{
            "id": "nope", "match": {"source": "listed:4661", "target": "name:存在しない社", "relation_type": "affiliate"},
            "action": "remove", "reason": "x"}]})
        self.assertFalse(log[0]["applied"])


if __name__ == "__main__":
    unittest.main()
