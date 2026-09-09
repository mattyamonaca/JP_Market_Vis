"""企業名の正規化と別名辞書（Issue #4）。

名寄せ（build_masters.py）と検索索引（M4 の name_kana / aliases）で同じ辞書 aliases.json を使う。

照合キーの作り方（`match_key`）:
  NFKC 正規化 → 旧字体・異体字の置換 → 法人格の除去 → 空白・中黒・ハイフンの除去 → 小文字化
法人格（株式会社・(株)・㈱・Inc.・Co., Ltd.・S.A.・有限公司 等）は除くが、
「ホールディングス」「グループ」等は法人の同一性に関わるため除かない
（旧実装は「ホールディングス」「HD」を除いており、持株会社と同名の事業会社を誤統合し得た）。

別名（aliases.json の listed / entities）は、法人格を除いた原文名との**完全一致**でだけ照合する。
類似名だけでの自動統合はしない。
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

ALIASES_PATH = Path(__file__).parent / "aliases.json"

# 法人格・組織種別（前後どちらにも付く）。順序: 長いものを先に
_LEGAL_FORMS = [
    "株式会社", "（株）", "(株)", "㈱", "合同会社", "（同）", "(同)", "合資会社", "合名会社", "有限会社", "（有）", "(有)", "㈲",
    "一般社団法人", "一般財団法人", "公益社団法人", "公益財団法人", "特定非営利活動法人", "学校法人", "医療法人社団", "医療法人財団",
    "医療法人", "社会福祉法人", "国立大学法人", "独立行政法人", "地方独立行政法人", "国立研究開発法人",
    "股份有限公司", "有限責任公司", "有限公司", "株式会社", "有限会社",
]
_LEGAL_SUFFIX_RE = re.compile(
    r"(?:[\s,、.]*(?:co\.?,?\s*ltd\.?|company\s+limited|company|corporation|corp\.?|incorporated|inc\.?|limited|ltd\.?|"
    r"l\.?l\.?c\.?|l\.?l\.?p\.?|plc|p\.?l\.?c\.?|s\.?a\.?|s\.?p\.?a\.?|s\.?a\.?s\.?|s\.?à\.?\s?r\.?l\.?|s\.?r\.?l\.?|"
    r"gmbh|ag|a\.?g\.?|b\.?v\.?|n\.?v\.?|pte\.?\s*ltd\.?|pty\.?\s*ltd\.?|pty\.?|sdn\.?\s*bhd\.?|bhd\.?|k\.?k\.?|"
    r"co\.?|oy|ab|as|a/s|aps|kft|s\.?a\.?\s*de\s*c\.?v\.?|tbk\.?|jsc|pjsc|ojsc)\.?)+\s*$",
    re.I,
)
_TRAILING_SHA_RE = re.compile(r"(?<=[A-Za-z0-9.)])\s*社$")  # 「Ceva社」のような欧文名＋社


def load_aliases(path: Path = ALIASES_PATH) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("kanji_variants", {})
    data.setdefault("listed", {})
    data.setdefault("entities", [])
    return data


_ALIASES = load_aliases()
_KANJI = {k: v for k, v in _ALIASES["kanji_variants"].items() if not k.startswith("_")}
_KANJI_RE = re.compile("|".join(map(re.escape, sorted(_KANJI, key=len, reverse=True)))) if _KANJI else None


def fold_kanji(s: str) -> str:
    return _KANJI_RE.sub(lambda m: _KANJI[m.group(0)], s) if _KANJI_RE else s


def strip_legal_form(name: str) -> str:
    """法人格を除いた名称（NFKC 済みを想定）。"""
    s = name.strip()
    changed = True
    while changed:
        changed = False
        for lf in _LEGAL_FORMS:
            if s.startswith(lf):
                s = s[len(lf):].strip(" 　・")
                changed = True
            if s.endswith(lf):
                s = s[: -len(lf)].strip(" 　・")
                changed = True
    s2 = _LEGAL_SUFFIX_RE.sub("", s).strip(" ,.、")
    if s2:
        s = s2
    s2 = _TRAILING_SHA_RE.sub("", s)
    if s2:
        s = s2
    return s


def has_legal_form(name: str | None) -> bool:
    n = unicodedata.normalize("NFKC", name or "").strip()
    return bool(n) and strip_legal_form(n) != n


def base_name(name: str | None) -> str:
    """NFKC・旧字体畳み込み・法人格除去まで（空白は残す）。別名の完全一致照合に使う。"""
    n = unicodedata.normalize("NFKC", name or "")
    n = fold_kanji(n)
    n = strip_legal_form(n)
    return re.sub(r"\s+", " ", n).strip()


def match_key(name: str | None) -> str:
    """名寄せ用の照合キー。"""
    n = base_name(name)
    n = unicodedata.normalize("NFKD", n)
    n = "".join(ch for ch in n if not unicodedata.combining(ch))  # アクセント除去（Santé → Sante）
    n = re.sub(r"[\s　・･\-－—–‐'’\"“”&＆,.、。()（）]+", "", n)
    return n.lower()


def kana_key(kana: str | None) -> str:
    """ヨミ（カタカナ）→ 検索用ひらがなキー。法人格のヨミ（カブシキガイシャ等）は除く。"""
    if not kana:
        return ""
    k = unicodedata.normalize("NFKC", kana)
    k = re.sub(r"カブシキ(カイシャ|ガイシャ)|ユウゲン(カイシャ|ガイシャ)|ゴウドウ(カイシャ|ガイシャ)", "", k)
    k = re.sub(r"[\s　・･\-－ー]+", "", k)
    return "".join(chr(ord(ch) - 0x60) if "ァ" <= ch <= "ヶ" else ch for ch in k).lower()


class AliasIndex:
    """上場企業（証券コード）と確認済み非上場法人への別名索引。"""

    def __init__(self, companies: dict[str, dict], aliases: dict | None = None):
        self.aliases = aliases or _ALIASES
        self.listed_bare: dict[str, str] = {}    # 法人格なしの別名: match_key → code（法人格のない原文名にだけ適用）
        self.listed_legal: dict[str, str] = {}   # 法人格付きの別名: match_key → code（法人格を無視して適用）
        self.listed_key: dict[str, str] = {}     # match_key(公式名) → code
        self.reasons: dict[str, dict[str, str]] = {}  # code → {別名: 理由}

        def add_alias(alias: str, code: str) -> None:
            if has_legal_form(alias):
                self.listed_legal.setdefault(match_key(alias), code)
            else:
                self.listed_bare.setdefault(match_key(alias), code)

        for code, c in companies.items():
            for official in (c.get("name"), c.get("name_edinet"), c.get("name_en")):
                if official:
                    self.listed_key.setdefault(match_key(official), code)
            for alias in c.get("aliases") or []:
                add_alias(alias, code)
        for code, spec in self.aliases["listed"].items():
            if code.startswith("_") or code not in companies:
                continue
            for alias in spec.get("aliases", []):
                add_alias(alias, code)
                self.reasons.setdefault(code, {})[alias] = spec.get("reason", "alias")
        self.entity_canonical: dict[str, str] = {}  # match_key(別名) → canonical 名
        self.entity_reason: dict[str, str] = {}
        for ent in self.aliases["entities"]:
            canon = ent["canonical"]
            for alias in [canon, *ent.get("aliases", [])]:
                self.entity_canonical[match_key(alias)] = canon
                self.entity_reason[canon] = ent.get("reason", "alias")

    def resolve_listed(self, name: str | None) -> tuple[str | None, str | None]:
        """名称 → (証券コード, 照合方法)。見つからなければ (None, None)。"""
        if not name:
            return None, None
        key = match_key(name)
        code = self.listed_key.get(key)
        if code:
            return code, "official_name"
        code = self.listed_legal.get(key)
        if code:
            return code, "alias"
        # 「ソニー」は別名として一致させるが「ソニー株式会社」（別法人）は一致させない
        if not has_legal_form(name):
            code = self.listed_bare.get(key)
            if code:
                return code, "alias"
        return None, None

    def canonical_entity_name(self, name: str) -> tuple[str, str | None]:
        """非上場名を確認済み別名辞書で正規名に寄せる。(正規名, 理由)。辞書にない名前はそのまま。"""
        canon = self.entity_canonical.get(match_key(name))
        if canon and canon != name:
            return canon, self.entity_reason.get(canon)
        return name, None


def compatible_official_names(jpx_name: str, edinet_name: str | None) -> bool:
    """EDINET の提出者名を JPX 名の別名として索引に加えてよいか。
    片方がもう片方を含む場合だけ許可し、「サッポロホールディングス」と「サッポロビール」のような
    別法人（親子）を同一視しない。"""
    if not edinet_name:
        return False
    a, b = match_key(jpx_name), match_key(edinet_name)
    if not a or not b:
        return False
    return a == b or a in b or b in a
