"""別名辞書と名寄せのテスト（Issue #4）。別法人の誤統合を防ぐことを含む。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import aliases as al  # noqa: E402
import build_masters as bm  # noqa: E402

COMPANIES = {
    "9533": {"name": "東邦瓦斯", "name_edinet": "東邦瓦斯株式会社", "name_kana": "トウホウガスカブシキガイシャ", "aliases": ["東邦ガス"]},
    "6758": {"name": "ソニーグループ", "name_edinet": "ソニーグループ株式会社", "aliases": ["ソニー"]},
    "7203": {"name": "トヨタ自動車", "name_edinet": "トヨタ自動車株式会社", "name_kana": "トヨタジドウシャカブシキカイシャ", "aliases": ["トヨタ"]},
    "8267": {"name": "イオン", "name_edinet": "イオン株式会社", "aliases": []},
    "7512": {"name": "イオン北海道", "name_edinet": "イオン北海道株式会社", "aliases": []},
    "9064": {"name": "ヤマトホールディングス", "name_edinet": "ヤマトホールディングス株式会社", "aliases": []},
    "2501": {"name": "サッポロホールディングス", "name_edinet": None, "aliases": []},
    "8031": {"name": "三井物産", "name_edinet": "三井物産株式会社", "aliases": []},
}


class MatchKeys(unittest.TestCase):
    def test_kanji_variant_and_legal_form(self):
        self.assertEqual(al.match_key("東邦瓦斯株式会社"), al.match_key("東邦ガス"))
        self.assertEqual(al.match_key("株式会社髙松コンストラクショングループ"), al.match_key("高松コンストラクショングループ"))
        self.assertEqual(al.match_key("Ceva Santé Animale SA"), al.match_key("Ceva Santé Animale社"))
        self.assertEqual(al.match_key("Ceva Sante Animale S.A."), al.match_key("Ceva Santé Animale"))

    def test_holdings_is_not_stripped(self):
        self.assertNotEqual(al.match_key("ヤマトホールディングス"), al.match_key("ヤマト"))
        self.assertNotEqual(al.match_key("ソニーグループ"), al.match_key("ソニー"))
        self.assertNotEqual(al.match_key("イオン北海道"), al.match_key("イオン"))

    def test_kana_key(self):
        self.assertEqual(al.kana_key("トヨタジドウシャカブシキカイシャ"), "とよたじどうしゃ")
        self.assertEqual(al.kana_key("トウホウガスカブシキガイシャ"), "とうほうがす")


class Resolution(unittest.TestCase):
    def setUp(self):
        self.idx = al.AliasIndex(COMPANIES)

    def test_tohogas_resolves_to_9533(self):
        for n in ("東邦ガス", "東邦瓦斯株式会社", "東邦ガス株式会社", "東邦瓦斯㈱"):
            self.assertEqual(self.idx.resolve_listed(n)[0], "9533", n)

    def test_bare_alias_does_not_capture_other_legal_entity(self):
        self.assertEqual(self.idx.resolve_listed("ソニー")[0], "6758")
        self.assertEqual(self.idx.resolve_listed("ソニーグループ株式会社")[0], "6758")
        self.assertIsNone(self.idx.resolve_listed("ソニー株式会社")[0])  # 事業会社は別法人
        self.assertIsNone(self.idx.resolve_listed("ソニー㈱")[0])

    def test_parent_and_subsidiary_stay_distinct(self):
        self.assertEqual(self.idx.resolve_listed("イオン(株)")[0], "8267")
        self.assertEqual(self.idx.resolve_listed("イオン北海道株式会社")[0], "7512")
        self.assertIsNone(self.idx.resolve_listed("ヤマト運輸株式会社")[0])
        self.assertIsNone(self.idx.resolve_listed("サッポロビール株式会社")[0])
        self.assertIsNone(self.idx.resolve_listed("三井物産インターナショナル")[0])

    def test_incompatible_edinet_name_is_not_an_alias(self):
        self.assertFalse(al.compatible_official_names("サッポロホールディングス", "サッポロビール株式会社"))
        self.assertTrue(al.compatible_official_names("高松コンストラクショングループ", "株式会社髙松コンストラクショングループ"))
        self.assertTrue(al.compatible_official_names("あい　ホールディングス", "あいホールディングス株式会社"))

    def test_entity_alias_merges_ceva_and_records_reason(self):
        b = bm.RelationBuilder(COMPANIES)
        rows = [{"filer_sec_code": "8031", "counterparty_name": n, "relation_type": t, "date": "2026-06-01",
                 "evidence_quote": "x", "source_url": "https://example.com"}
                for n, t in (("Ceva Santé Animale SA", "joint_venture"), ("Ceva Santé Animale社", "business_alliance"))]
        bm.add_ir_relations(b, rows, "2026-06-13")
        a = b.resolve_node(name="Ceva Santé Animale SA")
        c = b.resolve_node(name="Ceva Santé Animale社")
        self.assertEqual(a, c)
        self.assertEqual(b.entities[a["key"]]["name"], "Ceva Santé Animale")
        self.assertIn("Ceva Santé Animale SA", b.entity_merges[a["key"]])
        ents, rels = b.finalize()
        self.assertEqual(len(ents), 1)
        self.assertEqual(len(rels), 2)  # 別タイプの関係は統合せず証拠ごとに残る
        ent = next(iter(b.merge_report["entities"].values()))
        self.assertEqual(ent["name"], "Ceva Santé Animale")
        self.assertIn("Ceva Santé Animale社", ent["merged_names"])

    def test_tohogas_relation_becomes_listed_to_listed(self):
        b = bm.RelationBuilder(COMPANIES)
        bm.add_ir_relations(b, [{"filer_sec_code": "7203", "counterparty_name": "東邦ガス株式会社",
                                 "relation_type": "joint_research", "date": "2026-03-24",
                                 "evidence_quote": "x", "source_url": "https://example.com"}], "2026-06-13")
        ents, rels = b.finalize()
        self.assertEqual({rels[0]["source"]["key"], rels[0]["target"]["key"]}, {"7203", "9533"})
        self.assertEqual(rels[0]["source"]["type"], "listed")
        self.assertEqual(b.merge_report["listed"]["9533"], {"東邦ガス株式会社": "official_name"})


if __name__ == "__main__":
    unittest.main()
