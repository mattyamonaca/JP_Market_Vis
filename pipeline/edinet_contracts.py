"""有価証券報告書「経営上の重要な契約等」ブロック（CriticalContractsTextBlock）から提携関係を抽出する。

書き方は会社ごとに違う（年月＋概要の表、相手方・契約内容の列を持つ表、本文の箇条書き）ので、
表の列見出しが読める場合は列から、それ以外はセル・文単位のテキストから
「相手の会社名 ＋ 契約の種類を示す語」の組を拾う。契約の種類 → 関係タイプ:
  資本業務提携・業務資本提携・資本提携 → capital_alliance / 業務提携・販売提携・協業・包括提携 → business_alliance
  技術援助・技術提携・ライセンス・実施権 → technology_license / 共同開発・共同研究 → joint_research
  合弁契約（合弁会社名が読めれば joint_venture、読めなければ business_alliance に「合弁契約」の注記）
相手の会社名は原文のまま返し、上場企業への照合は build_masters 側で行う（上場企業に解決できない相手は投入しない）。
"""
from __future__ import annotations

import html
import re

import edinet_tables as et
from edinet_officers import _NestedParser

KIND_PATTERNS = [
    ("capital_alliance", r"資本業務提携|業務資本提携|資本提携|資本・業務提携"),
    ("technology_license", r"技術援助|技術提携|技術導入|技術供与|ライセンス契約|実施権|使用許諾|技術協力契約|技術援助契約|特許"),
    ("joint_research", r"共同開発|共同研究|共同技術開発|開発協力"),
    ("joint_venture", r"合弁|ジョイントベンチャー|ジョイント・ベンチャー|共同出資"),
    ("business_alliance", r"業務提携|販売提携|包括提携|戦略的提携|包括的提携|協業|業務協力|提携契約|提携に関する|業務委託契約|代理店契約|販売代理店|フランチャイズ|パートナーシップ|アライアンス"),
]
KIND_RE = [(k, re.compile(p)) for k, p in KIND_PATTERNS]
# 提携ではない契約（除外）
EXCLUDE_RE = re.compile(r"吸収分割|吸収合併|新設分割|株式交換|株式移転|株式譲渡|株式取得|公開買付|事業譲渡|経営管理契約|金銭消費貸借|シンジケート|コミットメントライン|賃貸借|借入|社債|融資|担保|保証委託|雇用|労働協約|退職|年金|工事請負|売買契約|不動産")
# 会社名の候補（前置・後置の法人格、または英文社名）
# 前置の法人格（㈱Ｘ）: 続く語は「と」「の」「、」「を」等の助詞・句読点・括弧で終わる
# 後置の法人格（Ｘ㈱ / X Inc.）: 直前の区切り（空白・句読点・括弧・助詞「と」「、」・年月）から法人格まで
# 後置形は「パナソニック コネクト㈱」のようにカタカナ・欧文の語の間の空白を許す
COMPANY_RE = re.compile(
    r"(?<![^\s、。,（）()「」『』と及びはがをにでも])(?:株式会社|㈱|（株）|\(株\))\s*[^\s、。,（）()「」『』とのをがはでもへ及び]{1,40}(?:\s[ァ-ヶー]{2,20}){0,2}"
    r"|(?<![^\s、。,（）()「」『』と及び])[^\s、。,（）()「」『』と]{1,40}?(?:\s[ァ-ヶーＡ-Ｚａ-ｚA-Za-z&＆.,]{1,20}){0,4}"
    r"(?:株式会社|㈱|（株）|\(株\)|有限公司|有限責任公司|\s?Inc\.?|\s?Corp\.?|\s?Corporation|\s?Co\.?,?\.?\s?Ltd\.?|\s?Ltd\.?|\s?LLC|\s?GmbH|"
    r"\s?S\.A\.|\s?N\.V\.|\s?B\.V\.|\s?AG|\s?plc|\s?Limited|\s?Company|\s?Holdings|\s?Group|社)(?![^\s、。,（）()「」『』と])"
)
CONJ_RE = re.compile(r"および|及び|並びに|ならびに|又は|または|ならび")
DATE_PREFIX_RE = re.compile(r"^(?:\d{4}|[０-９]{4})年\s*(?:\d{1,2}|[０-９]{1,2})月\s*")
RENAME_RE = re.compile(r"^(.*?)\s*[（(]\s*(?:現在の|現|旧|旧社名[:：]?)\s*[:：]?\s*(.+?)\s*[)）]\s*$")
HEADER_KEYS = {
    "counterparty": ["相手方", "契約相手", "相手先", "契約先", "契約の相手方", "相手方の名称", "契約締結先", "提携先"],
    "content": ["契約内容", "内容", "契約の内容", "契約品目", "概要", "契約の概要"],
    "party": ["契約会社名", "当社側", "契約締結会社", "契約当事者"],
    "period": ["契約期間", "期間"],
    "date": ["締結日", "契約年月日", "契約日", "年月"],
}
DATE_RE = re.compile(r"(\d{4}|[０-９]{4})年\s*(\d{1,2}|[０-９]{1,2})月")
SELF_RE = re.compile(r"^(当社|当行|当社グループ|同社|同行|提出会社)$")
# 会社名として採用しない一般語（表の見出し語・代名詞）
STOP_RE = re.compile(r"^(?:株式会社|㈱|（株）|\(株\))?(?:契約|相手|当該|同|各|両|他|関係|子|親|持株|提出|取引|販売|製造|本|対象|新|旧|当)会社$|"
                     r"^(?:相手先|契約先|取引先|提携先|契約相手|取扱商品|契約内容|契約期間|会社名|国名|連結子会社|関連会社|当社|同社)$")
