"""有価証券報告書「役員の状況」ブロック（InformationAboutOfficersTextBlock）から、役員の兼任状況を抽出する。

役員一覧の表は「役職名 / 氏名 / 生年月日 / 略歴 / 任期 / 所有株式数」で、略歴欄は
「年月 ＋ 経歴」の行が入れ子の表（または <br> 区切り）で並ぶ。edinet_tables のパーサーは入れ子を平坦化する
ため、ここでは入れ子を保ったまま HTML を読み、役員ごとに略歴行を復元する。

抽出するのは「現在も務めている他社の役職」（役員兼任）:
  - 略歴行に現任の印（現任／現在に至る／現職／現在）があり、退任・辞任の記述がない行
  - 行頭の会社名（「同社」は直前に出た会社、「当社」は提出会社）と役職名を分ける
  - 「(注) …は、○○株式会社の社外取締役を兼務しております」の注記も同様に読む
会社名の上場企業への照合は build_masters 側（別名索引）で行う。ここでは原文名のまま返す。
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

# 現任の印。「現在の」「現○○株式会社」（改名表記）は含めない
CURRENT_RE = re.compile(r"現任|現在に至る|現職|\(現在\)|（現在）|現在$")
RESIGNED_RE = re.compile(r"退任|退職|辞任|退社|退官|逝去|死去|解任|満了")
# 西暦（1984年４月）と和暦（昭和59年４月・平成元年）の両方
_YEAR = r"(?:\d{4}|[０-９]{4}|(?:昭和|平成|令和)\s*(?:\d{1,2}|[０-９]{1,2}|元))"
DATE_RE = re.compile(_YEAR + r"年\s*(\d{1,2}|[０-９]{1,2})月(?:\s*(\d{1,2}|[０-９]{1,2})日)?")
# 生年月日セル。「1958年１月９日 （男性）」のように性別が続く書き方もある
BIRTH_RE = re.compile(r"^\s*" + _YEAR + r"年\s*(\d{1,2}|[０-９]{1,2})月\s*(\d{1,2}|[０-９]{1,2})日\s*生?\b")
# 役職語（この語の直前までを会社名とみなす）。長いものを先に
ROLE_WORDS = [
    "代表取締役", "取締役", "監査役", "執行役員", "執行役", "理事長", "理事", "会長", "副会長", "社長", "副社長",
    "専務", "常務", "顧問", "相談役", "参与", "委員長", "委員", "所長", "学長", "総長", "教授", "講師", "研究員",
    "パートナー", "代表", "頭取", "社主", "支配人", "支店長", "本部長", "部長", "室長", "総裁", "副総裁", "館長",
    "審議役", "参事", "主席", "主幹", "議長",
    "President", "Chairman", "Chairperson", "Chair", "Director", "Officer", "CEO", "COO", "CFO", "CTO", "Partner",
    "Advisor", "Adviser", "Member", "Professor", "Fellow", "Executive", "Vice",
]
ROLE_RE = re.compile("|".join(re.escape(w) for w in sorted(ROLE_WORDS, key=len, reverse=True)))
# 会社らしさ（照合前の粗い判定）。法人格や「社」「銀行」「グループ」等で終わる、または始まる
COMPANY_HINT_RE = re.compile(
    r"株式会社|㈱|\(株\)|（株）|有限会社|㈲|合同会社|相互会社|有限公司|Inc\.?|Corp\.?|Corporation|Co\.,|Ltd\.?|LLC|GmbH|"
    r"S\.A\.|N\.V\.|B\.V\.|Limited|Company|社$|銀行|信託|生命|海上|火災|証券|ホールディングス|グループ|工業|製作所|"
    r"商事|物産|不動産|電力|ガス|鉄道|運輸|製薬|化学|製鋼|製紙|重工|電機|電気|自動車|建設|保険|リース|ファンド|機構|財団|法人|大学|協会|組合|センター"
)
NAME_SPACE_RE = re.compile(r"[\s　]+")


@dataclass
class Officer:
    role: str
    name: str
    birth: str | None
    career: list[tuple[str | None, str]] = field(default_factory=list)  # (年月, 経歴)


# ---------------------------------------------------------------------------
# 入れ子を保つ HTML パーサー
# ---------------------------------------------------------------------------

@dataclass
class _Cell:
    lines: list[str] = field(default_factory=list)   # ブロック要素・<br> で区切った行
    tables: list["_Table"] = field(default_factory=list)  # セル内の入れ子の表
    _buf: list[str] = field(default_factory=list)

    def flush(self) -> None:
        text = NAME_SPACE_RE.sub(" ", "".join(self._buf)).strip()
        self._buf.clear()
        if text:
            self.lines.append(text)


@dataclass
class _Table:
    rows: list[list[_Cell]] = field(default_factory=list)


class _NestedParser(HTMLParser):
    """table > tr > td の入れ子を木にする。表の外の本文は notes に集める。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[_Table] = []       # 最上位の表（文書順）
        self._stack: list[_Table] = []       # 開いている表
        self._cell_stack: list[_Cell] = []   # 開いているセル
        self.notes: list[str] = []           # 表の外のテキスト行
        self._note_buf: list[str] = []

    def _flush_note(self) -> None:
        text = NAME_SPACE_RE.sub(" ", "".join(self._note_buf)).strip()
        self._note_buf.clear()
        if text:
            self.notes.append(text)

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            t = _Table()
            if self._cell_stack:
                self._cell_stack[-1].flush()
                self._cell_stack[-1].tables.append(t)
            else:
                self._flush_note()
                self.tables.append(t)
            self._stack.append(t)
        elif tag == "tr" and self._stack:
            self._stack[-1].rows.append([])
        elif tag in ("td", "th") and self._stack:
            if not self._stack[-1].rows:
                self._stack[-1].rows.append([])
            cell = _Cell()
            self._stack[-1].rows[-1].append(cell)
            self._cell_stack.append(cell)
        elif tag in ("br", "p", "div", "li"):
            if self._cell_stack:
                self._cell_stack[-1].flush()
            else:
                self._flush_note()

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell_stack:
            self._cell_stack[-1].flush()
            self._cell_stack.pop()
        elif tag == "table" and self._stack:
            self._stack.pop()
        elif tag in ("p", "div", "li", "tr"):
            if self._cell_stack:
                self._cell_stack[-1].flush()
            else:
                self._flush_note()

    def handle_data(self, data):
        if self._cell_stack:
            self._cell_stack[-1]._buf.append(data)
        else:
            self._note_buf.append(data)

    def close(self):
        super().close()
        self._flush_note()


