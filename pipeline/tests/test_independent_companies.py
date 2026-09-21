import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepare_independent_companies import validate

class IndependentCompaniesTest(unittest.TestCase):
    def test_snapshot_preserves_unknowns_and_provenance(self):
        rows=validate(json.loads((Path(__file__).resolve().parents[1]/'data_raw/independent_companies.json').read_text()))
        companies={r['securities_code']:r for r in rows}
        self.assertNotIn('5660',companies)
        self.assertEqual(companies['5202']['corporate_number'],'4010401054474')
        for r in rows:
            self.assertFalse(r['industry_17'])
            self.assertFalse(r['scale_category'])
            self.assertNotIn('jpx.co.jp',json.dumps(r['field_sources']))
            if r['market_segment']=='unknown':
                self.assertIn('market_segment',r['data_quality']['needs_review'])
        self.assertIn('industry_33',companies['2121']['data_quality']['needs_review'])