# 法人らしさ（法人格がない名前を採用するときの条件）
HINT_RE = re.compile(r"株式会社|㈱|（株）|\(株\)|有限公司|Inc\.|Corp|Ltd|LLC|GmbH|S\.A\.|N\.V\.|B\.V\.|AG$|plc|Limited|Company|Holdings|Group|社$|銀行|信託|生命|海上|証券|ホールディングス|グループ|工業|製作所|商事|物産|不動産|電力|ガス|鉄道|製薬|化学|製鋼|重工|電機|電気|自動車|建設|保険|リース|研究所|大学|機構|法人|協会|組合")


def _kind_of(text: str) -> str | None:
    if EXCLUDE_RE.search(text) and not any(r.search(text) for _, r in KIND_RE[:1]):
        # 提携語がない除外契約（株式譲渡など）は対象外。資本業務提携は株式取得を伴っても対象
        if not any(r.search(text) for _, r in KIND_RE):
            return None
    for kind, r in KIND_RE:
        if r.search(text):
            return kind
    return None


def split_rename(name: str) -> list[str]:
    m = RENAME_RE.match(name)
    if m and m.group(1).strip():
        cur, old = (m.group(2), m.group(1)) if "旧" not in name[m.start(2) - 6: m.start(2)] else (m.group(1), m.group(2))
        return [cur.strip(), old.strip()]
    return [name.strip()]


def clean_company(name: str) -> str:
    s = name.strip(" 　、,。・")
    s = DATE_PREFIX_RE.sub("", s)
    s = re.sub(r"^(?:同社の|同社|当社の|当社|提出会社)(?:は|が|と|の|および|及び|も)?", "", s)
    s = re.sub(r"^(?:当社の)?(?:親会社|子会社|連結子会社|関連会社|持分法適用関連会社|主要株主|筆頭株主)である", "", s)
    s = re.sub(r"\s*(?:他|ほか|他\d+社|ほか\d+社)$", "", s)
    # 「PCOがオリックス㈱」のように欧文の略称＋助詞が前に付いた場合は助詞までを外す
    s = re.sub(r"^[A-Za-zＡ-Ｚａ-ｚ0-9０-９]{1,12}(?:が|は|を|に|で|も)(?=[ァ-ヶ一-龥])", "", s)
    s = re.sub(r"^(?:現在の|現|旧|米国|英国|中国|独国|仏国|韓国|台湾)", "", s)
    s = re.sub(r"(?:との間で|との|と|及び|および|等|など|各社|の子会社|の関連会社|傘下の)$", "", s).strip()
    return s


