"""役員の状況（役員兼任）パーサーの回帰テスト。fixtures は実書類のブロック（令和アカウンティング・ホールディングス S100VYST）。"""
import unittest
from pathlib import Path

import edinet_officers as eo

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


class OfficerParserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (FIXTURES / "reiwa_S100VYST_officers.html").read_text(encoding="utf-8")
        cls.officers, cls.notes = eo.parse_officers(cls.raw)
        cls.rows = eo.extract_officer_positions(cls.raw, "令和アカウンティング・ホールディングス株式会社")

    def test_roster_rows_are_recovered_with_careers(self):
        self.assertEqual(len(self.officers), 5)
        names = [o.name for o in self.officers]
        self.assertIn("石田 和男", names)
        self.assertTrue(all(o.birth for o in self.officers))
        self.assertTrue(all(len(o.career) >= 2 for o in self.officers))

    def test_current_outside_positions(self):
        pairs = {(r["person"], r["counterparty_candidates"][0], r["role_at_counterparty"]) for r in self.rows}
        self.assertIn(("石田 和男", "ヤーマン株式会社", "社外取締役"), pairs)
        self.assertIn(("鴛海 量明", "ソーバル株式会社", "監査役（非常勤）"), pairs)
        self.assertIn(("鴛海 量明", "タマホーム株式会社", "監査役（非常勤）"), pairs)
        # 改名表記「ＨＳＫ…（現 令和…）」は現在名を先頭候補にする
        cands = next(r["counterparty_candidates"] for r in self.rows if r["person"] == "佐々木 明日美")
        self.assertEqual(cands[0], "令和ヒューマン・ファースト株式会社")
        # 退任した役職・現任の印がない行は含めない
        self.assertTrue(all(eo.CURRENT_RE.search(r["quote"]) for r in self.rows if r["basis"] == "career_current"))

    def test_split_company_role(self):
        self.assertEqual(eo.split_company_role("東和不動産㈱（現トヨタ不動産㈱）代表取締役会長（現在に至る）"),
                         ("東和不動産㈱（現トヨタ不動産㈱）", "代表取締役会長"))
        self.assertEqual(eo.split_company_role("株式会社エヌ・ティ・ティ・データ 社外取締役(現職)"),
                         ("株式会社エヌ・ティ・ティ・データ", "社外取締役"))
        self.assertEqual(eo.split_company_role("当社取締役就任"), ("当社", "取締役"))
        self.assertEqual(eo.split_company_role("東京大学名誉教授(現職)")[1], "教授")

    def test_split_rename(self):
        self.assertEqual(eo.split_rename("東和不動産㈱（現トヨタ不動産㈱）"), ["トヨタ不動産㈱", "東和不動産㈱"])
        self.assertEqual(eo.split_rename("富士重工業㈱（現在の㈱ＳＵＢＡＲＵ）"), ["㈱ＳＵＢＡＲＵ", "富士重工業㈱"])
        self.assertEqual(eo.split_rename("スズキ㈱"), ["スズキ㈱"])

    def test_dousha_refers_to_previous_company_and_resigned_lines_are_skipped(self):
        officer = eo.Officer(role="取締役", name="山田 太郎", birth="1960年1月1日", career=[
            ("2000年4月", "Ａ株式会社入社"),
            ("2010年6月", "同社取締役（2015年6月退任）"),
            ("2016年6月", "Ｂ株式会社社外取締役（現任）"),
            ("2018年6月", "同社取締役会長（現任）"),
            ("2020年6月", "当社取締役（現任）"),
        ])
        rows = eo.current_positions(officer, None)
        self.assertEqual([(r["counterparty_name"], r["role_at_counterparty"]) for r in rows],
                         [("Ｂ株式会社", "社外取締役"), ("Ｂ株式会社", "取締役会長")])

    def test_japanese_era_dates(self):
        self.assertTrue(eo.BIRTH_RE.match("昭和30年９月９日"))
        self.assertTrue(eo.BIRTH_RE.match("1958年１月９日 （男性）"))
        self.assertTrue(eo.DATE_RE.fullmatch("平成元年４月"))


if __name__ == "__main__":
    unittest.main()
