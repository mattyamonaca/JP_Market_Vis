"""Validate the reviewed independent-source snapshot; never uses JPX values."""
import json
from pathlib import Path

def validate(rows):
    codes = [r['securities_code'] for r in rows]
    if len(codes) != len(set(codes)):
        raise ValueError('duplicate securities code')
    for r in rows:
        if not r['name'] or not r.get('field_sources'):
            raise ValueError('missing company identity or provenance')
        if r.get('industry_17') or r.get('scale_category'):
            raise ValueError('unsupported derived classification')
    return rows

if __name__ == '__main__':
    p = Path(__file__).parent / 'data_raw' / 'independent_companies.json'
    print(f'Independent snapshot: {len(validate(json.loads(p.read_text())))} companies')
