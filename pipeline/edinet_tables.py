"""有価証券報告書の HTML ブロックから、関係会社・大株主・主要顧客の行を構造化して抽出する。

旧パーサー（persona_project の 4_fetch_edinet_filings.py）の問題点と、本モジュールでの対応:

- rowspan / colspan を展開しなかったため、結合セルの下段では比率 `(87.74)` が企業名になった
  → `TableGrid` で結合セルを展開し、同じセルオブジェクトが続く行は前の行の続きとして扱う。
- 分類は行頭の全角括弧だけを見ていたため、見出し行・節見出し・区分列の分類を継承できず、
  親会社や「その他の関係会社」まで提出会社→相手の子会社になった
  → 節見出し（h3/h4/p の本文）・単独セル行・区分列・行頭括弧の順に分類を継承する。
- 所有／被所有を区別しなかった → 列見出しとセル内の「被所有」表記、および分類
  （親会社・その他の関係会社）から `owned_by_counterparty` を決める。
- 「20.14 (0.07)」の括弧内（間接所有・内数）を捨てていた → `ratio_total` / `ratio_indirect` を保持。

抽出結果の 1 行（affiliated の例）:
    {
      "counterparty_name": "京成電鉄",            # 正規化名（法人格・注記記号除去）
      "raw_name": "京成電鉄㈱",                   # セル原文
      "classification": "その他の関係会社",       # 正規化分類（None = 不明）
      "classification_source": "section",         # section / row / column / prefix / None
      "owned_by_counterparty": True,              # True = 相手が提出会社を所有（被所有）
      "direction_source": "classification",       # header / cell / classification / default
      "ratio_total": 0.2014, "ratio_indirect": 0.0007, "ratio_raw": "20.14 (0.07)",
      "relationship_note": "役員の兼任あり。",
      "table_index": 1, "row_index": 1
    }
"""
from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass, field
from html.parser import HTMLParser


# ---------------------------------------------------------------------------
# HTML → セクション付きテーブル列
# ---------------------------------------------------------------------------

@dataclass
class Cell:
    text: str
    rowspan: int = 1
    colspan: int = 1
    is_header: bool = False


@dataclass
class TableGrid:
    """rowspan/colspan を展開した表。grid[r][c] は Cell（結合セルは同一オブジェクトを共有）。"""
    rows: list[list[Cell]] = field(default_factory=list)
    context: str = ""  # 直前の本文テキスト（節見出し等）

    @property
    def ncols(self) -> int:
        return max((len(r) for r in self.rows), default=0)

    def cell(self, r: int, c: int) -> Cell | None:
        row = self.rows[r]
        return row[c] if c < len(row) else None

    def is_continuation(self, r: int, c: int) -> bool:
        """(r, c) のセルが上の行と同じ結合セルなら True。"""
        if r == 0:
            return False
        cur = self.cell(r, c)
        return cur is not None and cur is self.cell(r - 1, c)


