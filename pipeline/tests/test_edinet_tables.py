"""EDINET 表パーサーの回帰テスト（Issue #1）。

実書類から抜粋した fixtures/*.html と合成 HTML で、結合セル・分類見出しの継承・所有／被所有の
判定・数値ノードの非生成を確認する。実行: `python -m pytest pipeline/tests` または
`python -m unittest discover -s pipeline/tests`。
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import edinet_tables as et  # noqa: E402

FIXTURES = HERE.parent / "fixtures"


def load_fixture(name: str) -> tuple[str, dict]:
    return (FIXTURES / f"{name}.html").read_text(encoding="utf-8"), json.loads(
        (FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def affiliated(name: str) -> list[dict]:
    raw, _ = load_fixture(name)
    return et.extract_affiliated(et.parse_block(raw), et.block_text(raw))


def by_name(rows: list[dict], needle: str) -> dict:
    hits = [r for r in rows if needle in r["counterparty_name"]]
    assert hits, f"{needle} not found in {[r['counterparty_name'] for r in rows]}"
    return hits[0]


class RealFilingCases(unittest.TestCase):
    """Issue #1 / レビューで確認済みの固定ケース。"""

    def test_olc_keisei_is_other_affiliated_company_owned_by_counterparty(self):
        rows = affiliated("olc_S100VY55_affiliated")
        keisei = by_name(rows, "京成電鉄")
        self.assertEqual(keisei["classification"], "その他の関係会社")
        self.assertEqual(keisei["classification_source"], "section")
        self.assertTrue(keisei["owned_by_counterparty"])
        self.assertAlmostEqual(keisei["ratio_total"], 0.2014)
        self.assertAlmostEqual(keisei["ratio_indirect"], 0.0007)
        hotels = by_name(rows, "ミリアルリゾートホテルズ")
        self.assertEqual(hotels["classification"], "連結子会社")
        self.assertFalse(hotels["owned_by_counterparty"])
        # 「その他10社」は企業として扱わない
        self.assertEqual(by_name(rows, "その他10社")["name_problem"], "others_count")

    def test_zozo_parent_section_reverses_direction(self):
        rows = affiliated("zozo_S100Y951_affiliated")
        sbg = by_name(rows, "ソフトバンクグループ(株)")
        self.assertEqual(sbg["classification"], "親会社")
        self.assertTrue(sbg["owned_by_counterparty"])
        self.assertAlmostEqual(sbg["ratio_total"], 0.519)
        self.assertAlmostEqual(sbg["ratio_indirect"], 0.519)
        nxt = by_name(rows, "ZOZO NEXT")
        self.assertEqual(nxt["classification"], "連結子会社")
        self.assertEqual(nxt["classification_source"], "prefix")
        self.assertFalse(nxt["owned_by_counterparty"])
        self.assertEqual(nxt["counterparty_name"], "(株)ZOZO NEXT")  # 注記番号を残さない

    def test_m3_sony_uses_label_table_and_cell_marker(self):
        rows = affiliated("m3_S100W3NK_affiliated")
        sony = by_name(rows, "ソニーグループ")
        self.assertEqual(sony["classification"], "その他の関係会社")
        self.assertTrue(sony["owned_by_counterparty"])
        self.assertEqual(sony["direction_source"], "cell")
        self.assertAlmostEqual(sony["ratio_total"], 0.339)
        sol = by_name(rows, "エムスリーソリューションズ")
        self.assertEqual(sol["classification"], "連結子会社")
        self.assertFalse(sol["owned_by_counterparty"])

    def test_aeon_hokkaido_parent_row_label_keeps_indirect(self):
        rows = affiliated("aeon_hokkaido_S100Y36L_affiliated")
        aeon = by_name(rows, "イオン")
        self.assertEqual(aeon["classification"], "親会社")
        self.assertTrue(aeon["owned_by_counterparty"])
        self.assertAlmostEqual(aeon["ratio_total"], 0.672)
        self.assertAlmostEqual(aeon["ratio_indirect"], 0.016)

    def test_life_mitsubishi_owned_marker_and_ratio(self):
        rows = affiliated("life_S100Y63D_affiliated")
        mc = by_name(rows, "三菱商事")
        self.assertEqual(mc["classification"], "その他の関係会社")
        self.assertTrue(mc["owned_by_counterparty"])
        self.assertAlmostEqual(mc["ratio_total"], 0.244)
        self.assertAlmostEqual(mc["ratio_indirect"], 0.012)
        lfs = by_name(rows, "ライフフィナンシャルサービス")
        self.assertEqual(lfs["classification"], "連結子会社")
        self.assertFalse(lfs["owned_by_counterparty"])

    def test_two_column_owned_and_own_ratio(self):
        rows = affiliated("nssol_S100VY52_affiliated")
        ns = by_name(rows, "日本製鉄")
        self.assertEqual(ns["classification"], "親会社")
        self.assertTrue(ns["owned_by_counterparty"])
        self.assertAlmostEqual(ns["ratio_total"], 0.6344)
        sub = by_name(rows, "日鉄ソリューションズ北海道")
        self.assertEqual(sub["classification"], "連結子会社")
        self.assertFalse(sub["owned_by_counterparty"])
        self.assertAlmostEqual(sub["ratio_total"], 1.0)

    def test_prefix_classification_inherits_to_following_rows(self):
        rows = affiliated("nttdata_intramart_S100VYKA_affiliated")
        self.assertEqual(by_name(rows, "NTTデータグループ")["classification"], "親会社")
        self.assertTrue(by_name(rows, "NTTデータグループ")["owned_by_counterparty"])
        self.assertEqual(by_name(rows, "BiXi")["classification"], "連結子会社")
        self.assertFalse(by_name(rows, "BiXi")["owned_by_counterparty"])
        self.assertEqual(by_name(rows, "協立システム開発")["classification"], "持分法適用関連会社")

    def test_classification_column(self):
        rows = affiliated("okada_S100VYA7_affiliated")
        self.assertEqual(by_name(rows, "アイヨンテック")["classification"], "連結子会社")
        self.assertEqual(by_name(rows, "アイヨンテック")["classification_source"], "column")

    def test_shareholders_keep_as_of_date(self):
        raw, _ = load_fixture("olc_S100VY55_shareholder")
        rows = et.extract_shareholders(et.parse_block(raw), et.block_text(raw))
        keisei = by_name(rows, "京成電鉄")
        self.assertAlmostEqual(keisei["ratio_total"], 0.2005)
        self.assertEqual(keisei["as_of"], "2025-03-31")
        self.assertFalse(any(r["counterparty_name"] == "計" for r in rows))

    def test_customers_amount_and_unit(self):
        raw, _ = load_fixture("ymfg_S100VVT1_customer")
        rows = et.extract_customers(et.parse_block(raw))
        mazda = by_name(rows, "マツダ")
        self.assertEqual(mazda["sales_amount"], 79947)
        self.assertEqual(mazda["sales_unit"], "百万円")