def _cell_text(cell: _Cell) -> str:
    return " ".join(cell.lines)


def _is_date(s: str) -> bool:
    return bool(DATE_RE.fullmatch(s.strip()))


def _career_from_cell(cell: _Cell) -> list[tuple[str | None, str]]:
    """略歴セル → (年月, 経歴) の列。入れ子の表なら行ごと、<br> 区切りなら行の並びから復元する。"""
    out: list[tuple[str | None, str]] = []
    if cell.tables:
        for t in cell.tables:
            for row in t.rows:
                if not row:
                    continue
                if len(row) >= 2:
                    dates = [l for l in row[0].lines]
                    texts = [l for l in row[1].lines] + [l for c in row[2:] for l in c.lines]
                    # 年月と経歴が同じ行数なら 1:1、違えば年月なしで経歴を並べる（複数行セルの書き方）
                    if len(dates) == len(texts):
                        out.extend(zip(dates, texts))
                    else:
                        for l in texts:
                            out.append((dates[0] if len(dates) == 1 else None, l))
                else:
                    out.extend(_split_dated_lines(row[0].lines))
        return out
    return _split_dated_lines(cell.lines)


def _split_dated_lines(lines: list[str]) -> list[tuple[str | None, str]]:
    """「2019年6月 ○○入社」のような行、または年月だけの行と経歴だけの行の並びを (年月, 経歴) にする。"""
    out: list[tuple[str | None, str]] = []
    pending_date: str | None = None
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if _is_date(s):
            pending_date = s
            continue
        m = DATE_RE.match(s)
        if m and m.end() < len(s):
            out.append((m.group(0), s[m.end():].strip()))
            pending_date = None
        else:
            out.append((pending_date, s))
            pending_date = None
    return out