# 会社名の直後に相手方であることを示す語（「Ａと」「Ａとの間で」「Ａおよび」「Ａ、」）があるか
PARTY_CUE_RE = re.compile(r"^\s*(?:（[^（）]{0,20}）|\([^()]{0,20}\))?\s*(?:との間|と|および|及び|、|,|等|各社|を相手)")


def companies_in(text: str, with_cue: bool = False):
    out: list = []
    # 「Ａ（現在のＢ）」「Ａ（現Ｂ）」は括弧を外して両方を候補にする。「ＡおよびＢ」は区切りにする
    text = re.sub(r"[（(]\s*(?:現在の|現|旧)\s*([^（）()]+?)\s*[)）]", r" \1 ", text)
    text = CONJ_RE.sub("、", text)
    for m in COMPANY_RE.finditer(text):
        name = clean_company(m.group(0))
        if et.name_problem(name):
            continue
        # 法人格・記号を除いて 2 文字以上残らない断片（「.Ltd.」など）は採らない
        core = re.sub(r"株式会社|㈱|（株）|\(株\)|有限公司|Inc\.?|Corp\.?|Corporation|Co\.?,?\.?|Ltd\.?|LLC|GmbH|Limited|Company|[\s.,・&＆]", "", name)
        if not name or SELF_RE.match(name) or len(core) < 2:
            continue
        if STOP_RE.match(name) or re.fullmatch(r"(?:株式会社|㈱|（株）|\(株\))?(?:当社|同社|各社|他社|両社|３社|３社|２社|数社|に商号)", name):
            continue
        cue = bool(PARTY_CUE_RE.match(text[m.end(): m.end() + 40]))
        if name not in [n for n, _ in out]:
            out.append((name, cue))
    return out if with_cue else [n for n, _ in out]


def _sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text)
    return [s.strip() for s in re.split(r"(?<=[。])\s*|\n", text) if s and s.strip()]


def _find_header(grid: et.TableGrid) -> tuple[int, dict[str, int]] | None:
    for r in range(min(3, len(grid.rows))):
        texts = [(grid.cell(r, c).text if grid.cell(r, c) else "") for c in range(grid.ncols)]
        found: dict[str, int] = {}
        for c, tx in enumerate(texts):
            t = re.sub(r"\s+", "", tx)
            for key, words in HEADER_KEYS.items():
                if key not in found and any(w in t for w in words):
                    found[key] = c
        if "counterparty" in found:
            return r, found
    return None