class _BlockParser(HTMLParser):
    """テーブル（結合セル展開済み）と、テーブル間の本文テキストを文書順に集める。"""

    BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "br", "li", "tr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[TableGrid] = []
        self._text_buf: list[str] = []
        self._pending_rows: list[list[Cell]] | None = None
        self._cur_cells: list[Cell] | None = None
        self._cell_buf: list[str] | None = None
        self._cell_attrs: dict | None = None
        self._depth = 0  # ネストした table は無視して外側のみ扱う

    # -- text between tables
    def _flush_text(self) -> str:
        text = "".join(self._text_buf)
        self._text_buf = []
        return text

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._depth += 1
            if self._depth == 1:
                self._pending_rows = []
                self._context = self._flush_text()
            return
        if self._depth == 0:
            if tag in self.BLOCK_TAGS:
                self._text_buf.append("\n")
            return
        if tag == "tr":
            self._cur_cells = []
        elif tag in ("td", "th") and self._cur_cells is not None:
            self._cell_buf = []
            self._cell_attrs = dict(attrs)
            self._cell_attrs["_is_header"] = tag == "th"
        elif tag in ("br", "p", "div") and self._cell_buf is not None:
            self._cell_buf.append("\n")

    def handle_endtag(self, tag):
        if tag == "table":
            if self._depth == 1 and self._pending_rows is not None:
                grid = _expand(self._pending_rows)
                grid.context = getattr(self, "_context", "")
                if grid.rows:
                    self.tables.append(grid)
                self._pending_rows = None
            self._depth = max(0, self._depth - 1)
            return
        if self._depth == 0:
            if tag in self.BLOCK_TAGS:
                self._text_buf.append("\n")
            return
        if tag in ("td", "th") and self._cell_buf is not None and self._cur_cells is not None:
            attrs = self._cell_attrs or {}
            self._cur_cells.append(Cell(
                text=_clean_cell("".join(self._cell_buf)),
                rowspan=_span(attrs.get("rowspan")),
                colspan=_span(attrs.get("colspan")),
                is_header=bool(attrs.get("_is_header")),
            ))
            self._cell_buf = None
            self._cell_attrs = None
        elif tag == "tr" and self._cur_cells is not None:
            if self._pending_rows is not None:
                self._pending_rows.append(self._cur_cells)
            self._cur_cells = None
        elif tag in ("p", "div") and self._cell_buf is not None:
            self._cell_buf.append("\n")

    def handle_data(self, data):
        if self._cell_buf is not None:
            self._cell_buf.append(data)
        elif self._depth == 0:
            self._text_buf.append(data)

    def trailing_text(self) -> str:
        return "".join(self._text_buf)


def _span(v) -> int:
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError):
        return 1
    return max(1, min(n, 500))


def _clean_cell(s: str) -> str:
    s = s.replace("　", " ").replace("\xa0", " ")
    lines = [re.sub(r"[ \t\r]+", " ", ln).strip() for ln in s.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def _expand(raw_rows: list[list[Cell]]) -> TableGrid:
    """rowspan/colspan を展開した格子を作る。空セル位置は空 Cell で埋める。"""
    grid: list[list[Cell | None]] = []
    for r, cells in enumerate(raw_rows):
        while len(grid) <= r:
            grid.append([])
        row = grid[r]
        c = 0
        for cell in cells:
            while c < len(row) and row[c] is not None:
                c += 1
            for dr in range(cell.rowspan):
                while len(grid) <= r + dr:
                    grid.append([])
                target = grid[r + dr]
                for dc in range(cell.colspan):
                    while len(target) <= c + dc:
                        target.append(None)
                    if target[c + dc] is None:
                        target[c + dc] = cell
            c += cell.colspan
    # rowspan が表末尾を越えた分の空行は落とす
    rows: list[list[Cell]] = []
    for row in grid:
        if not row:
            continue
        rows.append([cell if cell is not None else Cell("") for cell in row])
    while rows and all(cell.text == "" for cell in rows[-1]):
        rows.pop()
    return TableGrid(rows=rows)


def parse_block(raw_block: str) -> list[TableGrid]:
    """XBRL テキストブロック（HTML エスケープ済み）→ テーブル列（各テーブルに直前本文 context 付き）。"""
    parser = _BlockParser()
    try:
        parser.feed(html.unescape(raw_block))
        parser.close()
    except Exception:
        return []
    return parser.tables


# ---------------------------------------------------------------------------
# 名称・分類・比率の正規化
# ---------------------------------------------------------------------------

CLASSIFICATIONS = [
    # (正規化ラベル, パターン)。順序は「より特定的なもの」を先に。
    ("持分法適用非連結子会社", r"持分法適用(の)?非連結子会社"),
    ("持分法非適用非連結子会社", r"持分法非適用(の)?非連結子会社"),
    ("非連結子会社", r"非連結子会社"),
    ("連結子会社", r"連結子会社"),
    ("持分法適用関連会社", r"持分法適用(の)?(関連会社|会社)"),
    ("持分法非適用関連会社", r"持分法非適用(の)?関連会社"),
    ("その他の関係会社", r"その他の関係会社"),
    ("関連会社", r"関連会社"),
    ("親会社", r"親会社"),
    ("子会社", r"子会社"),
]
_CLASS_RE = [(label, re.compile(pat)) for label, pat in CLASSIFICATIONS]
_CLASS_WORD = r"(持分法(適用|非適用)(の)?)?(非)?連結?子会社|(持分法(適用|非適用)(の)?)?関連会社|その他の関係会社|親会社|子会社"

def classify_text(text: str | None) -> str | None:
    """テキストに含まれる関係会社分類を返す（最も特定的なもの）。"""
    if not text:
        return None
    t = re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))
    for label, rx in _CLASS_RE:
        if rx.search(t):
            return label
    return None


