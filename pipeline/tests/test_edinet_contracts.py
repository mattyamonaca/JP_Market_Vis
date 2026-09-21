"""経営上の重要な契約等（提携）パーサーの回帰テスト。fixtures は実書類のブロック（トヨタ自動車 S100VWVY・ブラザー工業 S100W0FQ）。"""
import unittest
from pathlib import Path

import edinet_contracts as ec

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


class ContractParserTest(unittest.TestCase):
    def test_toyota_chronological_table(self):
        rows = ec.extract_contracts((FIXTURES / "toyota_S100VWVY_contracts.html").read_text(encoding="utf-8"))
        got = {(r["relation_type"], r["counterparty_candidates"][0]) for r in rows}
        self.assertIn(("business_alliance", "㈱ＳＵＢＡＲＵ"), got)      # 「富士重工業㈱（現在の㈱ＳＵＢＡＲＵ）と業務提携」
        self.assertIn(("capital_alliance", "マツダ㈱"), got)             # 業務資本提携
        self.assertIn(("capital_alliance", "スズキ㈱"), got)
        self.assertIn(("capital_alliance", "いすゞ自動車㈱"), got)
        self.assertIn(("joint_venture", "パナソニック㈱"), got)          # 合弁契約（相手はパートナー）
        names = {r["counterparty_candidates"][0] for r in rows}
        for junk in ("現在の㈱", "㈱ＳＵＢＡＲＵと業務資本提携拡大", "連結子会社", "契約会社"):
            self.assertNotIn(junk, names)
        # 相手方であることが文中で明示されている（「Ａと」「Ａとの間で」）
        self.assertTrue(all(r["party_cue"] for r in rows if r["counterparty_candidates"][0] in ("マツダ㈱", "スズキ㈱")))
        dates = {r["counterparty_candidates"][0]: r["date"] for r in rows if r["relation_type"] == "capital_alliance"}
        self.assertEqual(dates["マツダ㈱"], "2017-08")

    def test_brother_column_table(self):
        rows = ec.extract_contracts((FIXTURES / "brother_S100W0FQ_contracts.html").read_text(encoding="utf-8"))
        got = {(r["relation_type"], r["counterparty_candidates"][0], r["basis"]) for r in rows}
        self.assertIn(("technology_license", "キヤノン株式会社", "table_columns"), got)
        self.assertIn(("technology_license", "株式会社リコー", "table_columns"), got)
        self.assertIn(("technology_license", "セイコーエプソン株式会社", "table_columns"), got)
        self.assertEqual(len(rows), 3)

    def test_company_extraction_and_cues(self):
        self.assertEqual(ec.companies_in("当社はナゴヤピーシーエー株式会社と業務提携契約を締結", with_cue=True),
                         [("ナゴヤピーシーエー株式会社", True)])
        self.assertEqual(ec.companies_in("2017年８月 マツダ㈱と業務資本提携"), ["マツダ㈱"])
        self.assertEqual(ec.companies_in("契約会社 相手先 契約種類"), [])
        self.assertEqual(ec.companies_in("当社は株式会社セブン＆アイ・ホールディングスと資本業務提携契約を締結"), ["株式会社セブン＆アイ・ホールディングス"])
        self.assertEqual(ec.companies_in("PCOがオリックス㈱との間で"), ["オリックス㈱"])
        self.assertEqual(ec.companies_in("株式会社熊谷組他 / 技術供与"), ["株式会社熊谷組"])
        self.assertEqual(ec.companies_in("当社の親会社であるデジタル・アドバタイジング・コンソーシアム㈱との資本・業務提携契約"), ["デジタル・アドバタイジング・コンソーシアム㈱"])
        self.assertEqual(ec.companies_in("㈱広済堂 ホールディングス / 合弁契約"), ["㈱広済堂 ホールディングス"])
        self.assertEqual(ec.companies_in("Guandong TGPM Automotive Industry Group Co., Ltd. / 技術供与"), ["Guandong TGPM Automotive Industry Group Co., Ltd."])
        self.assertEqual(ec.companies_in("JUNEINTER Co,.Ltd. と技術提携"), ["JUNEINTER Co,.Ltd."])

    def test_context_kind_is_not_borrowed_by_loan_tables(self):
        html = ("<p>当社は株式会社セブン＆アイ・ホールディングスと資本業務提携契約を締結しております。</p>"
                "<p>（2）借入金に関する契約（シンジケートローン）</p><table><tr><th>相手方</th><th>契約内容</th></tr>"
                "<tr><td>株式会社静岡銀行</td><td>コミットメントライン</td></tr></table>")
        rows = ec.extract_contracts(html)
        self.assertEqual([(r["relation_type"], r["counterparty_name"]) for r in rows], [("capital_alliance", "株式会社セブン＆アイ・ホールディングス")])

    def test_direction_hint(self):
        self.assertEqual(ec.direction_hint("technology_license", "癌関連モノクローナル抗体技術の導入"), "in")
        self.assertEqual(ec.direction_hint("technology_license", "特許実施権の交換"), "mutual")
        self.assertEqual(ec.direction_hint("technology_license", "相手先に技術供与"), "out")
        self.assertIsNone(ec.direction_hint("business_alliance", "業務提携"))

    def test_excluded_contract_kinds(self):
        self.assertEqual(ec.extract_contracts("<p>当社は、Ｘ株式会社との間で株式譲渡契約を締結しました。</p>"), [])
        rows = ec.extract_contracts("<p>当社は、アルファ株式会社と資本業務提携契約を締結し、同社株式を取得しました。</p>")
        self.assertEqual([(r["relation_type"], r["counterparty_name"]) for r in rows], [("capital_alliance", "アルファ株式会社")])


if __name__ == "__main__":
    unittest.main()

class PublicNameGuardTest(unittest.TestCase):
    def test_foreign_legal_form_and_sentence_fragments_are_not_companies(self):
        import edinet_tables as et
        for name in ['股份有限公司', '有限公司', '20日開催の取締役会においてソニーグループ株式会社', '100％連結子会社であるパナソニック コネクト㈱']:
            self.assertIsNotNone(et.name_problem(name), name)
        for name in ['台湾扣具工業股份有限公司', 'パナソニック コネクト㈱', '株式会社88']:
            self.assertIsNone(et.name_problem(name), name)
