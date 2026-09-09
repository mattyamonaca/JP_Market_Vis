#!/usr/bin/env bash
# 企業関係データ生成パイプライン一括実行（EDINET の再取得はキャッシュ済み分をスキップ）
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -d .venv ]]; then python3 -m venv .venv; fi
source .venv/bin/activate
pip install -q -r requirements.txt
python -u fetch_jpx.py
python -u fetch_edinet_codes.py
python -u fetch_wikidata.py
python -u fetch_edinet_filings.py list
python -u fetch_edinet_filings.py fetch
python -u parse_edinet_filings.py
python -u build_masters.py
python -u make_viz_data.py
echo "DONE: public/M4_companies.json / public/M5_company_relations.json"