_LABEL_SUFFIX_RE = re.compile(r"(等|など|の状況|(及び|および|と)共同支配企業|(及び|および)?共同支配企業|であります|です)$")


def is_label_only(text: str) -> bool:
    """「（連結子会社）」「(1) その他の関係会社」「持分法適用関連会社および共同支配企業」など、
    企業名を含まない分類ラベルだけのセルか。企業名（例「子会社A」）は False。"""
    t = unicodedata.normalize("NFKC", text or "").strip()
    if not t or len(t) > 40:
        return False
    if classify_text(t) is None:
        return False
    body = re.sub(r"[\s()（）\[\]［］《》【】「」『』〔〕<>0-9一二三四五六七八九十.．、,:：]+", "", t)
    for _ in range(3):
        body = _LABEL_SUFFIX_RE.sub("", body)
    for label, rx in _CLASS_RE:
        if body in (label, label.replace("の", "")) or rx.fullmatch(body):
            return True
    return False


_NOTE_RE = re.compile(r"[（(]\s*注[^)）]{0,12}[)）]\s*[0-9０-９、,.．・]*|※\s*[0-9０-９]*|＊\s*[0-9０-９]*|\*\s*[0-9]*")
_TRAILING_MARK_RE = re.compile(r"(?<=[)）㈱株社Ｄd])\s*[0-9０-９]{1,2}(?:[・,、][0-9０-９]{1,2})*$")
_LEGAL_RE = re.compile(
    r"^(株式会社|（株）|\(株\)|㈱|合同会社|（同）|有限会社|（有）|\(有\)|㈲|一般社団法人|一般財団法人|公益財団法人|公益社団法人|学校法人|医療法人(社団|財団)?|国立大学法人|独立行政法人|社会福祉法人)\s*|"
    r"\s*(株式会社|（株）|\(株\)|㈱|合同会社|（同）|有限会社|（有）|\(有\)|㈲)$"
)
_OTHERS_RE = re.compile(r"^(その他|他)?\s*[0-9０-９,，]+\s*社$|^(その他|他)\s*[0-9０-９,，]+\s*社")


def clean_name(raw: str) -> str:
    """セル原文 → 名寄せ・表示用の名称。分類プレフィックス・注記記号・末尾の脚注番号を除く。"""
    s = unicodedata.normalize("NFKC", raw or "")
    s = s.replace("\n", " ")
    s = re.sub(r"^\s*[（(《【「〔\[][^）)》】」〕\]]{0,20}(子会社|関連会社|関係会社|親会社)[^）)》】」〕\]]{0,10}[）)》】」〕\]]\s*", "", s)
    s = re.sub(r"^\s*(" + _CLASS_WORD + r")\s+(?=\S)", "", s)
    s = _NOTE_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip(" ・,、")
    s = _TRAILING_MARK_RE.sub("", s).strip()
    return s


def strip_legal_form(name: str) -> str:
    """法人格を除いた名称（表示・名寄せ用の補助）。"""
    n = _LEGAL_RE.sub("", name).strip()
    return n or name


_NUMERIC_ONLY_RE = re.compile(r"^[\s0-9０-９.,．、()（）%％△▲\-−―－ー・/\[\]［］]*$")
_JUNK_WORDS_RE = re.compile(
    r"^(計|合計|小計|総数|―|－|ー|該当事項はありません|該当なし|なし|同上|同左|名称|氏名又は名称|氏名|会社名|相手先|顧客名)$|"
    r"^(注|注記|前連結会計年度|当連結会計年度|前事業年度|当事業年度|自己株式|該当)"
)


