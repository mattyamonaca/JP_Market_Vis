"""パイプライン共通定数（persona_project/persona_api/scripts/build_company_relations から移管）"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
REPO_DIR = BASE_DIR.parent
DATA_RAW = BASE_DIR / "data_raw"
DATA_PROCESSED = BASE_DIR / "data_processed"
# EDINET 有報の生テキストブロック（書類ID単位）。大きいため git 管理外。
EDINET_CACHE = DATA_RAW / "edinet_blocks"
# 生成した M4/M5 の出力先（公開アプリが fetch する public/）
PUBLIC_DIR = REPO_DIR / "public"
# 統合後のフル版（evidence を切り詰めない）。公開版は make_viz_data.py が作る
MASTERS_DIR = DATA_PROCESSED / "masters"

VERSION = "2026.09"

# --- データソース URL ---
JPX_LIST_URL = (
    "https://www.jpx.co.jp/markets/statistics-equities/misc/"
    "tvdivq0000001vg2-att/data_j.xls"
)
EDINET_CODELIST_URL = (
    "https://disclosure2dl.edinet-fsa.go.jp/searchdocument/codelist/Edinetcode.zip"
)
EDINET_API_BASE = "https://api.edinet-fsa.go.jp/api/v2"
# 書類閲覧（原本）URL。書類IDを付けて閲覧画面へ遷移する
EDINET_DOC_VIEW_URL = "https://disclosure2.edinet-fsa.go.jp/WZEK0040.aspx?{doc_id}"
WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
WIKIDATA_USER_AGENT = "jp-market-vis-company-relations/1.0 (research pipeline)"
WD_TSE_QID = "Q217475"

MARKET_SEGMENT_MAP = {
    "プライム（内国株式）": "prime",
    "スタンダード（内国株式）": "standard",
    "グロース（内国株式）": "growth",
}


def edinet_api_key() -> str:
    """環境変数 → ~/.persona/.env の順で EDINET_API_KEY を探す。"""
    key = os.environ.get("EDINET_API_KEY", "").strip()
    if key:
        return key
    env = Path.home() / ".persona" / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("EDINET_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


# --- 関係タイプ定義 ---
# 親子関係の定義は議決権50%超だけでなく、実質支配（連結）を含む。
RELATION_TYPES = {
    "parent_subsidiary": {
        "category": "capital",
        "directed": True,
        "ja": "親会社-子会社",
        "description": "親会社が子会社を支配する関係（議決権の過半数、または連結財務諸表上の実質支配）。source=親会社, target=子会社",
    },
    "affiliate": {
        "category": "capital",
        "directed": True,
        "ja": "関連会社",
        "description": "持分法適用の関連会社等（一般に議決権20〜50%だが実質的影響力による例外あり）。source=投資側, target=関連会社",
    },
    "ownership": {
        "category": "capital",
        "directed": True,
        "ja": "株式保有・大株主",
        "description": "大株主・政策保有株・持合い・その他の関係会社。source=保有側, target=被保有側",
    },
    "joint_venture": {
        "category": "capital",
        "directed": True,
        "ja": "合弁出資",
        "description": "合弁会社への共同出資。source=出資者, target=合弁会社",
    },
    "major_customer": {
        "category": "transaction",
        "directed": True,
        "ja": "主要販売先",
        "description": "連結売上10%以上の顧客（有報開示）。source=販売側, target=顧客",
    },
    "major_supplier": {
        "category": "transaction",
        "directed": True,
        "ja": "主要仕入先",
        "description": "source=仕入側, target=供給側",
    },
    "main_bank": {
        "category": "transaction",
        "directed": True,
        "ja": "主要借入先",
        "description": "有報・借入金等明細表の借入先。source=借入側, target=金融機関",
    },
    "business_alliance": {
        "category": "alliance",
        "directed": False,
        "ja": "業務提携",
        "description": "業務提携契約",
    },
    "capital_alliance": {
        "category": "alliance",
        "directed": False,
        "ja": "資本業務提携",
        "description": "資本参加を伴う業務提携",
    },
    "technology_license": {
        "category": "alliance",
        "directed": True,
        "ja": "技術提携・ライセンス",
        "description": "source=供与側, target=受領側",
    },
    "joint_research": {
        "category": "alliance",
        "directed": False,
        "ja": "共同研究",
        "description": "共同研究・共同特許出願",
    },
    "interlocking_director": {
        "category": "personnel",
        "directed": False,
        "ja": "役員兼任",
        "description": "同一人物が両社の役員を兼任",
    },
    "corporate_group": {
        "category": "group",
        "directed": True,
        "ja": "企業グループ所属",
        "description": "系列・企業グループへの所属。source=企業, target=グループ",
    },
    "merger_acquisition": {
        "category": "group",
        "directed": True,
        "ja": "合併・買収",
        "description": "source=存続/買収側, target=消滅/被買収側",
    },
}
