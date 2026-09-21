"""JPX Excelとの照合専用。結果を本番マスターの補完・選別に使用しない。

python compare_company_sources.py --jpx LOCAL.xlsx --independent DATA.json --out LOCAL_REPORT.json
読み取りにopenpyxlが必要。基準日の差、表記差、未確認を一致とみなさない。
"""
import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path


def normalized_name(value):
    return re.sub(r'株式会社|有限会社|[\s・･]', '', unicodedata.normalize('NFKC', value or ''))


def compare(jpx, independent):
    common = jpx.keys() & independent.keys()
    result = {'jpx_count': len(jpx), 'independent_count': len(independent), 'common': len(common),
              'jpx_only': sorted(jpx.keys() - independent.keys()),
              'independent_only': sorted(independent.keys() - jpx.keys()),
              'name_differences': [], 'industry_differences': [], 'market_differences': [], 'market_compared': 0}
    for code in sorted(common):
        j, e = jpx[code], independent[code]
        for field, key, norm in [('name', 'name_differences', normalized_name), ('industry_33', 'industry_differences', lambda s:s)]:
            if norm(j[field]) != norm(e[field]):
                result[key].append({'code': code, 'jpx': j[field], 'independent': e[field]})
        if e.get('market_segment'):
            result['market_compared'] += 1
            if j['market_segment'] != e['market_segment']:
                result['market_differences'].append({'code': code, 'jpx': j['market_segment'], 'independent': e['market_segment']})
    return result


def main():
    from openpyxl import load_workbook
    ap = argparse.ArgumentParser()
    ap.add_argument('--jpx', required=True)
    ap.add_argument('--independent', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    p = Path(args.jpx)
    rows = list(load_workbook(p, read_only=True, data_only=True).active.values)
    market = {'プライム（内国株式）':'prime', 'スタンダード（内国株式）':'standard', 'グロース（内国株式）':'growth'}
    jpx = {}
    for row in rows[1:]:
        r = dict(zip(rows[0], row))
        if r.get('市場・商品区分') in market:
            jpx[str(r['コード'])] = {'name': r['銘柄名'], 'industry_33': r['33業種区分'], 'market_segment': market[r['市場・商品区分']]}
    d = json.loads(Path(args.independent).read_text())
    independent = {r[1]: {'name':r[2], 'industry_33':r[5], 'market_segment':market.get(r[3])} for r in d['rows']}
    report = {**compare(jpx, independent), 'jpx_date':str(rows[1][0]), 'independent_date':d['as_of'],
              'jpx_sha256':hashlib.sha256(p.read_bytes()).hexdigest(), 'purpose':'comparison_only_not_a_production_input'}
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k:len(v) if isinstance(v,list) else v for k,v in report.items()},ensure_ascii=False))

if __name__ == '__main__':
    main()
