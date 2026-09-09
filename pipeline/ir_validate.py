"""IR（プレスリリース）由来の LLM 抽出行を、根拠文だけで確定してよいか判定する（Issue #6）。

方針: 根拠文（evidence_quote）に「相手」「関係タイプの手がかり」「（方向のあるタイプでは）方向の手がかり」が
揃っている場合だけ confirmed にする。共同登場・製品のベース技術・商標／PDF 注記・過去の取引だけからは
強い関係を推測せず、needs_review に回す。関係が現実にないという断定ではなく「この根拠では確定できない」という判定。

判定結果: {"status": "confirmed"|"needs_review", "reasons": [...], "cue": "一致した手がかり", "direction": "out"|"in"|None}

固定評価セット fixtures/ir_eval.json で改善前後を比較する: `python ir_validate.py --eval`
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

from aliases import base_name, match_key

# 抽出誤りの典型（注記・商標・閲覧環境・受賞・掲載）
NOISE_RE = re.compile(
    r"Adobe|Acrobat|Reader|商標|登録商標|trademark|PDF形式|ご覧になるには|Cookie|ブラウザ|振込手数料|ATM|"
    r"紙による|評価を得|受賞|表彰|掲載され|紹介され|オフィシャルパートナー|スポンサー|協賛|寄贈|"
    r"コンサートを開催|イベント|キャンペーン|フェア|セミナー|講演", re.I)

# 関係タイプごとの手がかり（肯定）。方向付きタイプは in（相手が主体）を先に、次に out（提出会社が主体）を判定
CUES = {
    "business_alliance": {
        "any": r"業務提携|包括(的)?(連携|提携|協定)|提携契約|提携(し|いた|を|に|について|基本)|協業|パートナーシップ|連携協定|協定を締結|"
               r"partnership|alliance|collaborat|agreement (with|to)|MOU|memorandum|代理店契約|販売契約|基本合意|連携(し|いた|を|に|協定)|"
               r"共同(で|して)?(開催|運営|展開|推進|実施|提供|販売)|協力(し|いた|して|に関する)",
    },
    "capital_alliance": {
        "any": r"資本業務提携|資本提携|資本(及び|・|および)業務提携|capital (and business )?alliance|株式.{0,20}提携|提携.{0,20}(出資|株式)|資本行提携",
    },
    "joint_venture": {
        "any": r"合弁|JV|joint venture|共同出資|共同で(設立|運営|事業|出資|実用化|事業化)|共同事業|新会社(を|の)設立|"
               r"jointly (establish|own|operate)|co-?founded|過半数出資|出資する新会社",
    },
    "joint_research": {
        "any": r"共同研究|共同開発|共同(で|して)?(研究|開発|検討|実証|技術検証|検証|実験)|(研究|開発|検討|実証|検証)を共同で|"
               r"協働して.{0,20}(検証|開発|研究)|joint(ly)? (research|develop)|co-?develop|研究契約|開発契約|"
               r"実証実験を(共同で)?(開始|実施)|共同実証",
    },
    "technology_license": {
        "in": r"(技術|特許|ライセンス)(の)?(導入|供与を受け|許諾を受け)|ライセンスを(受け|取得)|licen[cs]ed? from|技術を導入",
        "out": r"(技術|特許|ライセンス)を(供与|許諾|提供)|ライセンス(供与|許諾|契約を締結)|技術供与|license[ds]? (to|our)|grant(ed|s)? .{0,30}licen[cs]e|技術提携",
    },
    "ownership": {
        "in": r"(から|より)(の)?出資(を受け|を受け入れ)|第三者割当|割当先|出資を受け|株式を.{0,20}に譲渡|investment from|"
              r"(による|からの).{0,40}公開買付け|(による|からの).{0,40}株式.{0,10}取得|(による|からの).{0,40}TOB",
        "out": r"出資(?!を受|金)|株式.{0,20}(取得|引受|譲受|買い増し|買い付け)|持分.{0,8}取得|公開買付|TOB|増資を引き受け|資本参加|"
               r"acquire[sd]? .{0,40}(stake|shares|interest|equity)|invest(ed|s|ment)? in|subscri(be|ption)|株主とな",
    },
    "major_customer": {
        "in": r"(から|より)(の)?(購入|調達|仕入)|purchase[sd]? from|procure",
        "out": r"納入|納品|供給(し|いた|する|を|契約)|受注|採用(され|いただ|いたし)|に採用|ご採用|出荷|受託|導入(され|いただ)|"
               r"deliver(ed|y|ies)? to|supply|supplied|order(ed)? (from|by)|selected by|adopted by|向け(に)?(製造|提供|出荷|納入)|より受注|"
               r"主要(な)?(取引先|顧客|販売先|得意先)|取引先",
    },
    "merger_acquisition": {
        "in": r"(に|による|によって)(買収|吸収)|acquired by|(に|へ)(の)?(譲渡|売却)|(に|へ)株式を譲渡|(の)?完全子会社(となり|化され)",
        "out": r"買収|(全株式|株式|持分)(を|の)?(取得|譲受)|子会社化|吸収合併|合併|経営統合|統合|acqui(re|red|sition)|merge[rd]?|take ?over|"
               r"株式譲渡契約|譲受|公開買付|TOB|株式交換|share exchange",
    },
}
_CUES = {t: {k: re.compile(v, re.I) for k, v in spec.items()} for t, spec in CUES.items()}
_ALL_CUES = [(t, rx) for t, spec in _CUES.items() for rx in spec.values()]

# 「〜をベースとしている」「〜に準拠」など、技術関係を推測させるが供与を示さない表現
WEAK_TECH_RE = re.compile(r"をベース|based on|準拠|互換|対応(し|した)|搭載|を用いて|を使用|を採用し", re.I)
# 述語のない列挙（「A社、B社、C社」「JAL、三菱…」）
VERB_RE = re.compile(r"(し|する|した|します|ました|まし|いたし|締結|開始|設立|実施|決定|発表|合意|開催|運営|提供|取得|出資|供給|納入|受注|"
                     r"announce|agree|sign|launch|establish|acquire|invest|form|develop|deliver|supply|partner|collaborat)", re.I)
SELF_RE = re.compile(r"当社|弊社|自社|当行|当グループ|our|we |we've|the company", re.I)
UNDIRECTED_TYPES = {"business_alliance", "capital_alliance", "joint_venture", "joint_research"}


def _norm(s: str | None) -> str:
    return unicodedata.normalize("NFKC", s or "")


def mentions(text: str, name: str | None) -> bool:
    """根拠文に相手（法人格を除いた名称、または英字略称）が出ているか。"""
    if not name:
        return False
    t = match_key(text)
    b = match_key(name)
    if b and b in t:
        return True
    short = re.sub(r"\s+", "", base_name(name))
    if len(short) >= 2 and short.lower() in _norm(text).lower():
        return True
    # 「（以下、日立）」「（以下、トヨタ社）」のような略称定義
    for m in re.finditer(r"以下[、,]?\s*「?([^」）)]{1,12})」?\s*[）)]", _norm(text)):
        k = match_key(m.group(1))
        if k and k in b:
            return True
    # 欧文名は先頭の固有語（4 文字以上、一般語を除く）で照合（"Ceva Santé Animale SA" → "Ceva"）
    tokens = [t for t in re.split(r"[\s,.]+", base_name(name)) if len(t) >= 4 and t.lower() not in _GENERIC_TOKENS]
    if tokens and re.match(r"^[A-Za-z]", tokens[0]) and tokens[0].lower() in _norm(text).lower():
        return True
    return False


_GENERIC_TOKENS = {"group", "holdings", "holding", "international", "global", "japan", "america", "asia", "europe",
                   "technology", "technologies", "systems", "solutions", "industries", "company", "corporation"}


THIRD_PARTY_RE = re.compile(r"(が|により|によって)(設立|出資|保有|買収|運営)(した|する|している|され)")


def filer_mentioned(quote: str, filer_names: list[str] | None) -> bool:
    if SELF_RE.search(quote):
        return True
    return any(mentions(quote, n) for n in (filer_names or []) if n)


NEGATION_RE = re.compile(
    r"行いません|いたしません|しません|ではありません|はありません|ございません|否定|撤回|白紙|解消|終了|中止|見送|取りやめ|"
    r"取り止め|断念|破談|解除|失効|\bnot\b|\bno longer\b|terminat|cancel|withdraw|den(y|ied)|abandon|rescind", re.I)
_PARTICLE_AGENT = r"(が|は|による|により|によって|側が|側は)"
_PARTICLE_RECIPIENT = r"(に|へ|に対し|に対する|向け|宛て)"
_PARTICLE_SOURCE = r"(から|より)"


def syntactic_direction(quote: str, cp: str | None, rel_type: str, cue: str | None) -> str | None:
    """相手の直後の助詞（が／に／から）や英語の前置詞から、相手が主体か受け手かを判定する。
    戻り値: 'in'（相手が主体）/ 'out'（提出会社が主体）/ None（判定できない）。"""
    if not cp:
        return None
    base = re.sub(r"\s+", "", _norm(base_name(cp)))
    q = quote
    idx = -1
    for cand in (base, _norm(cp), re.sub(r"\s+", " ", base_name(cp))):
        idx = q.find(cand)
        if idx >= 0:
            after = q[idx + len(cand): idx + len(cand) + 12]
            before = q[max(0, idx - 8): idx]
            break
    else:
        # 「（以下、X）」の略称
        m = re.search(r"以下[、,]?\s*「?([^」）)]{1,12})」?\s*[）)]", q)
        if m and match_key(m.group(1)) and match_key(m.group(1)) in match_key(cp):
            short = m.group(1)
            pos = [i for i in range(len(q)) if q.startswith(short, i)]
            pos = [i for i in pos if i > m.end() - 1]
            if not pos:
                return None
            idx = pos[0]
            after = q[idx + len(short): idx + len(short) + 12]
            before = q[max(0, idx - 8): idx]
        else:
            return None
    after = re.sub(r"^[\s、）)」]*(株式会社|\(株\)|㈱|社|Inc\.?|Co\.,? ?Ltd\.?|Corporation|Ltd\.?)?[\s）)」]*", "", after)
    if re.match(_PARTICLE_AGENT, after):
        return "in"
    if re.match(_PARTICLE_RECIPIENT, after):
        return "out"
    if re.match(_PARTICLE_SOURCE, after):
        # 「Xから受注」は X が顧客（out）、「Xから出資を受け／購入」は X が主体（in）、「Xから買収／譲受」は提出会社が主体（out）
        if rel_type == "major_customer":
            return "out" if re.search(r"受注|注文", q) else "in"
        if rel_type in ("ownership", "technology_license"):
            return "in"
        return "out"
    if re.search(r"\bby\s*$", before, re.I):
        return "in"
    if re.search(r"\b(to|for|into)\s*$", before, re.I):
        return "out"
    if re.search(r"\bfrom\s*$", before, re.I):
        return "out" if rel_type in ("merger_acquisition",) else "in"
    return None


def validate(row: dict, filer_names: list[str] | None = None) -> dict:
    quote = _norm(row.get("evidence_quote"))
    rel_type = row.get("relation_type")
    cp = row.get("counterparty_name")
    filer_names = filer_names or row.get("filer_names") or ([row["filer_name"]] if row.get("filer_name") else None)
    reasons: list[str] = []
    cue = None
    direction = None
    resolved_type = rel_type
    retyped = False

    if not quote.strip():
        return {"status": "needs_review", "reasons": ["no_quote"], "cue": None, "direction": None,
                "resolved_type": rel_type}
    if NOISE_RE.search(quote) and not any(rx.search(quote) for rx in _CUES.get(rel_type, {}).values()):
        reasons.append("noise_context")
    if not mentions(quote, cp):
        reasons.append("counterparty_not_in_quote")

    spec = _CUES.get(rel_type)
    other_type = None
    if spec is None:
        reasons.append("unknown_type")
    else:
        for key, rx in spec.items():
            m = rx.search(quote)
            if m:
                cue = m.group(0)
                direction = key if key in ("out", "in") else None
                break
        if cue is None:
            others = []
            for t, rx in _ALL_CUES:
                if t != rel_type and rx.search(quote) and t not in others:
                    others.append(t)
            if rel_type == "technology_license" and WEAK_TECH_RE.search(quote):
                reasons.append("tech_basis_only")  # ベース技術・準拠だけではライセンス供与を確定できない
            elif others:
                other_type = others[0]
                # 根拠が別の無向タイプ（共同研究・提携・合弁）を明示している場合は、そのタイプに読み替えて確定する
                # 読み替えは提出会社（当社／社名）が根拠文に出ている場合に限る（第三者同士の記述を防ぐ）
                if len(others) == 1 and other_type in UNDIRECTED_TYPES and filer_mentioned(quote, filer_names):
                    resolved_type = other_type
                    cue = _CUES[other_type]["any"].search(quote).group(0)
                    retyped = True
                else:
                    reasons.append(f"cue_for_other_type:{other_type}")
            elif not VERB_RE.search(quote):
                reasons.append("co_mention_only")
            else:
                reasons.append("no_relation_cue")
        elif "out" in spec and direction is None:
            reasons.append("direction_unclear")
        # 方向のあるタイプは、手がかり語ではなく相手の助詞（が／に／から、by／to／from）で主体を決め直す
        if cue and "out" in spec:
            syn = syntactic_direction(quote, cp, rel_type, cue)
            if syn:
                # 受動態（「乙社に買収されました」）は主体が入れ替わる。採用され・選定され は相手が顧客なので反転しない
                if re.search(r"(買収|取得|供与|出資|譲渡|吸収)され", quote):
                    syn = "out" if syn == "in" else "in"
                direction = syn
                if "direction_unclear" in reasons:
                    reasons.remove("direction_unclear")
        # 否定・撤回・解消の記述は存在する関係として確定しない
        if NEGATION_RE.search(quote):
            reasons.append("negated_or_terminated")
        # 「X社とY社が設立した合弁会社」のように、提出会社が当事者でない記述
        if cue and THIRD_PARTY_RE.search(quote) and not filer_mentioned(quote, filer_names):
            reasons.append("third_party_statement")
        # 「Xによる…公開買付け／取得」は X が主体。X が当社（子会社）なら out、相手なら in
        if direction == "in":
            m = re.search(r"([^、。]{2,60}?)による", quote)
            if m and SELF_RE.search(m.group(1)) and not mentions(m.group(1), cp):
                direction = "out"
    status = "confirmed" if not reasons else "needs_review"
    out = {"status": status, "reasons": reasons, "cue": cue, "direction": direction,
           "resolved_type": resolved_type}
    if retyped:
        out["retyped_from"] = rel_type
    if other_type and not retyped:
        out["suggested_type"] = other_type
    return out


# ---------------------------------------------------------------------------
# 固定評価セット
# ---------------------------------------------------------------------------

EVAL_PATH = Path(__file__).parent / "fixtures" / "ir_eval.json"


def run_eval(path: Path = EVAL_PATH) -> int:
    cases = json.loads(path.read_text(encoding="utf-8"))["cases"]
    by_type: dict[str, dict[str, int]] = {}
    wrong = []
    for c in cases:
        got = validate(c["row"])
        exp = c["expected"]
        t = c["row"]["relation_type"]
        st = by_type.setdefault(t, {"n": 0, "ok": 0})
        st["n"] += 1
        ok = got["status"] == exp["status"] and (exp.get("direction") is None or exp["direction"] == got["direction"]) \
            and (exp.get("type") is None or exp["type"] == got.get("resolved_type"))
        if ok:
            st["ok"] += 1
        else:
            wrong.append((c["id"], exp, got))
    total = sum(s["n"] for s in by_type.values())
    okc = sum(s["ok"] for s in by_type.values())
    print(f"IR 評価セット: {okc}/{total} 一致")
    for t, st in sorted(by_type.items()):
        print(f"   {t:20} {st['ok']}/{st['n']}")
    for w in wrong:
        print("   MISMATCH", w[0], "expected", w[1], "got", {k: w[2].get(k) for k in ('status', 'reasons', 'direction', 'resolved_type')})
    return 0 if not wrong else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", action="store_true")
    ap.add_argument("--stats", action="store_true", help="ir_relations.json 全体の判定分布を表示")
    args = ap.parse_args()
    if args.eval:
        return run_eval()
    if args.stats:
        rows = json.loads((Path(__file__).parent / "ir_crawl" / "data" / "ir_relations.json").read_text(encoding="utf-8"))
        agg: dict[str, dict[str, int]] = {}
        for r in rows:
            v = validate(r)
            a = agg.setdefault(r["relation_type"], {})
            a["total"] = a.get("total", 0) + 1
            a[v["status"]] = a.get(v["status"], 0) + 1
            for reason in v["reasons"]:
                a["reason:" + reason] = a.get("reason:" + reason, 0) + 1
        for t, a in sorted(agg.items()):
            print(t, json.dumps(a, ensure_ascii=False))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
