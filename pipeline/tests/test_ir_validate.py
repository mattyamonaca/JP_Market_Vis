"""IR 抽出の根拠判定（Issue #6）。固定評価セット fixtures/ir_eval.json を全件通すこと。"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import build_masters as bm  # noqa: E402
import ir_validate as iv  # noqa: E402


class EvalSet(unittest.TestCase):
    def test_all_cases_match(self):
        cases = json.loads((HERE.parent / "fixtures" / "ir_eval.json").read_text(encoding="utf-8"))["cases"]
        self.assertGreaterEqual(len(cases), 25)
        for c in cases:
            got = iv.validate(c["row"])
            exp = c["expected"]
            with self.subTest(c["id"]):
                self.assertEqual(got["status"], exp["status"], got)
                if exp.get("direction"):
                    self.assertEqual(got["direction"], exp["direction"])
                if exp.get("type"):
                    self.assertEqual(got["resolved_type"], exp["type"])

    def test_jr_tokai_license_is_quarantined_with_reason(self):
        row = {"filer_sec_code": "7102", "counterparty_name": "東海旅客鉄道株式会社", "relation_type": "technology_license",
               "date": None, "evidence_quote": "完成した車両は、東海旅客鉄道株式会社の最新型新幹線車両「N700S」をベースとしています",
               "source_url": "https://www.n-sharyo.co.jp/business/tetsudo/topics/tp260519.html"}
        companies = {"7102": {"name": "日本車輌製造", "aliases": []}, "9022": {"name": "東海旅客鉄道", "aliases": ["JR東海"]}}
        b = bm.RelationBuilder(companies)
        bm.add_ir_relations(b, [row], "2026-06-13")
        ents, rels = b.finalize()
        self.assertEqual(rels[0]["status"], "needs_review")
        self.assertIn("ir:tech_basis_only", rels[0]["review_reasons"])
        self.assertEqual(rels[0]["evidence"][0]["extraction"]["reasons"], ["tech_basis_only"])
        self.assertEqual(rels[0]["evidence"][0]["quote"], row["evidence_quote"])

    def test_explicit_positive_is_confirmed_and_direction_in_is_reversed(self):
        companies = {"7229": {"name": "ユタカ技研", "aliases": []}}
        b = bm.RelationBuilder(companies)
        bm.add_ir_relations(b, [{"filer_sec_code": "7229", "counterparty_name": "マザーサングローバルインベストメンツビーブイ",
                                 "relation_type": "ownership", "date": "2026-03-11",
                                 "evidence_quote": "マザーサングローバルインベストメンツビーブイによる当社株式に対する公開買付けの結果に関するお知らせ",
                                 "source_url": "https://example.com"}], "2026-06-13")
        ents, rels = b.finalize()
        self.assertEqual(rels[0]["status"], "confirmed")
        self.assertEqual(rels[0]["source"]["type"], "entity")   # 相手が主体 → 相手→提出会社
        self.assertEqual(rels[0]["target"]["key"], "7229")


if __name__ == "__main__":
    unittest.main()