def name_problem(name: str | None) -> str | None:
    """企業名として不適切なら理由を返す（None なら妥当）。"""
    if not name:
        return "empty"
    n = unicodedata.normalize("NFKC", name).strip()
    if len(n) < 2:
        return "too_short"
    if _NUMERIC_ONLY_RE.match(n):
        return "numeric_only"
    if _OTHERS_RE.match(n):
        return "others_count"
    if _JUNK_WORDS_RE.match(n):
        return "label"
    if is_label_only(n):
        return "classification_label"
    if not re.search(r"[A-Za-z぀-ヿ一-鿿Ａ-Ｚａ-ｚ]", n):
        return "no_letters"
    return None


_NUM_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)")


def parse_ratio_cell(cell: str | None) -> dict:
    """議決権割合セル → {'total','indirect','raw','owned_marker'}。

    有報の慣行: 括弧の外が合計（直接＋間接）、括弧内が間接所有（内数）。
    「被所有」の文字があれば所有方向マーカーを立てる。
    """
    out = {"total": None, "indirect": None, "raw": None, "owned_marker": False, "direct_marker": False}
    if not cell:
        return out
    s = unicodedata.normalize("NFKC", cell).replace("\n", " ").strip()
    out["raw"] = s
    if "被所有" in s:
        out["owned_marker"] = True
    if re.search(r"(?<!被)所有", s):
        out["direct_marker"] = True
    s2 = s.replace(",", "").replace("△", "-").replace("▲", "-")
    # 括弧内（間接・内数）を取り出す
    inner = re.findall(r"[（(]\s*(\d{1,3}(?:\.\d+)?)\s*[%％]?\s*[)）]", s2)
    outer = re.sub(r"[（(][^）)]*[)）]", " ", s2)
    nums = _NUM_RE.findall(outer)
    total = _pct(nums[0]) if nums else None
    indirect = _pct(inner[0]) if inner else None
    if total is None and indirect is not None:
        # 「(87.74)」だけのセル: 合計不明・間接のみ
        out["indirect"] = indirect
        return out
    out["total"] = total
    out["indirect"] = indirect
    return out


def _pct(v: str) -> float | None:
    try:
        x = float(v)
    except ValueError:
        return None
    if 0 <= x <= 100:
        return round(x / 100, 4)
    return None


# ---------------------------------------------------------------------------
# 列見出しの検出
# ---------------------------------------------------------------------------

def _norm_header(text: str) -> str:
    return re.sub(r"[\s（）()%％]+", "", unicodedata.normalize("NFKC", text or ""))


def find_header(grid: TableGrid, keywords: dict[str, list[str]], max_rows: int = 4) -> tuple[int, dict[str, int]]:
    """先頭数行から列役割を検出。戻り値: (見出し最終行 index, {役割: 列index})。"""
    roles: dict[str, int] = {}
    header_end = -1
    all_kws = [k for kws in keywords.values() for k in kws]
    for r, row in enumerate(grid.rows[:max_rows]):
        matched = False
        for c, cell in enumerate(row):
            h = _norm_header(cell.text)
            if not h or len(h) > 40:
                continue
            if any(k in h for k in all_kws):
                matched = True  # 2 段見出しの下段（「所有割合」「被所有割合」等）も見出し行に含める
            for role, kws in keywords.items():
                if role in roles:
                    continue
                if any(k in h for k in kws):
                    roles[role] = c
        if matched:
            header_end = r
        elif roles:
            break  # 見出しの後にキーワードのない行が来たらデータ開始
    return header_end, roles


AFFILIATED_HEADER = {
    "name": ["名称", "会社名", "社名"],
    "vote": ["議決権", "所有割合", "被所有割合", "出資割合", "持分比率", "出資比率"],
    "classification": ["区分", "属性", "関係会社の種類", "種類"],
    "relationship": ["関係内容"],
    "business": ["事業の内容", "事業内容"],
}
SHAREHOLDER_HEADER = {
    "name": ["氏名又は名称", "氏名", "名称"],
    "ratio": ["割合"],
    "shares": ["所有株式数", "株式数"],
}
CUSTOMER_HEADER = {
    "name": ["相手先", "顧客", "名称", "販売先", "得意先"],
    "ratio": ["割合"],
    "amount": ["金額", "販売高", "売上高"],
    "segment": ["セグメント"],
}