class SyntheticCases(unittest.TestCase):
    """レビュー（reviews/2026-09-09/extractor-reproduction.json）の再現ケース。"""

    def test_rowspan_second_row_is_not_a_company(self):
        html = ('<table><tr><th>名称</th><th>議決権の所有割合</th></tr>'
                '<tr><td rowspan="2">子会社A</td><td>100</td></tr><tr><td>(87.74)</td></tr></table>')
        rows = et.extract_affiliated(et.parse_block(html))
        self.assertEqual([r["counterparty_name"] for r in rows], ["子会社A"])
        self.assertAlmostEqual(rows[0]["ratio_total"], 1.0)
        self.assertAlmostEqual(rows[0]["ratio_indirect"], 0.8774)

    def test_separate_category_row_is_inherited(self):
        html = ('<table><tr><th>名称</th><th>議決権の所有(被所有)割合</th></tr>'
                '<tr><td>（その他の関係会社）</td><td></td></tr>'
                '<tr><td>京成電鉄株式会社</td><td>被所有20.14</td></tr></table>')
        rows = et.extract_affiliated(et.parse_block(html))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["classification"], "その他の関係会社")
        self.assertEqual(rows[0]["classification_source"], "row")
        self.assertTrue(rows[0]["owned_by_counterparty"])

    def test_explicit_parent_prefix(self):
        html = ('<table><tr><th>名称</th><th>議決権の所有割合</th></tr>'
                '<tr><td>（親会社）ソフトバンクグループ株式会社</td><td>51.5</td></tr></table>')
        rows = et.extract_affiliated(et.parse_block(html))
        self.assertEqual(rows[0]["classification"], "親会社")
        self.assertTrue(rows[0]["owned_by_counterparty"])
        self.assertEqual(rows[0]["counterparty_name"], "ソフトバンクグループ株式会社")

    def test_unknown_classification_stays_unknown(self):
        html = ('<h3>４【関係会社の状況】</h3><table><tr><th>名称</th><th>議決権の所有割合</th></tr>'
                '<tr><td>某社</td><td>100</td></tr></table>')
        rows = et.extract_affiliated(et.parse_block(html))
        self.assertIsNone(rows[0]["classification"])
        self.assertFalse(rows[0]["owned_by_counterparty"])

    def test_note_marks_all_rows_as_consolidated(self):
        html = ('<table><tr><th>名称</th><th>議決権の所有割合</th></tr>'
                '<tr><td>某社</td><td>100</td></tr></table><p>(注) 上記会社は連結子会社であります。</p>')
        rows = et.extract_affiliated(et.parse_block(html), et.block_text(html))
        self.assertEqual(rows[0]["classification"], "連結子会社")
        self.assertEqual(rows[0]["classification_source"], "note")

    def test_header_owned_column_reverses_direction(self):
        html = ('<h4>(3) その他の関係会社</h4><table><tr><th>名称</th><th>議決権の被所有割合</th></tr>'
                '<tr><td>親玉株式会社</td><td>30.0</td></tr></table>')
        rows = et.extract_affiliated(et.parse_block(html))
        self.assertTrue(rows[0]["owned_by_counterparty"])
        self.assertEqual(rows[0]["classification"], "その他の関係会社")

    def test_numeric_and_symbol_names_are_flagged(self):
        for bad in ["(87.74)", "100", "―", "12,345", "計", "合計", "その他 3社", "5社"]:
            self.assertIsNotNone(et.name_problem(bad), bad)
        for good in ["京成電鉄(株)", "Sony Corporation of America", "索尼(中国)有限公司", "千葉県"]:
            self.assertIsNone(et.name_problem(good), good)

    def test_clean_name_strips_notes_and_footnote_marks(self):
        self.assertEqual(et.clean_name("㈱ZOZO NEXT (注)１"), "(株)ZOZO NEXT")
        self.assertEqual(et.clean_name("イオン(株)１"), "イオン(株)")
        self.assertEqual(et.clean_name("トヨタ モーター\nクレジット㈱ ＊１＊２"), "トヨタ モーター クレジット(株)")
        self.assertEqual(et.clean_name("（連結子会社）\n㈱ZOZO NEXT"), "(株)ZOZO NEXT")

    def test_ratio_cell_variants(self):
        self.assertEqual(et.parse_ratio_cell("20.14\n(0.07)")["total"], 0.2014)
        self.assertEqual(et.parse_ratio_cell("20.14\n(0.07)")["indirect"], 0.0007)
        self.assertEqual(et.parse_ratio_cell("(10.7) 100.0")["total"], 1.0)
        self.assertEqual(et.parse_ratio_cell("100.0％\n(100.0％)")["indirect"], 1.0)
        self.assertTrue(et.parse_ratio_cell("（被所有）\n33.9％")["owned_marker"])
        self.assertIsNone(et.parse_ratio_cell("―")["total"])
        self.assertEqual(et.parse_ratio_cell("50.00 [25.00]")["total"], 0.5)


if __name__ == "__main__":
    unittest.main()
