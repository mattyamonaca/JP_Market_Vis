"""Prevent unsupported IR excerpts and duplicate URLs inflating contribution."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_masters import RelationBuilder, add_ir_relations, add_officer_relations
from ir_validate import mentions
from ir_source_checks import row_key
from official_relations import add_official_relations
from source_contribution import contribution


COMPANIES = {"0001": {"name": "甲株式会社"}, "0002": {"name": "乙株式会社"}}
ROW = {"filer_sec_code": "0001", "counterparty_name": "乙株式会社", "relation_type": "business_alliance",
       "evidence_quote": "甲株式会社と乙株式会社は業務提携契約を締結しました。", "source_url": "https://example.com/release", "date": "2026-01-01"}


class Provenance(unittest.TestCase):
    def test_different_japanese_legal_forms_are_not_same_listed_company(self):
        b = RelationBuilder({"0001": {"name": "株式会社神戸物産"}})
        self.assertIsNone(b.resolve_listed(name="有限会社神戸物産"))
        self.assertIsNone(b.resolve_listed(name="神戸物産合同会社"))
        self.assertEqual(b.resolve_listed(name="神戸物産(株)"), "0001")

    def test_exact_nonlisted_legal_name_is_not_merged_with_listed_parent(self):
        b = RelationBuilder({"9435": {"name": "株式会社光通信"}, "0001": {"name": "甲株式会社"}})
        self.assertEqual(b.resolve_listed(name="株式会社光通信"), "9435")
        refs = [b.resolve_node(name=n) for n in ["光通信株式会社", "光通信(株)", "光通信㈱"]]
        self.assertTrue(all(r["type"] == "entity" for r in refs))
        self.assertEqual(refs[0], refs[1])
        self.assertEqual(refs[1], refs[2])
        self.assertIn("子会社", b.entities[refs[0]["key"]]["name"])

    def test_shared_brand_does_not_identify_the_legal_counterparty(self):
        self.assertFalse(mentions("Alpha Japanとの業務提携を開始", "Alpha Global Holdings"))
        self.assertTrue(mentions("乙株式会社と業務提携を開始", "乙株式会社"))

    def test_adviser_is_not_promoted_to_director_overlap(self):
        b = RelationBuilder(COMPANIES)
        add_officer_relations(b, [{"kind": "officers", "filer_sec_code": "0001", "counterparty_name": "乙株式会社",
            "person": "山田太郎", "role_at_filer": "社外取締役", "role_at_counterparty": "特別顧問",
            "doc_id": "TEST", "submit_date": "2026-01-01"}], "2026-09-21")
        rel = next(iter(b.relations.values()))
        self.assertEqual(rel["status"], "needs_review")
        self.assertEqual(contribution([rel])["edinet_supported"], 0)

    def test_nonstatutory_executive_officer_alone_does_not_prove_officer_overlap(self):
        for role, expected in [("常務執行役員", "needs_review"), ("常務執行役", "confirmed"), ("取締役兼執行役員", "confirmed")]:
            with self.subTest(role=role):
                b = RelationBuilder(COMPANIES)
                add_officer_relations(b, [{"kind": "officers", "filer_sec_code": "0001", "counterparty_name": "乙株式会社",
                    "person": "山田太郎", "role_at_filer": "社外取締役", "role_at_counterparty": role,
                    "doc_id": "TEST", "submit_date": "2026-01-01"}], "2026-09-21")
                self.assertEqual(next(iter(b.relations.values()))["status"], expected)

    def test_missing_or_changed_excerpt_is_not_confirmed(self):
        for checks in ({}, {row_key(ROW): {"status": "excerpt_not_found"}}):
            b = RelationBuilder(COMPANIES)
            add_ir_relations(b, [ROW], "2026-09-21", checks)
            rel = next(iter(b.relations.values()))
            self.assertEqual(rel["status"], "needs_review")
            self.assertEqual(rel["evidence"][0]["support_status"], "needs_review")
        changed = {**ROW, "evidence_quote": ROW["evidence_quote"] + "変更"}
        b = RelationBuilder(COMPANIES)
        add_ir_relations(b, [changed], "2026-09-21", {row_key(ROW): {"status": "excerpt_found"}})
        self.assertEqual(next(iter(b.relations.values()))["status"], "needs_review")

    def test_literal_match_does_not_upgrade_extraction_confidence(self):
        b = RelationBuilder(COMPANIES)
        add_ir_relations(b, [ROW], "2026-09-21", {row_key(ROW): {"status": "excerpt_found"}})
        rel = next(iter(b.relations.values()))
        self.assertEqual(rel["status"], "confirmed")
        self.assertEqual(rel["evidence"][0]["confidence"], "low")
        self.assertNotIn("verification", rel["evidence"][0])

    def test_same_url_failed_excerpt_does_not_hide_a_supported_excerpt(self):
        b = RelationBuilder(COMPANIES)
        changed = {**ROW, "evidence_quote": "甲株式会社は乙株式会社と業務提携を開始した。"}
        checks = {row_key(ROW): {"status": "excerpt_not_found"}, row_key(changed): {"status": "excerpt_found"}}
        add_ir_relations(b, [ROW, changed], "2026-09-21", checks)
        rel = next(iter(b.relations.values()))
        self.assertEqual(rel["status"], "confirmed")
        self.assertEqual(contribution([rel])["other_supported"], 1)

    def test_unconfirmed_ir_does_not_count_as_independent_support(self):
        b = RelationBuilder(COMPANIES)
        add_ir_relations(b, [ROW], "2026-09-21", {})
        rel = next(iter(b.relations.values()))
        rel["status"] = "confirmed"
        rel["evidence"] += [{"source": "edinet"}, {"source": "edinet"}]
        result = contribution([rel])
        self.assertEqual(result["edinet_supported"], 1)
        self.assertEqual(result["other_supported"], 0)
        rel["evidence"] += [{"source": "official_release"}, {"source": "official_release"}]
        result = contribution([rel])
        self.assertEqual(result["other_supported"], 1)
        self.assertEqual(result["buckets"], {"both": 1})

    def test_republished_filing_is_not_an_independent_source(self):
        rel = {"status": "confirmed", "source": {"type": "listed"}, "target": {"type": "listed"},
               "relation_type": "ownership", "evidence": [{"source": "official_release", "origin": "edinet_republication"}]}
        self.assertEqual(contribution([rel])["edinet_supported"], 1)
        self.assertEqual(contribution([rel])["other_supported"], 0)

    def test_official_directors_merge_people_without_space_duplicates(self):
        b = RelationBuilder(COMPANIES)
        b.add({"type": "listed", "key": "0001"}, {"type": "listed", "key": "0002"},
              "interlocking_director", {"persons": [{"name": "山田 太郎"}]}, {"source": "edinet"})
        row = {"id": "person", "source": {"code": "0001"}, "target": {"code": "0002"},
               "relation_type": "interlocking_director", "person": "山田太郎",
               "roles": {"0001": "取締役", "0002": "監査役"}, "as_of": None,
               "document": {"url": "https://example.com/officers", "origin": "independent_primary_website"},
               "review": {"on": "2026-09-21", "by": "test", "status": "source_checked"}}
        add_official_relations(b, [row, {**row, "id": "person2", "person": "佐藤花子"}])
        relation = next(iter(b.relations.values()))
        self.assertEqual(len(relation["attributes"]["persons"]), 2)
        self.assertEqual(len(relation["evidence"]), 3)

    def test_primary_release_requires_known_parties_and_review(self):
        row = {"id": "fixture", "source": {"code": "0001"}, "target": {"code": "0002"},
               "relation_type": "business_alliance", "document": {"url": "https://example.com/release",
               "published": "2026-01-01", "origin": "independent_primary_release"},
               "review": {"on": "2026-09-21", "by": "test", "status": "source_checked"}}
        for path, value in (("origin", "edinet_mirror"), ("target", "9999"), ("status", "candidate")):
            bad = copy.deepcopy(row)
            if path == "origin": bad["document"][path] = value
            elif path == "target": bad[path]["code"] = value
            else: bad["review"][path] = value
            with self.assertRaises(ValueError):
                add_official_relations(RelationBuilder(COMPANIES), [bad])
        b = RelationBuilder(COMPANIES)
        add_official_relations(b, [row, row])
        self.assertEqual(len(b.relations), 1)
        self.assertEqual(len(next(iter(b.relations.values()))["evidence"]), 1)


if __name__ == "__main__":
    unittest.main()