# ---------------------------------------------------------------------------
# 関係会社の状況
# ---------------------------------------------------------------------------

_OWNED_HEADER_RE = re.compile(r"被所有")
_OWN_HEADER_RE = re.compile(r"(?<!被)所有")


_NOTE_ALL_SUBSIDIARY_RE = re.compile(
    r"上記(の)?(各)?(会社|子会社|関係会社|(\d+|[0-9０-９]+)社)は(、)?(すべて|全て|いずれも)?(、)?連結子会社")


def extract_affiliated(tables: list[TableGrid], text: str = "") -> list[dict]:
    out: list[dict] = []
    section_cls: str | None = None
    # 注記「上記会社は連結子会社であります」がある場合、ラベルのない行の既定分類にする
    note_cls = "連結子会社" if _NOTE_ALL_SUBSIDIARY_RE.search(
        re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or ""))) else None
    row_cls: str | None = None  # 表内のラベル行から継承する分類（改ページで分割された続き表にも引き継ぐ）
    for ti, grid in enumerate(tables):
        # 節見出し（テーブル直前の本文）から分類を継承。本文に複数あれば末尾に近いものを採用
        ctx_cls = _last_classification(grid.context)
        if ctx_cls:
            section_cls = ctx_cls
            row_cls = None
        # 分類ラベルだけの表（1 セル）は節見出しとして扱う
        if len(grid.rows) <= 2 and grid.ncols <= 1:
            label = "\n".join(c.text for row in grid.rows for c in row)
            if is_label_only(label):
                section_cls = classify_text(label)
                row_cls = None
            continue
        header_end, roles = find_header(grid, AFFILIATED_HEADER)
        if "vote" not in roles or "name" not in roles:
            continue  # 関係会社テーブルでない（注記表・損益情報等）
        name_col = roles.get("name", 0)
        cols = _vote_columns(grid, header_end)
        vote_col = cols["own"] if cols["own"] is not None else cols["combined"]
        owned_col = cols["owned"]
        if vote_col is None and owned_col is None:
            continue
        header_direction = cols["direction"]
        # 見出しの名称セルに「（連結子会社）」が併記される様式
        header_name_cls = classify_text("\n".join(
            grid.rows[r][name_col].text for r in range(header_end + 1) if name_col < len(grid.rows[r])))
        if header_name_cls:
            row_cls = header_name_cls
        cls_col = roles.get("classification")
        rel_col = roles.get("relationship")

        prev_rec: dict | None = None
        for r in range(header_end + 1, len(grid.rows)):
            row = grid.rows[r]
            name_cell = grid.cell(r, name_col)
            if name_cell is None:
                continue
            texts = [c.text for c in row]
            nonempty = [t for t in texts if t and not _DASH_RE.match(t)]
            # 分類ラベルだけの行（例: 「（連結子会社）」を 1 行で置く様式）
            if nonempty and all(is_label_only(t) for t in nonempty):
                row_cls = classify_text(" ".join(nonempty))
                prev_rec = None
                continue
            # 行全体に広がる見出し行（セグメント名等）は分類でなければ読み飛ばす
            if name_cell.colspan >= max(2, grid.ncols - 1) and not grid.is_continuation(r, name_col):
                if classify_text(name_cell.text) and is_label_only(name_cell.text):
                    row_cls = classify_text(name_cell.text)
                prev_rec = None
                continue
            if grid.is_continuation(r, name_col):
                # 結合セルの続き行: 比率の追加情報のみ取り込む
                if prev_rec is not None:
                    for col in (vote_col, owned_col):
                        if col is None or col >= len(row) or grid.is_continuation(r, col):
                            continue
                        extra = parse_ratio_cell(row[col].text)
                        if prev_rec["ratio_indirect"] is None and extra["indirect"] is not None:
                            prev_rec["ratio_indirect"] = extra["indirect"]
                        if prev_rec["ratio_total"] is None and extra["total"] is not None:
                            prev_rec["ratio_total"] = extra["total"]
                        if extra["raw"]:
                            prev_rec["ratio_raw"] = f"{prev_rec['ratio_raw'] or ''} {extra['raw']}".strip()
                        if extra["owned_marker"]:
                            prev_rec["owned_by_counterparty"] = True
                            prev_rec["direction_source"] = "cell"
                continue
            raw_name = name_cell.text
            if not raw_name:
                continue
            name = clean_name(raw_name)
            problem = name_problem(name)
            prefix_cls = classify_text(_leading_paren(raw_name))
            # 名前セルが「連結子会社」等のラベルだけなら分類を継承
            if problem == "classification_label" or (problem == "empty" and prefix_cls):
                row_cls = classify_text(raw_name)
                prev_rec = None
                continue
            # 分類: 行頭括弧 > 区分列 > 表内ラベル行 > 節見出し
            col_cls = classify_text(row[cls_col].text) if cls_col is not None and cls_col < len(row) else None
            if prefix_cls:
                cls, cls_src = prefix_cls, "prefix"
                row_cls = prefix_cls  # 「（連結子会社）A社」の後続行は同じ分類を継承
            elif col_cls:
                cls, cls_src = col_cls, "column"
            elif row_cls:
                cls, cls_src = row_cls, "row"
            elif section_cls:
                cls, cls_src = section_cls, "section"
            elif note_cls:
                cls, cls_src = note_cls, "note"
            else:
                cls, cls_src = None, None

            ratio = parse_ratio_cell(row[vote_col].text if vote_col is not None and vote_col < len(row) else "")
            owned_ratio = parse_ratio_cell(row[owned_col].text if owned_col is not None and owned_col < len(row) else "")
            # 所有／被所有が別列の様式: 被所有列に値があればその行は「相手が提出会社を所有」
            if owned_col is not None and (owned_ratio["total"] is not None or owned_ratio["indirect"] is not None) \
                    and ratio["total"] is None and ratio["indirect"] is None:
                ratio = owned_ratio
                ratio["owned_marker"] = True
            # 所有方向: セル内の明示マーカー（所有／被所有）> 分類 > 列見出し > 既定（提出会社が所有）
            # 明示マーカーは継承した分類より優先し、矛盾があれば分類を不明に戻して要確認にする
            if ratio["owned_marker"]:
                owned, dsrc = True, "cell"
            elif ratio["direct_marker"]:
                owned, dsrc = False, "cell"
            elif cls in ("親会社", "その他の関係会社"):
                owned, dsrc = True, "classification"
            elif header_direction == "owned":
                owned, dsrc = True, "header"
            elif header_direction == "owning":
                owned, dsrc = False, "header"
            else:
                owned, dsrc = False, "default"
            # 分類と明示的な方向（セル内の所有／被所有表記・別列）が矛盾する場合は、
            # 継承した分類を捨てて要確認にする（例: 親会社行の後に続く子会社行）
            conflict = False
            if cls is not None and dsrc == "cell":
                cls_owned = cls in ("親会社", "その他の関係会社")
                if cls_owned != owned:
                    conflict = True
                    # 継承した分類（ラベル行・節見出し・注記・見出しセル・区分列）は捨てる。
                    # 同じ行に書かれた行頭の分類（prefix）は残し、矛盾として要確認にする
                    if cls_src in ("row", "section", "note", "column"):
                        cls, cls_src = None, None
            if header_direction == "owned" and cls in ("連結子会社", "非連結子会社", "子会社", "持分法適用非連結子会社"):
                conflict = True
            rec = {
                "counterparty_name": name,
                "raw_name": raw_name,
                "name_problem": problem,
                "classification": cls,
                "classification_source": cls_src,
                "owned_by_counterparty": owned,
                "direction_source": dsrc,
                "direction_conflict": conflict,
                "ratio_total": ratio["total"],
                "ratio_indirect": ratio["indirect"],
                "ratio_raw": ratio["raw"],
                "relationship_note": (row[rel_col].text if rel_col is not None and rel_col < len(row) else None) or None,
                "table_index": ti,
                "row_index": r,
            }
            out.append(rec)
            prev_rec = rec
    return out


