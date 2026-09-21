import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_masters as bm
from source_contribution import contribution

class PersonCorrectionTests(unittest.TestCase):
    def test_retirement_does_not_remove_other_current_officer_or_credit_retirement_source(self):
        b = bm.RelationBuilder({'1000': {'name': '甲'}, '2000': {'name': '乙'}})
        s, t = {'type': 'listed', 'key': '1000'}, {'type': 'listed', 'key': '2000'}
        r = b.add(s, t, 'interlocking_director', {}, {'source': 'edinet', 'person': '現 任', 'support_status': 'confirmed'})
        r['evidence'].append({'source': 'issuer_website', 'person': '退 任', 'support_status': 'confirmed'})
        r['attributes']['persons'] = [{'name': '現 任', 'roles': {}}, {'name': '退 任', 'roles': {}}]
        rule = {'id': 'retired', 'match': {'source': 'listed:1000', 'target': 'listed:2000', 'relation_type': 'interlocking_director'},
                'action': 'set_person_status', 'person': '退任', 'status': 'historical', 'as_of': '2026-06-01'}
        log = bm.apply_corrections(b, {'relations': [rule]})
        self.assertTrue(log[0]['applied'])
        self.assertEqual(r['status'], 'confirmed')
        self.assertEqual(r['attributes']['persons'][1]['valid_until'], '2026-06-01')
        self.assertEqual(contribution([r])['other_supported'], 0)
        self.assertEqual(contribution([r])['edinet_supported'], 1)
        bm.apply_corrections(b, {'relations': [{**rule, 'person': '現任', 'status': 'needs_review'}]})
        self.assertEqual(r['status'], 'needs_review')
        self.assertEqual(contribution([r])['edinet_supported'], 0)

    def test_missing_person_is_not_applied(self):
        b = bm.RelationBuilder({'1000': {'name': '甲'}, '2000': {'name': '乙'}})
        r = b.add({'type': 'listed', 'key': '1000'}, {'type': 'listed', 'key': '2000'}, 'interlocking_director', {}, {'source': 'edinet'})
        log = bm.apply_corrections(b, {'relations': [{'match': {'source': 'listed:1000', 'target': 'listed:2000', 'relation_type': 'interlocking_director'}, 'action': 'set_person_status', 'person': '不明', 'status': 'historical'}]})
        self.assertFalse(log[0]['applied'])
        self.assertEqual(r['status'], 'confirmed')
