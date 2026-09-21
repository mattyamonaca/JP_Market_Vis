"""公開データに原文を漏らさず、判断に必要な数値・時点・状態を維持する。"""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from make_viz_data import full_evidence, slim_ratio, public_verification


class PublicFactsTest(unittest.TestCase):
    def test_facts_keep_source_dates_and_uncertainty_without_prose(self):
        ev = {
            'source': 'edinet', 'doc_id': 'S1', 'url': 'https://example.com/report',
            'as_of': '2025-03-31', 'published': '2025-06-20', 'retrieved': '2026-09-20',
            'table_ref': 'table0/row2', 'quote': '転載しない文章',
            'relationship_note': '転載しない説明', 'note': '転載しない備考',
            'new_unreviewed_field': '将来のフィールドも漏らさない',
            'contract_date': '2025-02', 'deal_status': 'agreed',
            'person': '氏名', 'role_at_counterparty': '社外取締役',
            'extraction': {'cue': '原文断片', 'reasons': ['unknown_direction'], 'retyped_from': 'ownership'},
        }
        before = copy.deepcopy(ev)
        out = full_evidence(ev)
        for key in ('doc_id', 'url', 'as_of', 'published', 'retrieved', 'table_ref'):
            self.assertEqual(out[key], ev[key])
        self.assertEqual(out['facts']['deal_status'], 'agreed')
        self.assertEqual(out['facts']['contract_date'], '2025-02')
        self.assertEqual(out['facts']['role_at_counterparty'], '社外取締役')
        self.assertEqual(out['extraction']['reasons'], ['unknown_direction'])
        for key in ('quote', 'relationship_note', 'note', 'new_unreviewed_field'):
            self.assertNotIn(key, out)
        self.assertNotIn('cue', out['extraction'])
        self.assertEqual(ev, before)  # 検証用原本は変更しない
        self.assertNotIn('facts', full_evidence({'source': 'wikidata'}))

    def test_ratios_keep_zero_indirect_only_conflicts_and_history(self):
        ratio = {'scope': 'indirect_only', 'kind': 'voting', 'value': None, 'indirect': 0,
                 'raw': '原文', 'note': '注記', 'conflicting_values': [0.2, 0.3],
                 'history': [{'value': 0.2, 'as_of': '2024-03-31', 'doc_id': 'OLD', 'raw': '20%'}]}
        out = slim_ratio(ratio, with_history=True)
        self.assertNotIn('value', out)
        self.assertEqual(out['indirect'], 0)
        self.assertEqual(out['scope'], 'indirect_only')
        self.assertEqual(out['conflicting_values'], [0.2, 0.3])
        self.assertEqual(out['history'], [{'value': 0.2, 'as_of': '2024-03-31', 'doc_id': 'OLD'}])
        self.assertNotIn('raw', out)
        self.assertNotIn('note', out)

    def test_verification_retains_status_and_source_without_free_text(self):
        out = public_verification({'status': 'verified', 'on': '2026-09-20', 'note': '自由文',
                                   'source': {'url': 'https://example.com', 'title': '表題'}})
        self.assertEqual(out, {'status': 'verified', 'on': '2026-09-20',
                              'source': {'url': 'https://example.com'}})