_VOTE_KEYS = AFFILIATED_HEADER["vote"]
_DASH_RE = re.compile(r"^[\s―－ー\-−‐・．.、,]*$")


def _vote_columns(grid: TableGrid, header_end: int) -> dict:
    """議決権割合の列を特定する。

    戻り値: {"own": 所有割合列, "owned": 被所有割合列, "combined": 所有(被所有)併記列,
             "direction": 見出しだけで方向が決まる場合 'owning'/'owned'/None}
    2 段見出しで「所有割合」「被所有割合」が別列に分かれる様式（例: 日鉄ソリューションズ）にも対応する。
    """
    own = owned = combined = None
    for c in range(grid.ncols):
        cells = []
        for r in range(header_end + 1):
            cell = grid.cell(r, c)
            if cell is not None and cell.text and (not cells or cells[-1] is not cell):
                cells.append(cell)
        if not cells:
            continue
        joined = _norm_header("\n".join(cell.text for cell in cells))
        if not any(k in joined for k in _VOTE_KEYS):
            continue
        last = _norm_header(cells[-1].text)
        has_owned = "被所有" in last
        has_own = bool(re.search(r"(?<!被)所有|出資割合|持分比率|出資比率", last))
        if has_owned and not has_own:
            owned = c if owned is None else owned
        elif has_own and not has_owned:
            own = c if own is None else own
        else:
            combined = c if combined is None else combined
    direction = None
    if own is not None and owned is not None:
        direction = None  # 行ごとに列の値で決める
    elif owned is not None and own is None and combined is None:
        direction = "owned"
        combined = owned
        owned = None
    elif own is not None and combined is None:
        direction = "owning"
    elif combined is not None:
        joined_all = _norm_header("\n".join(
            grid.cell(r, combined).text for r in range(header_end + 1) if grid.cell(r, combined) is not None))
        if "被所有" not in joined_all:
            direction = "owning"
    return {"own": own, "owned": owned, "combined": combined, "direction": direction}