def _norm_name(s: str) -> str:
    return NAME_SPACE_RE.sub(" ", s).strip()


def parse_officers(raw_block: str) -> tuple[list[Officer], list[str]]:
    """役員の状況ブロック → (役員の列, 注記テキストの列)。"""
    p = _NestedParser()
    try:
        p.feed(html.unescape(raw_block or ""))
        p.close()
    except Exception:
        return [], []
    officers: list[Officer] = []
    for t in p.tables:
        header_idx: dict[str, int] | None = None
        for row in t.rows:
            texts = [_cell_text(c) for c in row]
            # 見出しは「氏 名」「略 歴」のように文字間に空白が入ることがある
            squeezed = [NAME_SPACE_RE.sub("", tx) for tx in texts]
            joined = "".join(squeezed)
            if "氏名" in joined and ("略歴" in joined or "生年月日" in joined):
                header_idx = {}
                for i, tx in enumerate(squeezed):
                    for key in ("役職名", "氏名", "生年月日", "略歴", "任期", "所有株式数"):
                        if key in tx and key not in header_idx:
                            header_idx[key] = i
                continue
            if header_idx is None or "氏名" not in header_idx:
                continue
            i_name = header_idx["氏名"]
            if i_name >= len(row):
                continue
            name = _norm_name(_cell_text(row[i_name]))
            i_birth = header_idx.get("生年月日")
            birth = _cell_text(row[i_birth]) if i_birth is not None and i_birth < len(row) else ""
            if not name or not BIRTH_RE.match(birth or ""):
                # 生年月日がない行（注記・空行）は役員行ではない
                continue
            i_role = header_idx.get("役職名", 0)
            role = _norm_name(_cell_text(row[i_role])) if i_role < len(row) else ""
            i_car = header_idx.get("略歴")
            career = _career_from_cell(row[i_car]) if i_car is not None and i_car < len(row) else []
            officers.append(Officer(role=role, name=name, birth=birth.strip(), career=career))
    notes = [n for n in p.notes if n]
    # 表内の注記行（役員行でないもの）も注記として拾う
    for t in p.tables:
        for row in t.rows:
            texts = [_cell_text(c) for c in row]
            if len(texts) <= 2 and any("兼" in tx for tx in texts):
                notes.append(" ".join(texts))
    return officers, notes


# ---------------------------------------------------------------------------
# 兼任の抽出
# ---------------------------------------------------------------------------

def split_rename(name: str) -> list[str]:
    """「東和不動産㈱（現トヨタ不動産㈱）」→ ['トヨタ不動産㈱', '東和不動産㈱']（現在名を先に）。"""
    m = re.match(r"^(.*?)\s*[（(]\s*現在?の?\s*[:：]?\s*(.+?)\s*[)）]\s*$", name)
    if m and m.group(1).strip():
        return [m.group(2).strip(), m.group(1).strip()]
    return [name.strip()]


def split_company_role(text: str) -> tuple[str | None, str | None]:
    """経歴テキスト「○○株式会社社外取締役」→ (会社名, 役職名)。会社名が判別できなければ (None, text)。"""
    s = re.sub(r"[（(]\s*(現任|現在に至る|現職|現在)\s*[)）]|現在に至る|現任$", "", text).strip()
    m = ROLE_RE.search(s)
    if not m:
        return None, s or None
    company = s[: m.start()].strip(" 　・、,")
    role = re.sub(r"(?:に就任|就任|に選任|選任)$", "", s[m.start():].strip())
    # 「社外取締役」「常勤監査役」のような修飾は役職側に寄せる
    for pre in ("社外", "常勤", "非常勤", "独立", "代表", "専任", "特別", "上席", "上級", "筆頭", "常任"):
        if company.endswith(pre):
            company = company[: -len(pre)].strip()
            role = pre + role
    if not company:
        return None, role
    return company, role