def extract_contracts(raw_block: str, filer_name: str | None = None) -> list[dict]:
    """ブロック → 提携行の列。各行: counterparty_name, counterparty_candidates, relation_type, quote, date, party, table_index."""
    rows: list[dict] = []
    tables = et.parse_block(raw_block)
    consumed_text: set[str] = set()
    for ti, grid in enumerate(tables):
        hdr = _find_header(grid)
        if hdr:
            hr, cols = hdr
            for r in range(hr + 1, len(grid.rows)):
                cell = lambda key: (grid.cell(r, cols[key]).text if key in cols and grid.cell(r, cols[key]) else "")  # noqa: E731
                cp = re.sub(r"\s+", " ", cell("counterparty")).strip()
                content = re.sub(r"\s+", " ", cell("content")).strip()
                if not cp or re.fullmatch(r"[―－\-〃]+|同上", cp):
                    continue
                # 契約の種類は行の内容から。内容に種類語がなければ表の直前の見出し（末尾 80 文字）から補うが、
                # 借入先・シンジケートローンなど提携でない表（除外語を含む）はその文脈で拾わない
                ctx_tail = (grid.context or "")[-80:]
                kind = _kind_of(content) or _kind_of(cp)
                if not kind and not EXCLUDE_RE.search(content + " " + ctx_tail):
                    kind = _kind_of(ctx_tail)
                if not kind:
                    continue
                party = re.sub(r"\s+", " ", cell("party")).strip() or None
                cleaned = clean_company(cp)
                # 法人格を除いて 2 文字以上残る名前だけ（「Ltd.」のような法人格だけの断片は採らない）
                fallback = [cleaned] if not et.name_problem(cleaned) and HINT_RE.search(cp) and not STOP_RE.match(cleaned) and len(re.sub(
                    r"株式会社|㈱|（株）|\(株\)|Inc\.?|Corp\.?|Ltd\.?|LLC|Co\.,?|Limited|Company|Corporation|[\s.,]", "", cleaned)) >= 2 else []
                for name in (companies_in(cp) or fallback):
                    rows.append({
                        "counterparty_name": name, "counterparty_candidates": split_rename(name),
                        "relation_type": kind, "quote": (f"{cp} / {content}".strip(" /"))[:300],
                        "date": _first_date(cell("date") or cell("period") or content), "party": party,
                        "table_index": ti, "basis": "table_columns", "party_cue": True,
                        "direction_hint": direction_hint(kind, content + " " + (grid.context or "")[-200:]),
                    })
                consumed_text.add(cp)
            continue
        # 年月＋概要の表や 1 列の表: セル単位の文から拾う
        for r in range(len(grid.rows)):
            texts = [(grid.cell(r, c).text if grid.cell(r, c) else "") for c in range(grid.ncols)]
            line = " ".join(t for t in texts if t)
            rows.extend(_rows_from_text(line, ti, "table_cells"))
    # 表の外の本文（表の中身は上で処理済みなので、表の外のテキスト行だけを文に分けて読む）
    p = _NestedParser()
    try:
        p.feed(html.unescape(raw_block or ""))
        p.close()
        outside = p.notes
    except Exception:
        outside = []
    for note in outside:
        for s in _sentences(note):
            rows.extend(_rows_from_text(s, None, "paragraph"))
    # 重複除去（相手・タイプ・引用の先頭 40 文字）
    seen = set()
    uniq = []
    for row in rows:
        key = (row["counterparty_candidates"][0], row["relation_type"], row["quote"][:40])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(row)
    return uniq


def _first_date(text: str) -> str | None:
    m = DATE_RE.search(text or "")
    if not m:
        return None
    y, mo = m.group(1), m.group(2)
    tr = str.maketrans("０１２３４５６７８９", "0123456789")
    return f"{y.translate(tr)}-{int(mo.translate(tr)):02d}"


def _rows_from_text(line: str, table_index: int | None, basis: str) -> list[dict]:
    line = re.sub(r"\s+", " ", line).strip()
    if len(line) < 6:
        return []
    kind = _kind_of(line)
    if not kind:
        return []
    out = []
    for name, cue in companies_in(line, with_cue=True):
        out.append({
            "counterparty_name": name, "counterparty_candidates": split_rename(name),
            "relation_type": kind, "quote": line[:300], "date": _first_date(line), "party": None,
            "table_index": table_index, "basis": basis, "party_cue": cue,
            "direction_hint": direction_hint(kind, line),
        })
    return out


def direction_hint(kind: str, text: str) -> str | None:
    """技術提携・ライセンスの方向: 'in' = 相手から当社へ（導入・援助を受ける）、'out' = 当社から相手へ（供与・許諾）。"""
    if kind != "technology_license":
        return None
    if re.search(r"相互|クロスライセンス|交換", text):
        return "mutual"
    if re.search(r"導入|援助を受け|許諾を受け|供与を受け|技術援助契約|使用権の取得|実施権の取得|実施権の許諾を受け|ライセンスを受け", text):
        return "in"
    if re.search(r"供与|許諾し|許諾する|ライセンスを付与|実施権を許諾|使用を許諾|技術援助を行|技術供与", text):
        return "out"
    return None