_LEADING_LABEL_RE = re.compile(
    r"^\s*(?:[（(《【「〔\[]\s*(?P<a>[^）)》】」〕\]]{1,30})\s*[）)》】」〕\]]|(?P<b>" + _CLASS_WORD + r")(?=\s))")


def _leading_paren(raw: str) -> str | None:
    """行頭の「（連結子会社）」「《親会社》」「連結子会社␣A社」から分類ラベル部分を返す。"""
    m = _LEADING_LABEL_RE.match(unicodedata.normalize("NFKC", raw or ""))
    if not m:
        return None
    return m.group("a") or m.group("b")


_ASOF_LINE_RE = re.compile(r"\d{4}年\s*\d{1,2}月\s*\d{1,2}日\s*現在")


def _last_classification(text: str) -> str | None:
    """本文テキストの末尾側に近い分類見出しを返す。「の状況」のような総称見出しは無視。"""
    if not text:
        return None
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in unicodedata.normalize("NFKC", text).split("\n")]
    lines = [_ASOF_LINE_RE.sub("", ln).strip() for ln in lines if ln]
    for ln in reversed(lines):
        if not ln:
            continue
        if "関係会社の状況" in ln and classify_text(ln.replace("関係会社の状況", "")) is None:
            continue
        # 注記文（「連結子会社であります」等）は見出しではない
        if len(ln) > 40 or ln.startswith(("(注", "（注", "注")):
            continue
        cls = classify_text(ln)
        if cls:
            return cls
    return None


# ---------------------------------------------------------------------------
# 大株主の状況
# ---------------------------------------------------------------------------