def _looks_like_company(name: str) -> bool:
    return bool(COMPANY_HINT_RE.search(name)) and not re.fullmatch(r"(当社|同社|同行|同)", name)


def current_positions(officer: Officer, filer_name: str | None) -> list[dict]:
    """役員の略歴から、現在も務めている他社の役職を返す。"""
    out: list[dict] = []
    last_company: str | None = None
    for date, text in officer.career:
        company, role = split_company_role(text)
        if company:
            if re.fullmatch(r"(当社|当行|当行グループ|当社グループ)", company):
                company = None  # 提出会社
            elif re.fullmatch(r"(同社|同行|同グループ|同法人|同機構|同大学)", company):
                company = last_company
            else:
                last_company = company
        if not CURRENT_RE.search(text) or RESIGNED_RE.search(text):
            continue
        if not company or not role:
            continue
        if not _looks_like_company(company):
            continue
        out.append({
            "person": officer.name,
            "role_at_filer": officer.role,
            "counterparty_name": company,
            "counterparty_candidates": split_rename(company),
            "role_at_counterparty": role,
            "since": date,
            "quote": f"{date or ''} {text}".strip(),
            "basis": "career_current",
        })
    return out


NOTE_RE = re.compile(
    r"(?P<person>[^\s、。,（）()]{2,10}(?:\s[^\s、。,（）()]{1,10})?)\s*(?:氏|は|、)?\s*は?、?\s*"
    r"(?P<company>[^\s、。,（）()]{2,40}?(?:株式会社|㈱|銀行|生命|海上|証券|ホールディングス|グループ|大学|法人|Inc\.|Corp\.|Ltd\.))の"
    r"(?P<role>[^\s、。,（）()]{2,20}?)を(?:兼務|兼任)"
)


def positions_from_notes(notes: list[str], officers: list[Officer]) -> list[dict]:
    """注記「X は、○○株式会社の社外取締役を兼務しております」→ 兼任行。氏名は役員一覧の氏名と照合する。"""
    names = {NAME_SPACE_RE.sub("", o.name): o for o in officers}
    out: list[dict] = []
    for note in notes:
        for m in NOTE_RE.finditer(note):
            person = NAME_SPACE_RE.sub("", m.group("person"))
            person = re.sub(r"^(取締役|社外取締役|監査役|社外監査役|執行役員|代表取締役)+", "", person)
            officer = names.get(person)
            if officer is None:
                # 「取締役 山田 太郎」のように役職付きの場合は末尾一致で探す
                cands = [o for k, o in names.items() if k and person.endswith(k)]
                officer = cands[0] if len(cands) == 1 else None
            if officer is None:
                continue
            company = m.group("company")
            out.append({
                "person": officer.name,
                "role_at_filer": officer.role,
                "counterparty_name": company,
                "counterparty_candidates": split_rename(company),
                "role_at_counterparty": m.group("role"),
                "since": None,
                "quote": m.group(0),
                "basis": "note_concurrent",
            })
    return out


def extract_officer_positions(raw_block: str, filer_name: str | None = None) -> list[dict]:
    """ブロック → 兼任行（他社での現任の役職）の列。同一人物・同一会社の重複は 1 行にまとめる。"""
    officers, notes = parse_officers(raw_block)
    rows = []
    for o in officers:
        rows.extend(current_positions(o, filer_name))
    rows.extend(positions_from_notes(notes, officers))
    seen = set()
    uniq = []
    for r in rows:
        key = (NAME_SPACE_RE.sub("", r["person"]), r["counterparty_candidates"][0], r["role_at_counterparty"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    return uniq


def officer_count(raw_block: str) -> int:
    return len(parse_officers(raw_block)[0])