_ASOF_RE = re.compile(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日\s*現在")
_AGENT_RE = re.compile(r"[（(]\s*常任代理人[^）)]*[)）]?")


def find_as_of(text: str) -> str | None:
    """「2025年３月31日現在」→ '2025-03-31'。"""
    if not text:
        return None
    ms = _ASOF_RE.findall(unicodedata.normalize("NFKC", text))
    if not ms:
        return None
    y, mo, d = (int(x) for x in ms[-1])  # 表に最も近い（末尾側の）「…現在」を採用
    return f"{y:04d}-{mo:02d}-{d:02d}"


def extract_shareholders(tables: list[TableGrid], block_text: str = "") -> list[dict]:
    out: list[dict] = []
    as_of = find_as_of(block_text)
    for ti, grid in enumerate(tables):
        ctx_as_of = find_as_of(grid.context) or as_of
        header_end, roles = find_header(grid, SHAREHOLDER_HEADER)
        if "ratio" not in roles:
            continue
        # 注記に添えられる大量保有報告書の写し（基準日・分母が大株主の状況と異なる）を区別する
        ctx_tail = unicodedata.normalize("NFKC", grid.context)[-400:]
        header_text = "".join(c.text for r in grid.rows[: header_end + 1] for c in r)
        large_holding = bool(re.search(r"大量保有|変更報告書|株券等保有割合", ctx_tail + header_text))
        name_col = roles.get("name", 0)
        ratio_col = roles["ratio"]
        for r in range(header_end + 1, len(grid.rows)):
            row = grid.rows[r]
            if grid.is_continuation(r, name_col) or name_col >= len(row):
                continue
            raw_name = row[name_col].text
            if not raw_name:
                continue
            holder = unicodedata.normalize("NFKC", raw_name).replace("\n", " ")
            holder = _AGENT_RE.sub("", holder)
            name = clean_name(holder)
            problem = name_problem(name)
            if problem in ("label", "empty", "too_short"):
                continue
            ratio = parse_ratio_cell(row[ratio_col].text if ratio_col < len(row) else "")
            out.append({
                "counterparty_name": name,
                "raw_name": raw_name,
                "name_problem": problem,
                "ratio_total": ratio["total"],
                "ratio_raw": ratio["raw"],
                "as_of": ctx_as_of,
                "report_kind": "large_holding_report" if large_holding else "major_shareholders",
                "table_index": ti,
                "row_index": r,
            })
    return out


# ---------------------------------------------------------------------------
# 主要な顧客
# ---------------------------------------------------------------------------

_UNIT_RE = re.compile(r"単位\s*[:：]\s*([^)）\s]+)")


def extract_customers(tables: list[TableGrid]) -> list[dict]:
    out: list[dict] = []
    for ti, grid in enumerate(tables):
        header_end, roles = find_header(grid, CUSTOMER_HEADER)
        if "name" not in roles:
            continue
        name_col = roles.get("name", 0)
        amount_col = roles.get("amount")
        unit_m = _UNIT_RE.search(unicodedata.normalize("NFKC", grid.context + "\n" + "\n".join(
            c.text for r in grid.rows[:header_end + 1] for c in r)))
        unit = unit_m.group(1) if unit_m else None
        # 「前連結会計年度 / 当連結会計年度」の 2 期並記は当期（右側）の割合列を採用
        ratio_cols = [c for c, cell in enumerate(grid.rows[header_end]) if header_end >= 0 and "割合" in cell.text] \
            if header_end >= 0 else []
        ratio_col = ratio_cols[-1] if ratio_cols else roles.get("ratio")
        for r in range(header_end + 1, len(grid.rows)):
            row = grid.rows[r]
            if grid.is_continuation(r, name_col) or name_col >= len(row):
                continue
            raw_name = row[name_col].text
            name = clean_name(raw_name)
            problem = name_problem(name)
            if problem in ("label", "empty", "too_short"):
                continue
            ratio = parse_ratio_cell(row[ratio_col].text) if ratio_col is not None and ratio_col < len(row) else parse_ratio_cell(None)
            amount = None
            if amount_col is not None and amount_col < len(row):
                m = re.search(r"\d[\d,]*", unicodedata.normalize("NFKC", row[amount_col].text))
                if m:
                    try:
                        amount = int(m.group(0).replace(",", ""))
                    except ValueError:
                        amount = None
            out.append({
                "counterparty_name": name,
                "raw_name": raw_name,
                "name_problem": problem,
                "ratio_total": ratio["total"],
                "ratio_raw": ratio["raw"],
                "sales_amount": amount,
                "sales_unit": unit,
                "table_index": ti,
                "row_index": r,
            })
    return out


def block_text(raw_block: str) -> str:
    """ブロック全体のプレーンテキスト（基準日検出などに使う）。"""
    return re.sub(r"<[^>]+>", " ", html.unescape(raw_block or ""))
